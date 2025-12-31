"""Utility functions for Focomy."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time as naive datetime for DB storage.

    PostgreSQL TIMESTAMP WITHOUT TIME ZONE expects naive datetimes.
    This function returns UTC time without tzinfo to avoid mismatch errors.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
