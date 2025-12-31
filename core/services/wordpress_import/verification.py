"""Verification Service - Verify import integrity and generate reports."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Entity, EntityValue, ImportJob

logger = logging.getLogger(__name__)


@dataclass
class VerificationIssue:
    """Represents a verification issue."""

    level: str  # error, warning, info
    category: str  # count, relation, media, link, seo
    entity_type: str
    entity_id: str | None
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class VerificationReport:
    """Complete verification report."""

    job_id: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    counts: dict = field(default_factory=dict)
    issues: list[VerificationIssue] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        """Count of error-level issues."""
        return len([i for i in self.issues if i.level == "error"])

    @property
    def warning_count(self) -> int:
        """Count of warning-level issues."""
        return len([i for i in self.issues if i.level == "warning"])

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return self.error_count > 0


class VerificationService:
    """
    Verify WordPress import integrity.

    Checks:
    - Count verification (expected vs actual)
    - Relation integrity
    - Media references
    - Internal links
    - SEO audit
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify(self, job_id: str) -> VerificationReport:
        """
        Run full verification for an import job.

        Args:
            job_id: Import job ID

        Returns:
            VerificationReport with all issues found
        """
        report = VerificationReport(job_id=job_id)

        # Get job info
        job = await self._get_job(job_id)
        if not job:
            report.issues.append(
                VerificationIssue(
                    level="error",
                    category="job",
                    entity_type="import_job",
                    entity_id=job_id,
                    message="Import job not found",
                )
            )
            return report

        # Run verifications
        await self._verify_counts(job, report)
        await self._verify_relations(report)
        await self._verify_media_references(report)
        await self._verify_internal_links(report)
        await self._verify_seo(report)

        # Generate summary
        report.summary = {
            "total_issues": len(report.issues),
            "errors": report.error_count,
            "warnings": report.warning_count,
            "info": len([i for i in report.issues if i.level == "info"]),
            "categories": self._count_by_category(report.issues),
        }

        logger.info(
            f"Verification complete: {report.error_count} errors, "
            f"{report.warning_count} warnings"
        )

        return report

    async def _get_job(self, job_id: str) -> ImportJob | None:
        """Get import job by ID."""
        result = await self.db.execute(
            select(ImportJob).where(ImportJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def _verify_counts(
        self, job: ImportJob, report: VerificationReport
    ) -> None:
        """Verify entity counts match expected."""
        entity_types = ["post", "page", "media", "category", "tag", "user", "menu"]

        for entity_type in entity_types:
            # Get actual count
            result = await self.db.execute(
                select(func.count(Entity.id))
                .join(EntityValue, Entity.id == EntityValue.entity_id)
                .where(
                    Entity.type == entity_type,
                    EntityValue.field_name == "wp_id",
                    Entity.deleted_at.is_(None),
                )
            )
            actual_count = result.scalar() or 0

            report.counts[entity_type] = actual_count

            # Check against job stats if available
            if job.stats:
                expected = job.stats.get(f"{entity_type}_count", 0)
                if expected and actual_count < expected:
                    report.issues.append(
                        VerificationIssue(
                            level="warning",
                            category="count",
                            entity_type=entity_type,
                            entity_id=None,
                            message=f"Count mismatch: expected {expected}, got {actual_count}",
                            details={
                                "expected": expected,
                                "actual": actual_count,
                                "missing": expected - actual_count,
                            },
                        )
                    )

    async def _verify_relations(self, report: VerificationReport) -> None:
        """Verify relation integrity."""
        # Check posts with invalid category references
        posts_result = await self.db.execute(
            select(Entity)
            .join(EntityValue, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "post",
                EntityValue.field_name == "category_slugs",
                Entity.deleted_at.is_(None),
            )
        )
        posts = posts_result.scalars().unique().all()

        # Get all category slugs
        cats_result = await self.db.execute(
            select(EntityValue.value_string)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "category",
                EntityValue.field_name == "slug",
                Entity.deleted_at.is_(None),
            )
        )
        valid_cat_slugs = {r[0] for r in cats_result.all() if r[0]}

        for post in posts:
            # Get category_slugs field
            slug_result = await self.db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == post.id,
                    EntityValue.field_name == "category_slugs",
                )
            )
            slug_ev = slug_result.scalar_one_or_none()

            if slug_ev and slug_ev.value_string:
                post_cats = slug_ev.value_string.split(",")
                for cat_slug in post_cats:
                    cat_slug = cat_slug.strip()
                    if cat_slug and cat_slug not in valid_cat_slugs:
                        report.issues.append(
                            VerificationIssue(
                                level="warning",
                                category="relation",
                                entity_type="post",
                                entity_id=post.id,
                                message=f"Reference to unknown category: {cat_slug}",
                                details={"category_slug": cat_slug},
                            )
                        )

        # Similar check for tags
        tags_result = await self.db.execute(
            select(EntityValue.value_string)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "tag",
                EntityValue.field_name == "slug",
                Entity.deleted_at.is_(None),
            )
        )
        valid_tag_slugs = {r[0] for r in tags_result.all() if r[0]}

        for post in posts:
            tag_result = await self.db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == post.id,
                    EntityValue.field_name == "tag_slugs",
                )
            )
            tag_ev = tag_result.scalar_one_or_none()

            if tag_ev and tag_ev.value_string:
                post_tags = tag_ev.value_string.split(",")
                for tag_slug in post_tags:
                    tag_slug = tag_slug.strip()
                    if tag_slug and tag_slug not in valid_tag_slugs:
                        report.issues.append(
                            VerificationIssue(
                                level="warning",
                                category="relation",
                                entity_type="post",
                                entity_id=post.id,
                                message=f"Reference to unknown tag: {tag_slug}",
                                details={"tag_slug": tag_slug},
                            )
                        )

    async def _verify_media_references(self, report: VerificationReport) -> None:
        """Verify media references in content."""
        # Get all media URLs
        media_result = await self.db.execute(
            select(EntityValue.value_string)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                Entity.type == "media",
                EntityValue.field_name == "url",
                Entity.deleted_at.is_(None),
            )
        )
        valid_media_urls = {r[0] for r in media_result.all() if r[0]}

        # Check posts and pages for media references
        for entity_type in ["post", "page"]:
            entities_result = await self.db.execute(
                select(Entity)
                .join(EntityValue, Entity.id == EntityValue.entity_id)
                .where(
                    Entity.type == entity_type,
                    EntityValue.field_name == "content",
                    Entity.deleted_at.is_(None),
                )
            )
            entities = entities_result.scalars().unique().all()

            for entity in entities:
                content_result = await self.db.execute(
                    select(EntityValue).where(
                        EntityValue.entity_id == entity.id,
                        EntityValue.field_name == "content",
                    )
                )
                content_ev = content_result.scalar_one_or_none()

                if content_ev and content_ev.value_text:
                    # Find image src references
                    img_pattern = re.compile(r'src=["\']([^"\']+)["\']')
                    for match in img_pattern.finditer(content_ev.value_text):
                        src = match.group(1)
                        # Check if it's a WordPress upload path
                        if "/wp-content/uploads/" in src:
                            report.issues.append(
                                VerificationIssue(
                                    level="warning",
                                    category="media",
                                    entity_type=entity_type,
                                    entity_id=entity.id,
                                    message="Reference to old WordPress media path",
                                    details={"src": src[:100]},
                                )
                            )

    async def _verify_internal_links(self, report: VerificationReport) -> None:
        """Verify internal links in content."""
        # Get all valid slugs
        slug_result = await self.db.execute(
            select(EntityValue.value_string, Entity.type)
            .join(Entity, Entity.id == EntityValue.entity_id)
            .where(
                EntityValue.field_name == "slug",
                Entity.deleted_at.is_(None),
            )
        )
        valid_slugs = {}
        for slug, entity_type in slug_result.all():
            if slug:
                valid_slugs[slug] = entity_type

        # Check content for internal links
        for entity_type in ["post", "page"]:
            entities_result = await self.db.execute(
                select(Entity)
                .join(EntityValue, Entity.id == EntityValue.entity_id)
                .where(
                    Entity.type == entity_type,
                    EntityValue.field_name == "content",
                    Entity.deleted_at.is_(None),
                )
            )
            entities = entities_result.scalars().unique().all()

            for entity in entities:
                content_result = await self.db.execute(
                    select(EntityValue).where(
                        EntityValue.entity_id == entity.id,
                        EntityValue.field_name == "content",
                    )
                )
                content_ev = content_result.scalar_one_or_none()

                if content_ev and content_ev.value_text:
                    # Find href links
                    href_pattern = re.compile(r'href=["\']([^"\']+)["\']')
                    for match in href_pattern.finditer(content_ev.value_text):
                        href = match.group(1)
                        # Check for WordPress-style internal links
                        if href.startswith("/") and "?" not in href:
                            # Extract potential slug
                            path = href.strip("/").split("/")[-1] if href.strip("/") else ""
                            if path and path not in valid_slugs:
                                # This might be a broken link
                                report.issues.append(
                                    VerificationIssue(
                                        level="info",
                                        category="link",
                                        entity_type=entity_type,
                                        entity_id=entity.id,
                                        message=f"Potential broken internal link: {href}",
                                        details={"href": href},
                                    )
                                )

    async def _verify_seo(self, report: VerificationReport) -> None:
        """Verify SEO metadata."""
        # SEO recommendations
        TITLE_MIN_LENGTH = 30
        TITLE_MAX_LENGTH = 60
        META_DESC_MIN_LENGTH = 120
        META_DESC_MAX_LENGTH = 160

        for entity_type in ["post", "page"]:
            entities_result = await self.db.execute(
                select(Entity)
                .join(EntityValue, Entity.id == EntityValue.entity_id)
                .where(
                    Entity.type == entity_type,
                    EntityValue.field_name == "wp_id",
                    Entity.deleted_at.is_(None),
                )
            )
            entities = entities_result.scalars().unique().all()

            for entity in entities:
                # Get title
                title_result = await self.db.execute(
                    select(EntityValue).where(
                        EntityValue.entity_id == entity.id,
                        EntityValue.field_name == "title",
                    )
                )
                title_ev = title_result.scalar_one_or_none()
                title = title_ev.value_string if title_ev else ""

                # Check title length
                if title:
                    if len(title) < TITLE_MIN_LENGTH:
                        report.issues.append(
                            VerificationIssue(
                                level="info",
                                category="seo",
                                entity_type=entity_type,
                                entity_id=entity.id,
                                message=f"Title too short ({len(title)} chars)",
                                details={
                                    "title": title,
                                    "length": len(title),
                                    "recommended_min": TITLE_MIN_LENGTH,
                                },
                            )
                        )
                    elif len(title) > TITLE_MAX_LENGTH:
                        report.issues.append(
                            VerificationIssue(
                                level="info",
                                category="seo",
                                entity_type=entity_type,
                                entity_id=entity.id,
                                message=f"Title too long ({len(title)} chars)",
                                details={
                                    "title": title[:50] + "...",
                                    "length": len(title),
                                    "recommended_max": TITLE_MAX_LENGTH,
                                },
                            )
                        )

                # Get meta description (SEO description)
                seo_desc_result = await self.db.execute(
                    select(EntityValue).where(
                        EntityValue.entity_id == entity.id,
                        EntityValue.field_name == "seo_description",
                    )
                )
                seo_desc_ev = seo_desc_result.scalar_one_or_none()
                seo_desc = seo_desc_ev.value_string if seo_desc_ev else ""

                # Check meta description
                if not seo_desc:
                    report.issues.append(
                        VerificationIssue(
                            level="info",
                            category="seo",
                            entity_type=entity_type,
                            entity_id=entity.id,
                            message="Missing meta description",
                            details={"title": title},
                        )
                    )
                elif len(seo_desc) < META_DESC_MIN_LENGTH:
                    report.issues.append(
                        VerificationIssue(
                            level="info",
                            category="seo",
                            entity_type=entity_type,
                            entity_id=entity.id,
                            message=f"Meta description too short ({len(seo_desc)} chars)",
                            details={
                                "length": len(seo_desc),
                                "recommended_min": META_DESC_MIN_LENGTH,
                            },
                        )
                    )
                elif len(seo_desc) > META_DESC_MAX_LENGTH:
                    report.issues.append(
                        VerificationIssue(
                            level="info",
                            category="seo",
                            entity_type=entity_type,
                            entity_id=entity.id,
                            message=f"Meta description too long ({len(seo_desc)} chars)",
                            details={
                                "length": len(seo_desc),
                                "recommended_max": META_DESC_MAX_LENGTH,
                            },
                        )
                    )

    def _count_by_category(self, issues: list[VerificationIssue]) -> dict:
        """Count issues by category."""
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.category] = counts.get(issue.category, 0) + 1
        return counts


async def verify_import(db: AsyncSession, job_id: str) -> VerificationReport:
    """
    Convenience function to verify import.

    Args:
        db: Database session
        job_id: Import job ID

    Returns:
        VerificationReport
    """
    service = VerificationService(db)
    return await service.verify(job_id)
