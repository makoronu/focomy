"""Preview Service - Import a few items for verification before full import."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...utils import utcnow
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, EntityValue, ImportJob
from ..entity import EntityService
from .constants import WP_STATUS_MAP
from .content_sanitizer import ContentSanitizer
from .wxr_parser import WXRData

logger = logging.getLogger(__name__)


@dataclass
class PreviewItem:
    """Imported preview item."""

    entity_type: str
    entity_id: str
    wp_id: int | str
    title: str
    slug: str
    status: str  # success, error
    message: str = ""


@dataclass
class PreviewResult:
    """Result of preview import."""

    job_id: str
    preview_id: str  # Unique ID for this preview session
    generated_at: datetime = field(default_factory=datetime.utcnow)
    items: list[PreviewItem] = field(default_factory=list)
    success_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    committed: bool = False  # Whether preview was committed
    rolled_back: bool = False  # Whether preview was rolled back

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return self.error_count > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "preview_id": self.preview_id,
            "generated_at": self.generated_at.isoformat(),
            "items": [
                {
                    "entity_type": i.entity_type,
                    "entity_id": i.entity_id,
                    "wp_id": i.wp_id,
                    "title": i.title,
                    "slug": i.slug,
                    "status": i.status,
                    "message": i.message,
                }
                for i in self.items
            ],
            "success_count": self.success_count,
            "error_count": self.error_count,
            "errors": self.errors,
            "has_errors": self.has_errors,
            "committed": self.committed,
            "rolled_back": self.rolled_back,
        }


class PreviewService:
    """
    Preview import service.

    Imports a small number of items to verify before full import.
    Preview items can be committed or rolled back.
    """

    DEFAULT_PREVIEW_COUNT = 3

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)
        self.sanitizer = ContentSanitizer()
        self._preview_entities: dict[str, list[str]] = {}  # preview_id -> entity_ids

    async def run_preview(
        self,
        job_id: str,
        wxr_data: WXRData,
        count: int = DEFAULT_PREVIEW_COUNT,
    ) -> PreviewResult:
        """
        Run preview import.

        Args:
            job_id: Import job ID
            wxr_data: Parsed WordPress data
            count: Number of items to preview (default 3)

        Returns:
            PreviewResult with imported items
        """
        import uuid

        preview_id = str(uuid.uuid4())[:8]
        result = PreviewResult(job_id=job_id, preview_id=preview_id)
        imported_entity_ids: list[str] = []

        try:
            # Import a few posts
            posts = [p for p in wxr_data.posts if p.post_type == "post"][:count]
            for post in posts:
                try:
                    # Check if already exists
                    existing = await self._find_by_wp_id("post", post.id)
                    if existing:
                        result.items.append(
                            PreviewItem(
                                entity_type="post",
                                entity_id="",
                                wp_id=post.id,
                                title=post.title,
                                slug=post.slug,
                                status="skip",
                                message="Already exists",
                            )
                        )
                        continue

                    # Sanitize content
                    content_result = self.sanitizer.sanitize(post.content or "")
                    excerpt_result = self.sanitizer.sanitize(post.excerpt or "")

                    # Create entity
                    entity = await self.entity_svc.create(
                        "post",
                        {
                            "title": post.title,
                            "slug": post.slug,
                            "content": content_result.content,
                            "excerpt": excerpt_result.content,
                            "status": WP_STATUS_MAP.get(post.status, "draft"),
                            "wp_id": post.id,
                            "preview": True,  # Mark as preview
                        },
                    )

                    imported_entity_ids.append(entity.id)

                    result.items.append(
                        PreviewItem(
                            entity_type="post",
                            entity_id=entity.id,
                            wp_id=post.id,
                            title=post.title,
                            slug=post.slug,
                            status="success",
                            message="Imported successfully",
                        )
                    )
                    result.success_count += 1

                except Exception as e:
                    result.items.append(
                        PreviewItem(
                            entity_type="post",
                            entity_id="",
                            wp_id=post.id,
                            title=post.title,
                            slug=post.slug,
                            status="error",
                            message=str(e),
                        )
                    )
                    result.error_count += 1
                    result.errors.append(f"Post {post.id}: {e}")

            # Import a few pages if we have room
            remaining = count - len(posts)
            if remaining > 0:
                pages = [p for p in wxr_data.posts if p.post_type == "page"][:remaining]
                for page in pages:
                    try:
                        existing = await self._find_by_wp_id("page", page.id)
                        if existing:
                            continue

                        content_result = self.sanitizer.sanitize(page.content or "")

                        entity = await self.entity_svc.create(
                            "page",
                            {
                                "title": page.title,
                                "slug": page.slug,
                                "content": content_result.content,
                                "status": "draft",
                                "wp_id": page.id,
                                "preview": True,
                            },
                        )

                        imported_entity_ids.append(entity.id)

                        result.items.append(
                            PreviewItem(
                                entity_type="page",
                                entity_id=entity.id,
                                wp_id=page.id,
                                title=page.title,
                                slug=page.slug,
                                status="success",
                                message="Imported successfully",
                            )
                        )
                        result.success_count += 1

                    except Exception as e:
                        result.error_count += 1
                        result.errors.append(f"Page {page.id}: {e}")

            # Store entity IDs for later commit/rollback
            self._preview_entities[preview_id] = imported_entity_ids

            # Commit to save preview items
            await self.db.commit()

            logger.info(
                f"Preview complete: {result.success_count} success, "
                f"{result.error_count} errors"
            )

        except Exception as e:
            logger.error(f"Preview failed: {e}")
            result.errors.append(str(e))
            await self.db.rollback()

        return result

    async def commit_preview(self, preview_id: str) -> dict:
        """
        Commit preview - keep imported items.

        Args:
            preview_id: Preview session ID

        Returns:
            Result dict
        """
        entity_ids = self._preview_entities.get(preview_id, [])

        if not entity_ids:
            return {
                "success": False,
                "error": "Preview not found or already processed",
            }

        # Remove preview flag from entities
        for entity_id in entity_ids:
            result = await self.db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == entity_id,
                    EntityValue.field_name == "preview",
                )
            )
            ev = result.scalar_one_or_none()
            if ev:
                await self.db.delete(ev)

        await self.db.commit()

        # Clean up
        del self._preview_entities[preview_id]

        logger.info(f"Preview {preview_id} committed: {len(entity_ids)} items")

        return {
            "success": True,
            "preview_id": preview_id,
            "committed_count": len(entity_ids),
        }

    async def rollback_preview(self, preview_id: str) -> dict:
        """
        Rollback preview - delete imported items.

        Args:
            preview_id: Preview session ID

        Returns:
            Result dict
        """
        entity_ids = self._preview_entities.get(preview_id, [])

        if not entity_ids:
            return {
                "success": False,
                "error": "Preview not found or already processed",
            }

        # Delete preview entities
        deleted_count = 0
        for entity_id in entity_ids:
            try:
                result = await self.db.execute(
                    select(Entity).where(Entity.id == entity_id)
                )
                entity = result.scalar_one_or_none()
                if entity:
                    # Soft delete
                    entity.deleted_at = utcnow()
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Error deleting preview entity {entity_id}: {e}")

        await self.db.commit()

        # Clean up
        del self._preview_entities[preview_id]

        logger.info(f"Preview {preview_id} rolled back: {deleted_count} items deleted")

        return {
            "success": True,
            "preview_id": preview_id,
            "rolled_back_count": deleted_count,
        }

    async def _find_by_wp_id(
        self, entity_type: str, wp_id: int
    ) -> Entity | None:
        """Find entity by WordPress ID."""
        result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "wp_id",
                EntityValue.value_int == wp_id,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


# Global preview service instance for session management
_preview_sessions: dict[str, list[str]] = {}


def get_preview_entities(preview_id: str) -> list[str]:
    """Get entity IDs for a preview session."""
    return _preview_sessions.get(preview_id, [])


def store_preview_entities(preview_id: str, entity_ids: list[str]) -> None:
    """Store entity IDs for a preview session."""
    _preview_sessions[preview_id] = entity_ids


def clear_preview_entities(preview_id: str) -> None:
    """Clear preview session."""
    if preview_id in _preview_sessions:
        del _preview_sessions[preview_id]
