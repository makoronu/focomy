"""AuthService - authentication and session management."""

from datetime import datetime, timedelta
from typing import Optional
import secrets

import bcrypt
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Entity, UserAuth, Session, LoginLog
from .entity import EntityService


class AuthService:
    """
    Authentication service.

    Handles login, logout, session management, password hashing.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def register(
        self,
        email: str,
        password: Optional[str],
        name: str,
        role: str = "author",
    ) -> Entity:
        """Register a new user."""
        # Check password strength (skip for OAuth users)
        if password is not None:
            if len(password) < settings.security.password_min_length:
                raise ValueError(
                    f"Password must be at least {settings.security.password_min_length} characters"
                )

        # Check if email exists
        existing = await self._get_user_auth_by_email(email)
        if existing:
            raise ValueError("Email already registered")

        # Create user entity
        password_hash = self._hash_password(password) if password else None
        user = await self.entity_svc.create(
            "user",
            {"name": name, "email": email, "role": role, "password": password_hash or ""},
        )

        # Create auth record
        user_auth = UserAuth(
            entity_id=user.id,
            email=email,
            password_hash=password_hash or "",
        )
        self.db.add(user_auth)
        await self.db.commit()

        return user

    async def login(
        self,
        email: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None,
    ) -> tuple[Entity, str]:
        """
        Login with email and password.

        Returns (user_entity, session_token) on success.
        Raises ValueError on failure.
        """
        user_auth = await self._get_user_auth_by_email(email)

        # Log attempt
        log = LoginLog(
            email=email,
            user_id=user_auth.entity_id if user_auth else None,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
        )

        if not user_auth:
            self.db.add(log)
            await self.db.commit()
            raise ValueError("Invalid email or password")

        # Check lockout
        if user_auth.locked_until and user_auth.locked_until > datetime.utcnow():
            self.db.add(log)
            await self.db.commit()
            remaining = (user_auth.locked_until - datetime.utcnow()).seconds
            raise ValueError(f"Account locked. Try again in {remaining} seconds")

        # Verify password
        if not self._verify_password(password, user_auth.password_hash):
            # Increment attempts
            user_auth.login_attempts += 1

            # Lock if too many attempts
            if user_auth.login_attempts >= settings.security.login_attempts:
                user_auth.locked_until = datetime.utcnow() + timedelta(
                    seconds=settings.security.lockout_duration
                )

            self.db.add(log)
            await self.db.commit()
            raise ValueError("Invalid email or password")

        # Success - reset attempts
        user_auth.login_attempts = 0
        user_auth.locked_until = None
        user_auth.last_login = datetime.utcnow()

        # Create session
        session_token = secrets.token_urlsafe(32)
        session = Session(
            id=session_token,
            user_id=user_auth.entity_id,
            expires_at=datetime.utcnow() + timedelta(
                seconds=settings.security.session_expire
            ),
        )
        self.db.add(session)

        # Log success
        log.success = True
        self.db.add(log)

        await self.db.commit()

        # Get user entity
        user = await self.entity_svc.get(user_auth.entity_id)
        return user, session_token

    async def logout(self, session_token: str) -> bool:
        """Logout - delete session."""
        query = select(Session).where(Session.id == session_token)
        result = await self.db.execute(query)
        session = result.scalar_one_or_none()

        if not session:
            return False

        await self.db.delete(session)
        await self.db.commit()
        return True

    async def get_current_user(self, session_token: str) -> Optional[Entity]:
        """Get current user from session token."""
        if not session_token:
            return None

        query = select(Session).where(
            and_(
                Session.id == session_token,
                Session.expires_at > datetime.utcnow(),
            )
        )
        result = await self.db.execute(query)
        session = result.scalar_one_or_none()

        if not session:
            return None

        return await self.entity_svc.get(session.user_id)

    async def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str,
    ) -> bool:
        """Change user password."""
        user_auth = await self._get_user_auth(user_id)
        if not user_auth:
            return False

        # Verify old password
        if not self._verify_password(old_password, user_auth.password_hash):
            raise ValueError("Invalid current password")

        # Check new password strength
        if len(new_password) < settings.security.password_min_length:
            raise ValueError(
                f"Password must be at least {settings.security.password_min_length} characters"
            )

        # Update password
        user_auth.password_hash = self._hash_password(new_password)
        await self.db.commit()
        return True

    async def _get_user_auth_by_email(self, email: str) -> Optional[UserAuth]:
        """Get user auth by email."""
        query = select(UserAuth).where(UserAuth.email == email)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_user_auth(self, user_id: str) -> Optional[UserAuth]:
        """Get user auth by user ID."""
        query = select(UserAuth).where(UserAuth.entity_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _hash_password(self, password: str) -> str:
        """Hash password with bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    async def login_oauth(self, user: Entity) -> tuple[Entity, str]:
        """
        Login via OAuth (no password needed).

        Returns (user_entity, session_token).
        """
        # Create session
        session_token = secrets.token_urlsafe(32)
        session = Session(
            id=session_token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(
                seconds=settings.security.session_expire
            ),
        )
        self.db.add(session)

        # Update last login
        user_auth = await self._get_user_auth(user.id)
        if user_auth:
            user_auth.last_login = datetime.utcnow()

        await self.db.commit()

        return user, session_token
