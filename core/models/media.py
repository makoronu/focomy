"""Media model - uploaded files management."""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Media(Base):
    """
    Uploaded media files.

    Stores metadata about uploaded files.
    Actual files are stored in the filesystem.
    """
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    stored_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    width: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    height: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    alt_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        onupdate=datetime.utcnow,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Media(id={self.id}, filename={self.filename})>"
