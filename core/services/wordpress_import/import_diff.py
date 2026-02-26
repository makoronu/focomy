"""Diff detection and differential import operations."""

from __future__ import annotations

import logging

from ...models import ImportJobPhase, ImportJobStatus
from ...utils import utcnow
from .constants import WP_STATUS_MAP
from .wxr_parser import WXRData

logger = logging.getLogger(__name__)


class DiffMixin:
    """Diff detection and differential import methods.

    Mixed into WordPressImportService.
    Requires: self.db, self.entity_svc, self.sanitizer,
              self.update_job(), self.get_job(), self._fetch_source_data(),
              self._find_by_wp_id()
    """

    async def detect_diff(self, job_id: str) -> dict | None:
        """
        Detect differences between WordPress data and database.

        Returns a summary of new/updated/unchanged/deleted items.
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        try:
            await self.update_job(
                job_id,
                status=ImportJobStatus.ANALYZING,
                phase=ImportJobPhase.ANALYZE,
                progress_message="Detecting differences...",
            )

            # Get WXR data from source
            wxr_data = await self._fetch_source_data(job)
            if not wxr_data:
                raise ValueError("Failed to fetch source data")

            # Run diff detection
            from .diff_detector import DiffDetector

            detector = DiffDetector(self.db)
            diff_result = await detector.detect(wxr_data)

            # Store diff result in job config
            config = job.config or {}
            config["diff_result"] = diff_result.to_dict()
            await self.update_job(
                job_id,
                status=ImportJobStatus.PENDING,
                phase=ImportJobPhase.INIT,
                config=config,
                progress_message="Diff detection complete",
            )

            return {
                "success": True,
                **diff_result.to_dict(),
            }

        except Exception as e:
            logger.exception(f"Diff detection failed for job {job_id}")
            return {
                "success": False,
                "error": str(e),
            }

    async def import_diff(
        self,
        job_id: str,
        import_new: bool = True,
        import_updated: bool = True,
        delete_removed: bool = False,
    ) -> dict | None:
        """
        Import only the differences (new and updated items).

        Args:
            job_id: Import job ID
            import_new: Import new items
            import_updated: Import updated items (will update existing)
            delete_removed: Delete items that are no longer in WordPress
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        config = job.config or {}
        diff_data = config.get("diff_result")

        if not diff_data:
            return {
                "success": False,
                "error": "No diff result found. Run detect_diff first.",
            }

        try:
            await self.update_job(
                job_id,
                status=ImportJobStatus.IMPORTING,
                phase=ImportJobPhase.POSTS,
                started_at=utcnow(),
                progress_message="Starting diff import...",
            )

            # Get WXR data again
            wxr_data = await self._fetch_source_data(job)
            if not wxr_data:
                raise ValueError("Failed to fetch source data")

            results = {
                "new_imported": 0,
                "updated": 0,
                "deleted": 0,
                "errors": [],
            }

            # Import new items
            if import_new:
                await self._import_new_from_diff(job_id, wxr_data, diff_data, results)

            # Update existing items
            if import_updated:
                await self._update_from_diff(job_id, wxr_data, diff_data, results)

            # Delete removed items
            if delete_removed:
                await self._delete_from_diff(job_id, diff_data, results)

            await self.update_job(
                job_id,
                status=ImportJobStatus.COMPLETED,
                phase=ImportJobPhase.COMPLETE,
                completed_at=utcnow(),
                progress_message="Diff import complete",
            )

            return {
                "success": True,
                **results,
            }

        except Exception as e:
            logger.exception(f"Diff import failed for job {job_id}")
            await self.update_job(
                job_id,
                status=ImportJobStatus.FAILED,
                completed_at=utcnow(),
                errors=[str(e)],
                progress_message=f"Diff import failed: {str(e)}",
            )
            return {
                "success": False,
                "error": str(e),
            }

    async def _import_new_from_diff(
        self,
        job_id: str,
        wxr_data: WXRData,
        diff_data: dict,
        results: dict,
    ) -> None:
        """Import new items from diff."""
        # Build lookup maps for WXR data
        posts_map = {p.id: p for p in wxr_data.posts if p.post_type == "post"}
        pages_map = {p.id: p for p in wxr_data.posts if p.post_type == "page"}
        cats_map = {c.id: c for c in wxr_data.categories}
        tags_map = {t.id: t for t in wxr_data.tags}

        # Import new posts
        for item in diff_data.get("new", {}).get("posts", []):
            wp_id = item["wp_id"]
            post = posts_map.get(wp_id)
            if post:
                try:
                    # Sanitize content
                    content_result = self.sanitizer.sanitize(post.content or "")
                    excerpt_result = self.sanitizer.sanitize(post.excerpt or "")
                    if content_result.had_issues or excerpt_result.had_issues:
                        logger.warning(f"Sanitized content in new post {wp_id}")

                    await self.entity_svc.create("post", {
                        "title": post.title,
                        "slug": post.slug,
                        "content": content_result.content,
                        "excerpt": excerpt_result.content,
                        "status": WP_STATUS_MAP.get(post.status, "draft"),
                        "wp_id": post.id,
                        "wp_modified": post.modified_at.isoformat() if post.modified_at else None,
                    })
                    results["new_imported"] += 1
                except Exception as e:
                    results["errors"].append(f"Post {wp_id}: {e}")

        # Import new pages
        for item in diff_data.get("new", {}).get("pages", []):
            wp_id = item["wp_id"]
            page = pages_map.get(wp_id)
            if page:
                try:
                    # Sanitize content
                    content_result = self.sanitizer.sanitize(page.content or "")
                    if content_result.had_issues:
                        logger.warning(f"Sanitized content in new page {wp_id}")

                    await self.entity_svc.create("page", {
                        "title": page.title,
                        "slug": page.slug,
                        "content": content_result.content,
                        "status": WP_STATUS_MAP.get(page.status, "draft"),
                        "wp_id": page.id,
                        "wp_modified": page.modified_at.isoformat() if page.modified_at else None,
                    })
                    results["new_imported"] += 1
                except Exception as e:
                    results["errors"].append(f"Page {wp_id}: {e}")

        # Import new categories
        for item in diff_data.get("new", {}).get("categories", []):
            wp_id = item["wp_id"]
            cat = cats_map.get(wp_id)
            if cat:
                try:
                    await self.entity_svc.create("category", {
                        "name": cat.name,
                        "slug": cat.slug,
                        "wp_id": cat.id,
                    })
                    results["new_imported"] += 1
                except Exception as e:
                    results["errors"].append(f"Category {wp_id}: {e}")

        # Import new tags
        for item in diff_data.get("new", {}).get("tags", []):
            wp_id = item["wp_id"]
            tag = tags_map.get(wp_id)
            if tag:
                try:
                    await self.entity_svc.create("tag", {
                        "name": tag.name,
                        "slug": tag.slug,
                        "wp_id": tag.id,
                    })
                    results["new_imported"] += 1
                except Exception as e:
                    results["errors"].append(f"Tag {wp_id}: {e}")

        await self.update_job(
            job_id,
            progress_message=f"Imported {results['new_imported']} new items",
        )

    async def _update_from_diff(
        self,
        job_id: str,
        wxr_data: WXRData,
        diff_data: dict,
        results: dict,
    ) -> None:
        """Update existing items from diff."""
        posts_map = {p.id: p for p in wxr_data.posts if p.post_type == "post"}
        pages_map = {p.id: p for p in wxr_data.posts if p.post_type == "page"}
        cats_map = {c.id: c for c in wxr_data.categories}
        tags_map = {t.id: t for t in wxr_data.tags}

        # Update posts
        for item in diff_data.get("updated", {}).get("posts", []):
            wp_id = item["wp_id"]
            post = posts_map.get(wp_id)
            if post:
                try:
                    existing = await self._find_by_wp_id("post", wp_id)
                    if existing:
                        # Sanitize content
                        content_result = self.sanitizer.sanitize(post.content or "")
                        excerpt_result = self.sanitizer.sanitize(post.excerpt or "")
                        if content_result.had_issues or excerpt_result.had_issues:
                            logger.warning(f"Sanitized content in updated post {wp_id}")

                        await self.entity_svc.update("post", existing.id, {
                            "title": post.title,
                            "slug": post.slug,
                            "content": content_result.content,
                            "excerpt": excerpt_result.content,
                            "status": WP_STATUS_MAP.get(post.status, "draft"),
                            "wp_modified": post.modified_at.isoformat() if post.modified_at else None,
                        })
                        results["updated"] += 1
                except Exception as e:
                    results["errors"].append(f"Update post {wp_id}: {e}")

        # Update pages
        for item in diff_data.get("updated", {}).get("pages", []):
            wp_id = item["wp_id"]
            page = pages_map.get(wp_id)
            if page:
                try:
                    existing = await self._find_by_wp_id("page", wp_id)
                    if existing:
                        # Sanitize content
                        content_result = self.sanitizer.sanitize(page.content or "")
                        if content_result.had_issues:
                            logger.warning(f"Sanitized content in updated page {wp_id}")

                        await self.entity_svc.update("page", existing.id, {
                            "title": page.title,
                            "slug": page.slug,
                            "content": content_result.content,
                            "status": WP_STATUS_MAP.get(page.status, "draft"),
                            "wp_modified": page.modified_at.isoformat() if page.modified_at else None,
                        })
                        results["updated"] += 1
                except Exception as e:
                    results["errors"].append(f"Update page {wp_id}: {e}")

        # Update categories
        for item in diff_data.get("updated", {}).get("categories", []):
            wp_id = item["wp_id"]
            cat = cats_map.get(wp_id)
            if cat:
                try:
                    existing = await self._find_by_wp_id("category", wp_id)
                    if existing:
                        await self.entity_svc.update("category", existing.id, {
                            "name": cat.name,
                            "slug": cat.slug,
                        })
                        results["updated"] += 1
                except Exception as e:
                    results["errors"].append(f"Update category {wp_id}: {e}")

        # Update tags
        for item in diff_data.get("updated", {}).get("tags", []):
            wp_id = item["wp_id"]
            tag = tags_map.get(wp_id)
            if tag:
                try:
                    existing = await self._find_by_wp_id("tag", wp_id)
                    if existing:
                        await self.entity_svc.update("tag", existing.id, {
                            "name": tag.name,
                            "slug": tag.slug,
                        })
                        results["updated"] += 1
                except Exception as e:
                    results["errors"].append(f"Update tag {wp_id}: {e}")

        await self.update_job(
            job_id,
            progress_message=f"Updated {results['updated']} items",
        )

    async def _delete_from_diff(
        self,
        job_id: str,
        diff_data: dict,
        results: dict,
    ) -> None:
        """Delete items that were removed from WordPress."""
        entity_type_map = {
            "posts": "post",
            "pages": "page",
            "media": "media",
            "categories": "category",
            "tags": "tag",
            "authors": "user",
        }

        for diff_type, entity_type in entity_type_map.items():
            for item in diff_data.get("deleted", {}).get(diff_type, []):
                wp_id = item["wp_id"]
                try:
                    existing = await self._find_by_wp_id(entity_type, wp_id)
                    if existing:
                        await self.entity_svc.delete(entity_type, existing.id)
                        results["deleted"] += 1
                except Exception as e:
                    results["errors"].append(f"Delete {diff_type} {wp_id}: {e}")

        await self.update_job(
            job_id,
            progress_message=f"Deleted {results['deleted']} items",
        )
