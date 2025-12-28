"""Update check service."""

from datetime import datetime, timedelta

import httpx

from core.cli import __version__

PYPI_PACKAGE = "focomy"
GITHUB_REPO = "focomy/focomy"


class UpdateInfo:
    """Update information."""

    def __init__(
        self,
        current_version: str,
        latest_version: str,
        has_update: bool,
        release_url: str | None = None,
        release_notes: str | None = None,
        checked_at: datetime | None = None,
    ):
        self.current_version = current_version
        self.latest_version = latest_version
        self.has_update = has_update
        self.release_url = release_url
        self.release_notes = release_notes
        self.checked_at = checked_at or datetime.now()


class UpdateService:
    """Service for checking updates."""

    _cache: UpdateInfo | None = None
    _cache_duration = timedelta(hours=6)

    async def check_for_updates(self, force: bool = False) -> UpdateInfo:
        """Check for updates from PyPI or GitHub."""
        if not force and self._cache:
            if datetime.now() - self._cache.checked_at < self._cache_duration:
                return self._cache

        try:
            update_info = await self._check_pypi()
        except Exception:
            try:
                update_info = await self._check_github()
            except Exception:
                update_info = UpdateInfo(
                    current_version=__version__,
                    latest_version=__version__,
                    has_update=False,
                )

        self._cache = update_info
        return update_info

    async def _check_pypi(self) -> UpdateInfo:
        """Check PyPI for latest version."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://pypi.org/pypi/{PYPI_PACKAGE}/json",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

        latest_version = data["info"]["version"]
        has_update = self._compare_versions(__version__, latest_version)

        return UpdateInfo(
            current_version=__version__,
            latest_version=latest_version,
            has_update=has_update,
            release_url=f"https://pypi.org/project/{PYPI_PACKAGE}/{latest_version}/",
        )

    async def _check_github(self) -> UpdateInfo:
        """Check GitHub for latest release."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

        latest_version = data["tag_name"].lstrip("v")
        has_update = self._compare_versions(__version__, latest_version)

        return UpdateInfo(
            current_version=__version__,
            latest_version=latest_version,
            has_update=has_update,
            release_url=data["html_url"],
            release_notes=data.get("body", ""),
        )

    def _compare_versions(self, current: str, latest: str) -> bool:
        """Compare version strings."""
        try:
            current_parts = [int(x) for x in current.split(".")]
            latest_parts = [int(x) for x in latest.split(".")]

            # Pad shorter version with zeros
            while len(current_parts) < len(latest_parts):
                current_parts.append(0)
            while len(latest_parts) < len(current_parts):
                latest_parts.append(0)

            return latest_parts > current_parts
        except ValueError:
            return current != latest

    def get_current_version(self) -> str:
        """Get current version."""
        return __version__


update_service = UpdateService()
