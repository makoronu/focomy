"""Import helpers - shared utility methods for WordPress import."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity

logger = logging.getLogger(__name__)


class ImportHelpersMixin:
    """Shared utility methods for import operations.

    Mixed into WordPressImportService.
    Requires: self.db (AsyncSession), self.entity_svc (EntityService)
    """

    async def _find_by_wp_id(self, entity_type: str, wp_id: int) -> Entity | None:
        """Find entity by WordPress ID."""
        from ...models import EntityValue

        result = await self.db.execute(
            select(Entity)
            .join(EntityValue)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "wp_id",
                EntityValue.value_int == wp_id,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _find_by_slug(self, entity_type: str, slug: str) -> Entity | None:
        """Find entity by slug."""
        from ...models import EntityValue

        result = await self.db.execute(
            select(Entity)
            .join(EntityValue)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "slug",
                EntityValue.value_text == slug,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_entity_field(self, entity_id: str, field_name: str) -> str | None:
        """Get a string field value from an entity."""
        from ...models import EntityValue

        result = await self.db.execute(
            select(EntityValue).where(
                EntityValue.entity_id == entity_id,
                EntityValue.field_name == field_name,
            )
        )
        ev = result.scalar_one_or_none()
        if ev:
            return ev.value_string or ev.value_text
        return None

    async def _get_checkpoint(self, job_id: str) -> dict:
        """Get checkpoint data for a job."""
        job = await self.get_job(job_id)
        if not job or not job.checkpoint:
            return {
                "authors": [],
                "categories": [],
                "tags": [],
                "media": [],
                "posts": [],
                "pages": [],
                "menus": [],
                "last_phase": None,
            }
        return job.checkpoint

    async def _save_checkpoint(
        self,
        job_id: str,
        item_type: str,
        wp_id: int,
        phase: str | None = None,
    ) -> None:
        """Save a processed item to checkpoint."""
        job = await self.get_job(job_id)
        if not job:
            return

        checkpoint = job.checkpoint or {
            "authors": [],
            "categories": [],
            "tags": [],
            "media": [],
            "posts": [],
            "pages": [],
            "menus": [],
            "last_phase": None,
        }

        if item_type in checkpoint and wp_id not in checkpoint[item_type]:
            checkpoint[item_type].append(wp_id)

        if phase:
            checkpoint["last_phase"] = phase

        await self.update_job(job_id, checkpoint=checkpoint)

    async def _is_processed(self, job_id: str, item_type: str, wp_id: int) -> bool:
        """Check if an item was already processed in a previous run."""
        checkpoint = await self._get_checkpoint(job_id)
        return wp_id in checkpoint.get(item_type, [])

    async def _is_menu_processed(self, job_id: str, menu_name: str) -> bool:
        """Check if a menu was already processed (uses name instead of ID)."""
        checkpoint = await self._get_checkpoint(job_id)
        return menu_name in checkpoint.get("menus", [])

    async def _save_menu_checkpoint(self, job_id: str, menu_name: str) -> None:
        """Save a processed menu to checkpoint (uses name instead of ID)."""
        job = await self.get_job(job_id)
        if not job:
            return

        checkpoint = job.checkpoint or {
            "authors": [],
            "categories": [],
            "tags": [],
            "media": [],
            "posts": [],
            "pages": [],
            "menus": [],
            "last_phase": None,
        }

        if "menus" not in checkpoint:
            checkpoint["menus"] = []

        if menu_name not in checkpoint["menus"]:
            checkpoint["menus"].append(menu_name)

        checkpoint["last_phase"] = "menus"

        await self.update_job(job_id, checkpoint=checkpoint)
