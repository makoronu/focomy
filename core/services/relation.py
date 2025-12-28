"""RelationService - relationship management."""

from typing import Any

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, Relation
from .field import FieldService, field_service


class RelationService:
    """
    Relation management service.

    Handles all relationships between entities.
    No foreign keys in entity tables - all managed here.
    """

    def __init__(self, db: AsyncSession, field_svc: FieldService = None):
        self.db = db
        self.field_svc = field_svc or field_service

    async def attach(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        sort_order: int = 0,
        metadata: dict[str, Any] = None,
    ) -> Relation:
        """Create a relation between two entities.

        For many_to_one relations, any existing relation from the same
        from_entity is automatically removed (enforcing the constraint).
        """
        # Validate relation type exists
        rel_def = self.field_svc.get_relation_type(relation_type)
        if not rel_def:
            raise ValueError(f"Unknown relation type: {relation_type}")

        # Check if relation already exists
        existing = await self._get_relation(from_id, to_id, relation_type)
        if existing:
            # Update existing
            existing.sort_order = sort_order
            if metadata:
                existing.metadata_ = metadata
            await self.db.commit()
            return existing

        # For many_to_one, remove any existing relation from this from_entity
        # This enforces the "one" constraint
        if rel_def.type == "many_to_one":
            existing_relations = await self.get_relations(from_id, relation_type, direction="from")
            for old_rel in existing_relations:
                await self.db.delete(old_rel)

        # For self_referential relations, check for circular references
        if rel_def.self_referential:
            await self._check_circular_reference(from_id, to_id, relation_type)

        # Create new relation
        relation = Relation(
            from_entity_id=from_id,
            to_entity_id=to_id,
            relation_type=relation_type,
            sort_order=sort_order,
            metadata_=metadata,
        )
        self.db.add(relation)
        await self.db.commit()
        await self.db.refresh(relation)
        return relation

    async def _check_circular_reference(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        max_depth: int = 10,
    ) -> None:
        """Check for circular references in self-referential relations.

        Raises:
            ValueError: If adding this relation would create a cycle
        """
        if from_id == to_id:
            raise ValueError("Cannot create self-referential relation to itself")

        # Walk up the tree from to_id to check if we reach from_id
        visited = {to_id}
        current_ids = [to_id]
        depth = 0

        while current_ids and depth < max_depth:
            # Get all parents of current nodes
            parent_ids = []
            for current_id in current_ids:
                relations = await self.get_relations(current_id, relation_type, direction="from")
                for rel in relations:
                    parent_id = rel.to_entity_id
                    if parent_id == from_id:
                        raise ValueError(
                            "Circular reference detected: adding this relation would create a cycle"
                        )
                    if parent_id not in visited:
                        visited.add(parent_id)
                        parent_ids.append(parent_id)

            current_ids = parent_ids
            depth += 1

    async def detach(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
    ) -> bool:
        """Remove a relation between two entities."""
        relation = await self._get_relation(from_id, to_id, relation_type)
        if not relation:
            return False

        await self.db.delete(relation)
        await self.db.commit()
        return True

    async def sync(
        self,
        from_id: str,
        to_ids: list[str],
        relation_type: str,
    ) -> list[Relation]:
        """
        Sync relations - set exact list of related entities.

        Removes relations not in to_ids, adds missing ones.
        """
        # Get current relations
        current = await self.get_relations(from_id, relation_type)
        current_to_ids = {r.to_entity_id for r in current}
        new_to_ids = set(to_ids)

        # Remove old
        to_remove = current_to_ids - new_to_ids
        for to_id in to_remove:
            await self.detach(from_id, to_id, relation_type)

        # Add new
        to_add = new_to_ids - current_to_ids
        for i, to_id in enumerate(to_ids):
            if to_id in to_add:
                await self.attach(from_id, to_id, relation_type, sort_order=i)

        # Update sort order for existing
        for i, to_id in enumerate(to_ids):
            if to_id in current_to_ids:
                rel = await self._get_relation(from_id, to_id, relation_type)
                if rel:
                    rel.sort_order = i

        await self.db.commit()
        return await self.get_relations(from_id, relation_type)

    async def get_relations(
        self,
        entity_id: str,
        relation_type: str,
        direction: str = "from",
    ) -> list[Relation]:
        """Get all relations of a type for an entity."""
        if direction == "from":
            query = (
                select(Relation)
                .where(
                    and_(
                        Relation.from_entity_id == entity_id,
                        Relation.relation_type == relation_type,
                    )
                )
                .order_by(Relation.sort_order)
            )
        else:
            query = (
                select(Relation)
                .where(
                    and_(
                        Relation.to_entity_id == entity_id,
                        Relation.relation_type == relation_type,
                    )
                )
                .order_by(Relation.sort_order)
            )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_related(
        self,
        entity_id: str,
        relation_type: str,
        direction: str = "from",
    ) -> list[Entity]:
        """Get related entities."""
        relations = await self.get_relations(entity_id, relation_type, direction)

        if not relations:
            return []

        if direction == "from":
            entity_ids = [r.to_entity_id for r in relations]
        else:
            entity_ids = [r.from_entity_id for r in relations]

        query = select(Entity).where(
            and_(
                Entity.id.in_(entity_ids),
                Entity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        entities = {e.id: e for e in result.scalars().all()}

        # Maintain sort order
        return [entities[eid] for eid in entity_ids if eid in entities]

    async def _get_relation(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
    ) -> Relation | None:
        """Get a specific relation."""
        query = select(Relation).where(
            and_(
                Relation.from_entity_id == from_id,
                Relation.to_entity_id == to_id,
                Relation.relation_type == relation_type,
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def delete_all_relations(
        self,
        entity_id: str,
    ):
        """Delete all relations for an entity (both directions)."""
        await self.db.execute(delete(Relation).where(Relation.from_entity_id == entity_id))
        await self.db.execute(delete(Relation).where(Relation.to_entity_id == entity_id))
        await self.db.commit()
