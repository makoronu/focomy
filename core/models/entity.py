"""Entity and EntityValue models - the core of the system."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Entity(Base):
    """
    Unified entity table - all content types are stored here.

    Post, Page, Category, User - all are just entities with different types.
    This is the foundation of the metadata-driven architecture.
    """

    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    # Optimistic locking
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    # Relationships
    values: Mapped[list["EntityValue"]] = relationship(
        "EntityValue",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    relations_from: Mapped[list["Relation"]] = relationship(
        "Relation",
        foreign_keys="Relation.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )
    relations_to: Mapped[list["Relation"]] = relationship(
        "Relation",
        foreign_keys="Relation.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_entities_type_deleted", "type", "deleted_at"),)

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, type={self.type})>"


class EntityValue(Base):
    """
    Field values for entities - EAV pattern done right.

    Type-specific columns prevent the "everything is a string" problem.
    Proper indexes make queries fast.
    """

    __tablename__ = "entity_values"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Type-specific value columns
    value_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    value_int: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    value_float: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    value_datetime: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    value_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationship
    entity: Mapped["Entity"] = relationship(
        "Entity",
        back_populates="values",
    )

    __table_args__ = (
        Index("idx_values_entity", "entity_id"),
        Index("idx_values_field", "field_name"),
        Index("idx_values_entity_field", "entity_id", "field_name", unique=True),
        Index("idx_values_text", "value_text"),
        Index("idx_values_int", "value_int"),
    )

    def __repr__(self) -> str:
        return f"<EntityValue(entity_id={self.entity_id}, field={self.field_name})>"

    @property
    def value(self):
        """Get the actual value based on which column is populated."""
        if self.value_json is not None:
            return self.value_json
        if self.value_datetime is not None:
            return self.value_datetime
        if self.value_float is not None:
            return self.value_float
        if self.value_int is not None:
            return self.value_int
        return self.value_text


# Import for type hints
from .relation import Relation
