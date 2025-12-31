"""OAuth Service - Social authentication and account management.

Supports:
- OAuth authentication (Google, GitHub, etc.)
- Account linking/unlinking
- User account merging
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..utils import utcnow


@dataclass
class OAuthUserInfo:
    """User info from OAuth provider."""

    provider: str
    provider_id: str
    email: str
    name: str
    picture: str | None = None


@dataclass
class OAuthConnection:
    """OAuth provider connection."""

    id: str
    user_id: str
    provider: str
    provider_user_id: str
    provider_email: str | None
    access_token: str | None
    refresh_token: str | None
    token_expires_at: datetime | None
    connected_at: datetime
    last_used_at: datetime | None


@dataclass
class MergeResult:
    """Result of user account merge."""

    source_user_id: str
    target_user_id: str
    entities_transferred: int
    oauth_connections_transferred: int
    success: bool
    error: str | None = None


class OAuthService:
    """
    OAuth authentication and account management service.

    Usage:
        # Basic auth
        oauth = OAuthService()
        oauth.configure(app)
        url = await oauth.get_authorization_url("google", redirect_uri, request)

        # Account management
        oauth_mgmt = OAuthAccountManager(db)
        await oauth_mgmt.link_account(user_id, "google", provider_id)
        await oauth_mgmt.unlink_account(user_id, "google")
    """

    def __init__(self):
        self.oauth = OAuth()
        self._configured = False

    def configure(self, app):
        """Configure OAuth with FastAPI app."""
        google_client_id = settings.oauth.google_client_id
        google_client_secret = settings.oauth.google_client_secret

        if google_client_id and google_client_secret:
            self.oauth.register(
                name="google",
                client_id=google_client_id,
                client_secret=google_client_secret,
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": "openid email profile"},
            )
            self._configured = True

        # GitHub
        github_client_id = getattr(settings.oauth, "github_client_id", None)
        github_client_secret = getattr(settings.oauth, "github_client_secret", None)

        if github_client_id and github_client_secret:
            self.oauth.register(
                name="github",
                client_id=github_client_id,
                client_secret=github_client_secret,
                authorize_url="https://github.com/login/oauth/authorize",
                access_token_url="https://github.com/login/oauth/access_token",
                api_base_url="https://api.github.com/",
                client_kwargs={"scope": "user:email"},
            )

    def is_configured(self, provider: str = "google") -> bool:
        """Check if a provider is configured."""
        return hasattr(self.oauth, provider)

    def get_available_providers(self) -> list[str]:
        """Get list of configured providers."""
        providers = []
        if hasattr(self.oauth, "google"):
            providers.append("google")
        if hasattr(self.oauth, "github"):
            providers.append("github")
        return providers

    async def get_authorization_url(
        self,
        provider: str,
        redirect_uri: str,
        request,
    ) -> str:
        """Get OAuth authorization URL."""
        if not hasattr(self.oauth, provider):
            raise ValueError(f"Provider not configured: {provider}")

        client = getattr(self.oauth, provider)
        return await client.authorize_redirect(request, redirect_uri)

    async def handle_callback(
        self,
        provider: str,
        request,
    ) -> OAuthUserInfo | None:
        """Handle OAuth callback and return user info."""
        if not hasattr(self.oauth, provider):
            raise ValueError(f"Unknown provider: {provider}")

        try:
            client = getattr(self.oauth, provider)
            token = await client.authorize_access_token(request)

            if provider == "google":
                user_info = token.get("userinfo")
                if user_info:
                    return OAuthUserInfo(
                        provider="google",
                        provider_id=user_info.get("sub"),
                        email=user_info.get("email"),
                        name=user_info.get("name"),
                        picture=user_info.get("picture"),
                    )

            elif provider == "github":
                resp = await client.get("user")
                profile = resp.json()
                # Get email separately
                email_resp = await client.get("user/emails")
                emails = email_resp.json()
                primary_email = next(
                    (e["email"] for e in emails if e.get("primary")),
                    emails[0]["email"] if emails else None,
                )

                return OAuthUserInfo(
                    provider="github",
                    provider_id=str(profile.get("id")),
                    email=primary_email or "",
                    name=profile.get("name") or profile.get("login"),
                    picture=profile.get("avatar_url"),
                )

        except Exception as e:
            print(f"OAuth callback error: {e}")
            return None

        return None


class OAuthAccountManager:
    """
    Manages OAuth account linking and user merging.

    Usage:
        manager = OAuthAccountManager(db)

        # Link account
        await manager.link_account(user_id, "google", provider_id)

        # Unlink account
        await manager.unlink_account(user_id, "google")

        # Merge accounts
        result = await manager.merge_accounts(old_user_id, new_user_id)
    """

    PROVIDERS = ["google", "github", "twitter", "facebook", "microsoft"]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def link_account(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
        provider_email: str = None,
        access_token: str = None,
        refresh_token: str = None,
        token_expires_at: datetime = None,
    ) -> OAuthConnection:
        """
        Link an OAuth provider to a user account.

        Raises:
            ValueError: If provider already linked
        """
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")

        # Check if already linked
        existing = await self.get_connection(user_id, provider)
        if existing:
            raise ValueError(f"Provider {provider} is already linked")

        # Check if provider account linked to another user
        other = await self.find_by_provider(provider, provider_user_id)
        if other and other.user_id != user_id:
            raise ValueError(f"This {provider} account is linked to another user")

        # Create connection
        from .entity import EntityService

        entity_service = EntityService(self.db)

        entity = await entity_service.create(
            type_name="oauth_connection",
            values={
                "user_id": user_id,
                "provider": provider,
                "provider_user_id": provider_user_id,
                "provider_email": provider_email,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
                "connected_at": utcnow().isoformat(),
            },
            user_id=user_id,
        )

        return OAuthConnection(
            id=entity.id,
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            connected_at=utcnow(),
            last_used_at=None,
        )

    async def unlink_account(self, user_id: str, provider: str) -> bool:
        """
        Unlink an OAuth provider from a user account.

        Raises:
            ValueError: If this is the only login method
        """
        # Check if user has password
        has_password = await self._user_has_password(user_id)

        # Count other connections
        connections = await self.list_connections(user_id)
        other_count = len([c for c in connections if c.provider != provider])

        if not has_password and other_count == 0:
            raise ValueError(
                "Cannot unlink: this is the only login method. "
                "Add a password or link another provider first."
            )

        connection = await self.get_connection(user_id, provider)
        if not connection:
            return False

        from .entity import EntityService

        entity_service = EntityService(self.db)
        await entity_service.delete(connection.id, user_id=user_id)

        return True

    async def get_connection(self, user_id: str, provider: str) -> OAuthConnection | None:
        """Get connection for a user and provider."""
        connections = await self.list_connections(user_id)
        return next((c for c in connections if c.provider == provider), None)

    async def list_connections(self, user_id: str) -> list[OAuthConnection]:
        """List all OAuth connections for a user."""
        from ..models import Entity

        query = select(Entity).where(
            and_(
                Entity.type == "oauth_connection",
                Entity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        entities = result.scalars().all()

        connections = []
        for entity in entities:
            values = await self._get_entity_values(entity.id)
            if values.get("user_id") == user_id:
                connections.append(self._to_connection(entity, values))

        return connections

    async def find_by_provider(
        self, provider: str, provider_user_id: str
    ) -> OAuthConnection | None:
        """Find connection by provider credentials."""
        from ..models import Entity

        query = select(Entity).where(
            and_(
                Entity.type == "oauth_connection",
                Entity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        entities = result.scalars().all()

        for entity in entities:
            values = await self._get_entity_values(entity.id)
            if (
                values.get("provider") == provider
                and values.get("provider_user_id") == provider_user_id
            ):
                return self._to_connection(entity, values)

        return None

    async def merge_accounts(
        self,
        source_user_id: str,
        target_user_id: str,
        delete_source: bool = True,
    ) -> MergeResult:
        """
        Merge source user into target user.

        Transfers content and OAuth connections.
        """
        from ..models import Entity

        try:
            entities_count = 0
            oauth_count = 0

            # Transfer created entities
            query = select(Entity).where(Entity.created_by == source_user_id)
            result = await self.db.execute(query)
            entities = result.scalars().all()

            for entity in entities:
                entity.created_by = target_user_id
                if entity.updated_by == source_user_id:
                    entity.updated_by = target_user_id
                entities_count += 1

            # Transfer OAuth connections
            connections = await self.list_connections(source_user_id)
            for conn in connections:
                from ..models import EntityValue

                query = select(EntityValue).where(
                    and_(
                        EntityValue.entity_id == conn.id,
                        EntityValue.field_name == "user_id",
                    )
                )
                result = await self.db.execute(query)
                value = result.scalar_one_or_none()
                if value:
                    value.value_text = target_user_id
                    oauth_count += 1

            # Delete source user
            if delete_source:
                from .entity import EntityService

                entity_service = EntityService(self.db)
                await entity_service.delete(source_user_id, user_id=target_user_id)

            await self.db.commit()

            return MergeResult(
                source_user_id=source_user_id,
                target_user_id=target_user_id,
                entities_transferred=entities_count,
                oauth_connections_transferred=oauth_count,
                success=True,
            )

        except Exception as e:
            await self.db.rollback()
            return MergeResult(
                source_user_id=source_user_id,
                target_user_id=target_user_id,
                entities_transferred=0,
                oauth_connections_transferred=0,
                success=False,
                error=str(e),
            )

    async def update_tokens(
        self,
        connection_id: str,
        access_token: str,
        refresh_token: str = None,
        expires_at: datetime = None,
    ) -> bool:
        """Update OAuth tokens for a connection."""
        from .entity import EntityService

        entity_service = EntityService(self.db)

        values = {
            "access_token": access_token,
            "last_used_at": utcnow().isoformat(),
        }
        if refresh_token:
            values["refresh_token"] = refresh_token
        if expires_at:
            values["token_expires_at"] = expires_at.isoformat()

        await entity_service.update(connection_id, values)
        return True

    async def _user_has_password(self, user_id: str) -> bool:
        """Check if user has password authentication."""
        from ..models import EntityValue

        query = select(EntityValue).where(
            and_(
                EntityValue.entity_id == user_id,
                EntityValue.field_name == "password_hash",
                EntityValue.value_text.isnot(None),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def _get_entity_values(self, entity_id: str) -> dict:
        """Get all values for an entity."""
        from ..models import EntityValue

        query = select(EntityValue).where(EntityValue.entity_id == entity_id)
        result = await self.db.execute(query)
        values = result.scalars().all()
        return {v.field_name: v.value_text for v in values}

    def _to_connection(self, entity, values: dict) -> OAuthConnection:
        """Convert entity to OAuthConnection."""
        return OAuthConnection(
            id=entity.id,
            user_id=values.get("user_id", ""),
            provider=values.get("provider", ""),
            provider_user_id=values.get("provider_user_id", ""),
            provider_email=values.get("provider_email"),
            access_token=values.get("access_token"),
            refresh_token=values.get("refresh_token"),
            token_expires_at=(
                datetime.fromisoformat(values["token_expires_at"])
                if values.get("token_expires_at")
                else None
            ),
            connected_at=(
                datetime.fromisoformat(values["connected_at"])
                if values.get("connected_at")
                else entity.created_at
            ),
            last_used_at=(
                datetime.fromisoformat(values["last_used_at"])
                if values.get("last_used_at")
                else None
            ),
        )


# Singleton for OAuth authentication
oauth_service = OAuthService()


def get_oauth_account_manager(db: AsyncSession) -> OAuthAccountManager:
    return OAuthAccountManager(db)
