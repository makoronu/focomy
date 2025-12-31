"""Diff Detector - Detect changes between WordPress and Focomy."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, EntityValue
from ..entity import EntityService
from .constants import WP_STATUS_MAP
from .wxr_parser import WXRData, WXRPost, WXRTerm, WXRAuthor

logger = logging.getLogger(__name__)


@dataclass
class DiffItem:
    """A single diff item."""

    entity_type: str
    wp_id: int
    title: str
    wp_data: Any  # WXRPost, WXRTerm, etc.
    existing_entity: Entity | None = None
    reason: str = ""  # Why it was classified this way


@dataclass
class DiffResult:
    """Result of diff detection."""

    new: dict[str, list[DiffItem]] = field(default_factory=lambda: {
        "posts": [],
        "pages": [],
        "media": [],
        "categories": [],
        "tags": [],
        "authors": [],
    })
    updated: dict[str, list[DiffItem]] = field(default_factory=lambda: {
        "posts": [],
        "pages": [],
        "media": [],
        "categories": [],
        "tags": [],
        "authors": [],
    })
    unchanged: dict[str, list[DiffItem]] = field(default_factory=lambda: {
        "posts": [],
        "pages": [],
        "media": [],
        "categories": [],
        "tags": [],
        "authors": [],
    })
    deleted: dict[str, list[DiffItem]] = field(default_factory=lambda: {
        "posts": [],
        "pages": [],
        "media": [],
        "categories": [],
        "tags": [],
        "authors": [],
    })

    def add_new(self, entity_type: str, item: DiffItem) -> None:
        """Add a new item."""
        if entity_type not in self.new:
            self.new[entity_type] = []
        self.new[entity_type].append(item)

    def add_updated(self, entity_type: str, item: DiffItem) -> None:
        """Add an updated item."""
        if entity_type not in self.updated:
            self.updated[entity_type] = []
        self.updated[entity_type].append(item)

    def add_unchanged(self, entity_type: str, item: DiffItem) -> None:
        """Add an unchanged item."""
        if entity_type not in self.unchanged:
            self.unchanged[entity_type] = []
        self.unchanged[entity_type].append(item)

    def add_deleted(self, entity_type: str, item: DiffItem) -> None:
        """Add a deleted item."""
        if entity_type not in self.deleted:
            self.deleted[entity_type] = []
        self.deleted[entity_type].append(item)

    def to_summary(self) -> dict[str, dict[str, int]]:
        """Return a summary of counts per entity type."""
        entity_types = ["posts", "pages", "media", "categories", "tags", "authors"]
        summary = {}

        for entity_type in entity_types:
            summary[entity_type] = {
                "new": len(self.new.get(entity_type, [])),
                "updated": len(self.updated.get(entity_type, [])),
                "unchanged": len(self.unchanged.get(entity_type, [])),
                "deleted": len(self.deleted.get(entity_type, [])),
            }

        return summary

    def to_dict(self) -> dict:
        """Convert to a serializable dict."""

        def items_to_list(items: list[DiffItem]) -> list[dict]:
            return [
                {
                    "entity_type": item.entity_type,
                    "wp_id": item.wp_id,
                    "title": item.title,
                    "reason": item.reason,
                }
                for item in items
            ]

        return {
            "summary": self.to_summary(),
            "new": {k: items_to_list(v) for k, v in self.new.items()},
            "updated": {k: items_to_list(v) for k, v in self.updated.items()},
            "unchanged": {k: items_to_list(v) for k, v in self.unchanged.items()},
            "deleted": {k: items_to_list(v) for k, v in self.deleted.items()},
        }


class DiffDetector:
    """Detect differences between WordPress data and Focomy database."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def detect(self, wxr_data: WXRData) -> DiffResult:
        """
        Detect all differences between WXR data and database.

        Returns a DiffResult with new/updated/unchanged/deleted items.
        """
        result = DiffResult()

        # Detect posts diff
        await self._detect_posts_diff(wxr_data, result)

        # Detect pages diff
        await self._detect_pages_diff(wxr_data, result)

        # Detect media diff
        await self._detect_media_diff(wxr_data, result)

        # Detect categories diff
        await self._detect_categories_diff(wxr_data, result)

        # Detect tags diff
        await self._detect_tags_diff(wxr_data, result)

        # Detect authors diff
        await self._detect_authors_diff(wxr_data, result)

        return result

    async def _detect_posts_diff(
        self,
        wxr_data: WXRData,
        result: DiffResult,
    ) -> None:
        """Detect posts differences."""
        posts = [p for p in wxr_data.posts if p.post_type == "post"]
        wxr_wp_ids = set()

        for post in posts:
            wxr_wp_ids.add(post.id)
            existing = await self._find_by_wp_id("post", post.id)

            item = DiffItem(
                entity_type="posts",
                wp_id=post.id,
                title=post.title,
                wp_data=post,
                existing_entity=existing,
            )

            if not existing:
                item.reason = "New post"
                result.add_new("posts", item)
            elif await self._is_post_updated(existing, post):
                item.reason = "Content or metadata changed"
                result.add_updated("posts", item)
            else:
                item.reason = "No changes detected"
                result.add_unchanged("posts", item)

        # Find deleted (in Focomy but not in WXR)
        focomy_wp_ids = await self._get_all_wp_ids("post")
        deleted_ids = focomy_wp_ids - wxr_wp_ids

        for wp_id in deleted_ids:
            entity = await self._find_by_wp_id("post", wp_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                item = DiffItem(
                    entity_type="posts",
                    wp_id=wp_id,
                    title=entity_data.get("title", "Unknown"),
                    wp_data=None,
                    existing_entity=entity,
                    reason="Deleted from WordPress",
                )
                result.add_deleted("posts", item)

    async def _detect_pages_diff(
        self,
        wxr_data: WXRData,
        result: DiffResult,
    ) -> None:
        """Detect pages differences."""
        pages = [p for p in wxr_data.posts if p.post_type == "page"]
        wxr_wp_ids = set()

        for page in pages:
            wxr_wp_ids.add(page.id)
            existing = await self._find_by_wp_id("page", page.id)

            item = DiffItem(
                entity_type="pages",
                wp_id=page.id,
                title=page.title,
                wp_data=page,
                existing_entity=existing,
            )

            if not existing:
                item.reason = "New page"
                result.add_new("pages", item)
            elif await self._is_post_updated(existing, page):
                item.reason = "Content or metadata changed"
                result.add_updated("pages", item)
            else:
                item.reason = "No changes detected"
                result.add_unchanged("pages", item)

        # Find deleted
        focomy_wp_ids = await self._get_all_wp_ids("page")
        deleted_ids = focomy_wp_ids - wxr_wp_ids

        for wp_id in deleted_ids:
            entity = await self._find_by_wp_id("page", wp_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                item = DiffItem(
                    entity_type="pages",
                    wp_id=wp_id,
                    title=entity_data.get("title", "Unknown"),
                    wp_data=None,
                    existing_entity=entity,
                    reason="Deleted from WordPress",
                )
                result.add_deleted("pages", item)

    async def _detect_media_diff(
        self,
        wxr_data: WXRData,
        result: DiffResult,
    ) -> None:
        """Detect media differences."""
        media_items = [p for p in wxr_data.posts if p.post_type == "attachment"]
        wxr_wp_ids = set()

        for media in media_items:
            wxr_wp_ids.add(media.id)
            existing = await self._find_by_wp_id("media", media.id)

            item = DiffItem(
                entity_type="media",
                wp_id=media.id,
                title=media.title or "Untitled",
                wp_data=media,
                existing_entity=existing,
            )

            if not existing:
                item.reason = "New media"
                result.add_new("media", item)
            else:
                # Media rarely updates, check title/alt only
                entity_data = self.entity_svc.serialize(existing)
                if entity_data.get("title") != media.title:
                    item.reason = "Title changed"
                    result.add_updated("media", item)
                else:
                    item.reason = "No changes detected"
                    result.add_unchanged("media", item)

        # Find deleted
        focomy_wp_ids = await self._get_all_wp_ids("media")
        deleted_ids = focomy_wp_ids - wxr_wp_ids

        for wp_id in deleted_ids:
            entity = await self._find_by_wp_id("media", wp_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                item = DiffItem(
                    entity_type="media",
                    wp_id=wp_id,
                    title=entity_data.get("title", "Unknown"),
                    wp_data=None,
                    existing_entity=entity,
                    reason="Deleted from WordPress",
                )
                result.add_deleted("media", item)

    async def _detect_categories_diff(
        self,
        wxr_data: WXRData,
        result: DiffResult,
    ) -> None:
        """Detect categories differences."""
        wxr_wp_ids = set()

        for cat in wxr_data.categories:
            wxr_wp_ids.add(cat.id)
            existing = await self._find_by_wp_id("category", cat.id)

            item = DiffItem(
                entity_type="categories",
                wp_id=cat.id,
                title=cat.name,
                wp_data=cat,
                existing_entity=existing,
            )

            if not existing:
                item.reason = "New category"
                result.add_new("categories", item)
            else:
                entity_data = self.entity_svc.serialize(existing)
                if (
                    entity_data.get("name") != cat.name
                    or entity_data.get("slug") != cat.slug
                ):
                    item.reason = "Name or slug changed"
                    result.add_updated("categories", item)
                else:
                    item.reason = "No changes detected"
                    result.add_unchanged("categories", item)

        # Find deleted
        focomy_wp_ids = await self._get_all_wp_ids("category")
        deleted_ids = focomy_wp_ids - wxr_wp_ids

        for wp_id in deleted_ids:
            entity = await self._find_by_wp_id("category", wp_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                item = DiffItem(
                    entity_type="categories",
                    wp_id=wp_id,
                    title=entity_data.get("name", "Unknown"),
                    wp_data=None,
                    existing_entity=entity,
                    reason="Deleted from WordPress",
                )
                result.add_deleted("categories", item)

    async def _detect_tags_diff(
        self,
        wxr_data: WXRData,
        result: DiffResult,
    ) -> None:
        """Detect tags differences."""
        wxr_wp_ids = set()

        for tag in wxr_data.tags:
            wxr_wp_ids.add(tag.id)
            existing = await self._find_by_wp_id("tag", tag.id)

            item = DiffItem(
                entity_type="tags",
                wp_id=tag.id,
                title=tag.name,
                wp_data=tag,
                existing_entity=existing,
            )

            if not existing:
                item.reason = "New tag"
                result.add_new("tags", item)
            else:
                entity_data = self.entity_svc.serialize(existing)
                if (
                    entity_data.get("name") != tag.name
                    or entity_data.get("slug") != tag.slug
                ):
                    item.reason = "Name or slug changed"
                    result.add_updated("tags", item)
                else:
                    item.reason = "No changes detected"
                    result.add_unchanged("tags", item)

        # Find deleted
        focomy_wp_ids = await self._get_all_wp_ids("tag")
        deleted_ids = focomy_wp_ids - wxr_wp_ids

        for wp_id in deleted_ids:
            entity = await self._find_by_wp_id("tag", wp_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                item = DiffItem(
                    entity_type="tags",
                    wp_id=wp_id,
                    title=entity_data.get("name", "Unknown"),
                    wp_data=None,
                    existing_entity=entity,
                    reason="Deleted from WordPress",
                )
                result.add_deleted("tags", item)

    async def _detect_authors_diff(
        self,
        wxr_data: WXRData,
        result: DiffResult,
    ) -> None:
        """Detect authors differences."""
        wxr_wp_ids = set()

        for author in wxr_data.authors:
            wxr_wp_ids.add(author.id)
            existing = await self._find_by_wp_id("user", author.id)

            item = DiffItem(
                entity_type="authors",
                wp_id=author.id,
                title=author.display_name or author.login,
                wp_data=author,
                existing_entity=existing,
            )

            if not existing:
                item.reason = "New author"
                result.add_new("authors", item)
            else:
                entity_data = self.entity_svc.serialize(existing)
                if entity_data.get("name") != (author.display_name or author.login):
                    item.reason = "Display name changed"
                    result.add_updated("authors", item)
                else:
                    item.reason = "No changes detected"
                    result.add_unchanged("authors", item)

        # Find deleted
        focomy_wp_ids = await self._get_all_wp_ids("user")
        deleted_ids = focomy_wp_ids - wxr_wp_ids

        for wp_id in deleted_ids:
            entity = await self._find_by_wp_id("user", wp_id)
            if entity:
                entity_data = self.entity_svc.serialize(entity)
                item = DiffItem(
                    entity_type="authors",
                    wp_id=wp_id,
                    title=entity_data.get("name", "Unknown"),
                    wp_data=None,
                    existing_entity=entity,
                    reason="Deleted from WordPress",
                )
                result.add_deleted("authors", item)

    async def _find_by_wp_id(self, entity_type: str, wp_id: int) -> Entity | None:
        """Find entity by WordPress ID."""
        result = await self.db.execute(
            select(Entity)
            .join(EntityValue)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "wp_id",
                EntityValue.value_int == wp_id,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_all_wp_ids(self, entity_type: str) -> set[int]:
        """Get all WordPress IDs for an entity type."""
        result = await self.db.execute(
            select(EntityValue.value_int)
            .join(Entity)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        return {row[0] for row in result.all() if row[0] is not None}

    async def _is_post_updated(self, existing: Entity, wp_post: WXRPost) -> bool:
        """Check if a post has been updated."""
        entity_data = self.entity_svc.serialize(existing)

        # Compare modified date if available
        existing_modified = entity_data.get("wp_modified")
        if existing_modified and wp_post.modified_at:
            try:
                if isinstance(existing_modified, str):
                    existing_dt = datetime.fromisoformat(existing_modified)
                else:
                    existing_dt = existing_modified
                return wp_post.modified_at > existing_dt
            except (ValueError, TypeError):
                pass

        # Fall back to content hash comparison
        existing_content = entity_data.get("content", "")
        existing_hash = self._hash_content(existing_content)
        new_hash = self._hash_content(wp_post.content or "")

        if existing_hash != new_hash:
            return True

        # Check title change
        if entity_data.get("title") != wp_post.title:
            return True

        # Check status change
        expected_status = WP_STATUS_MAP.get(wp_post.status, "draft")
        if entity_data.get("status") != expected_status:
            return True

        return False

    @staticmethod
    def _hash_content(content: str) -> str:
        """Generate a hash of content for comparison."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()
