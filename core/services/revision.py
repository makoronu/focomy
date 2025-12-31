"""RevisionService - version history management."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Revision
from ..utils import utcnow


class RevisionService:
    """
    Version history service.

    Features:
    - Create revisions (autosave, manual, publish)
    - List revisions for an entity
    - Restore from revision
    - Cleanup old autosaves
    """

    # Keep autosaves for 24 hours, then only keep one per hour
    AUTOSAVE_CLEANUP_HOURS = 24
    MAX_REVISIONS_PER_ENTITY = 50

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        entity_id: str,
        data: dict,
        revision_type: str = "manual",
        title: str = None,
        user_id: str = None,
    ) -> Revision:
        """Create a new revision."""
        revision = Revision(
            entity_id=entity_id,
            revision_type=revision_type,
            data=data,
            title=title,
            created_by=user_id,
        )
        self.db.add(revision)
        await self.db.commit()
        await self.db.refresh(revision)
        return revision

    async def get(self, revision_id: str) -> Revision | None:
        """Get a revision by ID."""
        query = select(Revision).where(Revision.id == revision_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_for_entity(
        self,
        entity_id: str,
        limit: int = 20,
        offset: int = 0,
        include_autosaves: bool = False,
    ) -> list[Revision]:
        """List revisions for an entity."""
        query = select(Revision).where(Revision.entity_id == entity_id)

        if not include_autosaves:
            query = query.where(Revision.revision_type != "autosave")

        query = query.order_by(Revision.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_for_entity(
        self,
        entity_id: str,
        include_autosaves: bool = False,
    ) -> int:
        """Count revisions for an entity."""
        query = select(func.count()).select_from(Revision).where(Revision.entity_id == entity_id)

        if not include_autosaves:
            query = query.where(Revision.revision_type != "autosave")

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_latest(
        self,
        entity_id: str,
        revision_type: str = None,
    ) -> Revision | None:
        """Get the latest revision for an entity."""
        query = select(Revision).where(Revision.entity_id == entity_id)

        if revision_type:
            query = query.where(Revision.revision_type == revision_type)

        query = query.order_by(Revision.created_at.desc()).limit(1)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def cleanup_autosaves(self, entity_id: str) -> int:
        """
        Cleanup old autosaves.

        Keeps:
        - All autosaves from last 24 hours
        - One autosave per hour for older ones
        - Maximum MAX_REVISIONS_PER_ENTITY total
        """
        cutoff = utcnow() - timedelta(hours=self.AUTOSAVE_CLEANUP_HOURS)

        # Get all autosaves older than cutoff
        query = (
            select(Revision)
            .where(
                and_(
                    Revision.entity_id == entity_id,
                    Revision.revision_type == "autosave",
                    Revision.created_at < cutoff,
                )
            )
            .order_by(Revision.created_at.desc())
        )

        result = await self.db.execute(query)
        old_autosaves = list(result.scalars().all())

        if not old_autosaves:
            return 0

        # Keep one per hour
        to_delete = []
        kept_hours = set()

        for rev in old_autosaves:
            hour_key = rev.created_at.strftime("%Y-%m-%d-%H")
            if hour_key in kept_hours:
                to_delete.append(rev)
            else:
                kept_hours.add(hour_key)

        for rev in to_delete:
            await self.db.delete(rev)

        await self.db.commit()
        return len(to_delete)

    async def delete(self, revision_id: str) -> bool:
        """Delete a revision."""
        revision = await self.get(revision_id)
        if not revision:
            return False

        await self.db.delete(revision)
        await self.db.commit()
        return True

    def serialize(self, revision: Revision) -> dict:
        """Serialize revision to dict."""
        return {
            "id": revision.id,
            "entity_id": revision.entity_id,
            "revision_type": revision.revision_type,
            "title": revision.title,
            "data": revision.data,
            "created_at": revision.created_at.isoformat() if revision.created_at else None,
            "created_by": revision.created_by,
        }
