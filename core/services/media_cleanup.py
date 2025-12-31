"""Media Cleanup Service - Unused media detection and cleanup.

Detects media files that are no longer referenced by any entity.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityValue
from ..utils import utcnow


@dataclass
class UnusedMedia:
    """Unused media file info."""

    id: str
    filename: str
    path: str
    size: int
    created_at: datetime
    last_reference_check: datetime


@dataclass
class MediaCleanupReport:
    """Cleanup operation report."""

    total_checked: int
    unused_count: int
    unused_size_bytes: int
    deleted_count: int
    deleted_size_bytes: int
    errors: list[str]


class MediaCleanupService:
    """
    Service for detecting and cleaning up unused media.

    Usage:
        cleanup = MediaCleanupService(db)

        # Find unused media
        unused = await cleanup.find_unused_media()

        # Preview what would be deleted
        report = await cleanup.preview_cleanup()

        # Actually delete unused media
        report = await cleanup.cleanup(dry_run=False)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._upload_dir = Path("uploads")

    async def find_unused_media(
        self,
        older_than_days: int = 30,
    ) -> list[UnusedMedia]:
        """
        Find media files that are not referenced by any entity.

        Args:
            older_than_days: Only consider media older than this many days

        Returns:
            List of unused media files
        """
        cutoff_date = utcnow() - timedelta(days=older_than_days)

        # Get all media entities
        media_query = select(Entity).where(
            and_(
                Entity.type == "media",
                Entity.deleted_at.is_(None),
                Entity.created_at < cutoff_date,
            )
        )
        result = await self.db.execute(media_query)
        all_media = result.scalars().all()

        # Get all referenced media IDs
        referenced_ids = await self._get_referenced_media_ids()

        # Find unreferenced media
        unused = []
        for media in all_media:
            if media.id not in referenced_ids:
                # Get file info
                file_info = await self._get_media_file_info(media.id)
                if file_info:
                    unused.append(
                        UnusedMedia(
                            id=media.id,
                            filename=file_info.get("filename", ""),
                            path=file_info.get("path", ""),
                            size=file_info.get("size", 0),
                            created_at=media.created_at,
                            last_reference_check=utcnow(),
                        )
                    )

        return unused

    async def _get_referenced_media_ids(self) -> set[str]:
        """Get all media IDs that are referenced by other entities."""
        referenced = set()

        # Check entity values for media references
        # Media fields store media IDs as values
        media_value_query = select(EntityValue.value_text).where(
            and_(
                EntityValue.field_name.in_(["featured_image", "image", "media", "attachment"]),
                EntityValue.value_text.isnot(None),
            )
        )
        result = await self.db.execute(media_value_query)
        for row in result.scalars().all():
            if row:
                referenced.add(row)

        # Check JSON fields for media references
        json_value_query = select(EntityValue.value_json).where(
            and_(
                EntityValue.field_name.in_(["content", "gallery", "images"]),
                EntityValue.value_json.isnot(None),
            )
        )
        result = await self.db.execute(json_value_query)
        for row in result.scalars().all():
            if row:
                # Extract media IDs from JSON content
                extracted = self._extract_media_ids_from_json(row)
                referenced.update(extracted)

        return referenced

    def _extract_media_ids_from_json(self, data: dict) -> set[str]:
        """Extract media IDs from JSON data (like Editor.js blocks)."""
        media_ids = set()

        if isinstance(data, dict):
            # Check for image blocks
            if data.get("type") == "image" and "data" in data:
                file_info = data["data"].get("file", {})
                if "media_id" in file_info:
                    media_ids.add(file_info["media_id"])
                # Check URL pattern for media ID
                url = file_info.get("url", "")
                if "/media/" in url:
                    parts = url.split("/media/")
                    if len(parts) > 1:
                        media_id = parts[1].split("/")[0]
                        media_ids.add(media_id)

            # Recurse into nested structures
            for value in data.values():
                if isinstance(value, (dict, list)):
                    media_ids.update(self._extract_media_ids_from_json(value))

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    media_ids.update(self._extract_media_ids_from_json(item))

        return media_ids

    async def _get_media_file_info(self, media_id: str) -> dict | None:
        """Get file info for a media entity."""
        query = select(EntityValue).where(EntityValue.entity_id == media_id)
        result = await self.db.execute(query)
        values = result.scalars().all()

        info = {"id": media_id}
        for value in values:
            if value.field_name == "filename":
                info["filename"] = value.value_text
            elif value.field_name == "path":
                info["path"] = value.value_text
            elif value.field_name == "size":
                info["size"] = int(value.value_text or 0)

        return info if "path" in info else None

    async def preview_cleanup(
        self,
        older_than_days: int = 30,
    ) -> MediaCleanupReport:
        """
        Preview what would be cleaned up (dry run).

        Returns:
            Report of what would be deleted
        """
        unused = await self.find_unused_media(older_than_days)

        total_size = sum(m.size for m in unused)

        return MediaCleanupReport(
            total_checked=await self._count_all_media(),
            unused_count=len(unused),
            unused_size_bytes=total_size,
            deleted_count=0,
            deleted_size_bytes=0,
            errors=[],
        )

    async def cleanup(
        self,
        older_than_days: int = 30,
        dry_run: bool = True,
    ) -> MediaCleanupReport:
        """
        Clean up unused media files.

        Args:
            older_than_days: Only delete media older than this
            dry_run: If True, only report what would be deleted

        Returns:
            Cleanup report
        """
        unused = await self.find_unused_media(older_than_days)

        if dry_run:
            return await self.preview_cleanup(older_than_days)

        errors = []
        deleted_count = 0
        deleted_size = 0

        for media in unused:
            try:
                # Delete file from filesystem
                file_path = self._upload_dir / media.path
                if file_path.exists():
                    file_path.unlink()

                # Soft delete the entity
                entity = await self.db.get(Entity, media.id)
                if entity:
                    entity.deleted_at = utcnow()

                deleted_count += 1
                deleted_size += media.size

            except Exception as e:
                errors.append(f"{media.filename}: {str(e)}")

        await self.db.commit()

        return MediaCleanupReport(
            total_checked=await self._count_all_media(),
            unused_count=len(unused),
            unused_size_bytes=sum(m.size for m in unused),
            deleted_count=deleted_count,
            deleted_size_bytes=deleted_size,
            errors=errors,
        )

    async def _count_all_media(self) -> int:
        """Count all non-deleted media entities."""
        query = select(func.count(Entity.id)).where(
            and_(
                Entity.type == "media",
                Entity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_orphan_files(self) -> list[str]:
        """
        Find files in uploads directory that have no corresponding entity.

        Returns:
            List of orphan file paths
        """
        orphans = []

        if not self._upload_dir.exists():
            return orphans

        # Get all file paths from DB
        query = select(EntityValue.value_text).where(
            and_(
                EntityValue.field_name == "path",
                EntityValue.value_text.isnot(None),
            )
        )
        result = await self.db.execute(query)
        known_paths = {row for row in result.scalars().all() if row}

        # Walk uploads directory
        for root, _dirs, files in os.walk(self._upload_dir):
            for filename in files:
                file_path = Path(root) / filename
                relative_path = str(file_path.relative_to(self._upload_dir))

                if relative_path not in known_paths:
                    orphans.append(str(file_path))

        return orphans

    async def delete_orphan_files(self, dry_run: bool = True) -> dict:
        """
        Delete orphan files (files with no entity).

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            Report with deleted files and errors
        """
        orphans = await self.get_orphan_files()

        if dry_run:
            return {
                "orphan_count": len(orphans),
                "orphan_files": orphans,
                "deleted_count": 0,
                "errors": [],
            }

        errors = []
        deleted = 0

        for file_path in orphans:
            try:
                Path(file_path).unlink()
                deleted += 1
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")

        return {
            "orphan_count": len(orphans),
            "orphan_files": orphans,
            "deleted_count": deleted,
            "errors": errors,
        }


def get_media_cleanup_service(db: AsyncSession) -> MediaCleanupService:
    return MediaCleanupService(db)
