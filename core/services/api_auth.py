"""API Authentication Service - JWT and API Key authentication.

Provides authentication for external API consumers:
- JWT tokens for temporary access
- API keys for long-lived integrations
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..utils import utcnow

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


@dataclass
class APIKey:
    """API key data."""

    id: str
    name: str
    key_hash: str
    prefix: str  # First 8 chars for identification
    scopes: list[str]  # e.g., ["read:entities", "write:entities"]
    user_id: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool = True


@dataclass
class TokenPayload:
    """JWT token payload."""

    sub: str  # User ID
    exp: datetime
    iat: datetime
    scopes: list[str]
    type: str = "access"


# In-memory storage for API keys (use database in production)
_api_keys: dict[str, APIKey] = {}


class APIAuthService:
    """
    API authentication service.

    Usage:
        api_auth = APIAuthService(db)

        # Generate JWT token
        token = await api_auth.create_jwt(user_id, scopes=["read:entities"])

        # Verify JWT token
        payload = await api_auth.verify_jwt(token)

        # Create API key
        key, secret = await api_auth.create_api_key(
            name="My Integration",
            user_id="user123",
            scopes=["read:entities", "write:media"],
        )

        # Verify API key
        api_key = await api_auth.verify_api_key(secret)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._secret_key = settings.security.secret_key

    # === JWT Token Methods ===

    async def create_jwt(
        self,
        user_id: str,
        scopes: list[str] = None,
        expiry_hours: int | None = None,
    ) -> str:
        """
        Create a JWT access token.

        Args:
            user_id: User ID to encode
            scopes: List of permission scopes
            expiry_hours: Custom expiry (default 24 hours)

        Returns:
            JWT token string
        """
        expiry = expiry_hours or JWT_EXPIRY_HOURS
        now = utcnow()

        payload = {
            "sub": user_id,
            "exp": now + timedelta(hours=expiry),
            "iat": now,
            "scopes": scopes or [],
            "type": "access",
        }

        return jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

    async def verify_jwt(self, token: str) -> TokenPayload | None:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            TokenPayload if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[JWT_ALGORITHM])

            return TokenPayload(
                sub=payload["sub"],
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                scopes=payload.get("scopes", []),
                type=payload.get("type", "access"),
            )
        except JWTError:
            return None

    async def create_refresh_token(
        self,
        user_id: str,
        expiry_days: int = 30,
    ) -> str:
        """Create a refresh token for obtaining new access tokens."""
        now = utcnow()

        payload = {
            "sub": user_id,
            "exp": now + timedelta(days=expiry_days),
            "iat": now,
            "type": "refresh",
        }

        return jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

    async def refresh_access_token(
        self,
        refresh_token: str,
        scopes: list[str] = None,
    ) -> str | None:
        """
        Use a refresh token to get a new access token.

        Args:
            refresh_token: Valid refresh token
            scopes: Scopes for new access token

        Returns:
            New access token, or None if refresh token is invalid
        """
        payload = await self.verify_jwt(refresh_token)
        if not payload or payload.type != "refresh":
            return None

        return await self.create_jwt(payload.sub, scopes)

    # === API Key Methods ===

    async def create_api_key(
        self,
        name: str,
        user_id: str,
        scopes: list[str] = None,
        expires_in_days: int | None = None,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key.

        Args:
            name: Human-readable name for the key
            user_id: Owner user ID
            scopes: Permission scopes
            expires_in_days: Optional expiration

        Returns:
            Tuple of (APIKey object, raw secret key)

        Note: The raw secret key is only returned once!
        """
        # Generate secret key
        raw_key = f"foc_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(raw_key)
        prefix = raw_key[:12]

        expires_at = None
        if expires_in_days:
            expires_at = utcnow() + timedelta(days=expires_in_days)

        api_key = APIKey(
            id=secrets.token_urlsafe(16),
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            scopes=scopes or [],
            user_id=user_id,
            created_at=utcnow(),
            last_used_at=None,
            expires_at=expires_at,
        )

        _api_keys[api_key.id] = api_key

        return api_key, raw_key

    async def verify_api_key(self, raw_key: str) -> APIKey | None:
        """
        Verify an API key and return its data.

        Args:
            raw_key: The raw API key to verify

        Returns:
            APIKey if valid, None otherwise
        """
        key_hash = self._hash_key(raw_key)
        raw_key[:12] if len(raw_key) >= 12 else ""

        for api_key in _api_keys.values():
            if api_key.key_hash == key_hash:
                # Check if active
                if not api_key.is_active:
                    return None

                # Check expiration
                if api_key.expires_at and api_key.expires_at < utcnow():
                    return None

                # Update last used
                api_key.last_used_at = utcnow()
                return api_key

        return None

    async def revoke_api_key(self, key_id: str, user_id: str) -> bool:
        """Revoke an API key (soft delete)."""
        api_key = _api_keys.get(key_id)
        if not api_key or api_key.user_id != user_id:
            return False

        api_key.is_active = False
        return True

    async def list_api_keys(self, user_id: str) -> list[APIKey]:
        """List all API keys for a user (active only)."""
        return [key for key in _api_keys.values() if key.user_id == user_id and key.is_active]

    async def delete_api_key(self, key_id: str, user_id: str) -> bool:
        """Permanently delete an API key."""
        api_key = _api_keys.get(key_id)
        if not api_key or api_key.user_id != user_id:
            return False

        del _api_keys[key_id]
        return True

    def _hash_key(self, raw_key: str) -> str:
        """Hash an API key for secure storage."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    # === Scope Checking ===

    def check_scope(
        self,
        required: str,
        granted: list[str],
    ) -> bool:
        """
        Check if required scope is in granted scopes.

        Supports wildcards: "read:*" matches "read:entities"
        """
        if required in granted:
            return True

        # Check wildcards
        parts = required.split(":")
        if len(parts) == 2:
            wildcard = f"{parts[0]}:*"
            if wildcard in granted:
                return True

            # Check full wildcard
            if "*" in granted:
                return True

        return False


# Available API scopes
class APIScopes:
    """Available API permission scopes."""

    # Entity operations
    READ_ENTITIES = "read:entities"
    WRITE_ENTITIES = "write:entities"
    DELETE_ENTITIES = "delete:entities"

    # Media operations
    READ_MEDIA = "read:media"
    WRITE_MEDIA = "write:media"
    DELETE_MEDIA = "delete:media"

    # User operations
    READ_USERS = "read:users"
    WRITE_USERS = "write:users"

    # Settings
    READ_SETTINGS = "read:settings"
    WRITE_SETTINGS = "write:settings"

    # Full access
    ALL = "*"

    @classmethod
    def all_scopes(cls) -> list[str]:
        return [
            cls.READ_ENTITIES,
            cls.WRITE_ENTITIES,
            cls.DELETE_ENTITIES,
            cls.READ_MEDIA,
            cls.WRITE_MEDIA,
            cls.DELETE_MEDIA,
            cls.READ_USERS,
            cls.WRITE_USERS,
            cls.READ_SETTINGS,
            cls.WRITE_SETTINGS,
        ]


def get_api_auth_service(db: AsyncSession) -> APIAuthService:
    return APIAuthService(db)
