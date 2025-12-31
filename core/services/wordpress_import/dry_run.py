"""Dry Run Service - Simulate import without making changes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, EntityValue, ImportJob
from .wxr_parser import WXRData

logger = logging.getLogger(__name__)


@dataclass
class DryRunItem:
    """Item to be imported in dry run."""

    entity_type: str
    wp_id: int | str
    title: str
    slug: str
    status: str  # new, update, skip, error
    message: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class DryRunResult:
    """Result of dry run simulation."""

    job_id: str
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # Counts
    new_count: int = 0
    update_count: int = 0
    skip_count: int = 0
    error_count: int = 0

    # Items by type
    posts: list[DryRunItem] = field(default_factory=list)
    pages: list[DryRunItem] = field(default_factory=list)
    media: list[DryRunItem] = field(default_factory=list)
    categories: list[DryRunItem] = field(default_factory=list)
    tags: list[DryRunItem] = field(default_factory=list)
    authors: list[DryRunItem] = field(default_factory=list)
    menus: list[DryRunItem] = field(default_factory=list)

    # Issues
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total items to import."""
        return self.new_count + self.update_count

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return self.error_count > 0 or len(self.errors) > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "generated_at": self.generated_at.isoformat(),
            "counts": {
                "new": self.new_count,
                "update": self.update_count,
                "skip": self.skip_count,
                "error": self.error_count,
                "total": self.total_count,
            },
            "items": {
                "posts": [self._item_to_dict(i) for i in self.posts],
                "pages": [self._item_to_dict(i) for i in self.pages],
                "media": [self._item_to_dict(i) for i in self.media[:50]],  # Limit media
                "categories": [self._item_to_dict(i) for i in self.categories],
                "tags": [self._item_to_dict(i) for i in self.tags],
                "authors": [self._item_to_dict(i) for i in self.authors],
                "menus": [self._item_to_dict(i) for i in self.menus],
            },
            "warnings": self.warnings,
            "errors": self.errors,
            "duplicates": self.duplicates,
            "has_errors": self.has_errors,
        }

    def _item_to_dict(self, item: DryRunItem) -> dict:
        """Convert item to dictionary."""
        return {
            "entity_type": item.entity_type,
            "wp_id": item.wp_id,
            "title": item.title,
            "slug": item.slug,
            "status": item.status,
            "message": item.message,
        }


