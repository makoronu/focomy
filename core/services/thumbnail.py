"""Thumbnail Service - Generate image thumbnails at upload time.

Creates multiple size variants of uploaded images for responsive use.
"""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image


@dataclass
class ThumbnailSize:
    """Thumbnail size configuration."""

    name: str
    width: int
    height: int
    suffix: str = ""
    crop: bool = False

    def __post_init__(self):
        if not self.suffix:
            self.suffix = f"_{self.name}"


# Default thumbnail sizes
DEFAULT_SIZES = [
    ThumbnailSize("thumb", 150, 150, crop=True),
    ThumbnailSize("small", 320, 240),
    ThumbnailSize("medium", 640, 480),
    ThumbnailSize("large", 1280, 960),
]


@dataclass
class GeneratedThumbnail:
    """Generated thumbnail info."""

    name: str
    width: int
    height: int
    path: str
    size: int


class ThumbnailService:
    """
    Service for generating image thumbnails.

    Usage:
        thumb_svc = ThumbnailService()
        thumbnails = await thumb_svc.generate(
            image_data,
            base_path="uploads/2025/01/image.jpg",
            sizes=[ThumbnailSize("thumb", 150, 150, crop=True)],
        )
    """

    def __init__(
        self,
        quality: int = 85,
        format: str = "webp",
        sizes: list[ThumbnailSize] = None,
    ):
        self.quality = quality
        self.format = format.lower()
        self.sizes = sizes or DEFAULT_SIZES

    async def generate(
        self,
        image_data: BinaryIO,
        base_path: str,
        sizes: list[ThumbnailSize] = None,
    ) -> list[GeneratedThumbnail]:
        """
        Generate thumbnails for an image.

        Args:
            image_data: Original image data
            base_path: Base path for generated files (e.g., "uploads/2025/01/image.jpg")
            sizes: List of sizes to generate (uses default if not provided)

        Returns:
            List of generated thumbnail info
        """
        sizes = sizes or self.sizes
        thumbnails = []

        # Parse base path
        path = Path(base_path)
        stem = path.stem
        parent = path.parent

        # Open original image
        try:
            original = Image.open(image_data)
        except Exception:
            return []

        # Convert to RGB if needed (for formats that don't support alpha)
        if original.mode in ("RGBA", "P") and self.format in ("jpg", "jpeg"):
            original = original.convert("RGB")
        elif original.mode not in ("RGB", "RGBA", "L"):
            original = original.convert("RGB")

        for size in sizes:
            try:
                thumb = self._create_thumbnail(original, size)
                if thumb:
                    # Generate output path
                    thumb_name = f"{stem}{size.suffix}.{self.format}"
                    thumb_path = parent / thumb_name

                    # Save to bytes
                    output = io.BytesIO()
                    save_kwargs = {"quality": self.quality}
                    if self.format == "webp":
                        save_kwargs["method"] = 6  # Slower but better compression
                    thumb.save(output, format=self.format.upper(), **save_kwargs)

                    thumbnails.append(
                        GeneratedThumbnail(
                            name=size.name,
                            width=thumb.width,
                            height=thumb.height,
                            path=str(thumb_path),
                            size=output.tell(),
                        )
                    )

                    # Store the bytes for saving
                    output.seek(0)
                    thumb._thumbnail_data = output.read()

            except Exception:
                continue

        return thumbnails

    def _create_thumbnail(
        self,
        image: Image.Image,
        size: ThumbnailSize,
    ) -> Image.Image | None:
        """Create a single thumbnail."""
        orig_width, orig_height = image.size

        # Skip if original is smaller
        if orig_width <= size.width and orig_height <= size.height:
            return None

        if size.crop:
            # Crop to exact size (center crop)
            return self._crop_thumbnail(image, size.width, size.height)
        else:
            # Fit within bounds (maintain aspect ratio)
            return self._fit_thumbnail(image, size.width, size.height)

    def _fit_thumbnail(
        self,
        image: Image.Image,
        max_width: int,
        max_height: int,
    ) -> Image.Image:
        """Resize to fit within bounds maintaining aspect ratio."""
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        return image.copy()

    def _crop_thumbnail(
        self,
        image: Image.Image,
        width: int,
        height: int,
    ) -> Image.Image:
        """Crop to exact size from center."""
        # Calculate aspect ratios
        img_ratio = image.width / image.height
        target_ratio = width / height

        if img_ratio > target_ratio:
            # Image is wider - crop sides
            new_width = int(image.height * target_ratio)
            left = (image.width - new_width) // 2
            crop_box = (left, 0, left + new_width, image.height)
        else:
            # Image is taller - crop top/bottom
            new_height = int(image.width / target_ratio)
            top = (image.height - new_height) // 2
            crop_box = (0, top, image.width, top + new_height)

        cropped = image.crop(crop_box)
        return cropped.resize((width, height), Image.Resampling.LANCZOS)

    def get_srcset(
        self,
        base_url: str,
        thumbnails: list[GeneratedThumbnail],
    ) -> str:
        """
        Generate srcset attribute for responsive images.

        Args:
            base_url: Base URL for the image directory
            thumbnails: List of generated thumbnails

        Returns:
            srcset string for use in <img> tag
        """
        base_url = base_url.rstrip("/")
        parts = []
        for thumb in sorted(thumbnails, key=lambda t: t.width):
            parts.append(f"{base_url}/{Path(thumb.path).name} {thumb.width}w")
        return ", ".join(parts)

    def get_sizes(self, thumbnails: list[GeneratedThumbnail]) -> dict:
        """Get thumbnail sizes as a dictionary."""
        return {
            thumb.name: {
                "width": thumb.width,
                "height": thumb.height,
                "path": thumb.path,
            }
            for thumb in thumbnails
        }


# Global thumbnail service instance
thumbnail_service = ThumbnailService()
