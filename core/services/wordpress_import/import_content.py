"""Content import - media and posts/pages."""

from __future__ import annotations

import logging
from pathlib import Path

from .constants import WP_STATUS_MAP
from .media import MediaImporter
from .wxr_parser import WXRData

logger = logging.getLogger(__name__)


class ContentImportMixin:
    """Import methods for media files and posts/pages.

    Mixed into WordPressImportService.
    Requires: self.db, self.entity_svc, self.error_collector,
              self.id_resolver, self.sanitizer, self.block_converter,
              self.update_job(), self._find_by_wp_id(), self._is_processed(),
              self._save_checkpoint()
    """

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
