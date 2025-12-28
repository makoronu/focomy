"""Revisions API - version history endpoints.

This module provides endpoints for managing entity revisions (version history).

Features:
- Manual and automatic revisions
- Autosave support (every 30 seconds in the editor)
- Restore from any previous revision
- Automatic cleanup of old autosaves
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.entity import EntityService
from ..services.revision import RevisionService

router = APIRouter(prefix="/revisions", tags=["Revisions"])


class AutosaveRequest(BaseModel):
    """Request body for autosave."""

    entity_id: str = Field(..., description="Entity ID to save")
    data: dict[str, Any] = Field(..., description="Current form data to save")


class RestoreRequest(BaseModel):
    """Request body for restore."""

    revision_id: str = Field(..., description="Revision ID to restore from")


@router.get(
    "/{entity_id}",
    summary="List revisions",
    description="Get version history for an entity.",
    responses={
        200: {
            "description": "List of revisions",
            "content": {
                "application/json": {
                    "example": {
                        "revisions": [
                            {
                                "id": "rev123",
                                "revision_type": "manual",
                                "title": "My Post",
                                "created_at": "2024-01-15T10:30:00Z",
                            }
                        ],
                        "total": 5,
                    }
                }
            },
        }
    },
)
async def list_revisions(
    entity_id: str,
    include_autosaves: bool = Query(False, description="Include autosave revisions"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List revisions for an entity.

    Returns manual revisions by default. Set include_autosaves=true to include
    automatic saves.
    """
    revision_svc = RevisionService(db)

    revisions = await revision_svc.list_for_entity(
        entity_id,
        limit=limit,
        offset=offset,
        include_autosaves=include_autosaves,
    )
    total = await revision_svc.count_for_entity(entity_id, include_autosaves)

    return {
        "revisions": [revision_svc.serialize(r) for r in revisions],
        "total": total,
    }


@router.get(
    "/{entity_id}/{revision_id}",
    summary="Get revision",
    description="Get details of a specific revision including its full data snapshot.",
    responses={
        200: {"description": "Revision details with data"},
        404: {"description": "Revision not found"},
    },
)
async def get_revision(
    entity_id: str,
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific revision.

    Returns the full data snapshot that was saved in this revision.
    """
    revision_svc = RevisionService(db)

    revision = await revision_svc.get(revision_id)
    if not revision or revision.entity_id != entity_id:
        raise HTTPException(status_code=404, detail="Revision not found")

    return revision_svc.serialize(revision)


@router.post(
    "/autosave",
    summary="Create autosave",
    description="Save form data automatically. Called by the editor every 30 seconds.",
    responses={200: {"description": "Autosave created"}, 404: {"description": "Entity not found"}},
)
async def autosave(
    body: AutosaveRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create an autosave revision.

    The editor calls this endpoint automatically every 30 seconds.
    Old autosaves are cleaned up automatically (keeps last 5).
    """
    entity_svc = EntityService(db)
    revision_svc = RevisionService(db)

    # Verify entity exists
    entity = await entity_svc.get(body.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Create autosave
    revision = await revision_svc.create(
        entity_id=body.entity_id,
        data=body.data,
        revision_type="autosave",
        title=body.data.get("title") or body.data.get("name"),
    )

    # Cleanup old autosaves
    await revision_svc.cleanup_autosaves(body.entity_id)

    return revision_svc.serialize(revision)


@router.post(
    "/{entity_id}/restore",
    summary="Restore revision",
    description="Restore an entity to a previous state from a revision.",
    responses={
        200: {
            "description": "Entity restored",
            "content": {
                "application/json": {"example": {"status": "restored", "revision_id": "rev123"}}
            },
        },
        404: {"description": "Entity or revision not found"},
    },
)
async def restore_revision(
    entity_id: str,
    body: RestoreRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Restore entity from a revision.

    Creates a new manual revision of the current state, then applies
    the selected revision's data to the entity.
    """
    entity_svc = EntityService(db)
    revision_svc = RevisionService(db)

    # Get revision
    revision = await revision_svc.get(body.revision_id)
    if not revision or revision.entity_id != entity_id:
        raise HTTPException(status_code=404, detail="Revision not found")

    # Get entity
    entity = await entity_svc.get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Restore by updating with revision data
    await entity_svc.update(
        entity_id=entity_id,
        data=revision.data,
        revision_type="manual",  # Create a manual revision before restoring
    )

    return {"status": "restored", "revision_id": body.revision_id}


@router.delete(
    "/{entity_id}/{revision_id}",
    summary="Delete revision",
    description="Delete a specific revision from history.",
    responses={
        200: {
            "description": "Revision deleted",
            "content": {"application/json": {"example": {"status": "deleted"}}},
        },
        404: {"description": "Revision not found"},
    },
)
async def delete_revision(
    entity_id: str,
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a revision.

    Permanently removes a revision from history. Cannot be undone.
    """
    revision_svc = RevisionService(db)

    revision = await revision_svc.get(revision_id)
    if not revision or revision.entity_id != entity_id:
        raise HTTPException(status_code=404, detail="Revision not found")

    await revision_svc.delete(revision_id)
    return {"status": "deleted"}
