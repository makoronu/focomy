"""Invite Service - User invitation flow.

Handles inviting users via email with initial password setup.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity
from ..utils import utcnow


@dataclass
class Invitation:
    """User invitation data."""

    id: str
    email: str
    role: str
    token: str
    expires_at: datetime
    created_by: str
    created_at: datetime
    accepted_at: datetime | None = None


# In-memory storage for invitations (use Redis in production)
_invitations: dict[str, Invitation] = {}


class InviteService:
    """
    Service for user invitation flow.

    Usage:
        invite_svc = InviteService(db)

        # Create invitation
        invite = await invite_svc.create_invitation(
            email="user@example.com",
            role="editor",
            invited_by="admin_user_id",
        )

        # Verify and accept invitation
        user = await invite_svc.accept_invitation(
            token=invite.token,
            name="User Name",
            password="secure_password",
        )
    """

    TOKEN_LENGTH = 32
    EXPIRY_DAYS = 7

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_invitation(
        self,
        email: str,
        role: str,
        invited_by: str,
        expiry_days: int | None = None,
    ) -> Invitation:
        """
        Create an invitation for a new user.

        Args:
            email: Email address to invite
            role: Role to assign (author, editor, admin)
            invited_by: User ID of the inviter
            expiry_days: Custom expiry (default 7 days)

        Returns:
            Invitation object with token

        Raises:
            ValueError: If email is already registered or has pending invite
        """
        # Check if email already registered
        from .auth import AuthService

        auth_svc = AuthService(self.db)
        existing = await auth_svc._get_user_auth_by_email(email)
        if existing:
            raise ValueError("Email is already registered")

        # Check for pending invitation
        for invite in _invitations.values():
            if invite.email == email and invite.expires_at > utcnow():
                if invite.accepted_at is None:
                    raise ValueError("A pending invitation already exists for this email")

        # Create invitation
        token = secrets.token_urlsafe(self.TOKEN_LENGTH)
        expiry = expiry_days or self.EXPIRY_DAYS

        invitation = Invitation(
            id=secrets.token_urlsafe(16),
            email=email,
            role=role,
            token=token,
            expires_at=utcnow() + timedelta(days=expiry),
            created_by=invited_by,
            created_at=utcnow(),
        )

        _invitations[token] = invitation
        return invitation

    async def get_invitation(self, token: str) -> Invitation | None:
        """Get invitation by token."""
        invitation = _invitations.get(token)
        if not invitation:
            return None

        # Check expiration
        if invitation.expires_at < utcnow():
            return None

        # Check if already accepted
        if invitation.accepted_at is not None:
            return None

        return invitation

    async def accept_invitation(
        self,
        token: str,
        name: str,
        password: str,
    ) -> Entity:
        """
        Accept an invitation and create user account.

        Args:
            token: Invitation token
            name: User's name
            password: Password for the new account

        Returns:
            Created user entity

        Raises:
            ValueError: If invitation is invalid, expired, or already used
        """
        invitation = await self.get_invitation(token)
        if not invitation:
            raise ValueError("Invalid or expired invitation")

        # Create user
        from .auth import AuthService

        auth_svc = AuthService(self.db)

        user = await auth_svc.register(
            email=invitation.email,
            password=password,
            name=name,
            role=invitation.role,
        )

        # Mark invitation as accepted
        invitation.accepted_at = utcnow()

        return user

    async def cancel_invitation(self, token: str) -> bool:
        """Cancel a pending invitation."""
        if token in _invitations:
            del _invitations[token]
            return True
        return False

    async def resend_invitation(self, token: str) -> Invitation | None:
        """Resend invitation with new token."""
        old_invite = _invitations.get(token)
        if not old_invite or old_invite.accepted_at is not None:
            return None

        # Create new invitation
        new_token = secrets.token_urlsafe(self.TOKEN_LENGTH)
        new_invite = Invitation(
            id=old_invite.id,
            email=old_invite.email,
            role=old_invite.role,
            token=new_token,
            expires_at=utcnow() + timedelta(days=self.EXPIRY_DAYS),
            created_by=old_invite.created_by,
            created_at=utcnow(),
        )

        # Remove old, add new
        del _invitations[token]
        _invitations[new_token] = new_invite

        return new_invite

    async def list_pending_invitations(self) -> list[Invitation]:
        """List all pending (non-expired, non-accepted) invitations."""
        now = utcnow()
        return [
            inv for inv in _invitations.values() if inv.expires_at > now and inv.accepted_at is None
        ]

    async def cleanup_expired(self) -> int:
        """Remove expired invitations."""
        now = utcnow()
        expired = [token for token, inv in _invitations.items() if inv.expires_at < now]
        for token in expired:
            del _invitations[token]
        return len(expired)

    def get_invite_url(self, token: str, base_url: str = "") -> str:
        """Generate invitation URL."""
        return f"{base_url}/admin/accept-invite?token={token}"


def get_invite_service(db: AsyncSession) -> InviteService:
    return InviteService(db)
