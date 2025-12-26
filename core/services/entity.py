"""EntityService - unified CRUD for all content types."""

from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityValue
from .field import field_service, FieldService
from .cache import cache_service


@dataclass
class QueryParams:
    """Query parameters for find operations."""
    filters: dict[str, Any] = field(default_factory=dict)
    sort: str = "-created_at"
    page: int = 1
    per_page: int = 20
    include_deleted: bool = False
    search: str = ""  # Full-text search query


class EntityService:
    """
    Unified CRUD service for all entity types.

    No PostService, PageService, etc.
    This single service handles all content types.
    """

    def __init__(self, db: AsyncSession, field_svc: FieldService = None):
        self.db = db
        self.field_svc = field_svc or field_service

    async def create(
        self,
        type_name: str,
        data: dict[str, Any],
        user_id: str = None,
    ) -> Entity:
        """Create a new entity."""
        # Validate
        validation = self.field_svc.validate(type_name, data)
        if not validation.valid:
            raise ValueError(f"Validation failed: {validation.errors}")

        # Create entity
        entity = Entity(
            type=type_name,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(entity)
        await self.db.flush()

        # Create values
        ct = self.field_svc.get_content_type(type_name)
        if ct:
            for field_def in ct.fields:
                value = data.get(field_def.name, field_def.default)
                if value is not None:
                    await self._set_value(entity.id, field_def.name, value, field_def.type)

        await self.db.commit()
        await self.db.refresh(entity)

        # Invalidate cache for this content type
        self._invalidate_cache(type_name)

        return entity

    async def update(
        self,
        entity_id: str,
        data: dict[str, Any],
        user_id: str = None,
        create_revision: bool = True,
        revision_type: str = "manual",
    ) -> Optional[Entity]:
        """Update an existing entity."""
        entity = await self.get(entity_id)
        if not entity:
            return None

        # Validate
        validation = self.field_svc.validate(entity.type, data)
        if not validation.valid:
            raise ValueError(f"Validation failed: {validation.errors}")

        # Create revision before updating
        if create_revision:
            from .revision import RevisionService
            revision_svc = RevisionService(self.db)
            current_data = self.serialize(entity)
            await revision_svc.create(
                entity_id=entity_id,
                data=current_data,
                revision_type=revision_type,
                title=current_data.get("title") or current_data.get("name"),
                user_id=user_id,
            )

        # Update entity
        entity.updated_at = datetime.utcnow()
        entity.updated_by = user_id

        # Update values
        ct = self.field_svc.get_content_type(entity.type)
        if ct:
            for field_def in ct.fields:
                if field_def.name in data:
                    await self._set_value(
                        entity_id,
                        field_def.name,
                        data[field_def.name],
                        field_def.type,
                    )

        await self.db.commit()
        await self.db.refresh(entity)

        # Invalidate cache for this content type
        self._invalidate_cache(entity.type)

        return entity

    async def delete(
        self,
        entity_id: str,
        user_id: str = None,
        hard: bool = False,
    ) -> bool:
        """Delete an entity (soft delete by default)."""
        entity = await self.get(entity_id, include_deleted=True)
        if not entity:
            return False

        entity_type = entity.type

        if hard:
            await self.db.delete(entity)
        else:
            entity.deleted_at = datetime.utcnow()
            entity.updated_by = user_id

        await self.db.commit()

        # Invalidate cache for this content type
        self._invalidate_cache(entity_type)

        return True

    def _invalidate_cache(self, type_name: str) -> None:
        """Invalidate page cache for a content type."""
        # Invalidate home page (shows recent posts)
        cache_service.delete("page:home")

        # Invalidate type-specific pages
        cache_service.invalidate_pattern(f"page:{type_name}")

        # Invalidate listings
        cache_service.invalidate_pattern("page:category")
        cache_service.invalidate_pattern("page:archive")

    async def get(
        self,
        entity_id: str,
        include_deleted: bool = False,
    ) -> Optional[Entity]:
        """Get entity by ID."""
        query = select(Entity).where(Entity.id == entity_id)
        if not include_deleted:
            query = query.where(Entity.deleted_at.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def find(
        self,
        type_name: str,
        params: QueryParams = None,
        *,
        limit: int = None,
        offset: int = None,
        order_by: str = None,
        filters: dict = None,
        include_deleted: bool = False,
    ) -> list[Entity]:
        """Find entities by type with filters."""
        # Support both QueryParams and keyword arguments
        if params:
            _filters = params.filters
            _sort = params.sort
            _offset = (params.page - 1) * params.per_page
            _limit = params.per_page
            _include_deleted = params.include_deleted
        else:
            _filters = filters or {}
            _sort = order_by or "-created_at"
            _offset = offset or 0
            _limit = limit or 20
            _include_deleted = include_deleted

        query = select(Entity).where(Entity.type == type_name)

        if not _include_deleted:
            query = query.where(Entity.deleted_at.is_(None))

        # Apply filters
        for field_name, value in _filters.items():
            if isinstance(value, dict):
                # Complex filter (gte, lte, etc.)
                for op, val in value.items():
                    query = self._apply_filter(query, field_name, op, val)
            else:
                # Simple equality
                query = self._apply_filter(query, field_name, "eq", value)

        # Apply sort
        if _sort.startswith("-"):
            sort_field = _sort[1:]
            desc = True
        else:
            sort_field = _sort
            desc = False

        if sort_field in ("created_at", "updated_at"):
            order_col = getattr(Entity, sort_field)
            query = query.order_by(order_col.desc() if desc else order_col)

        # Apply pagination
        query = query.offset(_offset).limit(_limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        type_name: str,
        params: QueryParams = None,
    ) -> int:
        """Count entities by type with filters."""
        params = params or QueryParams()

        query = select(func.count()).select_from(Entity).where(Entity.type == type_name)

        if not params.include_deleted:
            query = query.where(Entity.deleted_at.is_(None))

        for field_name, value in params.filters.items():
            if isinstance(value, dict):
                for op, val in value.items():
                    query = self._apply_filter(query, field_name, op, val)
            else:
                query = self._apply_filter(query, field_name, "eq", value)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _set_value(
        self,
        entity_id: str,
        field_name: str,
        value: Any,
        field_type: str,
    ):
        """Set a field value on an entity."""
        # Check if value exists
        query = select(EntityValue).where(
            and_(
                EntityValue.entity_id == entity_id,
                EntityValue.field_name == field_name,
            )
        )
        result = await self.db.execute(query)
        ev = result.scalar_one_or_none()

        if ev is None:
            ev = EntityValue(entity_id=entity_id, field_name=field_name)
            self.db.add(ev)

        # Clear all value columns
        ev.value_text = None
        ev.value_int = None
        ev.value_float = None
        ev.value_datetime = None
        ev.value_json = None

        # Set appropriate column based on type
        storage_type = self._get_storage_type(field_type)
        if storage_type == "text":
            ev.value_text = str(value) if value is not None else None
        elif storage_type == "int":
            ev.value_int = int(value) if value is not None else None
        elif storage_type == "float":
            ev.value_float = float(value) if value is not None else None
        elif storage_type == "datetime":
            if isinstance(value, datetime):
                ev.value_datetime = value
            elif isinstance(value, str):
                ev.value_datetime = datetime.fromisoformat(value)
        elif storage_type == "json":
            ev.value_json = value

    def _get_storage_type(self, field_type: str) -> str:
        """Get storage type for a field type."""
        type_mapping = {
            "string": "text",
            "text": "text",
            "slug": "text",
            "email": "text",
            "url": "text",
            "password": "text",
            "integer": "int",
            "float": "float",
            "boolean": "int",
            "datetime": "datetime",
            "date": "datetime",
            "select": "text",
            "multiselect": "json",
            "blocks": "json",
            "media": "text",
            "json": "json",
        }
        return type_mapping.get(field_type, "text")

    def _apply_filter(self, query, field_name: str, op: str, value: Any):
        """Apply a filter to the query."""
        # Entity-level fields
        if field_name in ("created_at", "updated_at", "deleted_at"):
            col = getattr(Entity, field_name)
            if op == "eq":
                return query.where(col == value)
            elif op == "gte":
                return query.where(col >= value)
            elif op == "lte":
                return query.where(col <= value)
            elif op == "gt":
                return query.where(col > value)
            elif op == "lt":
                return query.where(col < value)
            return query

        # EntityValue fields - use subquery
        # Determine which value column to compare based on value type
        if isinstance(value, bool):
            value_col = EntityValue.value_int
            compare_value = 1 if value else 0
        elif isinstance(value, int):
            value_col = EntityValue.value_int
            compare_value = value
        elif isinstance(value, float):
            value_col = EntityValue.value_float
            compare_value = value
        elif isinstance(value, datetime):
            value_col = EntityValue.value_datetime
            compare_value = value
        else:
            # Default to text comparison
            value_col = EntityValue.value_text
            compare_value = str(value) if value is not None else None

        # Build subquery for EntityValue filtering
        if op == "eq":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col == compare_value
                )
            )
        elif op == "neq":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col != compare_value
                )
            )
        elif op == "gte":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col >= compare_value
                )
            )
        elif op == "lte":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col <= compare_value
                )
            )
        elif op == "gt":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col > compare_value
                )
            )
        elif op == "lt":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col < compare_value
                )
            )
        elif op == "like":
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_name,
                    value_col.like(f"%{compare_value}%")
                )
            )
        elif op == "isnull":
            # Check if field doesn't exist or value is null
            if value:
                subq = select(EntityValue.entity_id).where(
                    and_(
                        EntityValue.field_name == field_name,
                        value_col.is_(None)
                    )
                )
            else:
                subq = select(EntityValue.entity_id).where(
                    and_(
                        EntityValue.field_name == field_name,
                        value_col.isnot(None)
                    )
                )
        else:
            return query

        return query.where(Entity.id.in_(subq))

    def serialize(self, entity: Entity) -> dict[str, Any]:
        """Serialize entity to dict."""
        data = {
            "id": entity.id,
            "type": entity.type,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
            "created_by": entity.created_by,
            "updated_by": entity.updated_by,
        }

        # Add field values
        for ev in entity.values:
            data[ev.field_name] = ev.value

        return data
