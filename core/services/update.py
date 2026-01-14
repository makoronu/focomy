"""Update check service."""

import os
import subprocess
import sys
from datetime import datetime, timedelta

import httpx
import structlog

from core import __version__

logger = structlog.get_logger(__name__)

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


class UpdateResult:
    """Update execution result."""

    def __init__(
        self,
        success: bool,
        message: str,
        old_version: str | None = None,
        new_version: str | None = None,
        output: str | None = None,
    ):
        self.success = success
        self.message = message
        self.old_version = old_version
        self.new_version = new_version
        self.output = output


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

    async def execute_update(self, target_version: str | None = None) -> UpdateResult:
        """Execute pip upgrade for focomy.

        Args:
            target_version: Specific version to install. If None, installs latest.

        Returns:
            UpdateResult with success status and message.
        """
        old_version = __version__
        package = PYPI_PACKAGE
        if target_version:
            package = f"{PYPI_PACKAGE}=={target_version}"

        logger.info(
            "update_started",
            old_version=old_version,
            target_version=target_version or "latest",
        )

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", package],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(
                    "update_failed",
                    returncode=result.returncode,
                    stderr=result.stderr,
                )
                return UpdateResult(
                    success=False,
                    message=f"アップデート失敗: {result.stderr}",
                    old_version=old_version,
                    output=result.stderr,
                )

            # Clear cache to force re-check
            self._cache = None

            # Get new version by re-checking
            update_info = await self.check_for_updates(force=True)
            new_version = update_info.current_version

            logger.info(
                "update_completed",
                old_version=old_version,
                new_version=new_version,
            )

            # Schedule restart after response is sent
            self._schedule_restart()

            if old_version == new_version:
                return UpdateResult(
                    success=True,
                    message=f"既に最新バージョン ({new_version}) です（再起動中...）",
                    old_version=old_version,
                    new_version=new_version,
                    output=result.stdout,
                )

            return UpdateResult(
                success=True,
                message=f"アップデート完了: {old_version} → {new_version}（再起動中...）",
                old_version=old_version,
                new_version=new_version,
                output=result.stdout,
            )

        except subprocess.TimeoutExpired:
            logger.error("update_timeout")
            return UpdateResult(
                success=False,
                message="アップデートがタイムアウトしました（120秒）",
                old_version=old_version,
            )
        except Exception as e:
            logger.error("update_exception", error=str(e))
            return UpdateResult(
                success=False,
                message=f"アップデートエラー: {str(e)}",
                old_version=old_version,
            )

    def _schedule_restart(self) -> None:
        """Schedule a process restart after a short delay.

        Spawns a background process that waits 2 seconds then restarts,
        allowing the HTTP response to be sent before the restart.
        """
        # Try PM2 first (most common for this project)
        pm2_path = self._find_executable("pm2")
        if pm2_path:
            logger.info("scheduling_restart", method="pm2")
            # Use nohup and & to detach from current process
            subprocess.Popen(
                f"sleep 2 && {pm2_path} restart focomy",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return

        # Try systemctl
        if os.path.exists("/usr/bin/systemctl"):
            logger.info("scheduling_restart", method="systemctl")
            subprocess.Popen(
                "sleep 2 && systemctl restart focomy",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return

        # Fallback: just log that manual restart is needed
        logger.warning("restart_manual_required", reason="no_process_manager_found")

    def _find_executable(self, name: str) -> str | None:
        """Find executable in common paths."""
        paths = [
            f"/usr/bin/{name}",
            f"/usr/local/bin/{name}",
            f"/root/.local/bin/{name}",
            f"/home/ubuntu/.local/bin/{name}",
            f"/root/.nvm/versions/node/v20.18.0/bin/{name}",
            f"/root/.nvm/versions/node/v18.20.0/bin/{name}",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return None


update_service = UpdateService()
