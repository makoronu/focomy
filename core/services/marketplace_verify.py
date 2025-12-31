"""Marketplace Verification - Package signature verification.

Verifies the authenticity and integrity of downloaded packages.
"""

import hashlib
import hmac
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


@dataclass
class PackageManifest:
    """Package manifest data."""

    name: str
    version: str
    type: str  # "plugin" or "theme"
    author: str
    checksum: str  # SHA256 of package contents
    signed_at: datetime
    signature: str
    files: list[str]


@dataclass
class VerificationResult:
    """Result of package verification."""

    valid: bool
    package_name: str
    package_version: str
    verified_at: datetime
    error: str | None = None
    warnings: list[str] = None


class MarketplaceVerifier:
    """
    Verifies marketplace package signatures.

    Usage:
        verifier = MarketplaceVerifier(public_key)

        # Verify a downloaded package
        result = verifier.verify_package("/path/to/package.zip")

        if result.valid:
            extract_and_install(package)
    """

    # Marketplace public key (would be fetched from server in production)
    DEFAULT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"""

    def __init__(self, public_key: str = None):
        self._public_key_pem = public_key or self.DEFAULT_PUBLIC_KEY
        self._public_key = None

        if CRYPTO_AVAILABLE and public_key:
            try:
                self._public_key = serialization.load_pem_public_key(self._public_key_pem.encode())
            except Exception:
                pass

    def verify_package(self, package_path: str) -> VerificationResult:
        """
        Verify a package's signature.

        Args:
            package_path: Path to the package ZIP file

        Returns:
            VerificationResult
        """
        package_path = Path(package_path)
        warnings = []

        if not package_path.exists():
            return VerificationResult(
                valid=False,
                package_name="",
                package_version="",
                verified_at=utcnow(),
                error="Package file not found",
            )

        try:
            # Extract manifest
            manifest = self._extract_manifest(package_path)
            if not manifest:
                return VerificationResult(
                    valid=False,
                    package_name="",
                    package_version="",
                    verified_at=utcnow(),
                    error="Package manifest not found",
                )

            # Verify checksum
            if not self._verify_checksum(package_path, manifest):
                return VerificationResult(
                    valid=False,
                    package_name=manifest.name,
                    package_version=manifest.version,
                    verified_at=utcnow(),
                    error="Checksum verification failed - package may be corrupted or tampered",
                )

            # Verify signature
            if not CRYPTO_AVAILABLE:
                warnings.append("Cryptography library not available - signature not verified")
            elif not self._public_key:
                warnings.append("Public key not configured - signature not verified")
            else:
                if not self._verify_signature(manifest):
                    return VerificationResult(
                        valid=False,
                        package_name=manifest.name,
                        package_version=manifest.version,
                        verified_at=utcnow(),
                        error="Signature verification failed - package is not from official marketplace",
                    )

            # Check for suspicious files
            suspicious = self._check_suspicious_files(manifest.files)
            if suspicious:
                warnings.extend(suspicious)

            return VerificationResult(
                valid=True,
                package_name=manifest.name,
                package_version=manifest.version,
                verified_at=utcnow(),
                warnings=warnings if warnings else None,
            )

        except Exception as e:
            return VerificationResult(
                valid=False,
                package_name="",
                package_version="",
                verified_at=utcnow(),
                error=f"Verification error: {str(e)}",
            )

    def _extract_manifest(self, package_path: Path) -> PackageManifest | None:
        """Extract manifest from package."""
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                manifest_data = zf.read("manifest.json")
                data = json.loads(manifest_data)

                return PackageManifest(
                    name=data.get("name", ""),
                    version=data.get("version", ""),
                    type=data.get("type", ""),
                    author=data.get("author", ""),
                    checksum=data.get("checksum", ""),
                    signed_at=datetime.fromisoformat(data.get("signed_at", "")),
                    signature=data.get("signature", ""),
                    files=data.get("files", []),
                )
        except (KeyError, json.JSONDecodeError, zipfile.BadZipFile):
            return None

    def _verify_checksum(self, package_path: Path, manifest: PackageManifest) -> bool:
        """Verify package checksum."""
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                hasher = hashlib.sha256()

                # Hash all files except manifest.json
                for name in sorted(zf.namelist()):
                    if name == "manifest.json":
                        continue
                    hasher.update(zf.read(name))

                calculated = hasher.hexdigest()
                return hmac.compare_digest(calculated, manifest.checksum)

        except Exception:
            return False

    def _verify_signature(self, manifest: PackageManifest) -> bool:
        """Verify package signature using public key."""
        if not CRYPTO_AVAILABLE or not self._public_key:
            return True  # Skip if not available

        try:
            # Build message to verify
            message = f"{manifest.name}:{manifest.version}:{manifest.checksum}"
            signature = bytes.fromhex(manifest.signature)

            self._public_key.verify(
                signature,
                message.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True

        except InvalidSignature:
            return False
        except Exception:
            return False

    def _check_suspicious_files(self, files: list[str]) -> list[str]:
        """Check for suspicious file patterns."""
        warnings = []

        suspicious_patterns = [
            ".exe",
            ".dll",
            ".so",
            ".dylib",  # Binaries
            ".php",
            ".asp",
            ".jsp",  # Server scripts
            "__pycache__",
            ".pyc",  # Python cache
            ".env",
            ".secret",  # Secrets
            ".git",
            ".svn",  # VCS
        ]

        for file_path in files:
            lower_path = file_path.lower()
            for pattern in suspicious_patterns:
                if pattern in lower_path:
                    warnings.append(f"Suspicious file found: {file_path}")
                    break

        return warnings

    def calculate_checksum(self, directory: Path) -> str:
        """Calculate checksum for a directory (for package creation)."""
        hasher = hashlib.sha256()

        for file_path in sorted(directory.rglob("*")):
            if file_path.is_file() and file_path.name != "manifest.json":
                hasher.update(file_path.read_bytes())

        return hasher.hexdigest()

    def create_manifest(
        self,
        directory: Path,
        name: str,
        version: str,
        package_type: str,
        author: str,
    ) -> PackageManifest:
        """Create a manifest for a package (for package creation)."""
        files = [str(f.relative_to(directory)) for f in directory.rglob("*") if f.is_file()]

        checksum = self.calculate_checksum(directory)

        return PackageManifest(
            name=name,
            version=version,
            type=package_type,
            author=author,
            checksum=checksum,
            signed_at=utcnow(),
            signature="",  # To be signed by marketplace
            files=files,
        )


def get_marketplace_verifier(public_key: str = None) -> MarketplaceVerifier:
    return MarketplaceVerifier(public_key)
