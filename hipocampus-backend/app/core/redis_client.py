"""
app/core/redis_client.py

Manages a single shared async Redis connection pool for the entire process.
The pool is opened once on startup and closed on shutdown.
Both the API layer and the Celery tasks read from the same REDIS_URL,
but Celery uses its own broker connection (handled in tasks/celery_app.py).
This module covers the application-level pool only: working-memory buffers,
preference caches, and any ad-hoc key/value ops from service code.
"""

from typing import Optional

import redis.asyncio as aioredis # type: ignore

from app.config import get_settings

settings = get_settings()

# Module-level pool reference.
# Starts as None; get_redis_client() raises clearly if called before init.
_redis_pool: Optional[aioredis.Redis] = None


async def init_redis_pool() -> None:
    """
    Creates the shared Redis connection pool and stores it at module level.
    Should be called exactly once, inside main.py's startup event, before
    any request is served.
    Takes no parameters — reads REDIS_URL from settings automatically.
    Used by: app/main.py startup event.
    """
    global _redis_pool
    _redis_pool = await aioredis.from_url(
        settings.REDIS_URL,
        # One physical connection per async worker is usually fine;
        # raise this if you see pool exhaustion warnings under load.
        max_connections=20,
        # Return Python str instead of bytes — every value we store is JSON,
        # so raw bytes would need manual decoding everywhere.
        decode_responses=True,
    )


async def close_redis_pool() -> None:
    """
    Drains and closes all connections in the pool gracefully.
    Called inside main.py's shutdown event so the process exits without
    leaving dangling TCP connections on the Redis side.
    Takes no parameters.
    Used by: app/main.py shutdown event.
    """
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


def get_redis_client() -> aioredis.Redis:
    """
    Returns the shared Redis client (backed by the pool created in init_redis_pool).
    Raises RuntimeError if called before the pool has been initialised —
    this surfaces immediately in tests and local runs rather than hiding
    behind a cryptic connection error.
    Takes no parameters.
    Used by: app/dependencies.py (to expose it as FastAPI Depends),
             app/services/memory_engine/redis_buffer.py (direct import in workers
             where Depends is not available).
    """
    if _redis_pool is None:
        raise RuntimeError(
            "Redis pool is not initialised. "
            "Ensure init_redis_pool() is awaited in the FastAPI startup event "
            "before any request is handled."
        )
    return _redis_pool