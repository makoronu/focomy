"""TOTP (Two-Factor Authentication) mixin for AuthService."""

import secrets

import bcrypt
import pyotp

from ..utils import utcnow
from .entity import EntityService

# TOTP configuration
TOTP_ISSUER = "Focomy"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8


class TOTPMixin:
    """
    TOTP two-factor authentication methods.

    Mixed into AuthService to provide 2FA functionality.
    Requires: self.db, self.entity_svc, self._get_user_auth(), self._verify_password()
    """

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

    def _verify_backup_code(self, user_auth, code: str) -> bool:
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
