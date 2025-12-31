"""Entity API endpoints - unified CRUD for all content types.

This module provides RESTful API endpoints for managing entities (content items)
in the CMS. It supports CRUD operations for any registered content type.

Example content types: post, page, category, tag, etc.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.entity import Entity
from ..rate_limit import limiter
from ..services.auth import AuthService
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
from .auth import get_session_token

router = APIRouter(prefix="/entities", tags=["Entities"])


async def _get_optional_user(request: Request, db: AsyncSession) -> Entity | None:
    """Get current user if authenticated, None otherwise."""
    token = get_session_token(request)
    if not token:
        return None
    auth_svc = AuthService(db)
    return await auth_svc.get_current_user(token)


class EntityCreate(BaseModel):
    """Request body for creating an entity.

    Example:
        ```json
        {
            "data": {
                "title": "My First Post",
                "slug": "my-first-post",
                "body": [{"type": "paragraph", "data": {"text": "Hello world!"}}],
                "status": "draft"
            }
        }
        ```
    """

    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Entity field values as key-value pairs",
        examples=[{"title": "My First Post", "slug": "my-first-post", "status": "draft"}],
    )


class EntityUpdate(BaseModel):
    """Request body for updating an entity.

    Only include fields that should be updated.
    """

    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Entity field values to update",
        examples=[{"status": "published"}],
    )


class EntityResponse(BaseModel):
    """Response for a single entity.

    Example:
        ```json
        {
            "id": "abc123",
            "type": "post",
            "title": "My First Post",
            "slug": "my-first-post",
            "status": "published",
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z"
        }
        ```
    """

    id: str = Field(..., description="Unique entity identifier")
    type: str = Field(..., description="Content type name")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601)")
    created_by: str | None = Field(None, description="Creator user ID")
    updated_by: str | None = Field(None, description="Last updater user ID")
    data: dict[str, Any] = Field(default_factory=dict, description="Entity field values")

    class Config:
        from_attributes = True


class EntityListResponse(BaseModel):
    """Response for paginated entity list.

    Example:
        ```json
        {
            "items": [{"id": "abc123", "type": "post", "title": "My Post"}],
            "total": 42,
            "page": 1,
            "per_page": 20,
            "pages": 3
        }
        ```
    """

    items: list[dict[str, Any]] = Field(..., description="List of entities")
    total: int = Field(..., description="Total number of entities")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")


@router.get(
    "/{type_name}",
    response_model=EntityListResponse,
    summary="List entities",
    description="Retrieve a paginated list of entities of the specified content type.",
    responses={
        200: {
            "description": "Paginated list of entities",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "abc123",
                                "type": "post",
                                "title": "Hello World",
                                "status": "published",
                            }
                        ],
                        "total": 42,
                        "page": 1,
                        "per_page": 20,
                        "pages": 3,
                    }
                }
            },
        },
        404: {"description": "Content type not found"},
    },
)
@limiter.limit("100/minute")
async def list_entities(
    request: Request,
    type_name: str,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    sort: str = Query("-created_at", description="Sort field (prefix with - for descending)"),
    db: AsyncSession = Depends(get_db),
) -> EntityListResponse:
    """List entities of a specific type.

    Retrieves a paginated list of entities. Supports sorting by any field.

    - Use `-field` for descending order (e.g., `-created_at`)
    - Use `field` for ascending order (e.g., `title`)
    """
    # Validate type exists
    ct = field_service.get_content_type(type_name)
    if not ct:
        raise HTTPException(status_code=404, detail=f"Content type '{type_name}' not found")

    service = EntityService(db)
    params = QueryParams(page=page, per_page=per_page, sort=sort)

    entities = await service.find(type_name, params)
    total = await service.count(type_name, params)
    pages = (total + per_page - 1) // per_page

    return EntityListResponse(
        items=[service.serialize(e) for e in entities],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.post(
    "/{type_name}",
    summary="Create entity",
    description="Create a new entity of the specified content type.",
    responses={
        200: {
            "description": "Created entity",
            "content": {
                "application/json": {
                    "example": {
                        "id": "abc123",
                        "type": "post",
                        "title": "My New Post",
                        "slug": "my-new-post",
                        "created_at": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        400: {"description": "Validation error"},
        404: {"description": "Content type not found"},
    },
)
@limiter.limit("100/minute")
async def create_entity(
    request: Request,
    type_name: str,
    body: EntityCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new entity.

    Creates a new entity with the provided field values.
    Required fields must be included in the request body.
    """
    # Validate type exists
    ct = field_service.get_content_type(type_name)
    if not ct:
        raise HTTPException(status_code=404, detail=f"Content type '{type_name}' not found")

    # Get current user for audit trail
    user = await _get_optional_user(request, db)
    user_id = user.id if user else None

    service = EntityService(db)

    try:
        entity = await service.create(type_name, body.data, user_id=user_id)
        return service.serialize(entity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{type_name}/{entity_id}",
    summary="Get entity",
    description="Retrieve a single entity by its ID.",
    responses={
        200: {
            "description": "Entity details",
            "content": {
                "application/json": {
                    "example": {
                        "id": "abc123",
                        "type": "post",
                        "title": "Hello World",
                        "slug": "hello-world",
                        "status": "published",
                        "created_at": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        404: {"description": "Entity not found"},
    },
)
@limiter.limit("100/minute")
async def get_entity(
    request: Request,
    type_name: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a single entity by ID.

    Returns all fields for the specified entity.
    """
    service = EntityService(db)
    entity = await service.get(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    return service.serialize(entity)


@router.put(
    "/{type_name}/{entity_id}",
    summary="Update entity",
    description="Update an existing entity with new field values.",
    responses={
        200: {
            "description": "Updated entity",
            "content": {
                "application/json": {
                    "example": {
                        "id": "abc123",
                        "type": "post",
                        "title": "Updated Title",
                        "status": "published",
                        "updated_at": "2024-01-15T12:00:00Z",
                    }
                }
            },
        },
        400: {"description": "Validation error"},
        404: {"description": "Entity not found"},
    },
)
@limiter.limit("100/minute")
async def update_entity(
    request: Request,
    type_name: str,
    entity_id: str,
    body: EntityUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update an entity.

    Only fields included in the request body will be updated.
    Omitted fields retain their current values.
    """
    service = EntityService(db)
    entity = await service.get(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Get current user for audit trail
    user = await _get_optional_user(request, db)
    user_id = user.id if user else None

    try:
        updated = await service.update(entity_id, body.data, user_id=user_id)
        return service.serialize(updated)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{type_name}/{entity_id}",
    summary="Delete entity",
    description="Delete an entity (soft delete by default, use hard=true for permanent deletion).",
    responses={
        200: {
            "description": "Deletion confirmation",
            "content": {"application/json": {"example": {"status": "deleted", "id": "abc123"}}},
        },
        404: {"description": "Entity not found"},
    },
)
@limiter.limit("100/minute")
async def delete_entity(
    request: Request,
    type_name: str,
    entity_id: str,
    hard: bool = Query(False, description="If true, permanently delete (cannot be undone)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete an entity.

    By default, performs a soft delete (sets deleted_at timestamp).
    Use `hard=true` to permanently delete the entity.

    **Warning**: Hard delete cannot be undone.
    """
    service = EntityService(db)
    entity = await service.get(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    await service.delete(entity_id, hard=hard)
    return {"status": "deleted", "id": entity_id}
