"""
Cache management module.
Provides in-memory and Redis caching capabilities.
"""

from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import asyncio
import json
import logging
from cachetools import TTLCache
import redis.asyncio as redis

from config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Cache manager with support for in-memory and Redis backends."""

    def __init__(self):
        """Initialize cache manager."""
        self._memory_cache: Optional[TTLCache] = None
        self._redis_client: Optional[redis.Redis] = None
        self._use_redis = settings.use_redis

        # Initialize memory cache if not using Redis
        if not self._use_redis:
            self._memory_cache = TTLCache(
                maxsize=1000,
                ttl=300  # 5 minutes default TTL
            )
            logger.info("Initialized in-memory cache")

    async def initialize_redis(self) -> None:
        """Initialize Redis connection if enabled."""
        if self._use_redis and settings.redis_url:
            try:
                self._redis_client = redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis_client.ping()
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis: {e}. Falling back to memory cache.")
                self._use_redis = False
                self._memory_cache = TTLCache(maxsize=1000, ttl=300)

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        try:
            if self._use_redis and self._redis_client:
                value = await self._redis_client.get(key)
                if value:
                    return json.loads(value)
            elif self._memory_cache is not None:
                return self._memory_cache.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")

        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        try:
            if self._use_redis and self._redis_client:
                serialized = json.dumps(value, default=str)
                await self._redis_client.setex(key, ttl, serialized)
                return True
            elif self._memory_cache is not None:
                # TTL Cache doesn't support per-key TTL easily,
                # so we store with timestamp
                self._memory_cache[key] = {
                    'value': value,
                    'expires_at': datetime.utcnow() + timedelta(seconds=ttl)
                }
                return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")

        return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        try:
            if self._use_redis and self._redis_client:
                await self._redis_client.delete(key)
                return True
            elif self._memory_cache is not None:
                self._memory_cache.pop(key, None)
                return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")

        return False

    async def clear(self) -> bool:
        """
        Clear all cache.

        Returns:
            True if cleared
        """
        try:
            if self._use_redis and self._redis_client:
                await self._redis_client.flushdb()
                return True
            elif self._memory_cache is not None:
                self._memory_cache.clear()
                return True
        except Exception as e:
            logger.error(f"Cache clear error: {e}")

        return False

    async def close(self) -> None:
        """Close cache connections."""
        if self._use_redis and self._redis_client:
            await self._redis_client.close()
            logger.info("Redis connection closed")


# Global cache manager
cache_manager = CacheManager()