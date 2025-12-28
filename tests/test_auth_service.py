"""Tests for AuthService.

Tests user registration, login, password reset, and TOTP.
"""


import pytest

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
    async def test_register_duplicate_email(
        self, auth_service: AuthService, sample_user_data: dict
    ):
        """Test that duplicate emails are rejected."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        with pytest.raises(ValueError, match="[Ee]mail"):
            await auth_service.register(
                email=sample_user_data["email"],
                password="different_password123",
                name="Different Name",
                role="author",
            )

    @pytest.mark.asyncio
    async def test_register_weak_password(self, auth_service: AuthService, sample_user_data: dict):
        """Test that weak passwords are rejected."""
        with pytest.raises(ValueError, match="[Pp]assword"):
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

        # login returns (user, token) tuple
        user, token = await auth_service.login(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
        )

        assert user is not None
        assert token is not None
        assert len(token) > 20

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, auth_service: AuthService, sample_user_data: dict):
        """Test login with wrong password."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        # login raises ValueError for wrong password
        with pytest.raises(ValueError, match="[Ii]nvalid"):
            await auth_service.login(
                email=sample_user_data["email"],
                password="wrong_password",
            )

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, auth_service: AuthService):
        """Test login with nonexistent email."""
        with pytest.raises(ValueError, match="[Ii]nvalid"):
            await auth_service.login(
                email="nonexistent@example.com",
                password="any_password",
            )


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
        with pytest.raises(ValueError):
            await auth_service.login(sample_user_data["email"], sample_user_data["password"])

        # New password should work
        user, session_token = await auth_service.login(sample_user_data["email"], new_password)
        assert user is not None

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, auth_service: AuthService):
        """Test password reset with invalid token."""
        result = await auth_service.reset_password("invalid_token", "new_password_123")
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

        # Enable TOTP by verifying
        totp = pyotp.TOTP(secret)
        code = totp.now()
        enabled = await auth_service.verify_and_enable_totp(user.id, code)
        assert enabled is True

        # Now verify works
        result = await auth_service.verify_totp(user.id, totp.now())
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_totp_invalid(self, auth_service: AuthService, sample_user_data: dict):
        """Test TOTP verification with invalid code."""
        import pyotp

        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        secret, _, _ = await auth_service.setup_totp(user.id)

        # Enable TOTP first
        totp = pyotp.TOTP(secret)
        await auth_service.verify_and_enable_totp(user.id, totp.now())

        # Invalid code should fail
        result = await auth_service.verify_totp(user.id, "000000")
        assert result is False

    @pytest.mark.asyncio
    async def test_totp_not_enabled_passes(self, auth_service: AuthService, sample_user_data: dict):
        """Test that verify_totp passes when TOTP is not enabled."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        # TOTP not set up, verify should pass
        result = await auth_service.verify_totp(user.id, "any_code")
        assert result is True


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

        # Login creates a session
        user, token = await auth_service.login(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
        )

        sessions = await auth_service.list_sessions(user.id)
        assert len(sessions) >= 1

    @pytest.mark.asyncio
    async def test_invalidate_all_sessions(self, auth_service: AuthService, sample_user_data: dict):
        """Test invalidating all sessions for a user."""
        user = await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        # Create multiple sessions by logging in
        for _i in range(3):
            await auth_service.login(
                email=sample_user_data["email"],
                password=sample_user_data["password"],
            )

        count = await auth_service.invalidate_all_sessions(user.id)
        assert count >= 3

        sessions = await auth_service.list_sessions(user.id)
        assert len(sessions) == 0


class TestLogout:
    """Logout test cases."""

    @pytest.mark.asyncio
    async def test_logout(self, auth_service: AuthService, sample_user_data: dict):
        """Test logout."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        user, token = await auth_service.login(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
        )

        result = await auth_service.logout(token)
        assert result is True

        # Session should be invalid now
        current = await auth_service.get_current_user(token)
        assert current is None

    @pytest.mark.asyncio
    async def test_logout_invalid_token(self, auth_service: AuthService):
        """Test logout with invalid token."""
        result = await auth_service.logout("invalid_token")
        assert result is False


class TestGetCurrentUser:
    """Get current user test cases."""

    @pytest.mark.asyncio
    async def test_get_current_user(self, auth_service: AuthService, sample_user_data: dict):
        """Test getting current user from session."""
        await auth_service.register(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
            name=sample_user_data["name"],
            role=sample_user_data["role"],
        )

        user, token = await auth_service.login(
            email=sample_user_data["email"],
            password=sample_user_data["password"],
        )

        current = await auth_service.get_current_user(token)
        assert current is not None
        assert current.id == user.id

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, auth_service: AuthService):
        """Test getting current user with invalid token."""
        current = await auth_service.get_current_user("invalid_token")
        assert current is None

    @pytest.mark.asyncio
    async def test_get_current_user_empty_token(self, auth_service: AuthService):
        """Test getting current user with empty token."""
        current = await auth_service.get_current_user("")
        assert current is None
