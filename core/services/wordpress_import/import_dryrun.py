"""Dry-run and preview import operations."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ...models import Entity, ImportJobPhase, ImportJobStatus
from .wxr_parser import WXRData

logger = logging.getLogger(__name__)


class DryRunMixin:
    """Dry-run simulation and preview import methods.

    Mixed into WordPressImportService.
    Requires: self.db, self.entity_svc, self.update_job(), self.get_job(),
              self._fetch_source_data(), self._find_by_wp_id(), self._find_by_slug()
    """

    async def dry_run(self, job_id: str) -> dict | None:
        """
        Perform a dry-run simulation of the import.

        Detects:
        - Duplicate content (by wp_id or slug)
        - Potential conflicts
        - Warnings and errors

        Returns a detailed report without making any changes.
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        try:
            await self.update_job(
                job_id,
                status=ImportJobStatus.ANALYZING,
                phase=ImportJobPhase.ANALYZE,
                progress_message="Running dry-run simulation...",
            )

            # Get WXR data from source
            wxr_data = await self._fetch_source_data(job)
            if not wxr_data:
                raise ValueError("Failed to fetch source data")

            # Initialize result
            dry_run_result = {
                "success": True,
                "summary": {
                    "authors": {"total": 0, "new": 0, "duplicates": 0, "errors": []},
                    "categories": {"total": 0, "new": 0, "duplicates": 0, "errors": []},
                    "tags": {"total": 0, "new": 0, "duplicates": 0, "errors": []},
                    "media": {"total": 0, "new": 0, "duplicates": 0, "errors": []},
                    "posts": {"total": 0, "new": 0, "duplicates": 0, "errors": []},
                    "pages": {"total": 0, "new": 0, "duplicates": 0, "errors": []},
                },
                "duplicates": [],
                "warnings": [],
                "errors": [],
            }

            # Check authors
            await self._dry_run_check_authors(wxr_data, dry_run_result)

            # Check categories
            await self._dry_run_check_categories(wxr_data, dry_run_result)

            # Check tags
            await self._dry_run_check_tags(wxr_data, dry_run_result)

            # Check media
            config = job.config or {}
            if config.get("import_media", True):
                await self._dry_run_check_media(wxr_data, dry_run_result)

            # Check posts
            await self._dry_run_check_posts(wxr_data, dry_run_result, "post")

            # Check pages
            await self._dry_run_check_posts(wxr_data, dry_run_result, "page")

            # Store dry-run result in job
            await self.update_job(
                job_id,
                status=ImportJobStatus.PENDING,
                phase=ImportJobPhase.INIT,
                dry_run_result=dry_run_result,
                progress_message="Dry-run complete",
            )

            return dry_run_result

        except Exception as e:
            logger.exception(f"Dry-run failed for job {job_id}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _dry_run_check_authors(
        self,
        wxr_data: WXRData,
        result: dict,
    ) -> None:
        """Check authors for duplicates."""
        from ...models import EntityValue

        summary = result["summary"]["authors"]
        summary["total"] = len(wxr_data.authors)

        for author in wxr_data.authors:
            existing = await self._find_by_wp_id("user", author.id)
            if existing:
                summary["duplicates"] += 1
                result["duplicates"].append({
                    "type": "author",
                    "wp_id": author.id,
                    "name": author.display_name or author.login,
                    "reason": "Already imported (wp_id match)",
                })
            else:
                # Check by email
                email_check = await self.db.execute(
                    select(Entity)
                    .join(EntityValue)
                    .where(
                        Entity.type == "user",
                        EntityValue.field_name == "email",
                        EntityValue.value_text == author.email,
                        Entity.deleted_at.is_(None),
                    )
                )
                if email_check.scalar_one_or_none():
                    summary["duplicates"] += 1
                    result["duplicates"].append({
                        "type": "author",
                        "wp_id": author.id,
                        "name": author.display_name or author.login,
                        "reason": f"Email already exists: {author.email}",
                    })
                else:
                    summary["new"] += 1

    async def _dry_run_check_categories(
        self,
        wxr_data: WXRData,
        result: dict,
    ) -> None:
        """Check categories for duplicates."""
        summary = result["summary"]["categories"]
        summary["total"] = len(wxr_data.categories)

        for cat in wxr_data.categories:
            existing = await self._find_by_wp_id("category", cat.id)
            if existing:
                summary["duplicates"] += 1
                result["duplicates"].append({
                    "type": "category",
                    "wp_id": cat.id,
                    "name": cat.name,
                    "reason": "Already imported (wp_id match)",
                })
            else:
                # Check by slug
                existing_slug = await self._find_by_slug("category", cat.slug)
                if existing_slug:
                    summary["duplicates"] += 1
                    result["duplicates"].append({
                        "type": "category",
                        "wp_id": cat.id,
                        "name": cat.name,
                        "reason": f"Slug already exists: {cat.slug}",
                    })
                else:
                    summary["new"] += 1

    async def _dry_run_check_tags(
        self,
        wxr_data: WXRData,
        result: dict,
    ) -> None:
        """Check tags for duplicates."""
        summary = result["summary"]["tags"]
        summary["total"] = len(wxr_data.tags)

        for tag in wxr_data.tags:
            existing = await self._find_by_wp_id("tag", tag.id)
            if existing:
                summary["duplicates"] += 1
                result["duplicates"].append({
                    "type": "tag",
                    "wp_id": tag.id,
                    "name": tag.name,
                    "reason": "Already imported (wp_id match)",
                })
            else:
                # Check by slug
                existing_slug = await self._find_by_slug("tag", tag.slug)
                if existing_slug:
                    summary["duplicates"] += 1
                    result["duplicates"].append({
                        "type": "tag",
                        "wp_id": tag.id,
                        "name": tag.name,
                        "reason": f"Slug already exists: {tag.slug}",
                    })
                else:
                    summary["new"] += 1

    async def _dry_run_check_media(
        self,
        wxr_data: WXRData,
        result: dict,
    ) -> None:
        """Check media for duplicates."""
        media_posts = [p for p in wxr_data.posts if p.post_type == "attachment"]
        summary = result["summary"]["media"]
        summary["total"] = len(media_posts)

        for media in media_posts:
            existing = await self._find_by_wp_id("media", media.id)
            if existing:
                summary["duplicates"] += 1
                result["duplicates"].append({
                    "type": "media",
                    "wp_id": media.id,
                    "name": media.title,
                    "reason": "Already imported (wp_id match)",
                })
            else:
                summary["new"] += 1

    async def _dry_run_check_posts(
        self,
        wxr_data: WXRData,
        result: dict,
        post_type: str,
    ) -> None:
        """Check posts/pages for duplicates."""
        posts = [p for p in wxr_data.posts if p.post_type == post_type]
        summary = result["summary"]["posts" if post_type == "post" else "pages"]
        summary["total"] = len(posts)

        for post in posts:
            existing = await self._find_by_wp_id(post_type, post.id)
            if existing:
                summary["duplicates"] += 1
                result["duplicates"].append({
                    "type": post_type,
                    "wp_id": post.id,
                    "title": post.title,
                    "reason": "Already imported (wp_id match)",
                })
            else:
                # Check by slug
                existing_slug = await self._find_by_slug(post_type, post.slug)
                if existing_slug:
                    summary["duplicates"] += 1
                    result["duplicates"].append({
                        "type": post_type,
                        "wp_id": post.id,
                        "title": post.title,
                        "reason": f"Slug already exists: {post.slug}",
                    })
                    result["warnings"].append({
                        "code": "SLUG_CONFLICT",
                        "message": f"{post_type.title()} '{post.title}' has conflicting slug: {post.slug}",
                        "wp_id": post.id,
                    })
                else:
                    summary["new"] += 1

    async def preview_import(
        self,
        job_id: str,
        limit: int = 3,
    ) -> dict | None:
        """
        Import a small number of items for preview.

        Imports up to `limit` posts/pages to let the user verify
        the import works correctly before doing the full import.

        Items are marked with is_preview=True for later confirmation or rollback.
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        try:
            await self.update_job(
                job_id,
                status=ImportJobStatus.IMPORTING,
                phase=ImportJobPhase.POSTS,
                progress_message="Creating preview import...",
            )

            # Get WXR data from source
            wxr_data = await self._fetch_source_data(job)
            if not wxr_data:
                raise ValueError("Failed to fetch source data")

            # Get posts for preview (prioritize published posts)
            all_posts = [p for p in wxr_data.posts if p.post_type == "post"]
            published_posts = [p for p in all_posts if p.status == "publish"]
            preview_posts = (published_posts or all_posts)[:limit]

            imported = []
            preview_ids = []

            for post in preview_posts:
                try:
                    existing = await self._find_by_wp_id("post", post.id)
                    if existing:
                        continue

                    post_data = {
                        "title": post.title,
                        "slug": f"preview-{post.slug}",  # Prefix to avoid conflicts
                        "content": post.content,
                        "excerpt": post.excerpt,
                        "status": "draft",  # Always draft for preview
                        "wp_id": post.id,
                        "wp_author_id": post.author_id,
                        "is_preview": True,  # Mark as preview
                        "created_at": post.created_at.isoformat(),
                        "updated_at": post.modified_at.isoformat(),
                    }

                    entity = await self.entity_svc.create("post", post_data)
                    entity_data = self.entity_svc.serialize(entity)
                    preview_ids.append(entity_data["id"])
                    imported.append({
                        "id": entity_data["id"],
                        "title": post.title,
                        "slug": entity_data.get("slug"),
                        "original_status": post.status,
                        "wp_id": post.id,
                        "content_preview": post.content[:500] if post.content else "",
                    })

                except Exception as e:
                    logger.warning(f"Failed to preview import post {post.id}: {e}")

            # Store preview IDs in job config for later confirmation/rollback
            config = job.config or {}
            config["preview_ids"] = preview_ids
            await self.update_job(
                job_id,
                status=ImportJobStatus.PENDING,
                phase=ImportJobPhase.INIT,
                config=config,
                progress_message="Preview complete",
            )

            return {
                "success": True,
                "preview_count": len(imported),
                "items": imported,
                "preview_ids": preview_ids,
            }

        except Exception as e:
            logger.exception(f"Preview failed for job {job_id}")
            return {
                "success": False,
                "error": str(e),
            }

    async def confirm_preview(self, job_id: str) -> dict | None:
        """Confirm preview items and update them to their original status."""
        job = await self.get_job(job_id)
        if not job:
            return None

        config = job.config or {}
        preview_ids = config.get("preview_ids", [])

        if not preview_ids:
            return {"success": False, "error": "No preview items to confirm"}

        confirmed = 0
        for entity_id in preview_ids:
            try:
                entity = await self.entity_svc.get("post", entity_id)
                if entity:
                    entity_data = self.entity_svc.serialize(entity)
                    # Remove preview prefix from slug
                    slug = entity_data.get("slug", "")
                    if slug.startswith("preview-"):
                        new_slug = slug[8:]  # Remove "preview-" prefix
                        await self.entity_svc.update("post", entity_id, {
                            "slug": new_slug,
                            "is_preview": False,
                        })
                    confirmed += 1
            except Exception as e:
                logger.warning(f"Failed to confirm preview {entity_id}: {e}")

        # Clear preview IDs
        config["preview_ids"] = []
        config["preview_confirmed"] = True
        await self.update_job(job_id, config=config)

        return {"success": True, "confirmed": confirmed}

    async def discard_preview(self, job_id: str) -> dict | None:
        """Discard preview items by deleting them."""
        job = await self.get_job(job_id)
        if not job:
            return None

        config = job.config or {}
        preview_ids = config.get("preview_ids", [])

        if not preview_ids:
            return {"success": False, "error": "No preview items to discard"}

        discarded = 0
        for entity_id in preview_ids:
            try:
                await self.entity_svc.delete("post", entity_id)
                discarded += 1
            except Exception as e:
                logger.warning(f"Failed to discard preview {entity_id}: {e}")

        # Clear preview IDs
        config["preview_ids"] = []
        config["preview_discarded"] = True
        await self.update_job(job_id, config=config)

        return {"success": True, "discarded": discarded}
