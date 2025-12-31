"""Preview Service - Generate preview tokens for draft content."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity
from ..utils import utcnow

# In-memory preview token storage (for simplicity)
# In production, consider using Redis or database
_preview_tokens: dict[str, dict] = {}


class PreviewService:
    """
    Service for generating preview URLs for draft content.

    Usage:
        # Generate preview token
        token = await preview_svc.create_token(entity_id, user_id)
        preview_url = f"/preview/{token}"

        # Verify token and get entity
        entity = await preview_svc.get_preview_entity(token)
    """

    TOKEN_EXPIRY_HOURS = 24
    TOKEN_LENGTH = 32

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_token(
        self,
        entity_id: str,
        user_id: str,
        expiry_hours: int | None = None,
    ) -> str:
        """
        Create a preview token for an entity.

        Args:
            entity_id: The entity to preview
            user_id: The user creating the preview
            expiry_hours: Custom expiry (default 24 hours)

        Returns:
            Preview token string
        """
        expiry = expiry_hours or self.TOKEN_EXPIRY_HOURS
        token = secrets.token_urlsafe(self.TOKEN_LENGTH)

        _preview_tokens[token] = {
            "entity_id": entity_id,
            "user_id": user_id,
            "created_at": utcnow(),
            "expires_at": utcnow() + timedelta(hours=expiry),
        }

        # Clean up expired tokens periodically
        self._cleanup_expired_tokens()

        return token

    async def get_preview_entity(self, token: str) -> Entity | None:
        """
        Get entity for preview if token is valid.

        Returns:
            Entity if token is valid, None otherwise
        """
        token_data = _preview_tokens.get(token)
        if not token_data:
            return None

        # Check expiration
        if utcnow() > token_data["expires_at"]:
            del _preview_tokens[token]
            return None

        # Get entity (including drafts/deleted)
        entity_id = token_data["entity_id"]
        result = await self.db.execute(select(Entity).where(Entity.id == entity_id))
        return result.scalar_one_or_none()

    async def revoke_token(self, token: str) -> bool:
        """Revoke a preview token."""
        if token in _preview_tokens:
            del _preview_tokens[token]
            return True
        return False

    async def revoke_entity_tokens(self, entity_id: str) -> int:
        """Revoke all preview tokens for an entity."""
        count = 0
        tokens_to_delete = [
            t for t, data in _preview_tokens.items() if data["entity_id"] == entity_id
        ]
        for token in tokens_to_delete:
            del _preview_tokens[token]
            count += 1
        return count

    async def get_entity_tokens(self, entity_id: str) -> list[dict]:
        """Get all active preview tokens for an entity."""
        self._cleanup_expired_tokens()
        return [
            {
                "token": token,
                "created_at": data["created_at"],
                "expires_at": data["expires_at"],
            }
            for token, data in _preview_tokens.items()
            if data["entity_id"] == entity_id
        ]

    def _cleanup_expired_tokens(self):
        """Remove expired tokens."""
        now = utcnow()
        expired = [t for t, data in _preview_tokens.items() if now > data["expires_at"]]
        for token in expired:
            del _preview_tokens[token]

    def get_preview_url(self, token: str, base_url: str = "") -> str:
        """Generate full preview URL."""
        return f"{base_url}/preview/{token}"


# Preview routes helper
def get_preview_service(db: AsyncSession) -> PreviewService:
    return PreviewService(db)
