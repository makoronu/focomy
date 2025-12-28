"""Sentry Integration - Error tracking.

Provides error tracking and performance monitoring via Sentry.
"""

from contextlib import contextmanager
from typing import Any

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


class SentryService:
    """
    Sentry error tracking service.

    Usage:
        # Initialize at startup
        sentry = SentryService()
        sentry.init(dsn="https://xxx@sentry.io/123")

        # Capture exception
        try:
            do_something()
        except Exception as e:
            sentry.capture_exception(e)

        # Capture message
        sentry.capture_message("Something happened", level="info")

        # Set user context
        sentry.set_user(id="123", email="user@example.com")
    """

    _initialized: bool = False

    def init(
        self,
        dsn: str,
        environment: str = "production",
        release: str | None = None,
        sample_rate: float = 1.0,
        traces_sample_rate: float = 0.1,
        debug: bool = False,
    ) -> bool:
        """
        Initialize Sentry SDK.

        Args:
            dsn: Sentry DSN
            environment: Environment name (production, staging, etc.)
            release: Release version
            sample_rate: Error sampling rate (0.0 to 1.0)
            traces_sample_rate: Performance monitoring rate
            debug: Enable debug mode

        Returns:
            True if initialized successfully
        """
        if not SENTRY_AVAILABLE:
            return False

        if not dsn:
            return False

        try:
            sentry_sdk.init(
                dsn=dsn,
                environment=environment,
                release=release,
                sample_rate=sample_rate,
                traces_sample_rate=traces_sample_rate,
                debug=debug,
                integrations=[
                    FastApiIntegration(),
                    SqlalchemyIntegration(),
                ],
                # Don't send PII by default
                send_default_pii=False,
            )
            self._initialized = True
            return True
        except Exception:
            return False

    def capture_exception(
        self,
        exception: Exception = None,
        **context,
    ) -> str | None:
        """
        Capture an exception.

        Args:
            exception: Exception to capture (uses current if None)
            **context: Additional context data

        Returns:
            Event ID if captured, None otherwise
        """
        if not self._initialized or not SENTRY_AVAILABLE:
            return None

        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_exception(exception)

    def capture_message(
        self,
        message: str,
        level: str = "info",
        **context,
    ) -> str | None:
        """
        Capture a message.

        Args:
            message: Message to capture
            level: Severity level (debug, info, warning, error, fatal)
            **context: Additional context data

        Returns:
            Event ID if captured, None otherwise
        """
        if not self._initialized or not SENTRY_AVAILABLE:
            return None

        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_message(message, level=level)

    def set_user(
        self,
        id: str = None,
        email: str = None,
        username: str = None,
        ip_address: str = None,
    ) -> None:
        """Set user context for error tracking."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return

        user_data = {}
        if id:
            user_data["id"] = id
        if email:
            user_data["email"] = email
        if username:
            user_data["username"] = username
        if ip_address:
            user_data["ip_address"] = ip_address

        sentry_sdk.set_user(user_data)

    def clear_user(self) -> None:
        """Clear user context."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return
        sentry_sdk.set_user(None)

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag for filtering."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return
        sentry_sdk.set_tag(key, value)

    def set_extra(self, key: str, value: Any) -> None:
        """Set extra context data."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return
        sentry_sdk.set_extra(key, value)

    @contextmanager
    def span(self, op: str, description: str):
        """Create a performance monitoring span."""
        if not self._initialized or not SENTRY_AVAILABLE:
            yield
            return

        with sentry_sdk.start_span(op=op, description=description) as span:
            yield span

    def add_breadcrumb(
        self,
        message: str,
        category: str = "default",
        level: str = "info",
        data: dict = None,
    ) -> None:
        """Add a breadcrumb for debugging."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return

        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {},
        )

    def flush(self, timeout: float = 2.0) -> None:
        """Flush pending events."""
        if not self._initialized or not SENTRY_AVAILABLE:
            return
        sentry_sdk.flush(timeout=timeout)


# Global instance
sentry_service = SentryService()


def init_sentry_from_settings(settings) -> None:
    """Initialize Sentry from application settings."""
    dsn = getattr(settings, "sentry_dsn", None)
    if dsn:
        sentry_service.init(
            dsn=dsn,
            environment="development" if settings.debug else "production",
            debug=settings.debug,
        )
