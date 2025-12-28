"""Relation model - relationships as first-class citizens."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .entity import Entity


class Relation(Base):
    """
    Relations between entities.

    No foreign keys hardcoded in entity tables.
    All relationships are managed through this single table.
    """

    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    from_entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    from_entity: Mapped["Entity"] = relationship(
        "Entity",
        foreign_keys=[from_entity_id],
        back_populates="relations_from",
    )
    to_entity: Mapped["Entity"] = relationship(
        "Entity",
        foreign_keys=[to_entity_id],
        back_populates="relations_to",
    )

    __table_args__ = (
        Index("idx_relations_from", "from_entity_id"),
        Index("idx_relations_to", "to_entity_id"),
        Index("idx_relations_type", "relation_type"),
        Index(
            "idx_relations_unique",
            "from_entity_id",
            "to_entity_id",
            "relation_type",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Relation({self.from_entity_id} -> {self.to_entity_id}, type={self.relation_type})>"
        )
