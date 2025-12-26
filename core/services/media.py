"""MediaService - file upload and image processing."""

from datetime import datetime
from pathlib import Path
from typing import Optional, BinaryIO
import hashlib
import mimetypes

from PIL import Image
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Media
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
        - Named with SHA256 hash
        - Stored in date-based folders
        """
        # Read file content
        content = file.read()
        file.seek(0)

        # Determine content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        # Generate hash-based filename
        file_hash = hashlib.sha256(content).hexdigest()[:16]

        # Determine storage path (date-based)
        date_path = datetime.utcnow().strftime("%Y/%m/%d")
        storage_dir = self.upload_dir / date_path
        storage_dir.mkdir(parents=True, exist_ok=True)

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

            # Convert to WebP
            stored_filename = f"{file_hash}.webp"
            stored_path = storage_dir / stored_filename
            img.save(stored_path, "WEBP", quality=self.WEBP_QUALITY)
            content_type = "image/webp"

            # Get actual file size after processing
            size = stored_path.stat().st_size
        else:
            # Non-image file - store as-is
            ext = Path(filename).suffix.lower()
            stored_filename = f"{file_hash}{ext}"
            stored_path = storage_dir / stored_filename

            with open(stored_path, "wb") as f:
                f.write(content)

            size = len(content)

        # Store relative path from uploads directory
        relative_path = f"{date_path}/{stored_filename}"

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
            created_by=user_id,
        )
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)

        return media

    async def get(self, media_id: str, include_deleted: bool = False) -> Optional[Media]:
        """Get media by ID."""
        query = select(Media).where(Media.id == media_id)
        if not include_deleted:
            query = query.where(Media.deleted_at.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_path(self, stored_path: str, include_deleted: bool = False) -> Optional[Media]:
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

    async def delete(self, media_id: str, user_id: str = None) -> bool:
        """
        論理削除（Soft Delete）。

        物理ファイルは削除せず、deleted_atを設定して非表示にする。
        物理ファイル削除が必要な場合は purge() を使用。
        """
        media = await self.get(media_id)
        if not media:
            return False

        media.deleted_at = datetime.utcnow()
        if user_id:
            media.updated_by = user_id
        await self.db.commit()

        return True

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

    async def restore(self, media_id: str, user_id: str = None) -> Optional[Media]:
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

    async def update_alt_text(self, media_id: str, alt_text: str) -> Optional[Media]:
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
