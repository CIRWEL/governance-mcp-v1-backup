"""
Redis-backed cache layer for distributed deployments.

Provides:
- Session cache: session_id -> agent_id bindings (survives restarts)
- Distributed locks: multi-server coordination (replaces file-based fcntl locks)

Usage:
    from src.cache import get_session_cache, get_distributed_lock

    # Session cache
    cache = get_session_cache()
    await cache.bind(session_id, agent_id)
    agent_id = await cache.get(session_id)

    # Distributed lock
    lock = get_distributed_lock()
    async with lock.acquire(agent_id):
        # exclusive access to agent state
        ...

Fallback:
    If Redis is unavailable, gracefully falls back to in-memory cache
    and file-based locking (current behavior).
"""

from .redis_client import (
    get_redis,
    is_redis_available,
    close_redis,
    reset_redis_state,
    get_redis_metrics,
    get_circuit_breaker,
    with_redis_fallback,
    ResilientRedisClient,
    RedisConfig,
    CircuitBreaker,
    RedisMetrics,
)
from .session_cache import SessionCache, get_session_cache
from .distributed_lock import DistributedLock, get_distributed_lock
from .rate_limiter import RateLimiter, get_rate_limiter
from .metadata_cache import MetadataCache, get_metadata_cache

__all__ = [
    # Redis client
    "get_redis",
    "is_redis_available",
    "close_redis",
    "reset_redis_state",
    "get_redis_metrics",
    "get_circuit_breaker",
    "with_redis_fallback",
    # Redis classes
    "ResilientRedisClient",
    "RedisConfig",
    "CircuitBreaker",
    "RedisMetrics",
    # Session cache
    "SessionCache",
    "get_session_cache",
    # Distributed lock
    "DistributedLock",
    "get_distributed_lock",
    # Rate limiter
    "RateLimiter",
    "get_rate_limiter",
    # Metadata cache
    "MetadataCache",
    "get_metadata_cache",
]
