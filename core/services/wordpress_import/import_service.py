"""WordPress Import Service - Orchestrates full import with EntityService integration."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import ImportJob, ImportJobPhase, ImportJobStatus
from ...utils import utcnow
from ..block_converter import BlockConverter
from ..entity import EntityService
from .analyzer import WordPressAnalyzer
from .content_sanitizer import ContentSanitizer
from .error_collector import ErrorCollector
from .id_resolver import WpIdResolver
from .import_content import ContentImportMixin
from .import_diff import DiffMixin
from .import_dryrun import DryRunMixin
from .import_entities import EntityImportMixin
from .import_helpers import ImportHelpersMixin
from .import_postprocess import PostProcessMixin
from .importer import ImportResult
from .rest_client import RESTClientConfig, WordPressRESTClient
from .wxr_parser import WXRData, WXRParser

logger = logging.getLogger(__name__)


class WordPressImportService(
    ImportHelpersMixin,
    EntityImportMixin,
    ContentImportMixin,
    DryRunMixin,
    DiffMixin,
    PostProcessMixin,
):
    """Full WordPress import service with database integration.

    Job creation/tracking, WXR/REST API source, progress updates,
    EntityService integration. Mixins: helpers, entities, content,
    dry-run, diff, post-processing.
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
