"""Internal Link Fixer - Rewrite WordPress URLs to Focomy URLs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from ...models import Entity

from ...models import Entity, EntityValue

logger = logging.getLogger(__name__)


@dataclass
class LinkFix:
    """Record of a link fix."""

    old_url: str
    new_url: str
    link_type: str  # href, src, gutenberg


@dataclass
class LinkFixResult:
    """Result of link fixing operation."""

    content: str
    fixes: list[LinkFix] = field(default_factory=list)

    @property
    def had_fixes(self) -> bool:
        """Check if any fixes were made."""
        return len(self.fixes) > 0


class InternalLinkFixer:
    """
    Fix internal links in WordPress content.

    Rewrites WordPress URLs to Focomy URLs based on URL mapping.
    """

    def __init__(self, url_map: dict[str, str], source_domain: str | None = None):
        """
        Initialize with URL mapping.

        Args:
            url_map: Dictionary mapping old paths to new paths
            source_domain: Original WordPress domain (for absolute URL matching)
        """
        self.url_map = url_map
        self.source_domain = source_domain

    def fix_content(self, content: str) -> LinkFixResult:
        """
        Fix internal links in HTML content.

        Args:
            content: HTML content to process

        Returns:
            LinkFixResult with fixed content and list of fixes
        """
        if not content:
            return LinkFixResult(content="")

        fixes: list[LinkFix] = []

        # Fix href attributes
        content = self._fix_href_links(content, fixes)

        # Fix src attributes
        content = self._fix_src_links(content, fixes)

        # Fix Gutenberg block links
        content = self._fix_gutenberg_links(content, fixes)

        # Log fixes
        if fixes:
            logger.info(f"Fixed {len(fixes)} internal links")
            for fix in fixes:
                logger.debug(f"  [{fix.link_type}] {fix.old_url} -> {fix.new_url}")

        return LinkFixResult(content=content, fixes=fixes)

    def _fix_href_links(self, content: str, fixes: list[LinkFix]) -> str:
        """Fix href attributes in content."""

        def replace_href(match: re.Match) -> str:
            attr_start = match.group(1)
            url = match.group(2)
            new_url = self._map_url(url)
            if new_url != url:
                fixes.append(LinkFix(old_url=url, new_url=new_url, link_type="href"))
                return f'{attr_start}"{new_url}"'
            return match.group(0)

        return re.sub(r'(href=)"([^"]+)"', replace_href, content, flags=re.IGNORECASE)

    def _fix_src_links(self, content: str, fixes: list[LinkFix]) -> str:
        """Fix src attributes in content."""

        def replace_src(match: re.Match) -> str:
            attr_start = match.group(1)
            url = match.group(2)
            new_url = self._map_url(url)
            if new_url != url:
                fixes.append(LinkFix(old_url=url, new_url=new_url, link_type="src"))
                return f'{attr_start}"{new_url}"'
            return match.group(0)

        return re.sub(r'(src=)"([^"]+)"', replace_src, content, flags=re.IGNORECASE)

    def _fix_gutenberg_links(self, content: str, fixes: list[LinkFix]) -> str:
        """Fix links in Gutenberg blocks."""

        def replace_gutenberg_attrs(match: re.Match) -> str:
            block_type = match.group(1)
            attrs_str = match.group(2)

            try:
                attrs = json.loads(attrs_str)
                modified = False

                # Fix url attribute
                if "url" in attrs and isinstance(attrs["url"], str):
                    new_url = self._map_url(attrs["url"])
                    if new_url != attrs["url"]:
                        fixes.append(
                            LinkFix(
                                old_url=attrs["url"],
                                new_url=new_url,
                                link_type="gutenberg",
                            )
                        )
                        attrs["url"] = new_url
                        modified = True

                # Fix href attribute
                if "href" in attrs and isinstance(attrs["href"], str):
                    new_url = self._map_url(attrs["href"])
                    if new_url != attrs["href"]:
                        fixes.append(
                            LinkFix(
                                old_url=attrs["href"],
                                new_url=new_url,
                                link_type="gutenberg",
                            )
                        )
                        attrs["href"] = new_url
                        modified = True

                # Fix mediaLink attribute
                if "mediaLink" in attrs and isinstance(attrs["mediaLink"], str):
                    new_url = self._map_url(attrs["mediaLink"])
                    if new_url != attrs["mediaLink"]:
                        fixes.append(
                            LinkFix(
                                old_url=attrs["mediaLink"],
                                new_url=new_url,
                                link_type="gutenberg",
                            )
                        )
                        attrs["mediaLink"] = new_url
                        modified = True

                if modified:
                    return f"<!-- wp:{block_type} {json.dumps(attrs)}"

            except (json.JSONDecodeError, TypeError):
                pass

            return match.group(0)

        # Match Gutenberg block comments with JSON attributes
        pattern = r"<!-- wp:(\w+(?:/\w+)?) ({[^}]+})"
        return re.sub(pattern, replace_gutenberg_attrs, content)

    def _map_url(self, url: str) -> str:
        """
        Map old URL to new URL.

        Args:
            url: Original URL (absolute or relative)

        Returns:
            Mapped URL if found, otherwise original URL
        """
        if not url:
            return url

        # Skip external URLs, anchors, and protocols other than http/https
        if url.startswith("#"):
            return url
        if url.startswith("mailto:") or url.startswith("tel:"):
            return url
        if url.startswith("javascript:"):
            return url

        # Extract path from URL
        parsed = urlparse(url)

        # Check if it's from the source domain
        if parsed.netloc:
            if self.source_domain and parsed.netloc != self.source_domain:
                # External URL, don't modify
                return url
            path = parsed.path
        else:
            # Relative URL
            path = url.split("?")[0].split("#")[0]  # Remove query and fragment

        # Try exact match
        if path in self.url_map:
            new_path = self.url_map[path]
            # Preserve query string and fragment
            result = new_path
            if parsed.query:
                result += f"?{parsed.query}"
            if parsed.fragment:
                result += f"#{parsed.fragment}"
            return result

        # Try with/without trailing slash
        normalized = path.rstrip("/") if path.endswith("/") else f"{path}/"
        if normalized in self.url_map:
            new_path = self.url_map[normalized]
            result = new_path
            if parsed.query:
                result += f"?{parsed.query}"
            if parsed.fragment:
                result += f"#{parsed.fragment}"
            return result

        return url


class URLMapBuilder:
    """Build URL mapping from WordPress data and Focomy entities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_map(self, source_domain: str | None = None) -> dict[str, str]:
        """
        Build URL mapping from imported entities.

        Creates mappings for:
        - Posts: /2024/01/old-slug -> /posts/new-slug
        - Pages: /old-page -> /pages/new-page
        - Categories: /category/old-cat -> /categories/new-cat
        - Tags: /tag/old-tag -> /tags/new-tag
        - Media: /wp-content/uploads/... -> /media/...

        Returns:
            Dictionary mapping old paths to new paths
        """
        url_map: dict[str, str] = {}

        # Get all entities with wp_id (imported from WordPress)
        entity_types = ["post", "page", "category", "tag", "media"]

        for entity_type in entity_types:
            # Find entities of this type with wp_id
            result = await self.db.execute(
                select(Entity)
                .join(EntityValue, Entity.id == EntityValue.entity_id)
                .where(
                    Entity.type == entity_type,
                    EntityValue.field_name == "slug",
                    Entity.deleted_at.is_(None),
                )
            )
            entities = result.scalars().unique().all()

            for entity in entities:
                # Get slug and wp_slug values
                slug = await self._get_field_value(entity.id, "slug")
                wp_slug = await self._get_field_value(entity.id, "wp_slug")
                wp_id = await self._get_field_value(entity.id, "wp_id")

                if not slug:
                    continue

                # Build new URL based on entity type
                new_url = self._build_new_url(entity_type, slug)

                # Build old URLs (WordPress patterns)
                old_urls = self._build_old_urls(entity_type, wp_slug or slug, wp_id)

                for old_url in old_urls:
                    url_map[old_url] = new_url

        logger.info(f"Built URL map with {len(url_map)} entries")
        return url_map

    async def _get_field_value(
        self, entity_id: str, field_name: str
    ) -> str | int | None:
        """Get a field value for an entity."""
        result = await self.db.execute(
            select(EntityValue).where(
                EntityValue.entity_id == entity_id,
                EntityValue.field_name == field_name,
            )
        )
        ev = result.scalar_one_or_none()
        if not ev:
            return None
        # Return appropriate value type
        if ev.value_string is not None:
            return ev.value_string
        if ev.value_int is not None:
            return ev.value_int
        return None

    def _build_new_url(self, entity_type: str, slug: str) -> str:
        """Build new Focomy URL."""
        if entity_type == "post":
            return f"/posts/{slug}"
        elif entity_type == "page":
            return f"/pages/{slug}"
        elif entity_type == "category":
            return f"/categories/{slug}"
        elif entity_type == "tag":
            return f"/tags/{slug}"
        elif entity_type == "media":
            return f"/media/{slug}"
        return f"/{entity_type}/{slug}"

    def _build_old_urls(
        self, entity_type: str, slug: str, wp_id: int | None = None
    ) -> list[str]:
        """Build possible old WordPress URLs."""
        urls = []

        if entity_type == "post":
            # Common WordPress post URL patterns
            urls.append(f"/{slug}")
            urls.append(f"/{slug}/")
            # Date-based patterns (we don't know the date, so these are just examples)
            # The actual URL will be matched if slug is in the path
            if wp_id:
                urls.append(f"/?p={wp_id}")
        elif entity_type == "page":
            urls.append(f"/{slug}")
            urls.append(f"/{slug}/")
            if wp_id:
                urls.append(f"/?page_id={wp_id}")
        elif entity_type == "category":
            urls.append(f"/category/{slug}")
            urls.append(f"/category/{slug}/")
        elif entity_type == "tag":
            urls.append(f"/tag/{slug}")
            urls.append(f"/tag/{slug}/")
        elif entity_type == "media":
            # Media URLs are more complex, handled separately
            pass

        return urls


async def build_url_map(db: AsyncSession, source_domain: str | None = None) -> dict[str, str]:
    """
    Convenience function to build URL map.

    Args:
        db: Database session
        source_domain: Original WordPress domain

    Returns:
        URL mapping dictionary
    """
    builder = URLMapBuilder(db)
    return await builder.build_map(source_domain)
