"""EntityService - unified CRUD for all content types."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityValue
from ..utils import utcnow
from .cache import cache_service
from .field import FieldService, field_service


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
        """Create a new entity.

        All operations are performed in a single transaction.
        On error, the entire transaction is rolled back.
        """
        # Validate before starting transaction
        validation = self.field_svc.validate(type_name, data)
        if not validation.valid:
            raise ValueError(f"Validation failed: {validation.errors}")

        # Check unique constraints before creating
        ct = self.field_svc.get_content_type(type_name)
        if ct:
            await self._check_unique_constraints(type_name, data, ct, entity_id=None)

        try:
            # Create entity
            entity = Entity(
                type=type_name,
                created_by=user_id,
                updated_by=user_id,
            )
            self.db.add(entity)
            await self.db.flush()

            # Create values
            if ct:
                for field_def in ct.fields:
                    value = data.get(field_def.name, field_def.default)
                    if value is not None:
                        await self._set_value(entity.id, field_def.name, value, field_def.type)

            await self.db.commit()

            # Invalidate cache for this content type
            await self._invalidate_cache(type_name)

            # Re-fetch to ensure values relationship is loaded
            return await self.get(entity.id)

        except Exception:
            await self.db.rollback()
            raise

    async def update(
        self,
        entity_id: str,
        data: dict[str, Any],
        user_id: str = None,
        create_revision: bool = True,
        revision_type: str = "manual",
        expected_version: int = None,
    ) -> Entity | None:
        """Update an existing entity.

        All operations are performed in a single transaction.
        On error, the entire transaction is rolled back.

        Args:
            expected_version: If provided, checks for concurrent modification.
                              Raises ValueError if versions don't match.
        """
        entity = await self.get(entity_id)
        if not entity:
            return None

        # Optimistic locking: check version if expected_version is provided
        if expected_version is not None and entity.version != expected_version:
            raise ValueError(
                f"Concurrent modification detected. Expected version {expected_version}, "
                f"but current version is {entity.version}. Please reload and try again."
            )

        # Validate before starting transaction
        validation = self.field_svc.validate(entity.type, data)
        if not validation.valid:
            raise ValueError(f"Validation failed: {validation.errors}")

        # Check unique constraints and transitions before updating
        ct = self.field_svc.get_content_type(entity.type)
        if ct:
            await self._check_unique_constraints(entity.type, data, ct, entity_id=entity_id)
            await self._check_status_transitions(entity, data, ct)

        try:
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
            entity.updated_at = utcnow()
            entity.updated_by = user_id
            entity.version += 1  # Increment version for optimistic locking

            # Update values
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

            # Invalidate cache for this content type
            await self._invalidate_cache(entity.type)

            # Re-fetch to ensure values relationship is loaded
            return await self.get(entity_id)

        except Exception:
            await self.db.rollback()
            raise

    async def delete(
        self,
        entity_id: str,
        user_id: str = None,
        hard: bool = False,
        cascade: bool = True,
    ) -> bool:
        """Delete an entity (soft delete by default).

        Args:
            entity_id: Entity to delete
            user_id: User performing the delete
            hard: If True, permanently delete (not recommended)
            cascade: If True, also soft-delete related entities marked with cascade_delete

        Returns:
            True if deleted, False if entity not found
        """
        entity = await self.get(entity_id, include_deleted=True)
        if not entity:
            return False

        entity_type = entity.type
        deleted_at = utcnow()

        try:
            if hard:
                await self.db.delete(entity)
            else:
                entity.deleted_at = deleted_at
                entity.updated_by = user_id

                # Handle cascade deletes
                if cascade:
                    await self._cascade_soft_delete(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        user_id=user_id,
                        deleted_at=deleted_at,
                    )

            await self.db.commit()

            # Invalidate cache for this content type
            await self._invalidate_cache(entity_type)

            return True

        except Exception:
            await self.db.rollback()
            raise

    async def _cascade_soft_delete(
        self,
        entity_id: str,
        entity_type: str,
        user_id: str,
        deleted_at: datetime,
    ) -> int:
        """Cascade soft delete to related entities.

        Finds all relations with cascade_delete=True that point TO this entity
        and soft-deletes the from_entities.

        Returns:
            Count of entities that were cascade-deleted
        """
        from ..models import Relation

        cascade_relations = self.field_svc.get_cascade_relations_for_type(entity_type)
        if not cascade_relations:
            return 0

        count = 0
        for relation_name, _rel_def in cascade_relations:
            # Find all entities that have a relation TO the deleted entity
            query = select(Relation).where(
                and_(
                    Relation.to_entity_id == entity_id,
                    Relation.relation_type == relation_name,
                )
            )
            result = await self.db.execute(query)
            relations = result.scalars().all()

            for relation in relations:
                # Get the from_entity and soft delete it
                from_entity = await self.get(relation.from_entity_id)
                if from_entity and from_entity.deleted_at is None:
                    from_entity.deleted_at = deleted_at
                    from_entity.updated_by = user_id
                    count += 1

                    # Recursively cascade (with depth limit handled by DB)
                    count += await self._cascade_soft_delete(
                        entity_id=from_entity.id,
                        entity_type=from_entity.type,
                        user_id=user_id,
                        deleted_at=deleted_at,
                    )

        return count

    async def restore(
        self,
        entity_id: str,
        user_id: str = None,
    ) -> Entity | None:
        """
        Restore a soft-deleted entity.

        Args:
            entity_id: Entity to restore
            user_id: User performing the restore

        Returns:
            Restored entity, or None if not found
        """
        entity = await self.get(entity_id, include_deleted=True)
        if not entity or entity.deleted_at is None:
            return None

        entity.deleted_at = None
        entity.updated_at = utcnow()
        entity.updated_by = user_id

        await self.db.commit()

        await self._invalidate_cache(entity.type)
        return entity

    async def list_deleted(
        self,
        type_name: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Entity], int]:
        """
        List soft-deleted entities (trash).

        Args:
            type_name: Optional filter by type
            limit: Max results
            offset: Pagination offset

        Returns:
            Tuple of (entities, total_count)
        """
        query = select(Entity).where(Entity.deleted_at.isnot(None))

        if type_name:
            query = query.where(Entity.type == type_name)

        # Order by deletion date (most recent first)
        query = query.order_by(Entity.deleted_at.desc())

        # Get total count
        from sqlalchemy import func

        count_query = select(func.count(Entity.id)).where(Entity.deleted_at.isnot(None))
        if type_name:
            count_query = count_query.where(Entity.type == type_name)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get entities with pagination
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        entities = result.scalars().all()

        return list(entities), total

    async def empty_trash(
        self,
        type_name: str = None,
        older_than_days: int = 30,
    ) -> int:
        """
        Permanently delete old soft-deleted entities.

        Args:
            type_name: Optional filter by type
            older_than_days: Only delete items deleted more than X days ago

        Returns:
            Count of permanently deleted entities
        """
        from sqlalchemy import delete as sql_delete

        cutoff = utcnow() - timedelta(days=older_than_days)

        conditions = [
            Entity.deleted_at.isnot(None),
            Entity.deleted_at < cutoff,
        ]
        if type_name:
            conditions.append(Entity.type == type_name)

        result = await self.db.execute(sql_delete(Entity).where(and_(*conditions)))
        await self.db.commit()

        return result.rowcount

    async def _invalidate_cache(self, type_name: str) -> None:
        """Invalidate page cache for a content type."""
        # Invalidate home page (shows recent posts)
        await cache_service.delete("page:home")

        # Invalidate type-specific pages
        await cache_service.invalidate_pattern(f"page:{type_name}")

        # Invalidate listings
        await cache_service.invalidate_pattern("page:category")
        await cache_service.invalidate_pattern("page:archive")

    async def get(
        self,
        entity_id: str,
        include_deleted: bool = False,
    ) -> Entity | None:
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
                and_(EntityValue.field_name == field_name, value_col == compare_value)
            )
        elif op == "neq":
            subq = select(EntityValue.entity_id).where(
                and_(EntityValue.field_name == field_name, value_col != compare_value)
            )
        elif op == "gte":
            subq = select(EntityValue.entity_id).where(
                and_(EntityValue.field_name == field_name, value_col >= compare_value)
            )
        elif op == "lte":
            subq = select(EntityValue.entity_id).where(
                and_(EntityValue.field_name == field_name, value_col <= compare_value)
            )
        elif op == "gt":
            subq = select(EntityValue.entity_id).where(
                and_(EntityValue.field_name == field_name, value_col > compare_value)
            )
        elif op == "lt":
            subq = select(EntityValue.entity_id).where(
                and_(EntityValue.field_name == field_name, value_col < compare_value)
            )
        elif op == "like":
            subq = select(EntityValue.entity_id).where(
                and_(EntityValue.field_name == field_name, value_col.like(f"%{compare_value}%"))
            )
        elif op == "isnull":
            # Check if field doesn't exist or value is null
            if value:
                subq = select(EntityValue.entity_id).where(
                    and_(EntityValue.field_name == field_name, value_col.is_(None))
                )
            else:
                subq = select(EntityValue.entity_id).where(
                    and_(EntityValue.field_name == field_name, value_col.isnot(None))
                )
        else:
            return query

        return query.where(Entity.id.in_(subq))

    async def _check_unique_constraints(
        self,
        type_name: str,
        data: dict[str, Any],
        content_type,
        entity_id: str = None,
    ) -> None:
        """Check unique constraints for fields.

        Args:
            type_name: Content type name
            data: Data to check
            content_type: ContentType definition
            entity_id: Current entity ID (for updates, to exclude self)

        Raises:
            ValueError: If a unique constraint is violated
        """
        for field_def in content_type.fields:
            if not field_def.unique:
                continue

            value = data.get(field_def.name)
            if value is None:
                continue

            # Check if another entity has this value
            storage_type = self._get_storage_type(field_def.type)
            if storage_type == "text":
                value_col = EntityValue.value_text
                compare_value = str(value)
            elif storage_type == "int":
                value_col = EntityValue.value_int
                compare_value = int(value)
            else:
                continue  # Skip non-text/int unique checks for now

            # Build query to find existing entity with same value
            subq = select(EntityValue.entity_id).where(
                and_(
                    EntityValue.field_name == field_def.name,
                    value_col == compare_value,
                )
            )

            query = select(Entity).where(
                and_(
                    Entity.type == type_name,
                    Entity.deleted_at.is_(None),
                    Entity.id.in_(subq),
                )
            )

            # Exclude current entity for updates
            if entity_id:
                query = query.where(Entity.id != entity_id)

            result = await self.db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                raise ValueError(
                    f"Unique constraint violation: {field_def.label or field_def.name} "
                    f"'{value}' already exists"
                )

    async def _check_status_transitions(
        self,
        entity: Entity,
        data: dict[str, Any],
        content_type,
    ) -> None:
        """Check if status field transitions are valid.

        Args:
            entity: Entity being updated
            data: New data
            content_type: ContentType definition

        Raises:
            ValueError: If a status transition is not allowed
        """
        # Get current field values for comparison
        current_data = self.serialize(entity)

        for field_def in content_type.fields:
            # Only check select fields with transitions defined
            if field_def.type != "select" or field_def.transitions is None:
                continue

            if field_def.name not in data:
                continue

            current_value = current_data.get(field_def.name)
            new_value = data[field_def.name]

            # Skip if value not changing
            if current_value == new_value:
                continue

            # Check if transition is allowed
            if not field_def.is_transition_allowed(current_value or "", new_value or ""):
                raise ValueError(
                    f"Invalid status transition: cannot change {field_def.label or field_def.name} "
                    f"from '{current_value}' to '{new_value}'"
                )

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