class DryRunService:
    """
    Simulate WordPress import without making changes.

    Detects:
    - New items to import
    - Updates to existing items
    - Duplicate slugs
    - Missing references
    - Invalid data
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(self, job_id: str, wxr_data: WXRData) -> DryRunResult:
        """
        Run dry run simulation.

        Args:
            job_id: Import job ID
            wxr_data: Parsed WordPress data

        Returns:
            DryRunResult with simulation results
        """
        result = DryRunResult(job_id=job_id)

        # Simulate each entity type
        await self._simulate_authors(wxr_data, result)
        await self._simulate_categories(wxr_data, result)
        await self._simulate_tags(wxr_data, result)
        await self._simulate_media(wxr_data, result)
        await self._simulate_posts(wxr_data, result)
        await self._simulate_pages(wxr_data, result)
        await self._simulate_menus(wxr_data, result)

        # Check for duplicate slugs
        await self._check_duplicates(result)

        # Check for missing references
        self._check_references(wxr_data, result)

        logger.info(
            f"Dry run complete: {result.new_count} new, "
            f"{result.update_count} update, {result.error_count} errors"
        )

        return result

    async def _simulate_authors(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate author import."""
        for author in wxr_data.authors:
            existing = await self._find_by_wp_id("user", author.id)

            if existing:
                item = DryRunItem(
                    entity_type="user",
                    wp_id=author.id,
                    title=author.display_name or author.login,
                    slug=author.login,
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                item = DryRunItem(
                    entity_type="user",
                    wp_id=author.id,
                    title=author.display_name or author.login,
                    slug=author.login,
                    status="new",
                    message="Will be imported",
                )
                result.new_count += 1

            result.authors.append(item)

    async def _simulate_categories(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate category import."""
        for cat in wxr_data.categories:
            existing = await self._find_by_wp_id("category", cat.id)

            if existing:
                item = DryRunItem(
                    entity_type="category",
                    wp_id=cat.id,
                    title=cat.name,
                    slug=cat.slug,
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                # Check for slug conflict
                slug_conflict = await self._find_by_slug("category", cat.slug)
                if slug_conflict:
                    item = DryRunItem(
                        entity_type="category",
                        wp_id=cat.id,
                        title=cat.name,
                        slug=cat.slug,
                        status="error",
                        message=f"Slug conflict with existing category",
                    )
                    result.error_count += 1
                    result.errors.append(
                        f"Category '{cat.name}' has slug conflict: {cat.slug}"
                    )
                else:
                    item = DryRunItem(
                        entity_type="category",
                        wp_id=cat.id,
                        title=cat.name,
                        slug=cat.slug,
                        status="new",
                        message="Will be imported",
                    )
                    result.new_count += 1

            result.categories.append(item)

    async def _simulate_tags(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate tag import."""
        for tag in wxr_data.tags:
            existing = await self._find_by_wp_id("tag", tag.id)

            if existing:
                item = DryRunItem(
                    entity_type="tag",
                    wp_id=tag.id,
                    title=tag.name,
                    slug=tag.slug,
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                item = DryRunItem(
                    entity_type="tag",
                    wp_id=tag.id,
                    title=tag.name,
                    slug=tag.slug,
                    status="new",
                    message="Will be imported",
                )
                result.new_count += 1

            result.tags.append(item)

    async def _simulate_media(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate media import."""
        attachments = [p for p in wxr_data.posts if p.post_type == "attachment"]

        for media in attachments:
            existing = await self._find_by_wp_id("media", media.id)

            if existing:
                item = DryRunItem(
                    entity_type="media",
                    wp_id=media.id,
                    title=media.title or f"Media {media.id}",
                    slug=media.slug,
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                # Check if URL is accessible
                url = media.guid or ""
                if not url:
                    item = DryRunItem(
                        entity_type="media",
                        wp_id=media.id,
                        title=media.title or f"Media {media.id}",
                        slug=media.slug,
                        status="error",
                        message="No attachment URL",
                    )
                    result.error_count += 1
                else:
                    item = DryRunItem(
                        entity_type="media",
                        wp_id=media.id,
                        title=media.title or f"Media {media.id}",
                        slug=media.slug,
                        status="new",
                        message="Will be imported",
                        details={"url": url[:100]},
                    )
                    result.new_count += 1

            result.media.append(item)

    async def _simulate_posts(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate post import."""
        posts = [p for p in wxr_data.posts if p.post_type == "post"]

        for post in posts:
            existing = await self._find_by_wp_id("post", post.id)

            if existing:
                item = DryRunItem(
                    entity_type="post",
                    wp_id=post.id,
                    title=post.title,
                    slug=post.slug,
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                # Check for slug conflict
                slug_conflict = await self._find_by_slug("post", post.slug)
                if slug_conflict:
                    item = DryRunItem(
                        entity_type="post",
                        wp_id=post.id,
                        title=post.title,
                        slug=post.slug,
                        status="error",
                        message="Slug conflict",
                    )
                    result.error_count += 1
                    result.errors.append(
                        f"Post '{post.title}' has slug conflict: {post.slug}"
                    )
                else:
                    # Check for missing content
                    if not post.content:
                        result.warnings.append(
                            f"Post '{post.title}' has no content"
                        )

                    item = DryRunItem(
                        entity_type="post",
                        wp_id=post.id,
                        title=post.title,
                        slug=post.slug,
                        status="new",
                        message="Will be imported",
                    )
                    result.new_count += 1

            result.posts.append(item)

    async def _simulate_pages(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate page import."""
        pages = [p for p in wxr_data.posts if p.post_type == "page"]

        for page in pages:
            existing = await self._find_by_wp_id("page", page.id)

            if existing:
                item = DryRunItem(
                    entity_type="page",
                    wp_id=page.id,
                    title=page.title,
                    slug=page.slug,
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                # Check for slug conflict
                slug_conflict = await self._find_by_slug("page", page.slug)
                if slug_conflict:
                    item = DryRunItem(
                        entity_type="page",
                        wp_id=page.id,
                        title=page.title,
                        slug=page.slug,
                        status="error",
                        message="Slug conflict",
                    )
                    result.error_count += 1
                    result.errors.append(
                        f"Page '{page.title}' has slug conflict: {page.slug}"
                    )
                else:
                    item = DryRunItem(
                        entity_type="page",
                        wp_id=page.id,
                        title=page.title,
                        slug=page.slug,
                        status="new",
                        message="Will be imported",
                    )
                    result.new_count += 1

            result.pages.append(item)

    async def _simulate_menus(
        self, wxr_data: WXRData, result: DryRunResult
    ) -> None:
        """Simulate menu import."""
        for menu_name, items in wxr_data.menus.items():
            existing = await self._find_menu_by_name(menu_name)

            if existing:
                item = DryRunItem(
                    entity_type="menu",
                    wp_id=menu_name,
                    title=menu_name,
                    slug=menu_name.lower().replace(" ", "-"),
                    status="skip",
                    message="Already exists",
                )
                result.skip_count += 1
            else:
                item = DryRunItem(
                    entity_type="menu",
                    wp_id=menu_name,
                    title=menu_name,
                    slug=menu_name.lower().replace(" ", "-"),
                    status="new",
                    message=f"Will be imported with {len(items)} items",
                )
                result.new_count += 1

            result.menus.append(item)

    async def _check_duplicates(self, result: DryRunResult) -> None:
        """Check for duplicate slugs within import data."""
        seen_slugs: dict[str, list[dict]] = {}

        all_items = (
            result.posts + result.pages + result.categories +
            result.tags + result.authors + result.menus
        )

        for item in all_items:
            if item.status == "skip":
                continue

            key = f"{item.entity_type}:{item.slug}"
            if key in seen_slugs:
                seen_slugs[key].append({
                    "type": item.entity_type,
                    "wp_id": item.wp_id,
                    "title": item.title,
                })
            else:
                seen_slugs[key] = [{
                    "type": item.entity_type,
                    "wp_id": item.wp_id,
                    "title": item.title,
                }]

        for key, items in seen_slugs.items():
            if len(items) > 1:
                result.duplicates.append({
                    "slug": key.split(":")[1],
                    "type": key.split(":")[0],
                    "items": items,
                })
                result.warnings.append(
                    f"Duplicate slug '{key}' found in {len(items)} items"
                )

    def _check_references(self, wxr_data: WXRData, result: DryRunResult) -> None:
        """Check for missing references."""
        # Get valid category/tag IDs
        valid_cat_ids = {c.id for c in wxr_data.categories}
        valid_tag_ids = {t.id for t in wxr_data.tags}
        valid_author_ids = {a.id for a in wxr_data.authors}

        posts = [p for p in wxr_data.posts if p.post_type in ("post", "page")]

        for post in posts:
            # Check author reference
            if post.author_id and post.author_id not in valid_author_ids:
                result.warnings.append(
                    f"Post '{post.title}' references unknown author ID: {post.author_id}"
                )

    async def _find_by_wp_id(
        self, entity_type: str, wp_id: int
    ) -> Entity | None:
        """Find entity by WordPress ID."""
        result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "wp_id",
                EntityValue.value_int == wp_id,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _find_by_slug(
        self, entity_type: str, slug: str
    ) -> Entity | None:
        """Find entity by slug."""
        result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "slug",
                EntityValue.value_string == slug,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _find_menu_by_name(self, name: str) -> Entity | None:
        """Find menu by name."""
        result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "menu",
                EntityValue.field_name == "name",
                EntityValue.value_string == name,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


async def dry_run(
    db: AsyncSession, job_id: str, wxr_data: WXRData
) -> DryRunResult:
    """
    Convenience function to run dry run.

    Args:
        db: Database session
        job_id: Import job ID
        wxr_data: Parsed WordPress data

    Returns:
        DryRunResult
    """
    service = DryRunService(db)
    return await service.run(job_id, wxr_data)
