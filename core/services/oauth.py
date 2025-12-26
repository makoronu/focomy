"""OAuth service for social authentication."""

from typing import Optional
from dataclasses import dataclass

from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

from ..config import settings


@dataclass
class OAuthUserInfo:
    """User info from OAuth provider."""
    provider: str
    provider_id: str
    email: str
    name: str
    picture: Optional[str] = None


class OAuthService:
    """
    OAuth authentication service.

    Supports:
    - Google
    - (extensible for GitHub, Facebook, etc.)

    Configure via environment variables:
    - GOOGLE_CLIENT_ID
    - GOOGLE_CLIENT_SECRET
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
                name='google',
                client_id=google_client_id,
                client_secret=google_client_secret,
                server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                client_kwargs={
                    'scope': 'openid email profile'
                }
            )
            self._configured = True

    def is_configured(self, provider: str = 'google') -> bool:
        """Check if a provider is configured."""
        if provider == 'google':
            return hasattr(self.oauth, 'google')
        return False

    async def get_authorization_url(
        self,
        provider: str,
        redirect_uri: str,
        request,
    ) -> str:
        """Get OAuth authorization URL."""
        if provider == 'google':
            client = self.oauth.google
            return await client.authorize_redirect(request, redirect_uri)
        raise ValueError(f"Unknown provider: {provider}")

    async def handle_callback(
        self,
        provider: str,
        request,
    ) -> Optional[OAuthUserInfo]:
        """Handle OAuth callback and return user info."""
        if provider == 'google':
            try:
                client = self.oauth.google
                token = await client.authorize_access_token(request)
                user_info = token.get('userinfo')

                if user_info:
                    return OAuthUserInfo(
                        provider='google',
                        provider_id=user_info.get('sub'),
                        email=user_info.get('email'),
                        name=user_info.get('name'),
                        picture=user_info.get('picture'),
                    )
            except Exception as e:
                print(f"OAuth callback error: {e}")
                return None

        raise ValueError(f"Unknown provider: {provider}")


# Singleton
oauth_service = OAuthService()
