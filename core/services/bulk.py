"""Bulk Operations Service - Batch entity operations.

Provides efficient bulk create, update, and delete operations.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService


@dataclass
class BulkResult:
    """Result of bulk operation."""

    success_count: int
    error_count: int
    errors: list[dict]


class BulkOperationService:
    """
    Service for bulk entity operations.

    Usage:
        bulk = BulkOperationService(db)

        # Bulk update
        result = await bulk.update_many(
            entity_ids=["id1", "id2", "id3"],
            data={"status": "published"},
            user_id="user123",
        )

        # Bulk delete
        result = await bulk.delete_many(
            entity_ids=["id1", "id2"],
            user_id="user123",
        )
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def update_many(
        self,
        entity_ids: list[str],
        data: dict[str, Any],
        user_id: str | None = None,
        validate: bool = True,
    ) -> BulkResult:
        """
        Update multiple entities with the same data.

        Args:
            entity_ids: List of entity IDs to update
            data: Fields to update (same for all entities)
            user_id: User performing the update
            validate: Whether to validate data against content type

        Returns:
            BulkResult with success/error counts
        """
        success_count = 0
        errors = []

        for entity_id in entity_ids:
            try:
                await self.entity_svc.update(
                    entity_id,
                    data,
                    user_id=user_id,
                    validate=validate,
                )
                success_count += 1
            except Exception as e:
                errors.append(
                    {
                        "entity_id": entity_id,
                        "error": str(e),
                    }
                )

        return BulkResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
        )

    async def delete_many(
        self,
        entity_ids: list[str],
        user_id: str | None = None,
        hard: bool = False,
    ) -> BulkResult:
        """
        Delete multiple entities.

        Args:
            entity_ids: List of entity IDs to delete
            user_id: User performing the delete
            hard: If True, permanently delete (not recommended)

        Returns:
            BulkResult with success/error counts
        """
        success_count = 0
        errors = []

        for entity_id in entity_ids:
            try:
                result = await self.entity_svc.delete(
                    entity_id,
                    user_id=user_id,
                    hard=hard,
                )
                if result:
                    success_count += 1
                else:
                    errors.append(
                        {
                            "entity_id": entity_id,
                            "error": "Entity not found",
                        }
                    )
            except Exception as e:
                errors.append(
                    {
                        "entity_id": entity_id,
                        "error": str(e),
                    }
                )

        return BulkResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
        )

    async def restore_many(
        self,
        entity_ids: list[str],
        user_id: str | None = None,
    ) -> BulkResult:
        """
        Restore multiple soft-deleted entities.

        Args:
            entity_ids: List of entity IDs to restore
            user_id: User performing the restore

        Returns:
            BulkResult with success/error counts
        """
        success_count = 0
        errors = []

        for entity_id in entity_ids:
            try:
                result = await self.entity_svc.restore(
                    entity_id,
                    user_id=user_id,
                )
                if result:
                    success_count += 1
                else:
                    errors.append(
                        {
                            "entity_id": entity_id,
                            "error": "Entity not found or not deleted",
                        }
                    )
            except Exception as e:
                errors.append(
                    {
                        "entity_id": entity_id,
                        "error": str(e),
                    }
                )

        return BulkResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
        )

    async def create_many(
        self,
        entity_type: str,
        items: list[dict[str, Any]],
        user_id: str | None = None,
    ) -> BulkResult:
        """
        Create multiple entities.

        Args:
            entity_type: Content type name
            items: List of entity data dicts
            user_id: User creating the entities

        Returns:
            BulkResult with success/error counts
        """
        success_count = 0
        errors = []

        for i, data in enumerate(items):
            try:
                await self.entity_svc.create(
                    entity_type,
                    data,
                    user_id=user_id,
                )
                success_count += 1
            except Exception as e:
                errors.append(
                    {
                        "index": i,
                        "data": data,
                        "error": str(e),
                    }
                )

        return BulkResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
        )

    async def update_status(
        self,
        entity_ids: list[str],
        status: str,
        user_id: str | None = None,
    ) -> BulkResult:
        """
        Update status for multiple entities.

        Convenience method for common bulk status change.

        Args:
            entity_ids: List of entity IDs
            status: New status value
            user_id: User performing the update

        Returns:
            BulkResult with success/error counts
        """
        return await self.update_many(
            entity_ids=entity_ids,
            data={"status": status},
            user_id=user_id,
        )

    async def assign_to(
        self,
        entity_ids: list[str],
        user_id: str,
        assigned_by: str | None = None,
    ) -> BulkResult:
        """
        Assign multiple entities to a user.

        Args:
            entity_ids: List of entity IDs
            user_id: User to assign to
            assigned_by: User performing the assignment

        Returns:
            BulkResult with success/error counts
        """
        return await self.update_many(
            entity_ids=entity_ids,
            data={"assigned_to": user_id},
            user_id=assigned_by,
        )


def get_bulk_service(db: AsyncSession) -> BulkOperationService:
    return BulkOperationService(db)
