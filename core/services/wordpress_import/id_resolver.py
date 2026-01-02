"""WordPress ID Resolver - Resolve WordPress IDs to Focomy entity IDs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..entity import EntityService
    from .media import MediaImportResult, MediaItem

logger = logging.getLogger(__name__)


class WpIdResolver:
    """Resolve WordPress IDs to Focomy entity IDs.

    This class provides caching and efficient lookup for:
    - WordPress user ID -> Focomy user entity ID
    - Category slug -> Focomy category entity ID
    - Tag slug -> Focomy tag entity ID
    - WordPress attachment ID -> New media URL
    - Default channel for imported posts
    """

    def __init__(self, entity_service: "EntityService"):
        """Initialize resolver.

        Args:
            entity_service: Focomy entity service for database queries
        """
        self.entity_svc = entity_service

        # Caches to avoid repeated database queries
        self._user_cache: dict[int, str | None] = {}
        self._category_cache: dict[str, str | None] = {}
        self._tag_cache: dict[str, str | None] = {}

        # Media mapping: WP attachment post_id -> new URL
        self._media_id_to_url: dict[int, str] = {}

        # Default channel cache
        self._default_channel_id: str | None = None

    def set_media_mapping(
        self,
        items: list["MediaItem"],
        result: "MediaImportResult",
    ) -> None:
        """Build WordPress attachment post_id -> new URL mapping.

        Call this after media import is complete.

        Args:
            items: List of media items that were imported
            result: Media import result containing url_mapping
        """
        for item in items:
            if item.original_url in result.url_mapping:
                self._media_id_to_url[item.post_id] = result.url_mapping[item.original_url]
                logger.debug(f"Media mapping: WP {item.post_id} -> {result.url_mapping[item.original_url]}")

        logger.info(f"Built media ID mapping: {len(self._media_id_to_url)} items")

    async def resolve_user(self, wp_id: int) -> str | None:
        """Resolve WordPress user ID to Focomy user entity ID.

        Args:
            wp_id: WordPress user ID

        Returns:
            Focomy user entity ID or None if not found
        """
        if wp_id in self._user_cache:
            return self._user_cache[wp_id]

        try:
            entities = await self.entity_svc.find(
                "user",
                filters={"wp_id": wp_id},
                limit=1,
            )
            result = entities[0].id if entities else None
        except Exception as e:
            logger.warning(f"Failed to resolve user wp_id={wp_id}: {e}")
            result = None

        self._user_cache[wp_id] = result
        return result

    async def resolve_category(self, slug: str) -> str | None:
        """Resolve category slug to Focomy category entity ID.

        Args:
            slug: Category slug

        Returns:
            Focomy category entity ID or None if not found
        """
        if slug in self._category_cache:
            return self._category_cache[slug]

        try:
            entities = await self.entity_svc.find(
                "category",
                filters={"slug": slug},
                limit=1,
            )
            result = entities[0].id if entities else None
        except Exception as e:
            logger.warning(f"Failed to resolve category slug={slug}: {e}")
            result = None

        self._category_cache[slug] = result
        return result

    async def resolve_tag(self, slug: str) -> str | None:
        """Resolve tag slug to Focomy tag entity ID.

        Args:
            slug: Tag slug

        Returns:
            Focomy tag entity ID or None if not found
        """
        if slug in self._tag_cache:
            return self._tag_cache[slug]

        try:
            entities = await self.entity_svc.find(
                "tag",
                filters={"slug": slug},
                limit=1,
            )
            result = entities[0].id if entities else None
        except Exception as e:
            logger.warning(f"Failed to resolve tag slug={slug}: {e}")
            result = None

        self._tag_cache[slug] = result
        return result

    def resolve_media(self, wp_id: int) -> str | None:
        """Resolve WordPress attachment ID to new media URL.

        This is a synchronous method as it only uses the cached mapping.
        Call set_media_mapping() or add_media_mapping() before using this method.

        Args:
            wp_id: WordPress attachment post ID

        Returns:
            New media URL or None if not found
        """
        return self._media_id_to_url.get(wp_id)

    def add_media_mapping(self, wp_id: int, new_url: str) -> None:
        """Add a single media mapping.

        Use this for incremental mapping during import loop.

        Args:
            wp_id: WordPress attachment post ID
            new_url: New media URL after import
        """
        self._media_id_to_url[wp_id] = new_url

    async def get_default_channel(self) -> str:
        """Get or create the default channel for imported posts.

        Returns:
            Focomy channel entity ID
        """
        if self._default_channel_id:
            return self._default_channel_id

        try:
            # Try to find existing default channel
            entities = await self.entity_svc.find(
                "channel",
                filters={"slug": "default"},
                limit=1,
            )

            if entities:
                self._default_channel_id = entities[0].id
                logger.info(f"Found existing default channel: {self._default_channel_id}")
            else:
                # Create default channel
                entity = await self.entity_svc.create(
                    "channel",
                    {
                        "title": "Default",
                        "slug": "default",
                        "description": "Default channel for imported posts",
                        "sort_order": 0,
                    },
                )
                self._default_channel_id = entity.id
                logger.info(f"Created default channel: {self._default_channel_id}")

        except Exception as e:
            logger.error(f"Failed to get/create default channel: {e}")
            raise

        return self._default_channel_id

    async def resolve_categories(self, slugs: list[str]) -> list[str]:
        """Resolve multiple category slugs to entity IDs.

        Args:
            slugs: List of category slugs

        Returns:
            List of Focomy category entity IDs (excludes None values)
        """
        result = []
        for slug in slugs:
            entity_id = await self.resolve_category(slug)
            if entity_id:
                result.append(entity_id)
        return result

    async def resolve_tags(self, slugs: list[str]) -> list[str]:
        """Resolve multiple tag slugs to entity IDs.

        Args:
            slugs: List of tag slugs

        Returns:
            List of Focomy tag entity IDs (excludes None values)
        """
        result = []
        for slug in slugs:
            entity_id = await self.resolve_tag(slug)
            if entity_id:
                result.append(entity_id)
        return result

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._user_cache.clear()
        self._category_cache.clear()
        self._tag_cache.clear()
        self._media_id_to_url.clear()
        self._default_channel_id = None
