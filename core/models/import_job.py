"""ImportJob model - Track WordPress import jobs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class ImportJobStatus:
    """Import job status (string constants)."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    IMPORTING = "importing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = [PENDING, ANALYZING, IMPORTING, COMPLETED, FAILED, CANCELLED]


class ImportJobPhase:
    """Import job phase (string constants)."""

    INIT = "init"
    CONNECT = "connect"
    ANALYZE = "analyze"
    AUTHORS = "authors"
    CATEGORIES = "categories"
    TAGS = "tags"
    MEDIA = "media"
    POSTS = "posts"
    PAGES = "pages"
    MENUS = "menus"
    REDIRECTS = "redirects"
    COMPLETE = "complete"

    ALL = [INIT, CONNECT, ANALYZE, AUTHORS, CATEGORIES, TAGS, MEDIA, POSTS, PAGES, MENUS, REDIRECTS, COMPLETE]


class ImportJob(Base):
    """
    Track WordPress import jobs.

    Stores progress, configuration, and results for background imports.
    """

    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )

    # Source configuration
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="wxr",  # wxr or rest_api
    )
    source_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    source_file: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ImportJobStatus.PENDING,
        index=True,
    )
    phase: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ImportJobPhase.INIT,
    )
    progress_current: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    progress_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    progress_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Configuration (stored as JSON)
    config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Analysis result (stored as JSON)
    analysis: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Dry-run result (stored as JSON)
    dry_run_result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Checkpoint data for resume (stores processed IDs by type)
    checkpoint: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Import results
    posts_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pages_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    media_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    categories_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    tags_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    authors_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    menus_imported: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    redirects_generated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Errors and warnings
    errors: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    warnings: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # User who initiated
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<ImportJob(id={self.id}, status={self.status}, phase={self.phase})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "source_file": self.source_file,
            "status": self.status,
            "phase": self.phase,
            "progress": {
                "current": self.progress_current,
                "total": self.progress_total,
                "message": self.progress_message,
                "percent": (
                    int(self.progress_current / self.progress_total * 100)
                    if self.progress_total > 0
                    else 0
                ),
            },
            "config": self.config,
            "analysis": self.analysis,
            "dry_run_result": self.dry_run_result,
            "checkpoint": self.checkpoint,
            "results": {
                "posts": self.posts_imported,
                "pages": self.pages_imported,
                "media": self.media_imported,
                "categories": self.categories_imported,
                "tags": self.tags_imported,
                "authors": self.authors_imported,
                "menus": self.menus_imported,
                "redirects": self.redirects_generated,
            },
            "errors": self.errors or [],
            "warnings": self.warnings or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at and self.started_at
                else None
            ),
        }
