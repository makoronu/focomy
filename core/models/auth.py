"""Authentication models - user auth, sessions, login logs."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class UserAuth(Base):
    """
    User authentication data.

    Separate from Entity for security reasons.
    Password hashes and TOTP secrets should be in their own table.
    """

    __tablename__ = "user_auth"

    entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    totp_secret: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    login_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    # Password reset
    reset_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    reset_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    # TOTP backup codes (comma-separated hashed codes)
    totp_backup_codes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    def __repr__(self) -> str:
        return f"<UserAuth(entity_id={self.entity_id}, email={self.email})>"


class Session(Base):
    """
    User sessions.

    Server-side session storage for security.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(64),  # token_urlsafe(32) produces 43 chars
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (Index("idx_sessions_expires", "expires_at"),)

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, user_id={self.user_id})>"


class LoginLog(Base):
    """
    Login attempt logs.

    For security monitoring and audit.
    """

    __tablename__ = "login_log"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<LoginLog(id={self.id}, email={self.email}, success={self.success})>"
