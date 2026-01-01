"""Rollback Service - Rollback WordPress import."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ...utils import utcnow

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, EntityValue, ImportJob, ImportJobStatus

logger = logging.getLogger(__name__)

# Rollback is valid for 30 days after import
ROLLBACK_VALIDITY_DAYS = 30


class RollbackService:
    """
    Service to rollback WordPress imports.

    Deletes all entities imported from WordPress by finding entities with wp_id.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_rollback(self, job_id: str) -> dict:
        """
        Check if a job can be rolled back.

        Returns:
            dict with 'can_rollback' boolean and 'reason' if False
        """
        result = await self.db.execute(
            select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return {"can_rollback": False, "reason": "Job not found"}

        if job.status != ImportJobStatus.COMPLETED:
            return {
                "can_rollback": False,
                "reason": f"Job status is {job.status}, not completed",
            }

        if not job.completed_at:
            return {"can_rollback": False, "reason": "Job has no completion date"}

        # Check 30-day validity
        expires_at = job.completed_at + timedelta(days=ROLLBACK_VALIDITY_DAYS)
        if utcnow() > expires_at:
            return {
                "can_rollback": False,
                "reason": f"Rollback expired on {expires_at.isoformat()}",
            }

        return {"can_rollback": True, "expires_at": expires_at.isoformat()}

    async def preview_rollback(self, job_id: str) -> dict:
        """
        Preview what will be deleted by rollback.

        Returns counts of entities that would be deleted.
        """
        result = await self.db.execute(
            select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return {"success": False, "error": "Job not found"}

        # Count entities with wp_id that were imported
        entity_types = ["post", "page", "media", "category", "tag", "user", "menu"]
        counts = {}

        for entity_type in entity_types:
            count_result = await self.db.execute(
                select(Entity.id)
                .join(EntityValue)
                .where(
                    Entity.type == entity_type,
                    EntityValue.field_name == "wp_id",
                    EntityValue.value_int.isnot(None),
                    Entity.deleted_at.is_(None),
                )
            )
            counts[entity_type] = len(count_result.all())

        return {
            "success": True,
            "job_id": job_id,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "counts": counts,
            "total": sum(counts.values()),
        }

    async def rollback(self, job_id: str) -> dict:
        """
        Rollback all entities imported from WordPress.

        This soft-deletes all entities that have a wp_id.
        """
        # Check if rollback is allowed
        can_rollback = await self.can_rollback(job_id)
        if not can_rollback.get("can_rollback"):
            return {
                "success": False,
                "error": can_rollback.get("reason", "Rollback not allowed"),
            }

        result = await self.db.execute(
            select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return {"success": False, "error": "Job not found"}

        # Delete entities with wp_id (soft delete)
        entity_types = ["post", "page", "media", "category", "tag", "user", "menu"]
        deleted_counts = {}
        total_deleted = 0

        for entity_type in entity_types:
            try:
                # Find entities with wp_id
                entities_result = await self.db.execute(
                    select(Entity)
                    .join(EntityValue)
                    .where(
                        Entity.type == entity_type,
                        EntityValue.field_name == "wp_id",
                        EntityValue.value_int.isnot(None),
                        Entity.deleted_at.is_(None),
                    )
                )
                entities = entities_result.scalars().all()

                count = 0
                for entity in entities:
                    # Soft delete
                    entity.deleted_at = utcnow()
                    count += 1

                deleted_counts[entity_type] = count
                total_deleted += count

            except Exception as e:
                logger.warning(f"Error deleting {entity_type} entities: {e}")
                deleted_counts[entity_type] = 0

        # Update job status
        job.status = "rolled_back"
        job.progress_message = f"Rolled back {total_deleted} entities"

        await self.db.commit()

        logger.info(f"Rolled back import job {job_id}: {total_deleted} entities deleted")

        return {
            "success": True,
            "job_id": job_id,
            "deleted_counts": deleted_counts,
            "total_deleted": total_deleted,
        }

    async def get_rollback_status(self, job_id: str) -> dict:
        """Get rollback status and information for a job."""
        result = await self.db.execute(
            select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return {"success": False, "error": "Job not found"}

        can_rollback = await self.can_rollback(job_id)
        preview = await self.preview_rollback(job_id)

        return {
            "success": True,
            "job_id": job_id,
            "status": job.status,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "can_rollback": can_rollback.get("can_rollback", False),
            "rollback_expires_at": can_rollback.get("expires_at"),
            "reason": can_rollback.get("reason"),
            "preview": preview.get("counts", {}),
            "total_to_delete": preview.get("total", 0),
        }
