"""Entity import - authors, categories, tags, menus."""

from __future__ import annotations

import logging
import secrets

from .wxr_parser import WXRData

logger = logging.getLogger(__name__)


class EntityImportMixin:
    """Import methods for authors, categories, tags, and menus.

    Mixed into WordPressImportService.
    Requires: self.db, self.entity_svc, self.error_collector,
              self.update_job(), self._find_by_wp_id(), self._is_processed(),
              self._save_checkpoint(), self._is_menu_processed(),
              self._save_menu_checkpoint()
    """

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
