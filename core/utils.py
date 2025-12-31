"""Utility functions for Focomy."""

from datetime import datetime, timezone
from functools import lru_cache

from fastapi import HTTPException


def utcnow() -> datetime:
    """Return current UTC time as naive datetime for DB storage.

    PostgreSQL TIMESTAMP WITHOUT TIME ZONE expects naive datetimes.
    This function returns UTC time without tzinfo to avoid mismatch errors.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled.

    Args:
        feature: Feature name (e.g., 'media', 'comment', 'wordpress_import')

    Returns:
        True if feature is enabled, False otherwise
    """
    from .config import get_settings

    settings = get_settings()
    return getattr(settings.features, feature, False)


def require_feature(feature: str) -> None:
    """Raise 404 if feature is disabled.

    Use this at the start of API endpoints to disable them when feature is off.

    Args:
        feature: Feature name

    Raises:
        HTTPException: 404 if feature is disabled
    """
    if not is_feature_enabled(feature):
        raise HTTPException(status_code=404, detail="Not Found")
