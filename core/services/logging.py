"""Structured logging service using structlog.

Provides consistent, JSON-structured logging across the application.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from ..config import settings


def configure_logging() -> None:
    """Configure structlog and standard logging.

    Call this once at application startup.
    """
    # Shared processors for all loggers
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.debug:
        # Development: colored console output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Production: JSON output
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to also use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str = None) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name, typically __name__ of the module

    Returns:
        A bound structlog logger
    """
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding structured context to logs.

    Usage:
        with LogContext(user_id="123", action="update"):
            logger.info("Operation completed")
            # Logs will include user_id and action
    """

    def __init__(self, **kwargs: Any):
        self.context = kwargs
        self._token = None

    def __enter__(self):
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, *args):
        structlog.contextvars.unbind_contextvars(*self.context.keys())


def bind_context(**kwargs: Any) -> None:
    """Bind context variables for the current async context.

    These values will be included in all subsequent log messages
    until unbound or the context ends.
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Unbind context variables."""
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all context variables."""
    structlog.contextvars.clear_contextvars()


# Pre-configured loggers for common use cases
logger = get_logger("focomy")
db_logger = get_logger("focomy.db")
auth_logger = get_logger("focomy.auth")
api_logger = get_logger("focomy.api")
admin_logger = get_logger("focomy.admin")
