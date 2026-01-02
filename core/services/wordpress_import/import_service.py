"""WordPress Import Service - Orchestrates full import with EntityService integration."""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import asdict
from datetime import datetime, timezone

from ...utils import utcnow
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, ImportJob, ImportJobPhase, ImportJobStatus
from ..entity import EntityService
from ..field import field_service
from .analyzer import WordPressAnalyzer
from ..block_converter import BlockConverter
from .content_sanitizer import ContentSanitizer, SanitizeResult
from .constants import WP_STATUS_MAP
from .error_collector import ErrorCollector
from .id_resolver import WpIdResolver
from .importer import ImportConfig, ImportProgress, ImportResult, WordPressImporter
from .link_fixer import InternalLinkFixer, URLMapBuilder
from .media import MediaImporter
from .redirects import RedirectGenerator, RedirectReport
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
        self.sanitizer = ContentSanitizer()
        self.block_converter = BlockConverter()
        self.id_resolver = WpIdResolver(self.entity_svc)
        self.error_collector = ErrorCollector()

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
            status=ImportJobStatus.PENDING,
            phase=ImportJobPhase.INIT,
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
                    ImportJobStatus.PENDING,
                    ImportJobStatus.ANALYZING,
                    ImportJobStatus.IMPORTING,
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
                status=ImportJobStatus.ANALYZING,
                phase=ImportJobPhase.ANALYZE,
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
                status=ImportJobStatus.PENDING,
                phase=ImportJobPhase.INIT,
                analysis=analysis_dict,
                progress_message="Analysis complete",
            )

            return analysis_dict

        except Exception as e:
            logger.exception(f"Analysis failed for job {job_id}")
            await self.update_job(
                job_id,
                status=ImportJobStatus.FAILED,
                errors=[str(e)],
                progress_message=f"Analysis failed: {str(e)}",
            )
            return None

    async def run_import(
        self,
        job_id: str,
        resume: bool = False,
    ) -> ImportResult | None:
        """
        Run full import.

        This is the main import method that should be called from background task.

        Args:
            job_id: The import job ID
            resume: If True, skip already processed items (from checkpoint)
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        try:
            if resume:
                checkpoint = await self._get_checkpoint(job_id)
                last_phase = checkpoint.get("last_phase")
                await self.update_job(
                    job_id,
                    status=ImportJobStatus.IMPORTING,
                    progress_message=f"Resuming import from {last_phase or 'beginning'}...",
                )
            else:
                await self.update_job(
                    job_id,
                    status=ImportJobStatus.IMPORTING,
                    phase=ImportJobPhase.CONNECT,
                    started_at=utcnow(),
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
                phase=ImportJobPhase.AUTHORS,
                progress_current=0,
                progress_total=len(wxr_data.authors),
                progress_message="Importing authors...",
            )
            authors_count = await self._import_authors(job_id, wxr_data, resume=resume)
            result.authors_imported = authors_count

            # Categories
            await self.update_job(
                job_id,
                phase=ImportJobPhase.CATEGORIES,
                progress_current=0,
                progress_total=len(wxr_data.categories),
                progress_message="Importing categories...",
            )
            cats_count = await self._import_categories(job_id, wxr_data, resume=resume)
            result.categories_imported = cats_count

            # Tags
            await self.update_job(
                job_id,
                phase=ImportJobPhase.TAGS,
                progress_current=0,
                progress_total=len(wxr_data.tags),
                progress_message="Importing tags...",
            )
            tags_count = await self._import_tags(job_id, wxr_data, resume=resume)
            result.tags_imported = tags_count

            # Media
            config = job.config or {}
            if config.get("import_media", True):
                media_posts = [p for p in wxr_data.posts if p.post_type == "attachment"]
                await self.update_job(
                    job_id,
                    phase=ImportJobPhase.MEDIA,
                    progress_current=0,
                    progress_total=len(media_posts),
                    progress_message="Importing media...",
                )
                media_count = await self._import_media(job_id, wxr_data, config, resume=resume)
                result.media_imported = media_count

            # Posts
            posts = [p for p in wxr_data.posts if p.post_type == "post"]
            await self.update_job(
                job_id,
                phase=ImportJobPhase.POSTS,
                progress_current=0,
                progress_total=len(posts),
                progress_message="Importing posts...",
            )
            posts_count = await self._import_posts(job_id, wxr_data, "post", resume=resume)
            result.posts_imported = posts_count

            # Pages
            pages = [p for p in wxr_data.posts if p.post_type == "page"]
            await self.update_job(
                job_id,
                phase=ImportJobPhase.PAGES,
                progress_current=0,
                progress_total=len(pages),
                progress_message="Importing pages...",
            )
            pages_count = await self._import_posts(job_id, wxr_data, "page", resume=resume)
            result.pages_imported = pages_count

            # Menus
            if config.get("import_menus", True) and wxr_data.menus:
                await self.update_job(
                    job_id,
                    phase=ImportJobPhase.MENUS,
                    progress_current=0,
                    progress_total=len(wxr_data.menus),
                    progress_message="Importing menus...",
                )
                menus_count = await self._import_menus(job_id, wxr_data, resume=resume)
                result.menus_imported = menus_count

            # Output error log
            error_summary = self.error_collector.summary()
            output_dir = Path(config.get("output_dir", "."))
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
            log_path = output_dir / f"import_errors_{job_id}_{timestamp}.log"
            self.error_collector.to_log_file(log_path)
            logger.info(f"Error log written to: {log_path}")

            # Complete
            result.success = True
            error_dict = self.error_collector.to_dict()
            await self.update_job(
                job_id,
                status=ImportJobStatus.COMPLETED,
                phase=ImportJobPhase.COMPLETE,
                completed_at=utcnow(),
                posts_imported=result.posts_imported,
                pages_imported=result.pages_imported,
                media_imported=result.media_imported,
                categories_imported=result.categories_imported,
                tags_imported=result.tags_imported,
                authors_imported=result.authors_imported,
                menus_imported=result.menus_imported,
                progress_message=f"Import completed! Errors: {error_summary['total_errors']}, Skipped: {error_summary['total_skipped']}",
                errors=error_dict,
            )

            # Clear error collector for next import
            self.error_collector.clear()

            return result

        except Exception as e:
            logger.exception(f"Import failed for job {job_id}")

            # Output error log even on failure
            try:
                error_summary = self.error_collector.summary()
                config = job.config or {} if job else {}
                output_dir = Path(config.get("output_dir", "."))
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
                log_path = output_dir / f"import_errors_{job_id}_{timestamp}.log"
                self.error_collector.to_log_file(log_path)
                logger.info(f"Error log written to: {log_path}")
            except Exception as log_error:
                logger.warning(f"Failed to write error log: {log_error}")

            # Add fatal error to collector
            self.error_collector.add_error(
                phase="fatal",
                item_id=0,
                item_title="Import Process",
                error_type="fatal_error",
                message=str(e),
                exc=e,
            )
            error_dict = self.error_collector.to_dict()

            await self.update_job(
                job_id,
                status=ImportJobStatus.FAILED,
                completed_at=utcnow(),
                errors=error_dict,
                progress_message=f"Import failed: {str(e)}",
            )

            # Clear error collector for next import
            self.error_collector.clear()

            return None

    async def _fetch_source_data(self, job: ImportJob) -> WXRData | None:
        """Fetch WXR data from source."""
        if job.source_type == "wxr":
            if not job.source_file:
                return None
            parser = WXRParser()
            return parser.parse(Path(job.source_file))

        elif job.source_type == "rest":
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

    async def _import_authors(
        self,
        job_id: str,
        wxr_data: WXRData,
        resume: bool = False,
    ) -> int:
        """Import authors as users."""
        count = 0
        skipped = 0
        for i, author in enumerate(wxr_data.authors):
            try:
                # Skip if already processed in previous run
                if resume and await self._is_processed(job_id, "authors", author.id):
                    skipped += 1
                    continue

                # Check if user already exists
                existing = await self._find_by_wp_id("user", author.id)
                if existing:
                    self.error_collector.add_skip(
                        phase="authors",
                        item_id=author.id,
                        item_title=author.display_name or author.login,
                        reason="already_exists",
                    )
                    await self._save_checkpoint(job_id, "authors", author.id, "authors")
                    continue

                # Generate random password (required field)
                random_password = secrets.token_urlsafe(16)

                # Create user entity
                user_data = {
                    "name": author.display_name or author.login,
                    "email": author.email or f"{author.login}@imported.local",
                    "password": random_password,
                    "role": "author",
                    "wp_id": author.id,
                }

                await self.entity_svc.create("user", user_data)
                count += 1

                # Save checkpoint after successful import
                await self._save_checkpoint(job_id, "authors", author.id, "authors")

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported author: {author.display_name or author.login}",
                )

            except Exception as e:
                self.error_collector.add_error(
                    phase="authors",
                    item_id=author.id,
                    item_title=author.display_name or author.login,
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"login": author.login, "email": author.email},
                )

        await self.update_job(job_id, authors_imported=count)
        if skipped:
            logger.info(f"Skipped {skipped} already processed authors")
        return count

    async def _import_categories(
        self,
        job_id: str,
        wxr_data: WXRData,
        resume: bool = False,
    ) -> int:
        """Import categories."""
        count = 0
        skipped = 0

        # Sort by parent to import parents first
        categories = sorted(wxr_data.categories, key=lambda c: c.parent_id)

        for i, cat in enumerate(categories):
            try:
                # Skip if already processed in previous run
                if resume and await self._is_processed(job_id, "categories", cat.id):
                    skipped += 1
                    continue

                existing = await self._find_by_wp_id("category", cat.id)
                if existing:
                    self.error_collector.add_skip(
                        phase="categories",
                        item_id=cat.id,
                        item_title=cat.name,
                        reason="already_exists",
                    )
                    await self._save_checkpoint(job_id, "categories", cat.id, "categories")
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

                # Save checkpoint after successful import
                await self._save_checkpoint(job_id, "categories", cat.id, "categories")

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported category: {cat.name}",
                )

            except Exception as e:
                self.error_collector.add_error(
                    phase="categories",
                    item_id=cat.id,
                    item_title=cat.name,
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"slug": cat.slug},
                )

        await self.update_job(job_id, categories_imported=count)
        if skipped:
            logger.info(f"Skipped {skipped} already processed categories")
        return count

    async def _import_tags(
        self,
        job_id: str,
        wxr_data: WXRData,
        resume: bool = False,
    ) -> int:
        """Import tags."""
        count = 0
        skipped = 0
        for i, tag in enumerate(wxr_data.tags):
            try:
                # Skip if already processed in previous run
                if resume and await self._is_processed(job_id, "tags", tag.id):
                    skipped += 1
                    continue

                existing = await self._find_by_wp_id("tag", tag.id)
                if existing:
                    self.error_collector.add_skip(
                        phase="tags",
                        item_id=tag.id,
                        item_title=tag.name,
                        reason="already_exists",
                    )
                    await self._save_checkpoint(job_id, "tags", tag.id, "tags")
                    continue

                tag_data = {
                    "name": tag.name,
                    "slug": tag.slug,
                    "description": tag.description,
                    "wp_id": tag.id,
                }

                await self.entity_svc.create("tag", tag_data)
                count += 1

                # Save checkpoint after successful import
                await self._save_checkpoint(job_id, "tags", tag.id, "tags")

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported tag: {tag.name}",
                )

            except Exception as e:
                self.error_collector.add_error(
                    phase="tags",
                    item_id=tag.id,
                    item_title=tag.name,
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"slug": tag.slug},
                )

        await self.update_job(job_id, tags_imported=count)
        if skipped:
            logger.info(f"Skipped {skipped} already processed tags")
        return count

    async def _import_media(
        self,
        job_id: str,
        wxr_data: WXRData,
        config: dict,
        resume: bool = False,
    ) -> int:
        """Import media files.

        If config['download_media'] is True, actually downloads the files.
        If config['convert_to_webp'] is True, converts images to WebP format.
        """
        count = 0
        skipped = 0
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
                # Skip if already processed in previous run
                if resume and await self._is_processed(job_id, "media", media.id):
                    skipped += 1
                    continue

                existing = await self._find_by_wp_id("media", media.id)
                if existing:
                    self.error_collector.add_skip(
                        phase="media",
                        item_id=media.id,
                        item_title=media.title or "untitled",
                        reason="already_exists",
                    )
                    await self._save_checkpoint(job_id, "media", media.id, "media")
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

                new_url = None  # Track new URL for id_resolver mapping

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
                        new_url = imported.new_url

                await self.entity_svc.create("media", media_data)
                count += 1

                # Add to id_resolver mapping for featured_image resolution
                if new_url:
                    self.id_resolver.add_media_mapping(media.id, new_url)
                elif media.guid:
                    # Use original URL if not downloaded
                    self.id_resolver.add_media_mapping(media.id, media.guid)

                # Save checkpoint after successful import
                await self._save_checkpoint(job_id, "media", media.id, "media")

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported media: {media.title[:50] if media.title else 'untitled'}",
                )

            except Exception as e:
                self.error_collector.add_error(
                    phase="media",
                    item_id=media.id,
                    item_title=media.title or "untitled",
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"source_url": media.guid},
                )

        await self.update_job(job_id, media_imported=count)
        if skipped:
            logger.info(f"Skipped {skipped} already processed media")
        return count

    async def _import_posts(
        self,
        job_id: str,
        wxr_data: WXRData,
        post_type: str,
        resume: bool = False,
    ) -> int:
        """Import posts or pages."""
        count = 0
        skipped = 0
        posts = [p for p in wxr_data.posts if p.post_type == post_type]

        # Checkpoint key: "posts" or "pages"
        checkpoint_key = "posts" if post_type == "post" else "pages"

        for i, post in enumerate(posts):
            try:
                # Skip if already processed in previous run
                if resume and await self._is_processed(job_id, checkpoint_key, post.id):
                    skipped += 1
                    continue

                existing = await self._find_by_wp_id(post_type, post.id)
                if existing:
                    self.error_collector.add_skip(
                        phase=checkpoint_key,
                        item_id=post.id,
                        item_title=post.title,
                        reason="already_exists",
                    )
                    await self._save_checkpoint(job_id, checkpoint_key, post.id, checkpoint_key)
                    continue

                # Sanitize content and excerpt
                content_result = self.sanitizer.sanitize(post.content or "")
                excerpt_result = self.sanitizer.sanitize(post.excerpt or "")

                # Log warnings if dangerous content was found
                if content_result.had_issues:
                    self.error_collector.add_warning(
                        phase=checkpoint_key,
                        item_id=post.id,
                        item_title=post.title,
                        warning_type="sanitized_content",
                        message=f"Sanitized {len(content_result.warnings)} dangerous elements",
                    )
                if excerpt_result.had_issues:
                    self.error_collector.add_warning(
                        phase=checkpoint_key,
                        item_id=post.id,
                        item_title=post.title,
                        warning_type="sanitized_excerpt",
                        message=f"Sanitized {len(excerpt_result.warnings)} dangerous elements in excerpt",
                    )

                # Convert HTML to Editor.js blocks
                body_blocks = self.block_converter.convert(content_result.content)

                post_data = {
                    "title": post.title,
                    "slug": post.slug,
                    "body": body_blocks,
                    "excerpt": excerpt_result.content,
                    "status": WP_STATUS_MAP.get(post.status, "draft"),
                    "wp_id": post.id,
                }

                # SEO data from Yoast
                if "_yoast_wpseo_title" in post.postmeta:
                    post_data["seo_title"] = post.postmeta["_yoast_wpseo_title"]
                if "_yoast_wpseo_metadesc" in post.postmeta:
                    post_data["seo_description"] = post.postmeta["_yoast_wpseo_metadesc"]

                # Featured image
                thumbnail_id = post.postmeta.get("_thumbnail_id")
                if thumbnail_id:
                    try:
                        thumbnail_id_int = int(thumbnail_id)
                        featured_url = self.id_resolver.resolve_media(thumbnail_id_int)
                        if featured_url:
                            post_data["featured_image"] = featured_url
                    except (ValueError, TypeError):
                        pass

                # Resolve author (required for post)
                author_id = await self.id_resolver.resolve_user(post.author_id)
                if not author_id:
                    self.error_collector.add_skip(
                        phase=checkpoint_key,
                        item_id=post.id,
                        item_title=post.title,
                        reason="no_author",
                        context={"wp_author_id": post.author_id},
                    )
                    await self._save_checkpoint(job_id, checkpoint_key, post.id, checkpoint_key)
                    continue

                post_data["post_author"] = author_id

                # post-specific relations
                if post_type == "post":
                    # channel (required)
                    channel_id = await self.id_resolver.get_default_channel()
                    post_data["post_channel"] = channel_id

                    # categories (optional)
                    if post.categories:
                        cat_slugs = [c["slug"] for c in post.categories]
                        category_ids = await self.id_resolver.resolve_categories(cat_slugs)
                        if category_ids:
                            post_data["post_categories"] = category_ids

                    # tags (optional)
                    if post.tags:
                        tag_slugs = [t["slug"] for t in post.tags]
                        tag_ids = await self.id_resolver.resolve_tags(tag_slugs)
                        if tag_ids:
                            post_data["post_tags"] = tag_ids

                await self.entity_svc.create(post_type, post_data)
                count += 1

                # Save checkpoint after successful import
                await self._save_checkpoint(job_id, checkpoint_key, post.id, checkpoint_key)

                await self.update_job(
                    job_id,
                    progress_current=i + 1,
                    progress_message=f"Imported {post_type}: {post.title[:50]}",
                )

            except Exception as e:
                self.error_collector.add_error(
                    phase=checkpoint_key,
                    item_id=post.id,
                    item_title=post.title,
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"slug": post.slug, "status": post.status},
                )

        if skipped:
            logger.info(f"Skipped {skipped} already processed {post_type}s")
        return count

    async def _import_menus(
        self,
        job_id: str,
        wxr_data: WXRData,
        resume: bool = False,
    ) -> int:
        """Import navigation menus."""
        count = 0
        skipped = 0
        for menu_name, items in wxr_data.menus.items():
            try:
                # Skip if already processed in previous run (use menu_name as ID)
                if resume and await self._is_menu_processed(job_id, menu_name):
                    skipped += 1
                    continue

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

                # Save checkpoint after successful import
                await self._save_menu_checkpoint(job_id, menu_name)

                await self.update_job(
                    job_id,
                    progress_current=count,
                    progress_message=f"Imported menu: {menu_name}",
                )

            except Exception as e:
                self.error_collector.add_error(
                    phase="menus",
                    item_id=menu_name,
                    item_title=menu_name,
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"items_count": len(items)},
                )

        await self.update_job(job_id, menus_imported=count)
        if skipped:
            logger.info(f"Skipped {skipped} already processed menus")
        return count

    async def _is_menu_processed(self, job_id: str, menu_name: str) -> bool:
        """Check if a menu was already processed (uses name instead of ID)."""
        checkpoint = await self._get_checkpoint(job_id)
        return menu_name in checkpoint.get("menus", [])

    async def _save_menu_checkpoint(self, job_id: str, menu_name: str) -> None:
        """Save a processed menu to checkpoint (uses name instead of ID)."""
        job = await self.get_job(job_id)
        if not job:
            return

        checkpoint = job.checkpoint or {
            "authors": [],
            "categories": [],
            "tags": [],
            "media": [],
            "posts": [],
            "pages": [],
            "menus": [],
            "last_phase": None,
        }

        if "menus" not in checkpoint:
            checkpoint["menus"] = []

        if menu_name not in checkpoint["menus"]:
            checkpoint["menus"].append(menu_name)

        checkpoint["last_phase"] = "menus"

        await self.update_job(job_id, checkpoint=checkpoint)

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

    async def _find_by_slug(self, entity_type: str, slug: str) -> Entity | None:
        """Find entity by slug."""
        from ...models import EntityValue

        result = await self.db.execute(
            select(Entity)
            .join(EntityValue)
            .where(
                Entity.type == entity_type,
                EntityValue.field_name == "slug",
                EntityValue.value_text == slug,
                Entity.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_checkpoint(self, job_id: str) -> dict:
        """Get checkpoint data for a job."""
        job = await self.get_job(job_id)
        if not job or not job.checkpoint:
            return {
                "authors": [],
                "categories": [],
                "tags": [],
                "media": [],
                "posts": [],
                "pages": [],
                "menus": [],
                "last_phase": None,
            }
        return job.checkpoint

    async def _save_checkpoint(
        self,
        job_id: str,
        item_type: str,
        wp_id: int,
        phase: str | None = None,
    ) -> None:
        """Save a processed item to checkpoint."""
        job = await self.get_job(job_id)
        if not job:
            return

        checkpoint = job.checkpoint or {
            "authors": [],
            "categories": [],
            "tags": [],
            "media": [],
            "posts": [],
            "pages": [],
            "menus": [],
            "last_phase": None,
        }

        if item_type in checkpoint and wp_id not in checkpoint[item_type]:
            checkpoint[item_type].append(wp_id)

        if phase:
            checkpoint["last_phase"] = phase

        await self.update_job(job_id, checkpoint=checkpoint)

    async def _is_processed(self, job_id: str, item_type: str, wp_id: int) -> bool:
        """Check if an item was already processed in a previous run."""
        checkpoint = await self._get_checkpoint(job_id)
        return wp_id in checkpoint.get(item_type, [])

    async def resume_import(self, job_id: str) -> dict | None:
        """
        Resume a failed or cancelled import from the last checkpoint.

        Returns the result of continuing the import.
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        if job.status not in (
            ImportJobStatus.FAILED,
            ImportJobStatus.CANCELLED,
        ):
            return {
                "success": False,
                "error": f"Cannot resume job with status: {job.status}",
            }

        checkpoint = await self._get_checkpoint(job_id)
        last_phase = checkpoint.get("last_phase")

        logger.info(f"Resuming import job {job_id} from phase: {last_phase}")

        # Re-run the import (it will skip already processed items)
        return await self.run_import(job_id, resume=True)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel an import job."""
        job = await self.get_job(job_id)
        if not job:
            return False

        if job.status in (ImportJobStatus.COMPLETED, ImportJobStatus.FAILED):
            return False

        await self.update_job(
            job_id,
            status=ImportJobStatus.CANCELLED,
            completed_at=utcnow(),
            progress_message="Import cancelled by user",
        )
        return True

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
                from ...models import EntityValue
                from sqlalchemy import select

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
        media_map = {p.id: p for p in wxr_data.posts if p.post_type == "attachment"}
        cats_map = {c.id: c for c in wxr_data.categories}
        tags_map = {t.id: t for t in wxr_data.tags}
        authors_map = {a.id: a for a in wxr_data.authors}

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

    async def _get_entity_field(self, entity_id: str, field_name: str) -> str | None:
        """Get a string field value from an entity."""
        result = await self.db.execute(
            select(EntityValue).where(
                EntityValue.entity_id == entity_id,
                EntityValue.field_name == field_name,
            )
        )
        ev = result.scalar_one_or_none()
        if ev:
            return ev.value_string or ev.value_text
        return None
