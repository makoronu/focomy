"""CacheService - simple in-memory cache with TTL."""

from datetime import datetime, timedelta
from typing import Any, Optional
from functools import wraps
import hashlib


class CacheEntry:
    """A single cache entry with expiration."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class CacheService:
    """
    Simple in-memory cache service.

    Features:
    - TTL-based expiration
    - Key prefix support for namespacing
    - Invalidation by pattern
    """

    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._cache[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a cached value with TTL (default 5 minutes)."""
        self._cache[key] = CacheEntry(value, ttl)

    def delete(self, key: str) -> bool:
        """Delete a cached value."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern (simple prefix match)."""
        to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
        for key in to_delete:
            del self._cache[key]
        return len(to_delete)

    def invalidate_all(self) -> int:
        """Clear all cached values."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def cleanup_expired(self) -> int:
        """Remove expired entries."""
        expired = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired:
            del self._cache[key]
        return len(expired)

    def stats(self) -> dict:
        """Get cache statistics."""
        valid = sum(1 for v in self._cache.values() if not v.is_expired())
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid,
            "expired_entries": len(self._cache) - valid,
        }


# Singleton instance
cache_service = CacheService()


def make_cache_key(*args, **kwargs) -> str:
    """Generate a cache key from arguments."""
    key_parts = [str(a) for a in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_str = ":".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def cached(prefix: str, ttl: int = 300):
    """
    Decorator for caching function results.

    Usage:
        @cached("page", ttl=300)
        async def get_page(slug):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = f"{prefix}:{make_cache_key(*args, **kwargs)}"

            # Check cache
            cached_value = cache_service.get(key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            if result is not None:
                cache_service.set(key, result, ttl)

            return result
        return wrapper
    return decorator


def invalidate_cache(prefix: str):
    """Invalidate all cache entries with a given prefix."""
    return cache_service.invalidate_pattern(prefix)
