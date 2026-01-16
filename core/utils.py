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


async def is_feature_enabled_async(feature: str, db) -> bool:
    """Check if a feature is enabled (async version, DB-first).

    Priority: DB settings > code default (True)
    Note: config.yaml is ignored for features to allow DB override without restart.

    Args:
        feature: Feature name (e.g., 'form', 'comment')
        db: AsyncSession database session

    Returns:
        True if feature is enabled, False otherwise
    """
    from .services.settings import SettingsService, DEFAULT_SETTINGS

    settings_svc = SettingsService(db)
    # Check DB directly (not through get() which includes config.yaml)
    db_value = await settings_svc._get_db_value(f"features.{feature}")

    if db_value is not None:
        # DB value exists, use it
        if isinstance(db_value, bool):
            return db_value
        if isinstance(db_value, str):
            return db_value.lower() in ("true", "1", "yes")
        return bool(db_value)

    # Fallback to code default (ignore config.yaml)
    return DEFAULT_SETTINGS.get("features", {}).get(feature, True)


async def require_feature_async(feature: str, db) -> None:
    """Raise 404 if feature is disabled (async version, DB-first).

    Use this at the start of API endpoints for dynamic feature checking.

    Args:
        feature: Feature name
        db: AsyncSession database session

    Raises:
        HTTPException: 404 if feature is disabled
    """
    if not await is_feature_enabled_async(feature, db):
        raise HTTPException(status_code=404, detail="Not Found")
