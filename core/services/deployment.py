"""Deployment Service - Zero-downtime deployment and rollback.

Provides:
- Health checks for deployment readiness
- Graceful shutdown
- Rollback procedures
"""

import asyncio
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class DeploymentState:
    """Deployment states (string constants)."""

    RUNNING = "running"
    DEPLOYING = "deploying"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"

    ALL = [RUNNING, DEPLOYING, DRAINING, STOPPED, FAILED]


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    healthy: bool
    checks: dict[str, bool]
    message: str
    timestamp: datetime


@dataclass
class DeploymentInfo:
    """Current deployment information."""

    version: str
    deployed_at: datetime
    state: str  # Use DeploymentState constants
    previous_version: str | None


class DeploymentService:
    """
    Service for zero-downtime deployment.

    Usage:
        deployment = DeploymentService()

        # Health check
        health = await deployment.health_check()

        # Prepare for shutdown
        await deployment.drain_connections()

        # Rollback
        await deployment.rollback()
    """

    VERSION_FILE = ".version"
    ROLLBACK_DIR = ".rollback"

    def __init__(self):
        self._state = DeploymentState.RUNNING
        self._active_requests = 0
        self._shutting_down = False
        self._version = self._read_version()
        self._previous_version: str | None = None
        self._health_checks: list[Callable[[], Awaitable[bool]]] = []
        self._shutdown_hooks: list[Callable[[], Awaitable[None]]] = []

    def _read_version(self) -> str:
        """Read current version from file."""
        version_file = Path(self.VERSION_FILE)
        if version_file.exists():
            return version_file.read_text().strip()
        return "unknown"

    def get_state(self) -> DeploymentState:
        """Get current deployment state."""
        return self._state

    def get_version(self) -> str:
        """Get current version."""
        return self._version

    def get_deployment_info(self) -> DeploymentInfo:
        """Get full deployment info."""
        return DeploymentInfo(
            version=self._version,
            deployed_at=self._get_deploy_time(),
            state=self._state,
            previous_version=self._previous_version,
        )

    def _get_deploy_time(self) -> datetime:
        """Get deployment timestamp."""
        version_file = Path(self.VERSION_FILE)
        if version_file.exists():
            return datetime.fromtimestamp(version_file.stat().st_mtime)
        return utcnow()

    def register_health_check(
        self,
        check: Callable[[], Awaitable[bool]],
    ) -> None:
        """Register a health check function."""
        self._health_checks.append(check)

    def register_shutdown_hook(
        self,
        hook: Callable[[], Awaitable[None]],
    ) -> None:
        """Register a shutdown hook."""
        self._shutdown_hooks.append(hook)

    async def health_check(self) -> HealthCheckResult:
        """
        Perform health check.

        Checks:
        - Database connectivity
        - Disk space
        - Memory usage
        - Custom health checks
        """
        checks = {}

        # Basic checks
        checks["state_ok"] = self._state == DeploymentState.RUNNING
        checks["not_shutting_down"] = not self._shutting_down

        # Database check
        checks["database"] = await self._check_database()

        # Disk space check
        checks["disk_space"] = self._check_disk_space()

        # Memory check
        checks["memory"] = self._check_memory()

        # Custom checks
        for i, check in enumerate(self._health_checks):
            try:
                checks[f"custom_{i}"] = await check()
            except Exception:
                checks[f"custom_{i}"] = False

        healthy = all(checks.values())

        return HealthCheckResult(
            healthy=healthy,
            checks=checks,
            message="OK" if healthy else "Some checks failed",
            timestamp=utcnow(),
        )

    async def _check_database(self) -> bool:
        """Check database connectivity."""
        try:
            from sqlalchemy import text

            from ..database import engine

            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def _check_disk_space(self, min_gb: float = 1.0) -> bool:
        """Check available disk space."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")
            free_gb = free / (1024**3)
            return free_gb >= min_gb
        except Exception:
            return True

    def _check_memory(self, max_percent: float = 90.0) -> bool:
        """Check memory usage."""
        try:
            import psutil

            memory = psutil.virtual_memory()
            return memory.percent < max_percent
        except ImportError:
            return True
        except Exception:
            return True

    async def drain_connections(self, timeout: int = 30) -> bool:
        """
        Gracefully drain active connections.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if drained successfully
        """
        self._state = DeploymentState.DRAINING
        self._shutting_down = True

        # Wait for active requests to complete
        start = utcnow()
        while self._active_requests > 0:
            elapsed = (utcnow() - start).total_seconds()
            if elapsed > timeout:
                return False
            await asyncio.sleep(0.5)

        return True

    async def graceful_shutdown(self, timeout: int = 30) -> None:
        """
        Perform graceful shutdown.

        1. Stop accepting new requests
        2. Wait for active requests
        3. Run shutdown hooks
        4. Close connections
        """
        # Drain connections
        drained = await self.drain_connections(timeout)
        if not drained:
            print("Warning: Timeout waiting for connections to drain")

        # Run shutdown hooks
        for hook in self._shutdown_hooks:
            try:
                await hook()
            except Exception as e:
                print(f"Shutdown hook error: {e}")

        self._state = DeploymentState.STOPPED

    def track_request_start(self) -> None:
        """Track that a request has started."""
        self._active_requests += 1

    def track_request_end(self) -> None:
        """Track that a request has ended."""
        self._active_requests = max(0, self._active_requests - 1)

    def is_accepting_requests(self) -> bool:
        """Check if server is accepting new requests."""
        return not self._shutting_down and self._state == DeploymentState.RUNNING

    async def prepare_rollback(self) -> bool:
        """
        Prepare for potential rollback by backing up current state.

        Returns:
            True if preparation successful
        """
        try:
            rollback_dir = Path(self.ROLLBACK_DIR)
            rollback_dir.mkdir(exist_ok=True)

            # Save current version
            version_backup = rollback_dir / "version"
            version_backup.write_text(self._version)

            # Record previous version
            self._previous_version = self._version

            return True
        except Exception:
            return False

    async def rollback(self) -> bool:
        """
        Rollback to previous version.

        Returns:
            True if rollback successful
        """
        try:
            rollback_dir = Path(self.ROLLBACK_DIR)
            version_file = rollback_dir / "version"

            if not version_file.exists():
                print("No rollback version available")
                return False

            previous = version_file.read_text().strip()

            # This would trigger actual rollback
            # In container environments, this might restart with previous image
            print(f"Rolling back from {self._version} to {previous}")

            self._version = previous
            self._state = DeploymentState.RUNNING

            return True
        except Exception as e:
            print(f"Rollback failed: {e}")
            self._state = DeploymentState.FAILED
            return False

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def handle_signal(sig):
            print(f"Received signal {sig}, initiating graceful shutdown...")
            asyncio.create_task(self.graceful_shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))


class RollingDeployment:
    """
    Coordinates rolling deployment across multiple instances.

    For use with container orchestrators or manual rolling updates.
    """

    def __init__(
        self,
        total_instances: int = 1,
        max_unavailable: int = 1,
    ):
        self.total_instances = total_instances
        self.max_unavailable = max_unavailable
        self._deployed_instances = 0
        self._failed_instances = 0

    def can_deploy_next(self) -> bool:
        """Check if another instance can be deployed."""
        currently_unavailable = self._deployed_instances
        return currently_unavailable < self.max_unavailable

    def record_deploy_start(self) -> None:
        """Record that an instance deployment started."""
        self._deployed_instances += 1

    def record_deploy_success(self) -> None:
        """Record that an instance deployment succeeded."""
        self._deployed_instances = max(0, self._deployed_instances - 1)

    def record_deploy_failure(self) -> None:
        """Record that an instance deployment failed."""
        self._failed_instances += 1
        self._deployed_instances = max(0, self._deployed_instances - 1)

    def should_abort(self, max_failures: int = 1) -> bool:
        """Check if deployment should be aborted."""
        return self._failed_instances >= max_failures

    def get_progress(self) -> dict:
        """Get deployment progress."""
        return {
            "total": self.total_instances,
            "in_progress": self._deployed_instances,
            "failed": self._failed_instances,
            "remaining": self.total_instances - self._deployed_instances - self._failed_instances,
        }


# Global instance
deployment_service = DeploymentService()


def get_deployment_service() -> DeploymentService:
    return deployment_service
