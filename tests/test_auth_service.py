"""Tests for AuthService.

Tests user registration, login, password reset, and TOTP.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from core.services.auth import AuthService


class TestUserRegistration:
    """User registration test cases."""

    @pytest.mark.asyncio
    async def test_register_user(self, auth_service: AuthService, sample_user_data: dict):
        """Test user registration."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        assert user is not None
        assert user.type == "user"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, auth_service: AuthService, sample_user_data: dict):
        """Test that duplicate emails are rejected."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        with pytest.raises(ValueError, match="email"):
            await auth_service.register(
                email=sample_user_data["email"],
                password="different_password",
                name="Different Name",
                role="author",
            )

    @pytest.mark.asyncio
    async def test_register_weak_password(self, auth_service: AuthService, sample_user_data: dict):
        """Test that weak passwords are rejected."""
        with pytest.raises(ValueError, match="password"):
            await auth_service.register(
                email=sample_user_data["email"],
                password="123",  # Too short
                name=sample_user_data["name"],
                role=sample_user_data["role"],
            )


class TestUserLogin:
    """User login test cases."""

    @pytest.mark.asyncio
    async def test_login_success(self, auth_service: AuthService, sample_user_data: dict):
        """Test successful login."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        user = await auth_service.login(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
        )

        assert user is not None

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, auth_service: AuthService, sample_user_data: dict):
        """Test login with wrong password."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        user = await auth_service.login(
            email=sample_user_data["email"],
            password="wrong_password",
        )

        assert user is None

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, auth_service: AuthService):
        """Test login with nonexistent email."""
        user = await auth_service.login(
            email="nonexistent@example.com",
            password="any_password",
        )

        assert user is None


class TestPasswordReset:
    """Password reset test cases."""

    @pytest.mark.asyncio
    async def test_request_password_reset(self, auth_service: AuthService, sample_user_data: dict):
        """Test requesting password reset."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        token = await auth_service.request_password_reset(sample_user_data["email"])

        assert token is not None
        assert len(token) > 20

    @pytest.mark.asyncio
    async def test_reset_password(self, auth_service: AuthService, sample_user_data: dict):
        """Test password reset with token."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        token = await auth_service.request_password_reset(sample_user_data["email"])
        new_password = "new_secure_password_456"

        result = await auth_service.reset_password(token, new_password)
        assert result is True

        # Old password should not work
        user = await auth_service.login(sample_user_data["email"], sample_user_data["password"])
        assert user is None

        # New password should work
        user = await auth_service.login(sample_user_data["email"], new_password)
        assert user is not None

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, auth_service: AuthService):
        """Test password reset with invalid token."""
        result = await auth_service.reset_password("invalid_token", "new_password")
        assert result is False

    @pytest.mark.asyncio
    async def test_request_reset_nonexistent_email(self, auth_service: AuthService):
        """Test requesting reset for nonexistent email."""
        # Should not raise error (prevent email enumeration)
        token = await auth_service.request_password_reset("nonexistent@example.com")
        assert token is None


class TestTOTP:
    """TOTP (2FA) test cases."""

    @pytest.mark.asyncio
    async def test_setup_totp(self, auth_service: AuthService, sample_user_data: dict):
        """Test TOTP setup."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        secret, uri, backup_codes = await auth_service.setup_totp(user.id)

        assert secret is not None
        assert len(secret) == 32  # Base32 encoded
        assert uri.startswith("otpauth://totp/")
        assert len(backup_codes) == 10

    @pytest.mark.asyncio
    async def test_verify_totp(self, auth_service: AuthService, sample_user_data: dict):
        """Test TOTP verification."""
        import pyotp

        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        secret, _, _ = await auth_service.setup_totp(user.id)
        totp = pyotp.TOTP(secret)
        code = totp.now()

        result = await auth_service.verify_totp(user.id, code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_totp_invalid(self, auth_service: AuthService, sample_user_data: dict):
        """Test TOTP verification with invalid code."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        await auth_service.setup_totp(user.id)

        result = await auth_service.verify_totp(user.id, "000000")
        assert result is False

    @pytest.mark.asyncio
    async def test_backup_code_usage(self, auth_service: AuthService, sample_user_data: dict):
        """Test backup code usage."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        _, _, backup_codes = await auth_service.setup_totp(user.id)
        first_code = backup_codes[0]

        # First use should succeed
        result = await auth_service.use_backup_code(user.id, first_code)
        assert result is True

        # Second use should fail
        result = await auth_service.use_backup_code(user.id, first_code)
        assert result is False


class TestSessionManagement:
    """Session management test cases."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, auth_service: AuthService, sample_user_data: dict):
        """Test listing user sessions."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        # Create session
        await auth_service.create_session(
            user_id=user.id,
            user_agent="Test Browser",
            ip_address="127.0.0.1",
        )

        sessions = await auth_service.list_sessions(user.id)
        assert len(sessions) == 1
        assert sessions[0]["user_agent"] == "Test Browser"

    @pytest.mark.asyncio
    async def test_revoke_session(self, auth_service: AuthService, sample_user_data: dict):
        """Test revoking a session."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        session_id = await auth_service.create_session(
            user_id=user.id,
            user_agent="Test Browser",
            ip_address="127.0.0.1",
        )

        result = await auth_service.revoke_session(user.id, session_id)
        assert result is True

        sessions = await auth_service.list_sessions(user.id)
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_revoke_all_sessions(self, auth_service: AuthService, sample_user_data: dict):
        """Test revoking all sessions for a user."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        # Create multiple sessions
        for i in range(3):
            await auth_service.create_session(
                user_id=user.id,
                user_agent=f"Browser {i}",
                ip_address="127.0.0.1",
            )

        count = await auth_service.revoke_all_sessions(user.id)
        assert count == 3

        sessions = await auth_service.list_sessions(user.id)
        assert len(sessions) == 0
