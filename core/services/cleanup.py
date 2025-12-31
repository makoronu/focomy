"""Cleanup Service - Remove orphaned data.

Handles cleanup of:
- EntityValues for deleted/non-existent fields
- Relations pointing to deleted entities
- Expired sessions
- Old audit logs
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityValue, Media, Relation, Session
from ..utils import utcnow


class CleanupService:
    """
    Service for cleaning up orphaned and expired data.

    Usage:
        cleanup = CleanupService(db)

        # Run all cleanup tasks
        results = await cleanup.run_all()

        # Run specific cleanup
        count = await cleanup.orphaned_values()
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_all(self) -> dict[str, int]:
        """Run all cleanup tasks and return results."""
        return {
            "orphaned_values": await self.orphaned_values(),
            "orphaned_relations": await self.orphaned_relations(),
            "expired_sessions": await self.expired_sessions(),
            "soft_deleted_old": await self.permanent_delete_old(days=90),
        }

    async def orphaned_values(self) -> int:
        """
        Clean up EntityValues that belong to deleted entities.

        Returns count of deleted records.
        """
        # Find EntityValues where the parent Entity is deleted or doesn't exist
        orphaned_query = select(EntityValue.id).where(
            ~EntityValue.entity_id.in_(select(Entity.id).where(Entity.deleted_at.is_(None)))
        )

        result = await self.db.execute(orphaned_query)
        orphaned_ids = [row[0] for row in result]

        if not orphaned_ids:
            return 0

        # Delete in batches
        batch_size = 1000
        total = 0
        for i in range(0, len(orphaned_ids), batch_size):
            batch = orphaned_ids[i : i + batch_size]
            await self.db.execute(delete(EntityValue).where(EntityValue.id.in_(batch)))
            total += len(batch)

        await self.db.commit()
        return total

    async def orphaned_relations(self) -> int:
        """
        Clean up Relations pointing to deleted entities.

        Returns count of deleted records.
        """
        valid_entity_ids = select(Entity.id).where(Entity.deleted_at.is_(None))

        # Find relations where from_entity or to_entity is deleted
        orphaned_query = select(Relation).where(
            ~and_(
                Relation.from_entity_id.in_(valid_entity_ids),
                Relation.to_entity_id.in_(valid_entity_ids),
            )
        )

        result = await self.db.execute(orphaned_query)
        orphaned = result.scalars().all()

        for relation in orphaned:
            await self.db.delete(relation)

        await self.db.commit()
        return len(orphaned)

    async def expired_sessions(self) -> int:
        """
        Clean up expired sessions.

        Returns count of deleted records.
        """
        result = await self.db.execute(
            delete(Session).where(Session.expires_at < utcnow())
        )
        await self.db.commit()
        return result.rowcount

    async def permanent_delete_old(self, days: int = 90) -> int:
        """
        Permanently delete entities soft-deleted more than X days ago.

        Args:
            days: Delete entities older than this many days

        Returns count of deleted records.
        """
        cutoff = utcnow() - timedelta(days=days)

        # First delete related EntityValues
        old_entity_ids = select(Entity.id).where(
            and_(
                Entity.deleted_at.isnot(None),
                Entity.deleted_at < cutoff,
            )
        )

        await self.db.execute(delete(EntityValue).where(EntityValue.entity_id.in_(old_entity_ids)))

        # Then delete the entities
        result = await self.db.execute(
            delete(Entity).where(
                and_(
                    Entity.deleted_at.isnot(None),
                    Entity.deleted_at < cutoff,
                )
            )
        )
        await self.db.commit()
        return result.rowcount

    async def unused_media(self, days_old: int = 30) -> list[dict]:
        """
        Find media files not referenced by any entity.

        Args:
            days_old: Only include media older than this many days

        Returns list of unused media info (doesn't delete, just reports).
        """
        cutoff = utcnow() - timedelta(days=days_old)

        # Get all media older than cutoff
        media_query = select(Media).where(Media.created_at < cutoff)
        result = await self.db.execute(media_query)
        all_media = result.scalars().all()

        unused = []
        for media in all_media:
            # Check if media is referenced in any EntityValue
            ref_query = (
                select(EntityValue).where(EntityValue.value_text.contains(media.id)).limit(1)
            )
            ref_result = await self.db.execute(ref_query)

            if not ref_result.scalar_one_or_none():
                unused.append(
                    {
                        "id": media.id,
                        "filename": media.filename,
                        "size": media.size,
                        "created_at": media.created_at.isoformat(),
                    }
                )

        return unused

    async def cleanup_field_values(
        self,
        entity_type: str,
        field_name: str,
    ) -> int:
        """
        Clean up values for a deleted field.

        Use when a field is removed from a content type definition.

        Args:
            entity_type: The content type
            field_name: The field that was deleted

        Returns count of deleted records.
        """
        # Get entity IDs of this type
        entity_ids = select(Entity.id).where(Entity.type == entity_type)

        # Delete values for this field
        result = await self.db.execute(
            delete(EntityValue).where(
                and_(
                    EntityValue.entity_id.in_(entity_ids),
                    EntityValue.field_name == field_name,
                )
            )
        )
        await self.db.commit()
        return result.rowcount

    async def vacuum_database(self) -> None:
        """
        Run PostgreSQL VACUUM to reclaim space.

        Note: This commits any pending transaction.
        """
        await self.db.execute(text("VACUUM ANALYZE"))
        await self.db.commit()


def get_cleanup_service(db: AsyncSession) -> CleanupService:
    return CleanupService(db)
