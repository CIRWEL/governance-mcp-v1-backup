"""
Tests for src/cache/metadata_cache.py (Redis cache for agent metadata).

Covers:
- get() - cache hit, cache miss, no redis
- set() - stores with TTL, custom TTL, no redis
- invalidate() - removes cached entry, no redis
- invalidate_all() - clears all metadata entries
- Singleton get_metadata_cache()
"""

import json
import pytest
from unittest.mock import patch

import fakeredis.aioredis

from src.cache.metadata_cache import (
    MetadataCache,
    get_metadata_cache,
    METADATA_PREFIX,
    DEFAULT_TTL,
)


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cache(fake_redis):
    """MetadataCache with fakeredis backend."""
    async def _get_fake_redis():
        return fake_redis

    with patch("src.cache.metadata_cache.get_redis", new=_get_fake_redis):
        yield MetadataCache()


@pytest.fixture
def cache_no_redis():
    """MetadataCache with no Redis (fallback behavior)."""
    async def _get_none():
        return None

    with patch("src.cache.metadata_cache.get_redis", new=_get_none):
        yield MetadataCache()


# ============================================================================
# get()
# ============================================================================

class TestGet:

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        result = await cache.get("nonexistent-agent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, cache, fake_redis):
        """Pre-populated cache returns data."""
        agent_id = "test-agent-uuid"
        metadata = {"label": "TestBot", "status": "active"}
        key = f"{METADATA_PREFIX}{agent_id}"
        await fake_redis.set(key, json.dumps(metadata))

        result = await cache.get(agent_id)
        assert result == metadata
        assert result["label"] == "TestBot"

    @pytest.mark.asyncio
    async def test_no_redis_returns_none(self, cache_no_redis):
        result = await cache_no_redis.get("any-agent")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self, cache, fake_redis):
        """Corrupted cache data handled gracefully."""
        key = f"{METADATA_PREFIX}corrupt-agent"
        await fake_redis.set(key, "not-valid-json{{{")

        result = await cache.get("corrupt-agent")
        assert result is None


# ============================================================================
# set()
# ============================================================================

class TestSet:

    @pytest.mark.asyncio
    async def test_set_stores_data(self, cache, fake_redis):
        agent_id = "store-agent"
        metadata = {"label": "StoreBot", "tags": ["test"]}

        result = await cache.set(agent_id, metadata)
        assert result is True

        # Verify in Redis
        key = f"{METADATA_PREFIX}{agent_id}"
        raw = await fake_redis.get(key)
        assert raw is not None
        assert json.loads(raw) == metadata

    @pytest.mark.asyncio
    async def test_set_default_ttl(self, cache, fake_redis):
        agent_id = "ttl-agent"
        await cache.set(agent_id, {"test": True})

        key = f"{METADATA_PREFIX}{agent_id}"
        ttl = await fake_redis.ttl(key)
        assert ttl > 0
        assert ttl <= DEFAULT_TTL

    @pytest.mark.asyncio
    async def test_set_custom_ttl(self, cache, fake_redis):
        agent_id = "custom-ttl"
        await cache.set(agent_id, {"test": True}, ttl=60)

        key = f"{METADATA_PREFIX}{agent_id}"
        ttl = await fake_redis.ttl(key)
        assert ttl > 0
        assert ttl <= 60

    @pytest.mark.asyncio
    async def test_set_no_redis(self, cache_no_redis):
        result = await cache_no_redis.set("any-agent", {"test": True})
        assert result is False

    @pytest.mark.asyncio
    async def test_set_then_get(self, cache):
        """Round-trip: set then get returns same data."""
        agent_id = "roundtrip-agent"
        metadata = {
            "label": "RoundTrip",
            "status": "active",
            "total_updates": 42,
        }
        await cache.set(agent_id, metadata)
        result = await cache.get(agent_id)
        assert result == metadata


# ============================================================================
# invalidate()
# ============================================================================

class TestInvalidate:

    @pytest.mark.asyncio
    async def test_invalidate_removes_entry(self, cache):
        agent_id = "invalidate-agent"
        await cache.set(agent_id, {"test": True})
        assert await cache.get(agent_id) is not None

        result = await cache.invalidate(agent_id)
        assert result is True
        assert await cache.get(agent_id) is None

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent(self, cache):
        """Invalidating nonexistent key doesn't raise."""
        result = await cache.invalidate("nonexistent")
        assert result is True  # Redis delete returns 0 but no error

    @pytest.mark.asyncio
    async def test_invalidate_no_redis(self, cache_no_redis):
        result = await cache_no_redis.invalidate("any-agent")
        assert result is False


# ============================================================================
# invalidate_all()
# ============================================================================

class TestInvalidateAll:

    @pytest.mark.asyncio
    async def test_invalidate_all(self, cache, fake_redis):
        """Clears all metadata cache entries."""
        await cache.set("agent-a", {"label": "A"})
        await cache.set("agent-b", {"label": "B"})
        await cache.set("agent-c", {"label": "C"})

        deleted = await cache.invalidate_all()
        assert deleted == 3

        # All should be gone
        assert await cache.get("agent-a") is None
        assert await cache.get("agent-b") is None
        assert await cache.get("agent-c") is None

    @pytest.mark.asyncio
    async def test_invalidate_all_empty(self, cache):
        """No entries to delete returns 0."""
        deleted = await cache.invalidate_all()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_invalidate_all_no_redis(self, cache_no_redis):
        deleted = await cache_no_redis.invalidate_all()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_invalidate_all_doesnt_touch_other_keys(self, cache, fake_redis):
        """Only metadata keys are deleted, not other Redis keys."""
        await cache.set("agent-x", {"label": "X"})
        # Set a non-metadata key directly
        await fake_redis.set("other:key", "value")

        deleted = await cache.invalidate_all()
        assert deleted == 1

        # Other key should still exist
        other = await fake_redis.get("other:key")
        assert other == "value"


# ============================================================================
# Singleton
# ============================================================================

class TestSingleton:

    def test_get_metadata_cache_returns_same_instance(self):
        import src.cache.metadata_cache as mod
        old = mod._metadata_cache
        mod._metadata_cache = None
        try:
            mc1 = get_metadata_cache()
            mc2 = get_metadata_cache()
            assert mc1 is mc2
        finally:
            mod._metadata_cache = old
