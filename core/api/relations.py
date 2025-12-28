"""Relation API endpoints - relationship management."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.entity import EntityService
from ..services.field import field_service
from ..services.relation import RelationService

router = APIRouter(tags=["relations"])


class RelationAttach(BaseModel):
    """Request to attach a relation."""

    to_id: str
    sort_order: int = 0
    metadata: dict[str, Any] | None = None


class RelationSync(BaseModel):
    """Request to sync relations."""

    to_ids: list[str]


@router.get("/entities/{type_name}/{entity_id}/relations/{relation_type}")
async def get_related(
    type_name: str,
    entity_id: str,
    relation_type: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get related entities."""
    # Validate entity exists
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Validate relation type
    rel_def = field_service.get_relation_type(relation_type)
    if not rel_def:
        raise HTTPException(status_code=404, detail=f"Relation type '{relation_type}' not found")

    # Get related entities
    relation_svc = RelationService(db)
    related = await relation_svc.get_related(entity_id, relation_type)

    return [entity_svc.serialize(e) for e in related]


@router.post("/entities/{type_name}/{entity_id}/relations/{relation_type}")
async def attach_relation(
    type_name: str,
    entity_id: str,
    relation_type: str,
    body: RelationAttach,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Attach a relation."""
    # Validate source entity
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Validate target entity
    target = await entity_svc.get(body.to_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target entity not found")

    # Validate relation type
    rel_def = field_service.get_relation_type(relation_type)
    if not rel_def:
        raise HTTPException(status_code=404, detail=f"Relation type '{relation_type}' not found")

    # Create relation
    relation_svc = RelationService(db)
    relation = await relation_svc.attach(
        entity_id,
        body.to_id,
        relation_type,
        sort_order=body.sort_order,
        metadata=body.metadata,
    )

    return {
        "id": relation.id,
        "from_entity_id": relation.from_entity_id,
        "to_entity_id": relation.to_entity_id,
        "relation_type": relation.relation_type,
        "sort_order": relation.sort_order,
    }


@router.delete("/entities/{type_name}/{entity_id}/relations/{relation_type}/{to_id}")
async def detach_relation(
    type_name: str,
    entity_id: str,
    relation_type: str,
    to_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Detach a relation."""
    # Validate entity
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Detach
    relation_svc = RelationService(db)
    success = await relation_svc.detach(entity_id, to_id, relation_type)

    if not success:
        raise HTTPException(status_code=404, detail="Relation not found")

    return {"status": "detached"}


@router.put("/entities/{type_name}/{entity_id}/relations/{relation_type}")
async def sync_relations(
    type_name: str,
    entity_id: str,
    relation_type: str,
    body: RelationSync,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Sync relations - set exact list of related entities."""
    # Validate entity
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Validate all target entities exist
    for to_id in body.to_ids:
        target = await entity_svc.get(to_id)
        if not target:
            raise HTTPException(status_code=404, detail=f"Target entity '{to_id}' not found")

    # Sync
    relation_svc = RelationService(db)
    relations = await relation_svc.sync(entity_id, body.to_ids, relation_type)

    return [
        {
            "id": r.id,
            "from_entity_id": r.from_entity_id,
            "to_entity_id": r.to_entity_id,
            "relation_type": r.relation_type,
            "sort_order": r.sort_order,
        }
        for r in relations
    ]
