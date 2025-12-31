"""AuthService - authentication and session management."""

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import pyotp
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Entity, LoginLog, Session, UserAuth
from ..utils import utcnow
from .entity import EntityService

# TOTP configuration
TOTP_ISSUER = "Focomy"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8


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
        password: str | None,
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
        if user_auth.locked_until and user_auth.locked_until > utcnow():
            self.db.add(log)
            await self.db.commit()
            remaining = (user_auth.locked_until - utcnow()).seconds
            raise ValueError(f"Account locked. Try again in {remaining} seconds")

        # Verify password
        if not self._verify_password(password, user_auth.password_hash):
            # Increment attempts
            user_auth.login_attempts += 1

            # Lock if too many attempts
            if user_auth.login_attempts >= settings.security.login_attempts:
                user_auth.locked_until = utcnow() + timedelta(
                    seconds=settings.security.lockout_duration
                )

            self.db.add(log)
            await self.db.commit()
            raise ValueError("Invalid email or password")

        # Success - reset attempts
        user_auth.login_attempts = 0
        user_auth.locked_until = None
        user_auth.last_login = utcnow()

        # Create session
        session_token = secrets.token_urlsafe(32)
        session = Session(
            id=session_token,
            user_id=user_auth.entity_id,
            expires_at=utcnow() + timedelta(seconds=settings.security.session_expire),
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

    async def get_current_user(self, session_token: str) -> Entity | None:
        """Get current user from session token."""
        if not session_token:
            return None

        query = select(Session).where(
            and_(
                Session.id == session_token,
                Session.expires_at > utcnow(),
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

    async def _get_user_auth_by_email(self, email: str) -> UserAuth | None:
        """Get user auth by email."""
        query = select(UserAuth).where(UserAuth.email == email)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_user_auth(self, user_id: str) -> UserAuth | None:
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

    async def request_password_reset(self, email: str) -> str | None:
        """
        Request a password reset.

        Returns the reset token (to be sent via email), or None if email not found.
        Note: For security, always return success to the user even if email not found.
        """
        user_auth = await self._get_user_auth_by_email(email)
        if not user_auth:
            return None

        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        user_auth.reset_token = reset_token
        user_auth.reset_token_expires = utcnow() + timedelta(hours=1)

        await self.db.commit()
        return reset_token

    async def reset_password(
        self,
        token: str,
        new_password: str,
    ) -> bool:
        """
        Reset password using a reset token.

        Returns True on success, False if token is invalid or expired.
        """
        # Find user by reset token
        query = select(UserAuth).where(
            and_(
                UserAuth.reset_token == token,
                UserAuth.reset_token_expires > utcnow(),
            )
        )
        result = await self.db.execute(query)
        user_auth = result.scalar_one_or_none()

        if not user_auth:
            return False

        # Check password strength
        if len(new_password) < settings.security.password_min_length:
            raise ValueError(
                f"Password must be at least {settings.security.password_min_length} characters"
            )

        # Update password
        user_auth.password_hash = self._hash_password(new_password)
        user_auth.reset_token = None
        user_auth.reset_token_expires = None
        user_auth.login_attempts = 0
        user_auth.locked_until = None

        await self.db.commit()
        return True

    async def invalidate_all_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user."""
        from sqlalchemy import delete

        result = await self.db.execute(delete(Session).where(Session.user_id == user_id))
        await self.db.commit()
        return result.rowcount

    async def list_sessions(self, user_id: str) -> list[dict]:
        """
        List all active sessions for a user.

        Returns list of session info dicts.
        """
        query = (
            select(Session)
            .where(
                and_(
                    Session.user_id == user_id,
                    Session.expires_at > utcnow(),
                )
            )
            .order_by(Session.created_at.desc())
        )

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        return [
            {
                "id": s.id[:8] + "...",  # Partial ID for security
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in sessions
        ]

    async def get_session_count(self, user_id: str) -> int:
        """Get count of active sessions for a user."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(Session.id)).where(
                and_(
                    Session.user_id == user_id,
                    Session.expires_at > utcnow(),
                )
            )
        )
        return result.scalar() or 0

    async def enforce_session_limit(
        self,
        user_id: str,
        max_sessions: int = 5,
    ) -> int:
        """
        Enforce maximum concurrent sessions.

        Removes oldest sessions if limit exceeded.

        Returns count of removed sessions.
        """
        from sqlalchemy import delete

        # Get current sessions ordered by creation (oldest first)
        query = (
            select(Session)
            .where(
                and_(
                    Session.user_id == user_id,
                    Session.expires_at > utcnow(),
                )
            )
            .order_by(Session.created_at.asc())
        )

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        # Remove excess sessions
        excess = len(sessions) - max_sessions
        if excess <= 0:
            return 0

        sessions_to_remove = sessions[:excess]
        ids_to_remove = [s.id for s in sessions_to_remove]

        await self.db.execute(delete(Session).where(Session.id.in_(ids_to_remove)))
        await self.db.commit()

        return excess

    async def cleanup_expired_sessions(self) -> int:
        """
        Remove all expired sessions.

        Should be called periodically (e.g., via cron).
        """
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(Session).where(Session.expires_at < utcnow())
        )
        await self.db.commit()
        return result.rowcount

    async def extend_session(self, session_token: str, hours: int = 24) -> bool:
        """
        Extend a session's expiration.

        Returns True if session was extended.
        """
        query = select(Session).where(Session.id == session_token)
        result = await self.db.execute(query)
        session = result.scalar_one_or_none()

        if not session or session.expires_at < utcnow():
            return False

        session.expires_at = utcnow() + timedelta(hours=hours)
        await self.db.commit()
        return True

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
            expires_at=utcnow() + timedelta(seconds=settings.security.session_expire),
        )
        self.db.add(session)

        # Update last login
        user_auth = await self._get_user_auth(user.id)
        if user_auth:
            user_auth.last_login = utcnow()

        await self.db.commit()

        return user, session_token

    # === TOTP (Two-Factor Authentication) ===

    async def setup_totp(self, user_id: str) -> tuple[str, str, list[str]]:
        """
        Set up TOTP for a user.

        Returns (secret, provisioning_uri, backup_codes).
        The user must verify with a valid TOTP code before it's enabled.
        """
        user_auth = await self._get_user_auth(user_id)
        if not user_auth:
            raise ValueError("User not found")

        # Generate new secret
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        # Generate provisioning URI for QR code
        user = await self.entity_svc.get(user_id)
        user_data = self.entity_svc.serialize(user)
        email = user_data.get("email", "user")
        uri = totp.provisioning_uri(name=email, issuer_name=TOTP_ISSUER)

        # Generate backup codes
        backup_codes = self._generate_backup_codes()

        # Store secret (not enabled yet - requires verification)
        user_auth.totp_secret = secret
        user_auth.totp_backup_codes = self._hash_backup_codes(backup_codes)
        user_auth.totp_enabled = False  # Will be enabled after verification

        await self.db.commit()

        return secret, uri, backup_codes

    async def verify_and_enable_totp(self, user_id: str, code: str) -> bool:
        """
        Verify TOTP code and enable 2FA.

        Must be called after setup_totp with a valid code.
        """
        user_auth = await self._get_user_auth(user_id)
        if not user_auth or not user_auth.totp_secret:
            return False

        totp = pyotp.TOTP(user_auth.totp_secret)
        if not totp.verify(code, valid_window=1):
            return False

        user_auth.totp_enabled = True
        await self.db.commit()
        return True

    async def verify_totp(self, user_id: str, code: str) -> bool:
        """
        Verify a TOTP code for login.

        Also accepts backup codes.
        """
        user_auth = await self._get_user_auth(user_id)
        if not user_auth or not user_auth.totp_enabled:
            return True  # TOTP not enabled, skip verification

        # Check if it's a backup code
        if len(code) == BACKUP_CODE_LENGTH and self._verify_backup_code(user_auth, code):
            await self.db.commit()  # Backup code was consumed
            return True

        # Check TOTP code
        if not user_auth.totp_secret:
            return False

        totp = pyotp.TOTP(user_auth.totp_secret)
        return totp.verify(code, valid_window=1)

    async def disable_totp(self, user_id: str, password: str) -> bool:
        """
        Disable TOTP for a user.

        Requires password verification.
        """
        user_auth = await self._get_user_auth(user_id)
        if not user_auth:
            return False

        # Verify password
        if not self._verify_password(password, user_auth.password_hash):
            raise ValueError("Invalid password")

        user_auth.totp_secret = None
        user_auth.totp_backup_codes = None
        user_auth.totp_enabled = False

        await self.db.commit()
        return True

    async def regenerate_backup_codes(self, user_id: str, password: str) -> list[str]:
        """
        Regenerate backup codes.

        Requires password verification.
        """
        user_auth = await self._get_user_auth(user_id)
        if not user_auth:
            raise ValueError("User not found")

        # Verify password
        if not self._verify_password(password, user_auth.password_hash):
            raise ValueError("Invalid password")

        # Generate new backup codes
        backup_codes = self._generate_backup_codes()
        user_auth.totp_backup_codes = self._hash_backup_codes(backup_codes)

        await self.db.commit()
        return backup_codes

    async def is_totp_enabled(self, user_id: str) -> bool:
        """Check if TOTP is enabled for a user."""
        user_auth = await self._get_user_auth(user_id)
        return user_auth is not None and user_auth.totp_enabled

    def _generate_backup_codes(self) -> list[str]:
        """Generate a set of backup codes."""
        codes = []
        for _ in range(BACKUP_CODE_COUNT):
            # Generate alphanumeric code without confusing characters
            alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
            code = "".join(secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
            codes.append(code)
        return codes

    def _hash_backup_codes(self, codes: list[str]) -> str:
        """Hash and join backup codes for storage."""
        hashed = []
        for code in codes:
            salt = bcrypt.gensalt(rounds=4)  # Faster for backup codes
            hashed_code = bcrypt.hashpw(code.encode(), salt).decode()
            hashed.append(hashed_code)
        return ",".join(hashed)

    def _verify_backup_code(self, user_auth: UserAuth, code: str) -> bool:
        """
        Verify and consume a backup code.

        Returns True if valid (and consumes it), False otherwise.
        """
        if not user_auth.totp_backup_codes:
            return False

        hashed_codes = user_auth.totp_backup_codes.split(",")
        code_upper = code.upper().replace("-", "").replace(" ", "")

        for i, hashed in enumerate(hashed_codes):
            if hashed and bcrypt.checkpw(code_upper.encode(), hashed.encode()):
                # Consume the code by marking it as used
                hashed_codes[i] = ""
                user_auth.totp_backup_codes = ",".join(hashed_codes)
                return True

        return False

    async def get_remaining_backup_codes_count(self, user_id: str) -> int:
        """Get count of remaining unused backup codes."""
        user_auth = await self._get_user_auth(user_id)
        if not user_auth or not user_auth.totp_backup_codes:
            return 0

        hashed_codes = user_auth.totp_backup_codes.split(",")
        return sum(1 for c in hashed_codes if c)
