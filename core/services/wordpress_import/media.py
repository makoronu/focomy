"""Media Importer - Downloads and processes WordPress media files."""

import asyncio
import hashlib
import io
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from PIL import Image


@dataclass
class MediaItem:
    """Represents a media item to import."""
    original_url: str
    filename: str
    post_id: int = 0
    title: str = ""
    alt_text: str = ""
    caption: str = ""
    description: str = ""
    mime_type: str = ""
    width: int = 0
    height: int = 0
    file_size: int = 0


@dataclass
class ImportedMedia:
    """Result of importing a media item."""
    original_url: str
    new_url: str
    new_path: str
    filename: str
    mime_type: str
    width: int = 0
    height: int = 0
    file_size: int = 0
    success: bool = True
    error: str = ""


@dataclass
class MediaImportResult:
    """Complete result of media import."""
    imported: list[ImportedMedia] = field(default_factory=list)
    failed: list[ImportedMedia] = field(default_factory=list)
    url_mapping: dict[str, str] = field(default_factory=dict)
    total_size: int = 0


class MediaImporter:
    """
    Downloads and processes WordPress media files.

    Features:
    - Async batch downloading
    - Image optimization
    - URL rewriting in content
    - Duplicate detection
    - Progress reporting
    """

    def __init__(
        self,
        upload_dir: Path,
        base_url: str,
        max_concurrent: int = 5,
        timeout: int = 30,
        max_image_size: int = 2048,
        jpeg_quality: int = 85,
    ):
        """
        Initialize MediaImporter.

        Args:
            upload_dir: Directory to save uploaded files
            base_url: Base URL for the new site
            max_concurrent: Maximum concurrent downloads
            timeout: Request timeout in seconds
            max_image_size: Maximum image dimension (width/height)
            jpeg_quality: JPEG compression quality (1-100)
        """
        self.upload_dir = Path(upload_dir)
        self.base_url = base_url.rstrip("/")
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.max_image_size = max_image_size
        self.jpeg_quality = jpeg_quality

        # Create upload directory
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        # Track imported files to avoid duplicates
        self._imported_hashes: dict[str, str] = {}

        # Semaphore for concurrent downloads
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def import_media(
        self,
        items: list[MediaItem],
        progress_callback: callable | None = None,
    ) -> MediaImportResult:
        """
        Import multiple media items.

        Args:
            items: List of media items to import
            progress_callback: Optional callback(current, total, item)

        Returns:
            MediaImportResult with all imported items and URL mapping
        """
        result = MediaImportResult()
        total = len(items)

        async with aiohttp.ClientSession() as session:
            tasks = []
            for i, item in enumerate(items):
                task = self._import_single(session, item, i, total, progress_callback)
                tasks.append(task)

            imported_items = await asyncio.gather(*tasks, return_exceptions=True)

            for item, imported in zip(items, imported_items, strict=False):
                if isinstance(imported, Exception):
                    failed = ImportedMedia(
                        original_url=item.original_url,
                        new_url="",
                        new_path="",
                        filename=item.filename,
                        mime_type=item.mime_type,
                        success=False,
                        error=str(imported),
                    )
                    result.failed.append(failed)
                elif imported.success:
                    result.imported.append(imported)
                    result.url_mapping[item.original_url] = imported.new_url
                    result.total_size += imported.file_size
                else:
                    result.failed.append(imported)

        return result

    async def _import_single(
        self,
        session: aiohttp.ClientSession,
        item: MediaItem,
        index: int,
        total: int,
        progress_callback: callable | None,
    ) -> ImportedMedia:
        """Import a single media item."""
        async with self._semaphore:
            try:
                # Download file
                data = await self._download(session, item.original_url)

                if not data:
                    return ImportedMedia(
                        original_url=item.original_url,
                        new_url="",
                        new_path="",
                        filename=item.filename,
                        mime_type=item.mime_type,
                        success=False,
                        error="Failed to download",
                    )

                # Check for duplicates
                file_hash = hashlib.md5(data).hexdigest()
                if file_hash in self._imported_hashes:
                    existing_path = self._imported_hashes[file_hash]
                    return ImportedMedia(
                        original_url=item.original_url,
                        new_url=self._path_to_url(existing_path),
                        new_path=existing_path,
                        filename=item.filename,
                        mime_type=item.mime_type,
                        file_size=len(data),
                        success=True,
                    )

                # Process image if applicable
                width, height = 0, 0
                if self._is_image(item.mime_type or item.filename):
                    data, width, height = self._process_image(data, item.filename)

                # Generate unique filename
                filename = self._generate_filename(item.filename, file_hash)

                # Save file
                save_path = self._save_file(data, filename)

                # Track hash
                self._imported_hashes[file_hash] = save_path

                # Report progress
                if progress_callback:
                    progress_callback(index + 1, total, item)

                return ImportedMedia(
                    original_url=item.original_url,
                    new_url=self._path_to_url(save_path),
                    new_path=save_path,
                    filename=filename,
                    mime_type=item.mime_type or mimetypes.guess_type(filename)[0] or "",
                    width=width,
                    height=height,
                    file_size=len(data),
                    success=True,
                )

            except Exception as e:
                return ImportedMedia(
                    original_url=item.original_url,
                    new_url="",
                    new_path="",
                    filename=item.filename,
                    mime_type=item.mime_type,
                    success=False,
                    error=str(e),
                )

    async def _download(self, session: aiohttp.ClientSession, url: str) -> bytes | None:
        """Download a file from URL."""
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": "Focomy-MediaImporter/1.0"},
            ) as response:
                if response.status == 200:
                    return await response.read()
                return None
        except Exception:
            return None

    def _is_image(self, mime_or_filename: str) -> bool:
        """Check if file is an image."""
        if "/" in mime_or_filename:
            return mime_or_filename.startswith("image/")

        ext = Path(mime_or_filename).suffix.lower()
        return ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}

    def _process_image(self, data: bytes, filename: str) -> tuple[bytes, int, int]:
        """Process and optimize image."""
        try:
            img = Image.open(io.BytesIO(data))
            width, height = img.size

            # Resize if too large
            if width > self.max_image_size or height > self.max_image_size:
                img.thumbnail((self.max_image_size, self.max_image_size), Image.Resampling.LANCZOS)
                width, height = img.size

            # Convert and compress
            output = io.BytesIO()
            ext = Path(filename).suffix.lower()

            if ext in {".jpg", ".jpeg"}:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(output, format="JPEG", quality=self.jpeg_quality, optimize=True)
            elif ext == ".png":
                img.save(output, format="PNG", optimize=True)
            elif ext == ".webp":
                img.save(output, format="WEBP", quality=self.jpeg_quality)
            elif ext == ".gif":
                img.save(output, format="GIF")
            else:
                # Keep original format
                return data, width, height

            return output.getvalue(), width, height

        except Exception:
            # Return original if processing fails
            return data, 0, 0

    def _generate_filename(self, original_filename: str, file_hash: str) -> str:
        """Generate unique filename."""
        path = Path(original_filename)
        stem = path.stem
        suffix = path.suffix.lower()

        # Sanitize filename
        stem = re.sub(r"[^\w\-]", "_", stem)
        stem = re.sub(r"_+", "_", stem).strip("_")

        if not stem:
            stem = "file"

        # Add hash prefix for uniqueness
        short_hash = file_hash[:8]
        return f"{short_hash}_{stem}{suffix}"

    def _save_file(self, data: bytes, filename: str) -> str:
        """Save file to upload directory."""
        # Organize by year/month
        from datetime import datetime
        now = datetime.now()
        subdir = self.upload_dir / str(now.year) / f"{now.month:02d}"
        subdir.mkdir(parents=True, exist_ok=True)

        # Handle filename conflicts
        save_path = subdir / filename
        counter = 1
        while save_path.exists():
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            save_path = subdir / f"{stem}_{counter}{suffix}"
            counter += 1

        save_path.write_bytes(data)
        return str(save_path.relative_to(self.upload_dir))

    def _path_to_url(self, path: str) -> str:
        """Convert file path to URL."""
        return f"{self.base_url}/uploads/{path}"

    def rewrite_content_urls(
        self,
        content: str,
        url_mapping: dict[str, str],
        old_base_url: str,
    ) -> str:
        """
        Rewrite media URLs in content.

        Args:
            content: HTML content
            url_mapping: Mapping of old URLs to new URLs
            old_base_url: Old WordPress site base URL

        Returns:
            Content with rewritten URLs
        """
        if not content:
            return content

        # Replace exact matches
        for old_url, new_url in url_mapping.items():
            content = content.replace(old_url, new_url)

        # Replace relative URLs
        parsed_base = urlparse(old_base_url)
        old_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"

        # Find and replace wp-content/uploads URLs
        pattern = re.compile(
            rf'({re.escape(old_domain)})?/wp-content/uploads/([^"\'\s>]+)',
            re.IGNORECASE,
        )

        def replace_wp_content(match):
            full_path = match.group(2)
            # Check if we have this file
            for old_url, new_url in url_mapping.items():
                if full_path in old_url:
                    return new_url
            # Keep original if not found
            return match.group(0)

        content = pattern.sub(replace_wp_content, content)

        return content

    def extract_media_from_content(self, content: str, base_url: str) -> list[str]:
        """
        Extract media URLs from HTML content.

        Args:
            content: HTML content
            base_url: Base URL for resolving relative URLs

        Returns:
            List of media URLs found in content
        """
        if not content:
            return []

        urls = set()

        # Find img src
        img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
        for match in img_pattern.finditer(content):
            urls.add(match.group(1))

        # Find srcset
        srcset_pattern = re.compile(r'srcset=["\']([^"\']+)["\']', re.IGNORECASE)
        for match in srcset_pattern.finditer(content):
            for part in match.group(1).split(","):
                url = part.strip().split()[0]
                if url:
                    urls.add(url)

        # Find video/audio sources
        source_pattern = re.compile(r'<(?:video|audio|source)[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
        for match in source_pattern.finditer(content):
            urls.add(match.group(1))

        # Find href to media files
        href_pattern = re.compile(
            r'href=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp|pdf|doc|docx|xls|xlsx|zip|mp3|mp4|mov|avi))["\']',
            re.IGNORECASE,
        )
        for match in href_pattern.finditer(content):
            urls.add(match.group(1))

        # Resolve relative URLs
        resolved = []
        for url in urls:
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = urljoin(base_url, url)
            elif not url.startswith("http"):
                url = urljoin(base_url, url)
            resolved.append(url)

        return resolved
