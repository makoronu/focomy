"""Post-processing - link fixing and redirect generation."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ...models import Entity
from .link_fixer import InternalLinkFixer, URLMapBuilder
from .redirects import RedirectGenerator

logger = logging.getLogger(__name__)


class PostProcessMixin:
    """Post-import processing methods: link fixing and redirect generation.

    Mixed into WordPressImportService.
    Requires: self.db, self.entity_svc, self.update_job(),
              self._get_entity_field()
    """

    async def fix_links(
        self,
        job_id: str,
        source_domain: str | None = None,
    ) -> dict:
        """
        Fix internal links in imported content.

        Rewrites WordPress URLs to Focomy URLs in post/page content.

        Args:
            job_id: Import job ID
            source_domain: Original WordPress domain for URL matching

        Returns:
            Dict with fix counts and details
        """
        from ...models import EntityValue

        await self.update_job(
            job_id,
            progress_message="Building URL map...",
        )

        # Build URL map
        builder = URLMapBuilder(self.db)
        url_map = await builder.build_map(source_domain)

        if not url_map:
            logger.info("No URL mappings found, skipping link fix")
            return {
                "success": True,
                "posts_fixed": 0,
                "pages_fixed": 0,
                "total_links_fixed": 0,
            }

        await self.update_job(
            job_id,
            progress_message=f"Fixing links with {len(url_map)} URL mappings...",
        )

        # Create link fixer
        fixer = InternalLinkFixer(url_map, source_domain)

        posts_fixed = 0
        pages_fixed = 0
        total_links_fixed = 0

        # Fix posts
        posts_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "post",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        posts = posts_result.scalars().unique().all()

        for post in posts:
            content_result = await self.db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == post.id,
                    EntityValue.field_name == "content",
                )
            )
            content_ev = content_result.scalar_one_or_none()

            if content_ev and content_ev.value_text:
                fix_result = fixer.fix_content(content_ev.value_text)
                if fix_result.had_fixes:
                    content_ev.value_text = fix_result.content
                    posts_fixed += 1
                    total_links_fixed += len(fix_result.fixes)

        # Fix pages
        pages_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "page",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        pages = pages_result.scalars().unique().all()

        for page in pages:
            content_result = await self.db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == page.id,
                    EntityValue.field_name == "content",
                )
            )
            content_ev = content_result.scalar_one_or_none()

            if content_ev and content_ev.value_text:
                fix_result = fixer.fix_content(content_ev.value_text)
                if fix_result.had_fixes:
                    content_ev.value_text = fix_result.content
                    pages_fixed += 1
                    total_links_fixed += len(fix_result.fixes)

        await self.db.commit()

        logger.info(
            f"Fixed links: {posts_fixed} posts, {pages_fixed} pages, "
            f"{total_links_fixed} total links"
        )

        await self.update_job(
            job_id,
            progress_message=f"Fixed {total_links_fixed} internal links",
        )

        return {
            "success": True,
            "posts_fixed": posts_fixed,
            "pages_fixed": pages_fixed,
            "total_links_fixed": total_links_fixed,
        }

    async def generate_redirects(
        self,
        job_id: str,
        source_url: str,
        config: dict | None = None,
    ) -> dict:
        """
        Generate URL redirects for imported content.

        Args:
            job_id: Import job ID
            source_url: Original WordPress site URL
            config: Optional configuration overrides

        Returns:
            Dict with redirect report data
        """
        from ...models import EntityValue

        await self.update_job(
            job_id,
            progress_message="Generating redirects...",
        )

        config = config or {}

        # Collect data from imported entities
        posts_data = []
        categories_data = []
        tags_data = []
        authors_data = []

        # Get posts
        posts_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "post",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        posts = posts_result.scalars().unique().all()

        for post in posts:
            slug = await self._get_entity_field(post.id, "slug")
            title = await self._get_entity_field(post.id, "title")
            if slug:
                posts_data.append({
                    "old_url": f"/{slug}",
                    "new_slug": slug,
                    "slug": slug,
                    "title": title or slug,
                    "post_type": "post",
                })

        # Get pages
        pages_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "page",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        pages = pages_result.scalars().unique().all()

        for page in pages:
            slug = await self._get_entity_field(page.id, "slug")
            title = await self._get_entity_field(page.id, "title")
            if slug:
                posts_data.append({
                    "old_url": f"/{slug}",
                    "new_slug": slug,
                    "slug": slug,
                    "title": title or slug,
                    "post_type": "page",
                })

        # Get categories
        cats_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "category",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        categories = cats_result.scalars().unique().all()

        for cat in categories:
            slug = await self._get_entity_field(cat.id, "slug")
            name = await self._get_entity_field(cat.id, "name")
            if slug:
                categories_data.append({
                    "slug": slug,
                    "old_slug": slug,
                    "new_slug": slug,
                    "name": name or slug,
                })

        # Get tags
        tags_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "tag",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        tags = tags_result.scalars().unique().all()

        for tag in tags:
            slug = await self._get_entity_field(tag.id, "slug")
            name = await self._get_entity_field(tag.id, "name")
            if slug:
                tags_data.append({
                    "slug": slug,
                    "old_slug": slug,
                    "new_slug": slug,
                    "name": name or slug,
                })

        # Get authors
        authors_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "user",
                EntityValue.field_name == "wp_id",
                Entity.deleted_at.is_(None),
            )
        )
        authors = authors_result.scalars().unique().all()

        for author in authors:
            login = await self._get_entity_field(author.id, "login")
            display_name = await self._get_entity_field(author.id, "display_name")
            if login:
                authors_data.append({
                    "login": login,
                    "new_slug": login,
                    "display_name": display_name or login,
                })

        # Generate redirects
        generator = RedirectGenerator(
            old_base_url=source_url,
            new_base_url=config.get("new_base_url", ""),
        )

        report = generator.generate_all(
            posts=posts_data,
            categories=categories_data,
            tags=tags_data,
            authors=authors_data,
            config=config,
        )

        logger.info(f"Generated {len(report.redirects)} redirects")

        await self.update_job(
            job_id,
            progress_message=f"Generated {len(report.redirects)} redirects",
        )

        return {
            "success": True,
            "redirect_count": len(report.redirects),
            "conflict_count": len(report.conflicts),
            "warnings": report.warnings,
            "redirects": [
                {
                    "from": r.from_path,
                    "to": r.to_path,
                    "status": r.status_code,
                    "regex": r.regex,
                    "comment": r.comment,
                }
                for r in report.redirects
            ],
            "conflicts": report.conflicts,
        }
