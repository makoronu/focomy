"""Media API endpoints - file upload and management.

This module provides endpoints for uploading, listing, and managing media files.

Features:
- Automatic image optimization (resize to max 1920px, convert to WebP)
- CDN support (optional S3 upload)
- Alt text management for accessibility
"""

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.media import MediaService

router = APIRouter(prefix="/media", tags=["Media"])


class MediaUpdate(BaseModel):
    """Update media metadata."""

    alt_text: str | None = Field(None, description="Alt text for accessibility")


@router.post(
    "",
    summary="Upload file",
    description="Upload a file. Images are automatically optimized (resized to max 1920px, converted to WebP).",
    responses={
        200: {
            "description": "Uploaded file details",
            "content": {
                "application/json": {
                    "example": {
                        "id": "media123",
                        "filename": "photo.jpg",
                        "url": "/uploads/2024/01/15/abc123.webp",
                        "mime_type": "image/webp",
                        "size": 102400,
                        "width": 1920,
                        "height": 1080,
                    }
                }
            },
        },
        400: {"description": "No filename provided"},
    },
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload a file.

    Images are automatically:
    - Resized to max 1920px on longest side
    - Converted to WebP format
    - Stored with a hash-based filename in date folders
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    media_svc = MediaService(db)
    media = await media_svc.upload(
        file=file.file,
        filename=file.filename,
        content_type=file.content_type,
    )

    return media_svc.serialize(media)


@router.get(
    "",
    summary="List media",
    description="Retrieve a paginated list of media files with optional filtering by MIME type.",
    responses={
        200: {
            "description": "Paginated list of media files",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "media123",
                                "filename": "photo.jpg",
                                "url": "/uploads/2024/01/15/abc.webp",
                            }
                        ],
                        "total": 42,
                        "page": 1,
                        "per_page": 20,
                        "pages": 3,
                    }
                }
            },
        }
    },
)
async def list_media(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    mime_type: str | None = Query(None, description="Filter by MIME type prefix (e.g., 'image')"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List media files.

    Filter by MIME type prefix to get only images, videos, etc.
    """
    media_svc = MediaService(db)
    offset = (page - 1) * per_page

    items = await media_svc.find(limit=per_page, offset=offset, mime_type=mime_type)
    total = await media_svc.count(mime_type=mime_type)

    return {
        "items": [media_svc.serialize(m) for m in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.get(
    "/{media_id}",
    summary="Get media",
    description="Retrieve media details by ID.",
    responses={
        200: {
            "description": "Media details",
            "content": {
                "application/json": {
                    "example": {
                        "id": "media123",
                        "filename": "photo.jpg",
                        "url": "/uploads/2024/01/15/abc123.webp",
                        "mime_type": "image/webp",
                        "size": 102400,
                        "width": 1920,
                        "height": 1080,
                        "alt_text": "A beautiful sunset",
                    }
                }
            },
        },
        404: {"description": "Media not found"},
    },
)
async def get_media(
    media_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get media by ID."""
    media_svc = MediaService(db)
    media = await media_svc.get(media_id)

    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    return media_svc.serialize(media)


@router.patch(
    "/{media_id}",
    summary="Update media",
    description="Update media metadata (e.g., alt text).",
    responses={
        200: {"description": "Updated media details"},
        404: {"description": "Media not found"},
    },
)
async def update_media(
    media_id: str,
    body: MediaUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update media metadata.

    Currently supports updating alt text for accessibility.
    """
    media_svc = MediaService(db)

    if body.alt_text is not None:
        media = await media_svc.update_alt_text(media_id, body.alt_text)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        return media_svc.serialize(media)

    media = await media_svc.get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return media_svc.serialize(media)


@router.delete(
    "/{media_id}",
    summary="Delete media",
    description="Delete a media file and its database record.",
    responses={
        200: {
            "description": "Deletion confirmation",
            "content": {"application/json": {"example": {"status": "deleted"}}},
        },
        404: {"description": "Media not found"},
    },
)
async def delete_media(
    media_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete media.

    Removes the file from storage (and S3 if configured) and deletes the database record.
    """
    media_svc = MediaService(db)
    success = await media_svc.delete(media_id)

    if not success:
        raise HTTPException(status_code=404, detail="Media not found")

    return {"status": "deleted"}
