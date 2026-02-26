"""Compatibility helpers for asyncpg pool acquisition in tests and runtime."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def compatible_acquire(pool: Any):
    """
    Acquire a DB connection from asyncpg pool with AsyncMock-safe behavior.

    In production, ``pool.acquire()`` returns a PoolAcquireContext which is
    BOTH awaitable AND an async context manager. We must use the context
    manager form (``async with``) to ensure the connection is released.

    In tests, mocked pools may return a plain async context manager.
    The old code used ``inspect.isawaitable()`` to detect mocks, but this
    also matched asyncpg's PoolAcquireContext (which implements __await__),
    causing connections to be acquired via ``await`` and never released.
    """
    acquire_result = pool.acquire()

    # asyncpg PoolAcquireContext supports both __await__ and __aenter__/__aexit__.
    # Always prefer the context manager form to ensure release.
    if hasattr(acquire_result, '__aenter__'):
        async with acquire_result as conn:
            yield conn
    elif inspect.isawaitable(acquire_result):
        # Test mock path: awaitable that resolves to a connection
        conn = await acquire_result
        try:
            yield conn
        finally:
            # Best-effort release for mocked connections
            if hasattr(conn, 'close'):
                try:
                    await conn.close()
                except Exception:
                    pass
    else:
        raise TypeError(f"pool.acquire() returned unexpected type: {type(acquire_result)}")
