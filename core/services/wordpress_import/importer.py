"""WordPress Importer - Main orchestration for WordPress site migration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .acf import ACFConverter
from .constants import WP_STATUS_MAP
from .analyzer import AnalysisReport, WordPressAnalyzer
from .error_collector import ErrorCollector
from .id_resolver import WpIdResolver
from .media import MediaImporter, MediaImportResult, MediaItem
from .redirects import RedirectGenerator, RedirectReport
from .wxr_parser import WXRData, WXRParser, WXRPost
from ..block_converter import block_converter

logger = logging.getLogger(__name__)


@dataclass
class ImportConfig:
    """Configuration for WordPress import."""

    # File paths
    wxr_file: Path | None = None
    upload_dir: Path = Path("uploads")
    output_dir: Path = Path("import_output")

    # Site settings
    old_base_url: str = ""
    new_base_url: str = ""
    new_post_prefix: str = "/blog"
    new_page_prefix: str = "/page"

    # Import options
    import_posts: bool = True
    import_pages: bool = True
    import_media: bool = True
    import_comments: bool = True
    import_authors: bool = True
    import_categories: bool = True
    import_tags: bool = True
    import_menus: bool = True

    # Media options
    download_media: bool = True
    max_concurrent_downloads: int = 5
    optimize_images: bool = True
    max_image_size: int = 2048
    jpeg_quality: int = 85

    # ACF options
    convert_acf: bool = True
    acf_export_file: Path | None = None

    # Redirect options
    generate_redirects: bool = True
    redirect_format: str = "yaml"  # yaml, json, nginx, apache

    # Processing options
    batch_size: int = 100
    skip_drafts: bool = False
    skip_private: bool = False
    default_author_id: str = ""

    # Checkpoint
    checkpoint_file: Path | None = None
    resume_from_checkpoint: bool = False


@dataclass
class ImportProgress:
    """Track import progress."""

    phase: str = ""
    current: int = 0
    total: int = 0
    message: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """Complete import result."""

    success: bool = True
    analysis: AnalysisReport | None = None
    posts_imported: int = 0
    pages_imported: int = 0
    media_imported: int = 0
    comments_imported: int = 0
    authors_imported: int = 0
    categories_imported: int = 0
    tags_imported: int = 0
    menus_imported: int = 0
    redirects_generated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    media_result: MediaImportResult | None = None
    redirect_report: RedirectReport | None = None
    duration_seconds: float = 0
    output_files: list[str] = field(default_factory=list)


class WordPressImporter:
    """
    Main WordPress import orchestrator.

    Handles:
    - WXR file parsing
    - Site analysis
    - Content import (posts, pages, categories, tags)
    - Media download and processing
    - ACF field conversion
    - Redirect generation
    - Checkpoint/resume capability
    """

    def __init__(
        self,
        config: ImportConfig,
        content_service: Any = None,
        media_service: Any = None,
    ):
        """
        Initialize WordPressImporter.

        Args:
            config: Import configuration
            content_service: Focomy content service for saving data
            media_service: Focomy media service for file handling
        """
        self.config = config
        self.content_service = content_service
        self.media_service = media_service

        self._parser = WXRParser()
        self._analyzer = WordPressAnalyzer()
        self._media_importer: MediaImporter | None = None
        self._acf_converter = ACFConverter()
        self._redirect_generator: RedirectGenerator | None = None
        self._id_resolver: WpIdResolver | None = None
        self._error_collector = ErrorCollector()

        self._wxr_data: WXRData | None = None
        self._analysis: AnalysisReport | None = None
        self._checkpoint: dict = {}
        self._progress_callback: callable | None = None
        self._media_items: list[MediaItem] = []

        # Setup output directory
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    def set_progress_callback(self, callback: callable):
        """Set callback for progress updates."""
        self._progress_callback = callback

    def _report_progress(self, progress: ImportProgress):
        """Report progress to callback."""
        if self._progress_callback:
            self._progress_callback(progress)

    async def analyze(self) -> AnalysisReport:
        """
        Analyze WordPress export without importing.

        Returns:
            AnalysisReport with site statistics and recommendations
        """
        if not self.config.wxr_file:
            raise ValueError("WXR file path not configured")

        # Parse WXR
        self._wxr_data = self._parser.parse(self.config.wxr_file)

        # Analyze
        self._analysis = self._analyzer.analyze(self._wxr_data)

        return self._analysis

    async def run(self) -> ImportResult:
        """
        Execute full WordPress import.

        Returns:
            ImportResult with complete import statistics
        """
        start_time = datetime.now(timezone.utc)
        result = ImportResult()

        try:
            # Load checkpoint if resuming
            if self.config.resume_from_checkpoint and self.config.checkpoint_file:
                self._load_checkpoint()

            # Phase 1: Parse WXR
            self._report_progress(
                ImportProgress(
                    phase="parsing",
                    message="Parsing WordPress export file...",
                )
            )

            if not self._wxr_data:
                self._wxr_data = self._parser.parse(self.config.wxr_file)

            # Phase 2: Analyze
            self._report_progress(
                ImportProgress(
                    phase="analyzing",
                    message="Analyzing site content...",
                )
            )

            if not self._analysis:
                self._analysis = self._analyzer.analyze(self._wxr_data)

            result.analysis = self._analysis

            # Setup components
            self._setup_components()

            # Phase 3: Import authors
            if self.config.import_authors:
                result.authors_imported = await self._import_authors()

            # Phase 4: Import categories
            if self.config.import_categories:
                result.categories_imported = await self._import_categories()

            # Phase 5: Import tags
            if self.config.import_tags:
                result.tags_imported = await self._import_tags()

            # Phase 6: Import media
            if self.config.import_media and self.config.download_media:
                media_result = await self._import_media()
                result.media_result = media_result
                result.media_imported = len(media_result.imported)

                # Build media ID mapping for featured image resolution
                if self._id_resolver and self._media_items:
                    self._id_resolver.set_media_mapping(self._media_items, media_result)

            # Phase 7: Import posts
            if self.config.import_posts:
                result.posts_imported = await self._import_posts("post")

            # Phase 8: Import pages
            if self.config.import_pages:
                result.pages_imported = await self._import_posts("page")

            # Phase 9: Import menus
            if self.config.import_menus:
                result.menus_imported = await self._import_menus()

            # Phase 10: Generate redirects
            if self.config.generate_redirects:
                redirect_report = self._generate_redirects()
                result.redirect_report = redirect_report
                result.redirects_generated = len(redirect_report.redirects)

            # Phase 11: Export results
            output_files = await self._export_results(result)
            result.output_files = output_files

            result.success = not self._error_collector.has_errors()
            result.errors = self._analysis.warnings if self._analysis else []

        except Exception as e:
            logger.exception("Import failed")
            result.success = False
            result.errors.append(str(e))
            self._error_collector.add_error(
                phase="global",
                item_id=0,
                item_title="Import Process",
                error_type="fatal",
                message=str(e),
                exc=e,
            )

        # Calculate duration
        result.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Phase 12: Write error log
        if self._error_collector.has_errors() or self._error_collector.skipped:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = self.config.output_dir / f"import_errors_{timestamp}.log"
            json_file = self.config.output_dir / f"import_errors_{timestamp}.json"

            self._error_collector.to_log_file(log_file)
            self._error_collector.to_json(json_file)

            result.output_files.append(str(log_file))
            result.output_files.append(str(json_file))

            # Log summary
            logger.info(self._error_collector.print_summary())
            logger.info(f"Error details: {log_file}")

        return result

    def _setup_components(self):
        """Setup import components."""
        # Media importer
        if self.config.download_media:
            self._media_importer = MediaImporter(
                upload_dir=self.config.upload_dir,
                base_url=self.config.new_base_url,
                max_concurrent=self.config.max_concurrent_downloads,
                max_image_size=self.config.max_image_size,
                jpeg_quality=self.config.jpeg_quality,
            )

        # Redirect generator
        if self.config.generate_redirects:
            self._redirect_generator = RedirectGenerator(
                old_base_url=self.config.old_base_url or self._wxr_data.site.base_blog_url,
                new_base_url=self.config.new_base_url,
            )

        # ID resolver for WP -> Focomy ID mapping
        if self.content_service:
            self._id_resolver = WpIdResolver(self.content_service)

        # Load ACF field groups if provided
        if self.config.convert_acf and self.config.acf_export_file:
            acf_data = json.loads(self.config.acf_export_file.read_text())
            self._acf_converter.parse_field_groups(acf_data)

    async def _import_authors(self) -> int:
        """Import WordPress authors."""
        self._report_progress(
            ImportProgress(
                phase="authors",
                total=len(self._wxr_data.authors),
                message="Importing authors...",
            )
        )

        count = 0
        for i, author in enumerate(self._wxr_data.authors):
            self._report_progress(
                ImportProgress(
                    phase="authors",
                    current=i + 1,
                    total=len(self._wxr_data.authors),
                    message=f"Importing author: {author.display_name}",
                )
            )

            try:
                author_data = {
                    "wp_id": author.id,
                    "login": author.login,
                    "email": author.email,
                    "display_name": author.display_name,
                    "first_name": author.first_name,
                    "last_name": author.last_name,
                }

                if self.content_service:
                    await self.content_service.create("author", author_data)

                count += 1
            except Exception as e:
                self._error_collector.add_error(
                    phase="authors",
                    item_id=author.id,
                    item_title=author.display_name or author.login,
                    error_type="create_failed",
                    message=str(e),
                    exc=e,
                    context={"email": author.email},
                )

            self._save_checkpoint("authors", i + 1)

        return count

    async def _import_categories(self) -> int:
        """Import WordPress categories."""
        self._report_progress(
            ImportProgress(
                phase="categories",
                total=len(self._wxr_data.categories),
                message="Importing categories...",
            )
        )

        count = 0
        for i, cat in enumerate(self._wxr_data.categories):
            self._report_progress(
                ImportProgress(
                    phase="categories",
                    current=i + 1,
                    total=len(self._wxr_data.categories),
                    message=f"Importing category: {cat.name}",
                )
            )

            try:
                cat_data = {
                    "wp_id": cat.id,
                    "name": cat.name,
                    "slug": cat.slug,
                    "description": cat.description,
                    "parent_wp_id": cat.parent_id,
                }

                if self.content_service:
                    await self.content_service.create("category", cat_data)

                count += 1
            except Exception as e:
                self._error_collector.add_error(
                    phase="categories",
                    item_id=cat.id,
                    item_title=cat.name,
                    error_type="create_failed",
                    message=str(e),
                    exc=e,
                    context={"slug": cat.slug},
                )

            self._save_checkpoint("categories", i + 1)

        return count

    async def _import_tags(self) -> int:
        """Import WordPress tags."""
        self._report_progress(
            ImportProgress(
                phase="tags",
                total=len(self._wxr_data.tags),
                message="Importing tags...",
            )
        )

        count = 0
        for i, tag in enumerate(self._wxr_data.tags):
            self._report_progress(
                ImportProgress(
                    phase="tags",
                    current=i + 1,
                    total=len(self._wxr_data.tags),
                    message=f"Importing tag: {tag.name}",
                )
            )

            try:
                tag_data = {
                    "wp_id": tag.id,
                    "name": tag.name,
                    "slug": tag.slug,
                    "description": tag.description,
                }

                if self.content_service:
                    await self.content_service.create("tag", tag_data)

                count += 1
            except Exception as e:
                self._error_collector.add_error(
                    phase="tags",
                    item_id=tag.id,
                    item_title=tag.name,
                    error_type="create_failed",
                    message=str(e),
                    exc=e,
                    context={"slug": tag.slug},
                )

            self._save_checkpoint("tags", i + 1)

        return count

    async def _import_media(self) -> MediaImportResult:
        """Import WordPress media files."""
        if not self._media_importer:
            return MediaImportResult()

        # Collect media items from attachments
        self._media_items = []
        for post in self._wxr_data.posts:
            if post.post_type == "attachment":
                self._media_items.append(
                    MediaItem(
                        original_url=post.guid or post.link,
                        filename=post.slug or f"media_{post.id}",
                        post_id=post.id,
                        title=post.title,
                        alt_text=post.postmeta.get("_wp_attachment_image_alt", ""),
                        caption=post.excerpt,
                        description=post.content,
                    )
                )

        self._report_progress(
            ImportProgress(
                phase="media",
                total=len(self._media_items),
                message="Downloading media files...",
            )
        )

        def progress_callback(current, total, item):
            self._report_progress(
                ImportProgress(
                    phase="media",
                    current=current,
                    total=total,
                    message=f"Downloading: {item.filename}",
                )
            )

        result = await self._media_importer.import_media(
            self._media_items,
            progress_callback=progress_callback,
        )

        return result

    async def _import_posts(self, post_type: str) -> int:
        """Import WordPress posts or pages."""
        posts = [p for p in self._wxr_data.posts if p.post_type == post_type]

        # Filter by status
        if self.config.skip_drafts:
            posts = [p for p in posts if p.status != "draft"]
        if self.config.skip_private:
            posts = [p for p in posts if p.status != "private"]

        self._report_progress(
            ImportProgress(
                phase=post_type,
                total=len(posts),
                message=f"Importing {post_type}s...",
            )
        )

        count = 0
        for i, post in enumerate(posts):
            self._report_progress(
                ImportProgress(
                    phase=post_type,
                    current=i + 1,
                    total=len(posts),
                    message=f"Importing: {post.title[:50]}",
                )
            )

            try:
                # Rewrite media URLs in raw HTML first
                content = post.content
                if self._media_importer and self._media_items:
                    # Get url_mapping from id_resolver if available
                    url_mapping = {}
                    if self._id_resolver:
                        url_mapping = {
                            item.original_url: self._id_resolver.resolve_media(item.post_id)
                            for item in self._media_items
                            if self._id_resolver.resolve_media(item.post_id)
                        }
                    if url_mapping:
                        content = self._media_importer.rewrite_content_urls(
                            content,
                            url_mapping,
                            self.config.old_base_url,
                        )

                # Transform post data (converts content to Editor.js blocks)
                # Returns (fields_dict, relations_dict)
                post_data, relations_data = self._transform_post_with_content(post, content)

                # Convert ACF fields
                if self.config.convert_acf:
                    acf_groups = self._acf_converter._field_groups
                    post_data["acf_fields"] = self._acf_converter.convert_post_meta(
                        post.postmeta,
                        acf_groups,
                    )

                # S4: Set relations
                if self._id_resolver:
                    # author解決（post/page共通、relation名は異なる）
                    author_relation = f"{post_type}_author"
                    author_id = None
                    if relations_data.get("author_wp_id"):
                        author_id = await self._id_resolver.resolve_user(
                            relations_data["author_wp_id"]
                        )

                    if author_id:
                        post_data[author_relation] = author_id
                    elif self.config.default_author_id:
                        post_data[author_relation] = self.config.default_author_id
                    else:
                        self._error_collector.add_skip(
                            phase=post_type,
                            item_id=post.id,
                            item_title=post.title,
                            reason="no_author",
                            context={"author_wp_id": relations_data.get("author_wp_id")},
                        )
                        self._save_checkpoint(post_type, i + 1)
                        continue

                    # post専用のリレーション
                    if post_type == "post":
                        # channel（required）
                        channel_id = await self._id_resolver.get_default_channel()
                        post_data["post_channel"] = channel_id

                        # categories（optional）
                        category_ids = await self._id_resolver.resolve_categories(
                            relations_data["category_slugs"]
                        )
                        if category_ids:
                            post_data["post_categories"] = category_ids

                        # tags（optional）
                        tag_ids = await self._id_resolver.resolve_tags(
                            relations_data["tag_slugs"]
                        )
                        if tag_ids:
                            post_data["post_tags"] = tag_ids

                if self.content_service:
                    await self.content_service.create(post_type, post_data)

                count += 1

            except Exception as e:
                self._error_collector.add_error(
                    phase=post_type,
                    item_id=post.id,
                    item_title=post.title,
                    error_type="import_failed",
                    message=str(e),
                    exc=e,
                    context={"slug": post.slug, "status": post.status},
                )

            self._save_checkpoint(post_type, i + 1)

        return count

    def _transform_post_with_content(
        self, post: WXRPost, content: str
    ) -> tuple[dict, dict]:
        """Transform WXR post to Focomy format.

        Args:
            post: WXR post data
            content: HTML content (may have rewritten URLs)

        Returns:
            Tuple of (fields_dict, relations_dict)
            - fields_dict: Fields for EntityService.create()
            - relations_dict: Data for relation resolution in S4
        """
        # Convert HTML content to Editor.js blocks
        body_blocks = block_converter.convert(content)

        # Resolve featured image WP attachment ID to URL
        featured_image_url = None
        thumbnail_id = post.postmeta.get("_thumbnail_id")
        if thumbnail_id and self._id_resolver:
            try:
                wp_id = int(thumbnail_id)
                featured_image_url = self._id_resolver.resolve_media(wp_id)
            except (ValueError, TypeError):
                logger.warning(f"Invalid thumbnail_id: {thumbnail_id}")

        # Flatten SEO from Yoast meta
        seo_title = post.postmeta.get("_yoast_wpseo_title", "")
        seo_description = post.postmeta.get("_yoast_wpseo_metadesc", "")

        # Fields dict (only fields in post.yaml)
        fields = {
            "wp_id": post.id,
            "title": post.title,
            "slug": post.slug,
            "body": body_blocks,
            "excerpt": post.excerpt,
            "status": WP_STATUS_MAP.get(post.status, "draft"),
            "published_at": post.created_at.isoformat() if post.created_at else None,
            "featured_image": featured_image_url,
            "seo_title": seo_title,
            "seo_description": seo_description,
        }

        # Relations dict (for S4 to resolve)
        relations = {
            "author_wp_id": post.author_id,
            "category_slugs": [c["slug"] for c in post.categories],
            "tag_slugs": [t["slug"] for t in post.tags],
        }

        return fields, relations

    async def _import_menus(self) -> int:
        """Import WordPress navigation menus."""
        menus = self._wxr_data.menus

        self._report_progress(
            ImportProgress(
                phase="menus",
                total=len(menus),
                message="Importing menus...",
            )
        )

        count = 0
        for menu_name, items in menus.items():
            self._report_progress(
                ImportProgress(
                    phase="menus",
                    current=count + 1,
                    total=len(menus),
                    message=f"Importing menu: {menu_name}",
                )
            )

            try:
                menu_data = {
                    "name": menu_name,
                    "items": [
                        {
                            "wp_id": item.id,
                            "title": item.title,
                            "url": item.url,
                            "parent_wp_id": item.parent_id,
                            "order": item.order,
                            "object_type": item.object_type,
                            "object_id": item.object_id,
                            "target": item.target,
                            "classes": item.classes,
                        }
                        for item in items
                    ],
                }

                if self.content_service:
                    await self.content_service.create("menu", menu_data)

                count += 1
            except Exception as e:
                self._error_collector.add_error(
                    phase="menus",
                    item_id=menu_name,
                    item_title=menu_name,
                    error_type="create_failed",
                    message=str(e),
                    exc=e,
                    context={"item_count": len(items)},
                )

        return count

    def _generate_redirects(self) -> RedirectReport:
        """Generate URL redirects."""
        if not self._redirect_generator:
            return RedirectReport()

        self._report_progress(
            ImportProgress(
                phase="redirects",
                message="Generating redirects...",
            )
        )

        # Prepare data for redirect generation
        posts = [
            {
                "old_url": p.link or p.guid,
                "slug": p.slug,
                "title": p.title,
                "post_type": p.post_type,
            }
            for p in self._wxr_data.posts
            if p.post_type in ("post", "page")
        ]

        categories = [
            {
                "slug": c.slug,
                "name": c.name,
            }
            for c in self._wxr_data.categories
        ]

        tags = [
            {
                "slug": t.slug,
                "name": t.name,
            }
            for t in self._wxr_data.tags
        ]

        authors = [
            {
                "login": a.login,
                "display_name": a.display_name,
            }
            for a in self._wxr_data.authors
        ]

        report = self._redirect_generator.generate_all(
            posts=posts,
            categories=categories,
            tags=tags,
            authors=authors,
            config={
                "post_path_prefix": self.config.new_post_prefix,
            },
        )

        return report

    async def _export_results(self, result: ImportResult) -> list[str]:
        """Export import results to files."""
        output_files = []

        # Export redirects
        if result.redirect_report and result.redirect_report.redirects:
            redirect_file = self.config.output_dir / f"redirects.{self.config.redirect_format}"

            if self.config.redirect_format == "yaml":
                content = self._redirect_generator.export_yaml(result.redirect_report.redirects)
            elif self.config.redirect_format == "json":
                content = self._redirect_generator.export_json(result.redirect_report.redirects)
            elif self.config.redirect_format == "nginx":
                content = self._redirect_generator.export_nginx(result.redirect_report.redirects)
            elif self.config.redirect_format == "apache":
                content = self._redirect_generator.export_apache(result.redirect_report.redirects)
            else:
                content = self._redirect_generator.export_yaml(result.redirect_report.redirects)

            redirect_file.write_text(content)
            output_files.append(str(redirect_file))

        # Export URL mapping
        if result.media_result and result.media_result.url_mapping:
            mapping_file = self.config.output_dir / "url_mapping.json"
            mapping_file.write_text(
                json.dumps(
                    result.media_result.url_mapping,
                    indent=2,
                    ensure_ascii=False,
                )
            )
            output_files.append(str(mapping_file))

        # Export import summary
        summary_file = self.config.output_dir / "import_summary.json"
        summary = {
            "success": result.success,
            "duration_seconds": result.duration_seconds,
            "posts_imported": result.posts_imported,
            "pages_imported": result.pages_imported,
            "media_imported": result.media_imported,
            "comments_imported": result.comments_imported,
            "authors_imported": result.authors_imported,
            "categories_imported": result.categories_imported,
            "tags_imported": result.tags_imported,
            "menus_imported": result.menus_imported,
            "redirects_generated": result.redirects_generated,
            "errors": result.errors,
            "warnings": result.warnings,
        }
        summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        output_files.append(str(summary_file))

        return output_files

    def _save_checkpoint(self, phase: str, progress: int):
        """Save checkpoint for resumable import."""
        if not self.config.checkpoint_file:
            return

        self._checkpoint[phase] = progress
        self._checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()

        self.config.checkpoint_file.write_text(
            json.dumps(
                self._checkpoint,
                indent=2,
            )
        )

    def _load_checkpoint(self):
        """Load checkpoint for resuming import."""
        if not self.config.checkpoint_file or not self.config.checkpoint_file.exists():
            return

        try:
            self._checkpoint = json.loads(self.config.checkpoint_file.read_text())
            logger.info(f"Loaded checkpoint: {self._checkpoint}")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            self._checkpoint = {}


# Convenience function for simple imports
async def import_wordpress(
    wxr_file: Path,
    output_dir: Path,
    new_base_url: str,
    content_service: Any = None,
    progress_callback: callable | None = None,
) -> ImportResult:
    """
    Simple WordPress import function.

    Args:
        wxr_file: Path to WordPress export file
        output_dir: Directory for output files
        new_base_url: Base URL for new site
        content_service: Content service for saving data
        progress_callback: Optional progress callback

    Returns:
        ImportResult with import statistics
    """
    config = ImportConfig(
        wxr_file=wxr_file,
        output_dir=output_dir,
        new_base_url=new_base_url,
    )

    importer = WordPressImporter(config, content_service=content_service)

    if progress_callback:
        importer.set_progress_callback(progress_callback)

    return await importer.run()
