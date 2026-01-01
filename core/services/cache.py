"""Cache Service - Supports Redis and in-memory caching.

Provides a unified caching interface that:
- Uses Redis when configured
- Falls back to in-memory cache otherwise
- Supports TTL (time-to-live)
- Supports cache invalidation patterns
"""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)
from functools import wraps
from typing import Any, Optional, TypeVar

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


T = TypeVar("T")

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        pass

    @abstractmethod
    async def clear(self) -> int:
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass


class CacheEntry:
    """A single cache entry with expiration."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.expires_at = utcnow() + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at


class InMemoryBackend(CacheBackend):
    """In-memory cache backend with TTL support."""

    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl or 300  # Default 5 minutes
        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching glob pattern."""
        import fnmatch

        async with self._lock:
            to_delete = [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
            for key in to_delete:
                del self._cache[key]
            return len(to_delete)

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    async def exists(self, key: str) -> bool:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True

    def cleanup_expired(self) -> int:
        """Remove expired entries (sync for periodic cleanup)."""
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
            "backend": "memory",
        }


class RedisBackend(CacheBackend):
    """Redis cache backend."""

    def __init__(self, client, prefix: str = "focomy:"):
        self._redis = client
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> Any | None:
        try:
            data = await self._redis.get(self._key(key))
            if data is None:
                return None
            return json.loads(data)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl or 300
        try:
            serialized = json.dumps(value, default=str)
            await self._redis.setex(self._key(key), ttl, serialized)
        except Exception as e:
            logger.debug(f"Redis cache set failed for key {key}: {e}")

    async def delete(self, key: str) -> bool:
        try:
            result = await self._redis.delete(self._key(key))
            return result > 0
        except Exception:
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern using SCAN."""
        try:
            count = 0
            cursor = 0
            match_pattern = self._key(pattern)

            while True:
                cursor, keys = await self._redis.scan(cursor, match=match_pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception:
            return 0

    async def clear(self) -> int:
        """Clear all focomy cache entries."""
        return await self.delete_pattern("*")

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self._redis.exists(self._key(key)))
        except Exception:
            return False

    def stats(self) -> dict:
        """Get cache statistics."""
        return {"backend": "redis"}


class CacheService:
    """
    Unified cache service with Redis support.

    Usage:
        cache = CacheService()
        await cache.connect()  # Optional: auto-connects on first use

        # Basic operations
        await cache.set("key", {"data": "value"}, ttl=300)
        value = await cache.get("key")
        await cache.delete("key")

        # Pattern invalidation
        await cache.invalidate_pattern("entity:*")
    """

    _instance: Optional["CacheService"] = None

    def __new__(cls, redis_url: str | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._redis_url = redis_url
            cls._instance._backend = None
            cls._instance._connected = False
        return cls._instance

    async def connect(self, redis_url: str | None = None) -> None:
        """Initialize cache backend."""
        if self._connected:
            return

        url = redis_url or self._redis_url

        # Try Redis if available and configured
        if REDIS_AVAILABLE and url:
            try:
                client = aioredis.from_url(url, decode_responses=True)
                await client.ping()
                self._backend = RedisBackend(client)
                self._connected = True
                return
            except Exception as e:
                logger.debug(f"Redis connection failed: {e}")

        # Fall back to in-memory
        self._backend = InMemoryBackend()
        self._connected = True

    async def disconnect(self) -> None:
        """Close connections."""
        if isinstance(self._backend, RedisBackend):
            await self._backend._redis.close()
        self._backend = None
        self._connected = False

    @property
    def backend(self) -> CacheBackend:
        if self._backend is None:
            self._backend = InMemoryBackend()
            self._connected = True
        return self._backend

    # Core operations (async)
    async def get(self, key: str) -> Any | None:
        return await self.backend.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.backend.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        return await self.backend.delete(key)

    async def invalidate_pattern(self, pattern: str) -> int:
        return await self.backend.delete_pattern(pattern)

    async def invalidate_all(self) -> int:
        return await self.backend.clear()

    async def exists(self, key: str) -> bool:
        return await self.backend.exists(key)

    # Sync operations (for backward compatibility)
    def get_sync(self, key: str) -> Any | None:
        """Synchronous get (only works with in-memory backend)."""
        if isinstance(self.backend, InMemoryBackend):
            entry = self.backend._cache.get(key)
            if entry and not entry.is_expired():
                return entry.value
        return None

    def set_sync(self, key: str, value: Any, ttl: int = 300) -> None:
        """Synchronous set (only works with in-memory backend)."""
        if isinstance(self.backend, InMemoryBackend):
            self.backend._cache[key] = CacheEntry(value, ttl)

    def delete_sync(self, key: str) -> bool:
        """Synchronous delete (only works with in-memory backend)."""
        if isinstance(self.backend, InMemoryBackend):
            if key in self.backend._cache:
                del self.backend._cache[key]
                return True
        return False

    # Utility methods
    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | None = None,
    ) -> Any:
        """Get from cache or compute and store."""
        value = await self.get(key)
        if value is not None:
            return value

        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        if value is not None:
            await self.set(key, value, ttl)
        return value

    def stats(self) -> dict:
        """Get cache statistics."""
        if isinstance(self.backend, InMemoryBackend):
            return self.backend.stats()
        elif isinstance(self.backend, RedisBackend):
            return self.backend.stats()
        return {"backend": "none"}


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
    Decorator for caching async function results.

    Usage:
        @cached("page", ttl=300)
        async def get_page(slug):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = f"{prefix}:{make_cache_key(*args, **kwargs)}"

            cached_value = await cache_service.get(key)
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)

            if result is not None:
                await cache_service.set(key, result, ttl)

            return result

        # Add invalidation helpers
        wrapper.cache_key = lambda *a, **kw: f"{prefix}:{make_cache_key(*a, **kw)}"
        wrapper.invalidate = lambda *a, **kw: cache_service.delete(
            f"{prefix}:{make_cache_key(*a, **kw)}"
        )
        wrapper.invalidate_all = lambda: cache_service.invalidate_pattern(f"{prefix}:*")

        return wrapper

    return decorator


def invalidate_cache(prefix: str) -> int:
    """Invalidate all cache entries with a given prefix (sync, for backward compat)."""
    if isinstance(cache_service.backend, InMemoryBackend):
        to_delete = [k for k in cache_service.backend._cache.keys() if k.startswith(prefix)]
        for key in to_delete:
            del cache_service.backend._cache[key]
        return len(to_delete)
    return 0


# Cache key helpers
class CacheKeys:
    """Common cache key patterns."""

    @staticmethod
    def entity(entity_id: str) -> str:
        return f"entity:{entity_id}"

    @staticmethod
    def entity_list(entity_type: str, page: int = 1) -> str:
        return f"list:{entity_type}:{page}"

    @staticmethod
    def settings(key: str = "all") -> str:
        return f"settings:{key}"

    @staticmethod
    def theme(theme_name: str) -> str:
        return f"theme:{theme_name}"
