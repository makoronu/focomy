"""WordPress Import Service - Orchestrates full import with EntityService integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, ImportJob, ImportJobPhase, ImportJobStatus
from ..entity import EntityService
from ..field import field_service
from .analyzer import WordPressAnalyzer
from .importer import ImportConfig, ImportProgress, ImportResult, WordPressImporter
from .media import MediaImporter
from .rest_client import RESTClientConfig, WordPressRESTClient
from .wxr_parser import WXRData, WXRParser

logger = logging.getLogger(__name__)


class WordPressImportService:
    """
    Full WordPress import service with database integration.

    Handles:
    - Job creation and tracking
    - WXR file or REST API as source
    - Progress updates
    - EntityService integration for actual data import
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def create_job(
        self,
        source_type: str,
        source_url: str | None = None,
        source_file: str | None = None,
        config: dict | None = None,
        user_id: str | None = None,
    ) -> ImportJob:
        """Create a new import job."""
        job = ImportJob(
            source_type=source_type,
            source_url=source_url,
            source_file=source_file,
            config=config or {},
            created_by=user_id,
            status=ImportJobStatus.PENDING.value,
            phase=ImportJobPhase.INIT.value,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_job(self, job_id: str) -> ImportJob | None:
        """Get import job by ID."""
        result = await self.db.execute(select(ImportJob).where(ImportJob.id == job_id))
        return result.scalar_one_or_none()

    async def get_active_jobs(self) -> list[ImportJob]:
        """Get all active (non-completed) jobs."""
        result = await self.db.execute(
            select(ImportJob).where(
                ImportJob.status.in_([
                    ImportJobStatus.PENDING.value,
                    ImportJobStatus.ANALYZING.value,
                    ImportJobStatus.IMPORTING.value,
                ])
            )
        )
        return list(result.scalars().all())

    async def update_job(
        self,
        job_id: str,
        status: str | None = None,
        phase: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
        progress_message: str | None = None,
        **kwargs,
    ) -> ImportJob | None:
        """Update import job status and progress."""
        job = await self.get_job(job_id)
        if not job:
            return None

        if status:
            job.status = status
        if phase:
            job.phase = phase
        if progress_current is not None:
            job.progress_current = progress_current
        if progress_total is not None:
            job.progress_total = progress_total
        if progress_message is not None:
            job.progress_message = progress_message

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def analyze(self, job_id: str) -> dict | None:
        """
        Analyze source without importing.

        Updates job with analysis results.
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        try:
            await self.update_job(
                job_id,
                status=ImportJobStatus.ANALYZING.value,
                phase=ImportJobPhase.ANALYZE.value,
                progress_message="Analyzing WordPress data...",
            )

            # Get WXR data from source
            wxr_data = await self._fetch_source_data(job)
            if not wxr_data:
                raise ValueError("Failed to fetch source data")

            # Analyze
            analyzer = WordPressAnalyzer()
            report = analyzer.analyze_data(wxr_data)

            # Convert report to dict
            analysis_dict = {
                "site_url": report.site_url,
                "site_name": report.site_name,
                "wp_version": report.wp_version,
                "language": report.language,
                "posts": {
                    "total": report.posts.total,
                    "published": report.posts.published,
                    "draft": report.posts.draft,
                },
                "pages": {
                    "total": report.pages.total,
                    "published": report.pages.published,
                    "draft": report.pages.draft,
                },
                "media": {
                    "total_count": report.media_stats.total_count,
                    "by_type": report.media_stats.by_type,
                },
                "categories_count": len(report.categories),
                "tags_count": len(report.tags),
                "users_count": report.users_count,
                "comments_count": report.comments_count,
                "menus_count": report.menus_count,
                "custom_post_types": [
                    {"name": cpt.name, "count": cpt.count}
                    for cpt in report.custom_post_types
                ],
                "detected_plugins": [
                    {"name": p.name, "slug": p.slug}
                    for p in report.detected_plugins
                ],
                "warnings": [
                    {"code": w.code, "message": w.message}
                    for w in report.warnings
                ],
                "recommendations": report.recommendations,
                "estimated_time": report.estimated_time,
                "estimated_storage": report.estimated_storage,
            }

            await self.update_job(
                job_id,
                status=ImportJobStatus.PENDING.value,
                phase=ImportJobPhase.INIT.value,
                analysis=analysis_dict,
                progress_message="Analysis complete",
            )

            return analysis_dict

        except Exception as e:
            logger.exception(f"Analysis failed for job {job_id}")
            await self.update_job(
                job_id,
                status=ImportJobStatus.FAILED.value,
                errors=[str(e)],
                progress_message=f"Analysis failed: {str(e)}",
            )
            return None

    async def run_import(self, job_id: str) -> ImportResult | None:
        """
        Run full import.

        This is the main import method that should be called from background task.
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        try:
            await self.update_job(
                job_id,
                status=ImportJobStatus.IMPORTING.value,
                phase=ImportJobPhase.CONNECT.value,
                started_at=datetime.utcnow(),
                progress_message="Starting import...",
            )

            # Get WXR data from source
            wxr_data = await self._fetch_source_data(job)
            if not wxr_data:
                raise ValueError("Failed to fetch source data")

            # Import each type
            result = ImportResult()

            # Authors
            await self.update_job(
                job_id,
                phase=ImportJobPhase.AUTHORS.value,
                progress_current=0,
                progress_total=len(wxr_data.authors),
                progress_message="Importing authors...",
            )
            authors_count = await self._import_authors(job_id, wxr_data)
            result.authors_imported = authors_count

            # Categories
            await self.update_job(
                job_id,
                phase=ImportJobPhase.CATEGORIES.value,
                progress_current=0,
                progress_total=len(wxr_data.categories),
                progress_message="Importing categories...",
            )
            cats_count = await self._import_categories(job_id, wxr_data)
            result.categories_imported = cats_count

            # Tags
            await self.update_job(
                job_id,
                phase=ImportJobPhase.TAGS.value,
                progress_current=0,
                progress_total=len(wxr_data.tags),
                progress_message="Importing tags...",
            )
            tags_count = await self._import_tags(job_id, wxr_data)
            result.tags_imported = tags_count

            # Media
            config = job.config or {}
            if config.get("import_media", True):
                media_posts = [p for p in wxr_data.posts if p.post_type == "attachment"]
                await self.update_job(
                    job_id,
                    phase=ImportJobPhase.MEDIA.value,
                    progress_current=0,
                    progress_total=len(media_posts),
                    progress_message="Importing media...",
                )
                media_count = await self._import_media(job_id, wxr_data, config)
                result.media_imported = media_count

            # Posts
            posts = [p for p in wxr_data.posts if p.post_type == "post"]
            await self.update_job(
                job_id,
                phase=ImportJobPhase.POSTS.value,
                progress_current=0,
                progress_total=len(posts),
                progress_message="Importing posts...",
            )
            posts_count = await self._import_posts(job_id, wxr_data, "post")
            result.posts_imported = posts_count

            # Pages
            pages = [p for p in wxr_data.posts if p.post_type == "page"]
            await self.update_job(
                job_id,
                phase=ImportJobPhase.PAGES.value,
                progress_current=0,
                progress_total=len(pages),
                progress_message="Importing pages...",
            )
            pages_count = await self._import_posts(job_id, wxr_data, "page")
            result.pages_imported = pages_count

            # Menus
            if config.get("import_menus", True) and wxr_data.menus:
                await self.update_job(
                    job_id,
                    phase=ImportJobPhase.MENUS.value,
                    progress_current=0,
                    progress_total=len(wxr_data.menus),
                    progress_message="Importing menus...",
                )
                menus_count = await self._import_menus(job_id, wxr_data)
                result.menus_imported = menus_count

            # Complete
            result.success = True
            await self.update_job(
                job_id,
                status=ImportJobStatus.COMPLETED.value,
                phase=ImportJobPhase.COMPLETE.value,
                completed_at=datetime.utcnow(),
                posts_imported=result.posts_imported,
                pages_imported=result.pages_imported,
                media_imported=result.media_imported,
                categories_imported=result.categories_imported,
                tags_imported=result.tags_imported,
                authors_imported=result.authors_imported,
                menus_imported=result.menus_imported,
                progress_message="Import completed successfully!",
            )

            return result

        except Exception as e:
            logger.exception(f"Import failed for job {job_id}")
            await self.update_job(
                job_id,
                status=ImportJobStatus.FAILED.value,
                completed_at=datetime.utcnow(),
                errors=[str(e)],
                progress_message=f"Import failed: {str(e)}",
            )
            return None

    async def _fetch_source_data(self, job: ImportJob) -> WXRData | None:
        """Fetch WXR data from source."""
        if job.source_type == "wxr":
            if not job.source_file:
                return None
            parser = WXRParser()
            return parser.parse(Path(job.source_file))

        elif job.source_type == "rest_api":
            if not job.source_url:
                return None

            config = job.config or {}
            rest_config = RESTClientConfig(
                site_url=job.source_url,
                username=config.get("username", ""),
                password=config.get("password", ""),
            )

            async with WordPressRESTClient(rest_config) as client:
                return await client.fetch_all(
                    include_drafts=config.get("include_drafts", True),
                    include_media=config.get("import_media", True),
                    include_comments=config.get("import_comments", True),
                    include_menus=config.get("import_menus", True),
                )

        return None

    async def _import_authors(self, job_id: str, wxr_data: WXRData) -> int:
        """Import authors as users."""
        count = 0
        for i, author in enumerate(wxr_data.authors):
            try:
                # Check if user already exists
                existing = await self._find_by_wp_id("user", author.id)
                if existing:
                    continue

                # Create user entity
                user_data = {
                    "name": author.display_name or author.login,
                    "email": author.email or f"{author.login}@imported.local",
                    "role": "author",
                    "wp_id": author.id,
                    "wp_login": author.login,
                }

                await self.entity_svc.create("user", user_data)
                count += 1

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported author: {author.display_name}",
                )

            except Exception as e:
                logger.warning(f"Failed to import author {author.login}: {e}")

        await self.update_job(job_id, authors_imported=count)
        return count

    async def _import_categories(self, job_id: str, wxr_data: WXRData) -> int:
        """Import categories."""
        count = 0

        # Sort by parent to import parents first
        categories = sorted(wxr_data.categories, key=lambda c: c.parent_id)

        for i, cat in enumerate(categories):
            try:
                existing = await self._find_by_wp_id("category", cat.id)
                if existing:
                    continue

                cat_data = {
                    "name": cat.name,
                    "slug": cat.slug,
                    "description": cat.description,
                    "wp_id": cat.id,
                    "wp_parent_id": cat.parent_id,
                }

                await self.entity_svc.create("category", cat_data)
                count += 1

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported category: {cat.name}",
                )

            except Exception as e:
                logger.warning(f"Failed to import category {cat.name}: {e}")

        await self.update_job(job_id, categories_imported=count)
        return count

    async def _import_tags(self, job_id: str, wxr_data: WXRData) -> int:
        """Import tags."""
        count = 0
        for i, tag in enumerate(wxr_data.tags):
            try:
                existing = await self._find_by_wp_id("tag", tag.id)
                if existing:
                    continue

                tag_data = {
                    "name": tag.name,
                    "slug": tag.slug,
                    "description": tag.description,
                    "wp_id": tag.id,
                }

                await self.entity_svc.create("tag", tag_data)
                count += 1

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported tag: {tag.name}",
                )

            except Exception as e:
                logger.warning(f"Failed to import tag {tag.name}: {e}")

        await self.update_job(job_id, tags_imported=count)
        return count

    async def _import_media(
        self,
        job_id: str,
        wxr_data: WXRData,
        config: dict,
    ) -> int:
        """Import media files.

        If config['download_media'] is True, actually downloads the files.
        If config['convert_to_webp'] is True, converts images to WebP format.
        """
        count = 0
        media_posts = [p for p in wxr_data.posts if p.post_type == "attachment"]

        # Initialize MediaImporter if downloading files
        media_importer = None
        download_media = config.get("download_media", False)

        if download_media:
            from pathlib import Path

            upload_dir = Path(config.get("upload_dir", "uploads"))
            base_url = config.get("base_url", "")

            media_importer = MediaImporter(
                upload_dir=upload_dir,
                base_url=base_url,
                convert_to_webp=config.get("convert_to_webp", False),
                webp_quality=config.get("webp_quality", 85),
                max_image_size=config.get("max_image_size", 2048),
                jpeg_quality=config.get("jpeg_quality", 85),
            )

        for i, media in enumerate(media_posts):
            try:
                existing = await self._find_by_wp_id("media", media.id)
                if existing:
                    continue

                # Base media data
                media_data = {
                    "title": media.title,
                    "slug": media.slug,
                    "alt_text": media.postmeta.get("_wp_attachment_image_alt", ""),
                    "caption": media.excerpt,
                    "description": media.content,
                    "source_url": media.guid,
                    "wp_id": media.id,
                }

                # Download and process file if enabled
                if media_importer and media.guid:
                    from .media import MediaItem

                    item = MediaItem(
                        original_url=media.guid,
                        filename=Path(media.guid).name if media.guid else f"media_{media.id}",
                        post_id=media.id,
                        title=media.title,
                        alt_text=media.postmeta.get("_wp_attachment_image_alt", ""),
                    )

                    result = await media_importer.import_media([item])
                    if result.imported:
                        imported = result.imported[0]
                        media_data["filename"] = imported.filename
                        media_data["stored_path"] = imported.new_path
                        media_data["mime_type"] = imported.mime_type
                        media_data["size"] = imported.file_size
                        media_data["width"] = imported.width
                        media_data["height"] = imported.height

                await self.entity_svc.create("media", media_data)
                count += 1

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported media: {media.title[:50] if media.title else 'untitled'}",
                )

            except Exception as e:
                logger.warning(f"Failed to import media {media.id}: {e}")

        await self.update_job(job_id, media_imported=count)
        return count

    async def _import_posts(
        self,
        job_id: str,
        wxr_data: WXRData,
        post_type: str,
    ) -> int:
        """Import posts or pages."""
        count = 0
        posts = [p for p in wxr_data.posts if p.post_type == post_type]

        # Map status
        status_map = {
            "publish": "published",
            "draft": "draft",
            "pending": "pending",
            "private": "private",
            "future": "scheduled",
            "trash": "archived",
        }

        for i, post in enumerate(posts):
            try:
                existing = await self._find_by_wp_id(post_type, post.id)
                if existing:
                    continue

                post_data = {
                    "title": post.title,
                    "slug": post.slug,
                    "content": post.content,
                    "excerpt": post.excerpt,
                    "status": status_map.get(post.status, "draft"),
                    "wp_id": post.id,
                    "wp_author_id": post.author_id,
                    "created_at": post.created_at.isoformat(),
                    "updated_at": post.modified_at.isoformat(),
                }

                # SEO data from Yoast
                if "_yoast_wpseo_title" in post.postmeta:
                    post_data["seo_title"] = post.postmeta["_yoast_wpseo_title"]
                if "_yoast_wpseo_metadesc" in post.postmeta:
                    post_data["seo_description"] = post.postmeta["_yoast_wpseo_metadesc"]

                # Categories and tags as comma-separated slugs
                if post.categories:
                    post_data["category_slugs"] = ",".join(c["slug"] for c in post.categories)
                if post.tags:
                    post_data["tag_slugs"] = ",".join(t["slug"] for t in post.tags)

                await self.entity_svc.create(post_type, post_data)
                count += 1

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported {post_type}: {post.title[:50]}",
                )

            except Exception as e:
                logger.warning(f"Failed to import {post_type} {post.id}: {e}")

        return count

    async def _import_menus(self, job_id: str, wxr_data: WXRData) -> int:
        """Import navigation menus."""
        count = 0
        for menu_name, items in wxr_data.menus.items():
            try:
                # Create menu entity
                menu_data = {
                    "name": menu_name,
                    "slug": menu_name.lower().replace(" ", "-"),
                    "items": [
                        {
                            "title": item.title,
                            "url": item.url,
                            "parent_id": item.parent_id,
                            "order": item.order,
                            "object_type": item.object_type,
                            "object_id": item.object_id,
                        }
                        for item in items
                    ],
                }

                await self.entity_svc.create("menu", menu_data)
                count += 1

                await self.update_job(
                    job_id,
                    progress_current=count,
                    progress_message=f"Imported menu: {menu_name}",
                )

            except Exception as e:
                logger.warning(f"Failed to import menu {menu_name}: {e}")

        await self.update_job(job_id, menus_imported=count)
        return count

    async def _find_by_wp_id(self, entity_type: str, wp_id: int) -> Entity | None:
        """Find entity by WordPress ID."""
        from ...models import EntityValue

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

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel an import job."""
        job = await self.get_job(job_id)
        if not job:
            return False

        if job.status in (ImportJobStatus.COMPLETED.value, ImportJobStatus.FAILED.value):
            return False

        await self.update_job(
            job_id,
            status=ImportJobStatus.CANCELLED.value,
            completed_at=datetime.utcnow(),
            progress_message="Import cancelled by user",
        )
        return True
