"""Revision model - version history for entities."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

# リビジョンタイプ定数（ENUMではなく文字列定数で管理）
REVISION_TYPE_AUTOSAVE = "autosave"
REVISION_TYPE_MANUAL = "manual"
REVISION_TYPE_PUBLISH = "publish"


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Revision(Base):
    """
    Version history for entities.

    Stores snapshots of entity data for:
    - Autosave (every 30 seconds while editing)
    - Manual save
    - Publish events

    Allows restoring previous versions.
    """

    __tablename__ = "revisions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
    )
    data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    __table_args__ = (Index("idx_revisions_entity_created", "entity_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<Revision(id={self.id}, entity_id={self.entity_id}, type={self.revision_type})>"
