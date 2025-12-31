"""MediaService - file upload and image processing."""

import hashlib
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Media
from ..utils import utcnow
from .assets import get_upload_url, s3_client


class MediaService:
    """
    Media management service.

    Handles file uploads, image processing, and media metadata.
    """

    MAX_DIMENSION = 1920
    WEBP_QUALITY = 85

    def __init__(self, db: AsyncSession):
        self.db = db
        self.upload_dir = settings.base_dir / "uploads"
        self.upload_dir.mkdir(exist_ok=True)

    def _get_next_sequence(self) -> int:
        """Get next sequence number from existing files in upload directory."""
        max_seq = 0
        for f in self.upload_dir.iterdir():
            if f.is_file():
                match = re.match(r"(\d+)_", f.name)
                if match:
                    max_seq = max(max_seq, int(match.group(1)))
        return max_seq + 1

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        stem = Path(filename).stem
        # Replace non-word characters with underscore
        stem = re.sub(r"[^\w\-]", "_", stem)
        # Collapse multiple underscores
        stem = re.sub(r"_+", "_", stem).strip("_")
        # Ensure not empty
        if not stem:
            stem = "file"
        return stem

    def _generate_filename(self, original: str, sequence: int, ext: str) -> str:
        """Generate sequential filename."""
        stem = self._sanitize_filename(original)
        return f"{sequence:03d}_{stem}{ext}"

    async def upload(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str = None,
        user_id: str = None,
    ) -> Media:
        """
        Upload a file.

        Images are automatically:
        - Converted to WebP
        - Resized to max 1920px on longest side
        - Named with sequential number + original name
        - Stored in flat uploads/ directory
        """
        # Read file content
        content = file.read()
        file.seek(0)

        # Determine content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        # Generate hash for duplicate detection
        file_hash = hashlib.sha256(content).hexdigest()

        # Get next sequence number
        sequence = self._get_next_sequence()

        # Process images
        is_image = content_type.startswith("image/")
        width, height = None, None

        if is_image:
            # Process and convert image
            img = Image.open(file)
            width, height = img.size

            # Resize if needed
            if max(width, height) > self.MAX_DIMENSION:
                img = self._resize_image(img)
                width, height = img.size

            # Generate filename with .webp extension
            stored_filename = self._generate_filename(filename, sequence, ".webp")
            stored_path = self.upload_dir / stored_filename

            # Handle collision
            while stored_path.exists():
                sequence += 1
                stored_filename = self._generate_filename(filename, sequence, ".webp")
                stored_path = self.upload_dir / stored_filename

            img.save(stored_path, "WEBP", quality=self.WEBP_QUALITY)
            content_type = "image/webp"

            # Get actual file size after processing
            size = stored_path.stat().st_size
        else:
            # Non-image file - store as-is
            ext = Path(filename).suffix.lower()
            stored_filename = self._generate_filename(filename, sequence, ext)
            stored_path = self.upload_dir / stored_filename

            # Handle collision
            while stored_path.exists():
                sequence += 1
                stored_filename = self._generate_filename(filename, sequence, ext)
                stored_path = self.upload_dir / stored_filename

            with open(stored_path, "wb") as f:
                f.write(content)

            size = len(content)

        # Store just filename (flat structure)
        relative_path = stored_filename

        # Upload to S3 if configured
        cdn_config = settings.media.cdn
        if cdn_config.enabled and cdn_config.upload_to_s3:
            try:
                s3_key = f"uploads/{relative_path}"
                s3_client.upload_file(stored_path, s3_key, content_type)
            except Exception:
                # Log error but continue - local file is still saved
                pass

        # Create media record
        media = Media(
            filename=filename,
            stored_path=relative_path,
            mime_type=content_type,
            size=size,
            width=width,
            height=height,
            file_hash=file_hash,
            created_by=user_id,
        )
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)

        return media

    async def get(self, media_id: str, include_deleted: bool = False) -> Media | None:
        """Get media by ID."""
        query = select(Media).where(Media.id == media_id)
        if not include_deleted:
            query = query.where(Media.deleted_at.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_path(self, stored_path: str, include_deleted: bool = False) -> Media | None:
        """Get media by stored path."""
        query = select(Media).where(Media.stored_path == stored_path)
        if not include_deleted:
            query = query.where(Media.deleted_at.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def find(
        self,
        limit: int = 20,
        offset: int = 0,
        mime_type: str = None,
        search: str = None,
        include_deleted: bool = False,
    ) -> list[Media]:
        """Find media files."""
        query = select(Media).order_by(Media.created_at.desc())

        if not include_deleted:
            query = query.where(Media.deleted_at.is_(None))

        if mime_type:
            query = query.where(Media.mime_type.startswith(mime_type))

        if search:
            query = query.where(Media.filename.ilike(f"%{search}%"))

        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        mime_type: str = None,
        search: str = None,
        include_deleted: bool = False,
    ) -> int:
        """Count media files."""
        query = select(func.count()).select_from(Media)

        if not include_deleted:
            query = query.where(Media.deleted_at.is_(None))

        if mime_type:
            query = query.where(Media.mime_type.startswith(mime_type))

        if search:
            query = query.where(Media.filename.ilike(f"%{search}%"))

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def delete(
        self,
        media_id: str,
        user_id: str = None,
        force: bool = False,
    ) -> bool:
        """
        論理削除（Soft Delete）。

        物理ファイルは削除せず、deleted_atを設定して非表示にする。
        物理ファイル削除が必要な場合は purge() を使用。

        Args:
            media_id: Media to delete
            user_id: User performing the deletion
            force: If False, check for references and fail if in use.
                   If True, delete even if referenced (orphans references).

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If media is in use and force=False
        """
        media = await self.get(media_id)
        if not media:
            return False

        # Check for references unless forced
        if not force:
            references = await self.find_references(media_id)
            if references:
                ref_count = len(references)
                entity_types = list({r["entity_type"] for r in references})
                raise ValueError(
                    f"Cannot delete media: referenced by {ref_count} entities "
                    f"(types: {', '.join(entity_types)}). Use force=True to delete anyway."
                )

        media.deleted_at = utcnow()
        if user_id:
            media.updated_by = user_id
        await self.db.commit()

        return True

    async def find_references(self, media_id: str) -> list[dict]:
        """Find entities that reference this media.

        Checks:
        - EntityValues with value_text containing media ID or path
        - EntityValues with value_json containing media references

        Returns:
            List of {entity_id, entity_type, field_name} dicts
        """
        from sqlalchemy import or_

        from ..models import Entity, EntityValue

        media = await self.get(media_id, include_deleted=True)
        if not media:
            return []

        # Build search patterns
        media_path = media.stored_path
        media_url = f"/uploads/{media_path}"

        # Search value_text for media ID or path
        query = (
            select(EntityValue.entity_id, EntityValue.field_name, Entity.type)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                Entity.deleted_at.is_(None),
                or_(
                    EntityValue.value_text == media_id,
                    EntityValue.value_text == media_path,
                    EntityValue.value_text.contains(media_url),
                ),
            )
        )
        result = await self.db.execute(query)
        rows = result.fetchall()

        references = [
            {
                "entity_id": row[0],
                "field_name": row[1],
                "entity_type": row[2],
            }
            for row in rows
        ]

        # Also check JSON fields (blocks containing media)
        # This is more expensive, so we only do basic check
        json_query = (
            select(EntityValue.entity_id, EntityValue.field_name, Entity.type)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                Entity.deleted_at.is_(None),
                EntityValue.value_json.isnot(None),
            )
        )
        json_result = await self.db.execute(json_query)
        json_rows = json_result.fetchall()

        for row in json_rows:
            entity_id, field_name, entity_type = row
            # Get the actual JSON value
            ev_query = select(EntityValue.value_json).where(
                EntityValue.entity_id == entity_id,
                EntityValue.field_name == field_name,
            )
            ev_result = await self.db.execute(ev_query)
            json_value = ev_result.scalar_one_or_none()

            if json_value and self._json_contains_media(json_value, media_id, media_url):
                references.append(
                    {
                        "entity_id": entity_id,
                        "field_name": field_name,
                        "entity_type": entity_type,
                    }
                )

        return references

    def _json_contains_media(self, json_value: any, media_id: str, media_url: str) -> bool:
        """Check if a JSON value contains a media reference."""
        import json

        # Convert to string for simple search
        if isinstance(json_value, (dict, list)):
            json_str = json.dumps(json_value)
        else:
            json_str = str(json_value)

        return media_id in json_str or media_url in json_str

    async def purge(self, media_id: str) -> bool:
        """
        物理削除（完全削除）。

        論理削除済みのファイルのみ物理削除可能。
        ファイルシステムとS3からも削除。
        """
        media = await self.get(media_id, include_deleted=True)
        if not media:
            return False

        # 論理削除されていない場合は拒否
        if media.deleted_at is None:
            return False

        # ファイルシステムから削除
        file_path = self.upload_dir / media.stored_path
        if file_path.exists():
            file_path.unlink()

        # S3から削除
        cdn_config = settings.media.cdn
        if cdn_config.enabled and cdn_config.upload_to_s3:
            try:
                s3_key = f"uploads/{media.stored_path}"
                s3_client.delete_file(s3_key)
            except Exception:
                pass

        # DBから物理削除
        await self.db.delete(media)
        await self.db.commit()

        return True

    async def restore(self, media_id: str, user_id: str = None) -> Media | None:
        """論理削除を取り消す（復元）。"""
        media = await self.get(media_id, include_deleted=True)
        if not media or media.deleted_at is None:
            return None

        media.deleted_at = None
        if user_id:
            media.updated_by = user_id
        await self.db.commit()
        await self.db.refresh(media)

        return media

    async def update_alt_text(self, media_id: str, alt_text: str) -> Media | None:
        """Update alt text for media."""
        media = await self.get(media_id)
        if not media:
            return None

        media.alt_text = alt_text
        await self.db.commit()
        await self.db.refresh(media)

        return media

    def get_url(self, media: Media) -> str:
        """Get public URL for media (uses CDN if configured)."""
        return get_upload_url(media.stored_path)

    def get_absolute_path(self, media: Media) -> Path:
        """Get absolute filesystem path for media."""
        return self.upload_dir / media.stored_path

    def _resize_image(self, img: Image.Image) -> Image.Image:
        """Resize image to fit within MAX_DIMENSION."""
        width, height = img.size

        if width >= height:
            # Landscape
            new_width = self.MAX_DIMENSION
            new_height = int(height * (self.MAX_DIMENSION / width))
        else:
            # Portrait
            new_height = self.MAX_DIMENSION
            new_width = int(width * (self.MAX_DIMENSION / height))

        return img.resize((new_width, new_height), Image.LANCZOS)

    def serialize(self, media: Media) -> dict:
        """Serialize media to dict."""
        return {
            "id": media.id,
            "filename": media.filename,
            "url": self.get_url(media),
            "mime_type": media.mime_type,
            "size": media.size,
            "width": media.width,
            "height": media.height,
            "alt_text": media.alt_text,
            "created_at": media.created_at.isoformat() if media.created_at else None,
            "created_by": media.created_by,
            "updated_at": media.updated_at.isoformat() if media.updated_at else None,
            "updated_by": media.updated_by,
            "deleted_at": media.deleted_at.isoformat() if media.deleted_at else None,
        }
