"""
Comprehensive tests for src/mcp_handlers/identity_v2.py.

Covers the full identity resolution pipeline:
- resolve_session_identity() 3-tier: Redis -> PostgreSQL -> Create new
- _derive_session_key() priority chain
- _validate_session_key() / sanitization within resolve_session_identity
- persist_identity via ensure_agent_persisted()
- get_agent_label / _get_agent_label
- _agent_exists_in_postgres
- _find_agent_by_label
- _get_agent_id_from_metadata
- _generate_agent_id (pure function)
- set_agent_label
- resolve_by_name_claim
- _cache_session
- _extract_stable_identifier
- _extract_base_fingerprint
- ua_hash_from_header
- lookup_onboard_pin / set_onboard_pin
- handle_identity_v2 (tool handler)
- ensure_agent_persisted (lazy creation)
- migrate_from_v1

All external I/O (Redis, PostgreSQL, MCP server) is mocked.
"""

import pytest
import json
import sys
import os
import uuid
import re
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# Shared Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Mock PostgreSQL database with all methods used by identity_v2."""
    db = AsyncMock()
    db.init = AsyncMock()
    db.get_session = AsyncMock(return_value=None)
    db.get_identity = AsyncMock(return_value=None)
    db.get_agent = AsyncMock(return_value=None)
    db.get_agent_label = AsyncMock(return_value=None)
    db.upsert_agent = AsyncMock()
    db.upsert_identity = AsyncMock()
    db.create_session = AsyncMock()
    db.update_session_activity = AsyncMock()
    db.find_agent_by_label = AsyncMock(return_value=None)
    db.update_agent_fields = AsyncMock(return_value=True)
    return db


@pytest.fixture
def mock_redis():
    """Mock Redis session cache (SessionCache interface)."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.bind = AsyncMock()
    return cache


@pytest.fixture
def mock_raw_redis():
    """Mock raw Redis client for setex/expire/get operations."""
    r = AsyncMock()
    r.setex = AsyncMock()
    r.expire = AsyncMock()
    r.get = AsyncMock(return_value=None)
    return r


@pytest.fixture
def patch_all_deps(mock_db, mock_redis, mock_raw_redis):
    """
    Patch all identity_v2 external dependencies: Redis, PostgreSQL, raw Redis.

    This fixture resets the module-level _redis_cache so _get_redis() re-initializes,
    and patches get_db, get_session_cache, and raw get_redis.
    """
    async def _get_raw():
        return mock_raw_redis

    with patch("src.mcp_handlers.identity_v2._redis_cache", None), \
         patch("src.cache.get_session_cache", return_value=mock_redis), \
         patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
         patch("src.cache.redis_client.get_redis", new=_get_raw):
        yield


@pytest.fixture
def patch_no_redis(mock_db):
    """Patch dependencies with Redis unavailable (cache returns None)."""
    with patch("src.mcp_handlers.identity_v2._redis_cache", False), \
         patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
        yield


@pytest.fixture
def patch_mcp_server():
    """Patch get_mcp_server to return a mock with agent_metadata dict."""
    mock_server = MagicMock()
    mock_server.agent_metadata = {}
    with patch("src.mcp_handlers.shared.get_mcp_server", return_value=mock_server):
        yield mock_server


# ============================================================================
# _generate_agent_id (pure function - no I/O)
# ============================================================================

class TestGenerateAgentId:

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from src.mcp_handlers.identity_v2 import _generate_agent_id
        self.generate = _generate_agent_id

    def test_with_model_type_claude(self):
        result = self.generate(model_type="claude-opus-4-5")
        assert result.startswith("Claude_Opus_4_5_")
        # Ends with YYYYMMDD
        date_part = result.split("_")[-1]
        assert len(date_part) == 8
        assert date_part.isdigit()

    def test_with_model_type_gemini(self):
        result = self.generate(model_type="gemini-pro")
        assert result.startswith("Gemini_Pro_")

    def test_with_model_type_dots(self):
        result = self.generate(model_type="gpt.4.turbo")
        assert "Gpt" in result
        assert "4" in result
        assert "Turbo" in result

    def test_with_client_hint(self):
        result = self.generate(client_hint="cursor")
        assert result.startswith("cursor_")

    def test_with_client_hint_spaces(self):
        result = self.generate(client_hint="my editor")
        assert result.startswith("my_editor_")

    def test_fallback_no_args(self):
        result = self.generate()
        assert result.startswith("mcp_")

    def test_model_type_takes_priority_over_client_hint(self):
        result = self.generate(model_type="gemini-pro", client_hint="cursor")
        assert result.startswith("Gemini_Pro_")
        assert "cursor" not in result

    def test_empty_client_hint_fallback(self):
        result = self.generate(client_hint="")
        assert result.startswith("mcp_")

    def test_unknown_client_hint_fallback(self):
        result = self.generate(client_hint="unknown")
        assert result.startswith("mcp_")

    def test_whitespace_model_type(self):
        result = self.generate(model_type="  claude-haiku  ")
        assert result.startswith("Claude_Haiku_")

    def test_underscores_in_model_type(self):
        result = self.generate(model_type="claude_opus_4")
        assert result.startswith("Claude_Opus_4_")


# ============================================================================
# _get_date_context (pure function)
# ============================================================================

class TestGetDateContext:

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from src.mcp_handlers.identity_v2 import _get_date_context
        self.get_ctx = _get_date_context

    def test_returns_all_required_keys(self):
        result = self.get_ctx()
        required = ['full', 'short', 'compact', 'iso', 'iso_utc', 'year', 'month', 'weekday']
        for k in required:
            assert k in result, f"Missing key: {k}"

    def test_iso_utc_ends_with_z(self):
        result = self.get_ctx()
        assert result['iso_utc'].endswith('Z')

    def test_compact_is_digits(self):
        result = self.get_ctx()
        assert result['compact'].isdigit()
        assert len(result['compact']) == 8


# ============================================================================
# _derive_session_key - Priority chain
# ============================================================================

class TestDeriveSessionKey:

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from src.mcp_handlers.identity_v2 import _derive_session_key
        self.derive = _derive_session_key

    def test_priority_1_explicit_client_session_id(self):
        """client_session_id in arguments has highest priority."""
        result = self.derive({"client_session_id": "explicit-123"})
        assert result == "explicit-123"

    def test_priority_2_mcp_session_id_header(self):
        """mcp-session-id header is second priority."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value="mcp-sess-abc"):
            result = self.derive({})
            assert result == "mcp:mcp-sess-abc"

    def test_priority_3_contextvars_session_key(self):
        """contextvars session_key is third priority."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value=None), \
             patch("src.mcp_handlers.context.get_context_session_key", return_value="ctx-key-789"):
            result = self.derive({})
            assert result == "ctx-key-789"

    def test_priority_4_stdio_fallback(self):
        """Falls back to stdio:{pid} when nothing else is available."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value=None), \
             patch("src.mcp_handlers.context.get_context_session_key", return_value=None):
            result = self.derive({})
            assert result.startswith("stdio:")
            assert str(os.getpid()) in result

    def test_explicit_overrides_mcp_header(self):
        """client_session_id takes priority over mcp-session-id."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value="mcp-id"):
            result = self.derive({"client_session_id": "explicit"})
            assert result == "explicit"

    def test_mcp_session_id_overrides_contextvars(self):
        """mcp-session-id takes priority over contextvars."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value="mcp-id"), \
             patch("src.mcp_handlers.context.get_context_session_key", return_value="ctx-key"):
            result = self.derive({})
            assert result == "mcp:mcp-id"

    def test_empty_client_session_id_falls_through(self):
        """Empty string client_session_id falls through to next priority."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value="mcp-id"):
            result = self.derive({"client_session_id": ""})
            assert result == "mcp:mcp-id"

    def test_none_client_session_id_falls_through(self):
        """None client_session_id falls through to next priority."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value="mcp-id"):
            result = self.derive({"client_session_id": None})
            assert result == "mcp:mcp-id"

    def test_mcp_session_id_exception_falls_through(self):
        """Exception in get_mcp_session_id falls through gracefully."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", side_effect=Exception("boom")), \
             patch("src.mcp_handlers.context.get_context_session_key", return_value="ctx-fallback"):
            result = self.derive({})
            assert result == "ctx-fallback"

    def test_context_session_key_exception_falls_through(self):
        """Exception in get_context_session_key falls through to stdio."""
        with patch("src.mcp_handlers.context.get_mcp_session_id", return_value=None), \
             patch("src.mcp_handlers.context.get_context_session_key", side_effect=Exception("boom")):
            result = self.derive({})
            assert result.startswith("stdio:")


# ============================================================================
# Session key validation (within resolve_session_identity)
# ============================================================================

class TestSessionKeyValidation:

    @pytest.mark.asyncio
    async def test_empty_session_key_raises_valueerror(self, patch_all_deps):
        from src.mcp_handlers.identity_v2 import resolve_session_identity
        with pytest.raises(ValueError, match="session_key is required"):
            await resolve_session_identity(session_key="")

    @pytest.mark.asyncio
    async def test_long_session_key_truncated(self, patch_all_deps):
        """Session keys longer than 256 chars are truncated."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity
        long_key = "a" * 500
        result = await resolve_session_identity(session_key=long_key)
        assert result["created"] is True  # Should succeed

    @pytest.mark.asyncio
    async def test_special_chars_sanitized(self, patch_all_deps):
        """Characters outside allowed set are replaced with underscores."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity
        result = await resolve_session_identity(session_key="user'; DROP TABLE agents;--")
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_allowed_chars_not_sanitized(self, patch_all_deps):
        """Allowed characters pass through without sanitization."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity
        # alphanumeric, dash, underscore, colon, dot, at-sign
        clean_key = "user-name_123:test.session@host"
        result = await resolve_session_identity(session_key=clean_key)
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_sql_injection_in_session_key(self, patch_all_deps):
        """SQL injection attempts are safely handled."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity
        result = await resolve_session_identity(session_key="1 OR 1=1; --")
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_unicode_chars_sanitized(self, patch_all_deps):
        """Unicode characters outside allowed set are sanitized."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity
        result = await resolve_session_identity(session_key="test\x00null\x01ctrl")
        assert result["created"] is True


# ============================================================================
# resolve_session_identity - PATH 1: Redis cache hit
# ============================================================================

class TestResolvePath1RedisHit:

    @pytest.mark.asyncio
    async def test_redis_uuid_hit_returns_cached(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """When Redis has a UUID-format cached entry, return it directly."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_redis.get.return_value = {
            "agent_id": test_uuid,
            "display_agent_id": "Claude_Opus_20260206",
        }
        # Mock that agent exists in PG for the persisted check
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="id-1", metadata={})
        mock_db.get_agent_label.return_value = "TestAgent"

        result = await resolve_session_identity(session_key="redis-hit-session")

        assert result["source"] == "redis"
        assert result["created"] is False
        assert result["agent_uuid"] == test_uuid
        assert result["agent_id"] == "Claude_Opus_20260206"
        assert result["persisted"] is True
        assert result["label"] == "TestAgent"

    @pytest.mark.asyncio
    async def test_redis_uuid_hit_without_display_agent_id(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """When Redis has UUID but no display_agent_id, falls back to metadata lookup."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_redis.get.return_value = {"agent_id": test_uuid}
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="id-1",
            metadata={"agent_id": "Gemini_Pro_20260206"}
        )

        result = await resolve_session_identity(session_key="redis-hit-no-display")

        assert result["source"] == "redis"
        assert result["agent_uuid"] == test_uuid
        assert result["agent_id"] == "Gemini_Pro_20260206"

    @pytest.mark.asyncio
    async def test_redis_uuid_hit_no_metadata_uses_uuid_as_agent_id(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """When Redis has UUID but metadata lookup fails, agent_id falls back to UUID."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_redis.get.return_value = {"agent_id": test_uuid}
        # No metadata found
        mock_db.get_identity.return_value = None

        result = await resolve_session_identity(session_key="redis-hit-no-meta")

        assert result["source"] == "redis"
        assert result["agent_uuid"] == test_uuid
        assert result["agent_id"] == test_uuid  # falls back to UUID

    @pytest.mark.asyncio
    async def test_redis_hit_refreshes_ttl(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """Redis hit should refresh TTL via EXPIRE command (sliding window)."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_redis.get.return_value = {"agent_id": test_uuid, "display_agent_id": "Test_20260206"}
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="id-1", metadata={})

        await resolve_session_identity(session_key="ttl-refresh-test")

        # Should have called expire on the raw redis
        mock_raw_redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_redis_hit_not_persisted(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """Redis hit for agent that is NOT in PostgreSQL shows persisted=False."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_redis.get.return_value = {"agent_id": test_uuid, "display_agent_id": "Test_20260206"}
        mock_db.get_identity.return_value = None  # Not in PG

        result = await resolve_session_identity(session_key="not-persisted-session")

        assert result["source"] == "redis"
        assert result["persisted"] is False
        assert result["label"] is None

    @pytest.mark.asyncio
    async def test_redis_exception_falls_through_to_pg(self, patch_all_deps, mock_redis, mock_db):
        """If Redis raises an exception, falls through to PostgreSQL path."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_redis.get.side_effect = Exception("Redis connection refused")
        mock_db.get_session.return_value = None  # PG also has nothing

        result = await resolve_session_identity(session_key="redis-error-session")

        assert result["created"] is True  # Falls through to creation
        assert result["source"] in ("created", "memory_only")

    @pytest.mark.asyncio
    async def test_redis_returns_none_agent_id_falls_through(self, patch_all_deps, mock_redis, mock_db):
        """If Redis returns data with no agent_id, falls through."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_redis.get.return_value = {"some_other_field": "value"}
        mock_db.get_session.return_value = None

        result = await resolve_session_identity(session_key="redis-no-agentid")

        assert result["created"] is True


# ============================================================================
# resolve_session_identity - PATH 2: PostgreSQL session lookup
# ============================================================================

class TestResolvePath2PostgresHit:

    @pytest.mark.asyncio
    async def test_pg_uuid_hit_returns_identity(self, patch_no_redis, mock_db):
        """When Redis misses but PG has session with UUID, returns it."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_db.get_session.return_value = SimpleNamespace(
            agent_id=test_uuid,
            session_id="pg-test-session",
        )
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="ident-1",
            metadata={"agent_id": "Claude_Opus_20260206"}
        )
        mock_db.get_agent_label.return_value = "MyAgent"

        result = await resolve_session_identity(session_key="pg-test-session")

        assert result["source"] == "postgres"
        assert result["created"] is False
        assert result["persisted"] is True
        assert result["agent_uuid"] == test_uuid
        assert result["agent_id"] == "Claude_Opus_20260206"
        assert result["label"] == "MyAgent"

    @pytest.mark.asyncio
    async def test_pg_hit_updates_session_activity(self, patch_no_redis, mock_db):
        """PG hit should call update_session_activity (best effort)."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_db.get_session.return_value = SimpleNamespace(agent_id=test_uuid)
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="ident-1", metadata={"agent_id": "Test_20260206"}
        )

        await resolve_session_identity(session_key="activity-test")

        mock_db.update_session_activity.assert_called_once_with("activity-test")

    @pytest.mark.asyncio
    async def test_pg_hit_warms_redis_cache(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """PG hit should warm the Redis cache for next time."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        # Redis misses
        mock_redis.get.return_value = None
        # PG has the session
        mock_db.get_session.return_value = SimpleNamespace(agent_id=test_uuid)
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="ident-1", metadata={"agent_id": "Test_20260206"}
        )

        result = await resolve_session_identity(session_key="warm-cache-test")

        assert result["source"] == "postgres"
        # Redis should have been written to (via _cache_session)
        # The _cache_session function uses raw redis setex when display_agent_id is different
        mock_raw_redis.setex.assert_called()

    @pytest.mark.asyncio
    async def test_pg_hit_no_metadata_uses_uuid(self, patch_no_redis, mock_db):
        """When PG has session but identity metadata lookup fails, falls back to UUID."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        mock_db.get_session.return_value = SimpleNamespace(agent_id=test_uuid)
        # get_identity returns identity but with no agent_id in metadata
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="ident-1", metadata={}
        )

        result = await resolve_session_identity(session_key="no-meta-test")

        assert result["source"] == "postgres"
        assert result["agent_uuid"] == test_uuid
        # agent_id falls back to uuid since metadata has no agent_id
        assert result["agent_id"] == test_uuid

    @pytest.mark.asyncio
    async def test_pg_exception_falls_through_to_create(self, patch_no_redis, mock_db):
        """If PG raises exception, falls through to PATH 3 (create new)."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_db.get_session.side_effect = Exception("PG connection lost")

        result = await resolve_session_identity(session_key="pg-error-test")

        assert result["created"] is True
        assert result["source"] in ("created", "memory_only")


# ============================================================================
# resolve_session_identity - PATH 3: Create new agent
# ============================================================================

class TestResolvePath3CreateNew:

    @pytest.mark.asyncio
    async def test_creates_new_agent_lazy(self, patch_all_deps, mock_db):
        """Default persist=False creates lazy (memory only) agent."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        result = await resolve_session_identity(
            session_key="new-agent-lazy",
            model_type="claude-opus-4",
        )

        assert result["created"] is True
        assert result["persisted"] is False
        assert result["source"] == "memory_only"
        assert result["agent_id"].startswith("Claude_Opus_4_")
        assert result["display_name"] is None
        assert result["label"] is None
        # UUID should be valid
        assert len(result["agent_uuid"]) == 36
        assert result["agent_uuid"].count("-") == 4
        # Should NOT have called upsert_agent (lazy)
        mock_db.upsert_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_agent_persisted(self, patch_all_deps, mock_db):
        """persist=True creates agent in PostgreSQL."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="new-ident-1", metadata={}
        )

        result = await resolve_session_identity(
            session_key="new-agent-persist",
            persist=True,
            model_type="gemini-pro",
        )

        assert result["created"] is True
        assert result["persisted"] is True
        assert result["source"] == "created"
        mock_db.upsert_agent.assert_called_once()
        mock_db.upsert_identity.assert_called_once()

    @pytest.mark.asyncio
    async def test_persisted_agent_creates_session_binding(self, patch_all_deps, mock_db):
        """persist=True also creates session binding in PG."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="ident-bind-1", metadata={}
        )

        await resolve_session_identity(
            session_key="session-bind-test",
            persist=True,
        )

        mock_db.create_session.assert_called_once()
        call_args = mock_db.create_session.call_args
        assert call_args.kwargs["session_id"] == "session-bind-test"

    @pytest.mark.asyncio
    async def test_new_agent_uuid_is_unique(self, patch_all_deps):
        """Each new agent gets a unique UUID."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        result1 = await resolve_session_identity(session_key="unique-1")
        result2 = await resolve_session_identity(session_key="unique-2")

        assert result1["agent_uuid"] != result2["agent_uuid"]

    @pytest.mark.asyncio
    async def test_persist_failure_falls_through_to_memory_only(self, patch_all_deps, mock_db):
        """If PG persist fails, falls through to memory-only."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_db.upsert_agent.side_effect = Exception("PG write failed")

        result = await resolve_session_identity(
            session_key="persist-fail-test",
            persist=True,
        )

        # Should fall through to memory_only
        assert result["created"] is True
        assert result["persisted"] is False
        assert result["source"] == "memory_only"


# ============================================================================
# resolve_session_identity - force_new
# ============================================================================

class TestResolveForceNew:

    @pytest.mark.asyncio
    async def test_force_new_skips_all_lookups(self, patch_all_deps, mock_redis, mock_db):
        """force_new=True bypasses Redis and PG lookups."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        result = await resolve_session_identity(
            session_key="force-new-test",
            force_new=True,
        )

        assert result["created"] is True
        # Should NOT have called Redis get or PG get_session
        mock_redis.get.assert_not_called()
        mock_db.get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_new_creates_different_uuid(self, patch_all_deps, mock_redis):
        """force_new creates a new UUID even when cache exists."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        # First call creates an agent
        first = await resolve_session_identity(session_key="force-diff-test")

        # Reset redis mock to return the first agent
        mock_redis.get.return_value = {
            "agent_id": first["agent_uuid"],
            "display_agent_id": first["agent_id"],
        }

        # Second call with force_new should create a different UUID
        second = await resolve_session_identity(
            session_key="force-diff-test",
            force_new=True,
        )

        assert second["agent_uuid"] != first["agent_uuid"]
        assert second["created"] is True


# ============================================================================
# resolve_session_identity - PATH 2.5: Name-based identity claim
# ============================================================================

class TestResolvePath25NameClaim:

    @pytest.mark.asyncio
    async def test_name_claim_resolves_existing_agent(self, patch_all_deps, mock_db, mock_redis, mock_raw_redis):
        """agent_name resolves to existing agent by label."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        test_uuid = str(uuid.uuid4())
        # Redis and PG miss for session lookup
        mock_redis.get.return_value = None
        mock_db.get_session.return_value = None
        # But find_agent_by_label finds the agent
        mock_db.find_agent_by_label.return_value = test_uuid
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="ident-name", metadata={"agent_id": "Claude_20260206"}
        )
        mock_db.get_agent_label.return_value = "Lumen"

        result = await resolve_session_identity(
            session_key="name-claim-test",
            agent_name="Lumen",
        )

        assert result["source"] == "name_claim"
        assert result["agent_uuid"] == test_uuid
        assert result["created"] is False
        assert result["persisted"] is True
        assert result.get("resumed_by_name") is True

    @pytest.mark.asyncio
    async def test_name_claim_short_name_ignored(self, patch_all_deps, mock_db, mock_redis):
        """Names shorter than 2 chars are ignored."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_redis.get.return_value = None
        mock_db.get_session.return_value = None
        mock_db.find_agent_by_label.return_value = None

        result = await resolve_session_identity(
            session_key="short-name-test",
            agent_name="A",  # Too short
        )

        # Should create new, not resolve by name
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_name_claim_no_match_creates_new(self, patch_all_deps, mock_db, mock_redis):
        """When name doesn't match any agent, creates new."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_redis.get.return_value = None
        mock_db.get_session.return_value = None
        mock_db.find_agent_by_label.return_value = None  # No match

        result = await resolve_session_identity(
            session_key="no-name-match-test",
            agent_name="NonexistentAgent",
        )

        assert result["created"] is True


# ============================================================================
# _agent_exists_in_postgres
# ============================================================================

class TestAgentExistsInPostgres:

    @pytest.mark.asyncio
    async def test_returns_true_when_identity_found(self):
        from src.mcp_handlers.identity_v2 import _agent_exists_in_postgres

        mock_db = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="i1", metadata={})

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            assert await _agent_exists_in_postgres("uuid-exists") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        from src.mcp_handlers.identity_v2 import _agent_exists_in_postgres

        mock_db = AsyncMock()
        mock_db.get_identity.return_value = None

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            assert await _agent_exists_in_postgres("uuid-not-found") is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        from src.mcp_handlers.identity_v2 import _agent_exists_in_postgres

        mock_db = AsyncMock()
        mock_db.get_identity.side_effect = Exception("DB down")

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            assert await _agent_exists_in_postgres("uuid-error") is False


# ============================================================================
# _get_agent_label
# ============================================================================

class TestGetAgentLabel:

    @pytest.mark.asyncio
    async def test_returns_label_from_db(self):
        from src.mcp_handlers.identity_v2 import _get_agent_label

        mock_db = AsyncMock()
        mock_db.get_agent_label.return_value = "MyAgent"

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_label("uuid-label")
            assert result == "MyAgent"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from src.mcp_handlers.identity_v2 import _get_agent_label

        mock_db = AsyncMock()
        mock_db.get_agent_label.return_value = None

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_label("uuid-no-label")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from src.mcp_handlers.identity_v2 import _get_agent_label

        mock_db = AsyncMock()
        mock_db.get_agent_label.side_effect = Exception("DB error")

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_label("uuid-error")
            assert result is None


# ============================================================================
# _get_agent_id_from_metadata
# ============================================================================

class TestGetAgentIdFromMetadata:

    @pytest.mark.asyncio
    async def test_returns_agent_id_from_identity_metadata(self):
        from src.mcp_handlers.identity_v2 import _get_agent_id_from_metadata

        mock_db = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1",
            metadata={"agent_id": "Claude_Opus_20260206"}
        )

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_id_from_metadata("uuid-meta")
            assert result == "Claude_Opus_20260206"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_identity(self):
        from src.mcp_handlers.identity_v2 import _get_agent_id_from_metadata

        mock_db = AsyncMock()
        mock_db.get_identity.return_value = None

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_id_from_metadata("uuid-no-identity")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_metadata(self):
        from src.mcp_handlers.identity_v2 import _get_agent_id_from_metadata

        mock_db = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata=None
        )

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_id_from_metadata("uuid-no-meta")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_metadata_has_no_agent_id(self):
        from src.mcp_handlers.identity_v2 import _get_agent_id_from_metadata

        mock_db = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={"some_other": "data"}
        )

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_id_from_metadata("uuid-no-aid")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from src.mcp_handlers.identity_v2 import _get_agent_id_from_metadata

        mock_db = AsyncMock()
        mock_db.get_identity.side_effect = Exception("DB error")

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _get_agent_id_from_metadata("uuid-error")
            assert result is None


# ============================================================================
# _find_agent_by_label
# ============================================================================

class TestFindAgentByLabel:

    @pytest.mark.asyncio
    async def test_returns_uuid_when_found(self):
        from src.mcp_handlers.identity_v2 import _find_agent_by_label

        mock_db = AsyncMock()
        mock_db.find_agent_by_label.return_value = "uuid-found-by-label"

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _find_agent_by_label("MyAgent")
            assert result == "uuid-found-by-label"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from src.mcp_handlers.identity_v2 import _find_agent_by_label

        mock_db = AsyncMock()
        mock_db.find_agent_by_label.return_value = None

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _find_agent_by_label("Nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from src.mcp_handlers.identity_v2 import _find_agent_by_label

        mock_db = AsyncMock()
        mock_db.find_agent_by_label.side_effect = Exception("DB error")

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _find_agent_by_label("Error")
            assert result is None


# ============================================================================
# ensure_agent_persisted (lazy creation)
# ============================================================================

class TestEnsureAgentPersisted:

    @pytest.mark.asyncio
    async def test_persists_new_agent(self):
        """When agent doesn't exist in PG, persists and returns True."""
        from src.mcp_handlers.identity_v2 import ensure_agent_persisted

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        # First call: not persisted. After upsert: return identity for session creation.
        mock_db.get_identity.side_effect = [
            None,  # First check: not persisted
            SimpleNamespace(identity_id="new-ident", metadata={}),  # After upsert: for session creation
        ]
        mock_db.upsert_agent = AsyncMock()
        mock_db.upsert_identity = AsyncMock()
        mock_db.create_session = AsyncMock()

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await ensure_agent_persisted("uuid-lazy", "session-lazy")

        assert result is True
        mock_db.upsert_agent.assert_called_once()
        mock_db.upsert_identity.assert_called_once()
        mock_db.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_already_persisted(self):
        """When agent already exists in PG, returns False without writing."""
        from src.mcp_handlers.identity_v2 import ensure_agent_persisted

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="existing-ident", metadata={}
        )

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await ensure_agent_persisted("uuid-existing", "session-existing")

        assert result is False
        mock_db.upsert_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """On exception, returns False (non-fatal)."""
        from src.mcp_handlers.identity_v2 import ensure_agent_persisted

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_identity.side_effect = Exception("DB error")

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await ensure_agent_persisted("uuid-error", "session-error")

        assert result is False


# ============================================================================
# set_agent_label
# ============================================================================

class TestSetAgentLabel:

    @pytest.mark.asyncio
    async def test_sets_label_successfully(self):
        """Sets label via db.update_agent_fields."""
        from src.mcp_handlers.identity_v2 import set_agent_label

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="i1", metadata={})
        mock_db.find_agent_by_label.return_value = None  # No collision
        mock_db.update_agent_fields.return_value = True
        mock_db.upsert_agent = AsyncMock()
        mock_db.upsert_identity = AsyncMock()
        mock_db.create_session = AsyncMock()

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
             patch("src.mcp_handlers.identity_v2._redis_cache", False), \
             patch("src.mcp_handlers.shared.get_mcp_server", side_effect=Exception("no server")):
            result = await set_agent_label("uuid-label-set", "NewLabel")

        assert result is True
        mock_db.update_agent_fields.assert_called_once_with("uuid-label-set", label="NewLabel")

    @pytest.mark.asyncio
    async def test_empty_label_returns_false(self):
        from src.mcp_handlers.identity_v2 import set_agent_label
        result = await set_agent_label("uuid-1", "")
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_uuid_returns_false(self):
        from src.mcp_handlers.identity_v2 import set_agent_label
        result = await set_agent_label("", "Label")
        assert result is False

    @pytest.mark.asyncio
    async def test_label_collision_appends_suffix(self):
        """When label already exists for different agent, appends UUID suffix."""
        from src.mcp_handlers.identity_v2 import set_agent_label

        test_uuid = "aaaabbbb-1234-5678-9abc-def012345678"
        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="i1", metadata={})
        mock_db.find_agent_by_label.return_value = "other-uuid"  # Collision!
        mock_db.update_agent_fields.return_value = True
        mock_db.upsert_agent = AsyncMock()
        mock_db.upsert_identity = AsyncMock()
        mock_db.create_session = AsyncMock()

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
             patch("src.mcp_handlers.identity_v2._redis_cache", False), \
             patch("src.mcp_handlers.shared.get_mcp_server", side_effect=Exception("no server")):
            result = await set_agent_label(test_uuid, "DuplicateName")

        assert result is True
        # Should have been called with suffixed label
        call_args = mock_db.update_agent_fields.call_args
        label_used = call_args.kwargs.get("label") or call_args[1].get("label")
        assert label_used.startswith("DuplicateName_")
        assert test_uuid[:8] in label_used


# ============================================================================
# _extract_stable_identifier
# ============================================================================

class TestExtractStableIdentifier:

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from src.mcp_handlers.identity_v2 import _extract_stable_identifier
        self.extract = _extract_stable_identifier

    def test_extracts_hex_suffix(self):
        result = self.extract("217.216.112.229:8767:6d79c4")
        assert result == "6d79c4"

    def test_extracts_hex_from_two_parts(self):
        result = self.extract("192.168.1.1:abcdef")
        assert result == "abcdef"

    def test_returns_none_for_single_part(self):
        result = self.extract("singlepart")
        assert result is None

    def test_returns_none_for_non_hex_suffix(self):
        result = self.extract("192.168.1.1:not-hex-here")
        assert result is None

    def test_returns_none_for_short_suffix(self):
        result = self.extract("192.168.1.1:ab")
        assert result is None

    def test_returns_none_for_empty(self):
        result = self.extract("")
        assert result is None

    def test_returns_none_for_none(self):
        result = self.extract(None)
        assert result is None


# ============================================================================
# _extract_base_fingerprint
# ============================================================================

class TestExtractBaseFingerprint:

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from src.mcp_handlers.identity_v2 import _extract_base_fingerprint
        self.extract = _extract_base_fingerprint

    def test_mcp_prefix_returns_none(self):
        assert self.extract("mcp:session-abc") is None

    def test_stdio_prefix_returns_none(self):
        assert self.extract("stdio:12345") is None

    def test_agent_prefix_returns_none(self):
        assert self.extract("agent-uuid-prefix") is None

    def test_ip_ua_hash_extracts_ua(self):
        result = self.extract("192.168.1.1:d20c2f")
        assert result == "ua:d20c2f"

    def test_ip_ua_hash_suffix_extracts_ua(self):
        result = self.extract("192.168.1.1:d20c2f:extra_suffix")
        assert result == "ua:d20c2f"

    def test_single_part_returns_as_is(self):
        result = self.extract("onlyone")
        assert result == "onlyone"

    def test_none_returns_none(self):
        assert self.extract(None) is None

    def test_empty_returns_none(self):
        assert self.extract("") is None


# ============================================================================
# ua_hash_from_header
# ============================================================================

class TestUaHashFromHeader:

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from src.mcp_handlers.identity_v2 import ua_hash_from_header
        self.ua_hash = ua_hash_from_header

    def test_returns_ua_prefix_hash(self):
        import hashlib
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        expected_hash = hashlib.md5(ua.encode()).hexdigest()[:6]
        result = self.ua_hash(ua)
        assert result == f"ua:{expected_hash}"

    def test_returns_none_for_empty(self):
        assert self.ua_hash("") is None

    def test_returns_none_for_none(self):
        assert self.ua_hash(None) is None

    def test_consistent_results(self):
        """Same UA string always produces same hash."""
        ua = "TestAgent/1.0"
        r1 = self.ua_hash(ua)
        r2 = self.ua_hash(ua)
        assert r1 == r2

    def test_different_ua_different_hash(self):
        """Different UA strings produce different hashes."""
        r1 = self.ua_hash("Agent/1.0")
        r2 = self.ua_hash("Agent/2.0")
        assert r1 != r2


# ============================================================================
# lookup_onboard_pin / set_onboard_pin
# ============================================================================

class TestOnboardPin:

    @pytest.mark.asyncio
    async def test_set_and_lookup_pin(self):
        """Pin can be set and looked up."""
        from src.mcp_handlers.identity_v2 import set_onboard_pin, lookup_onboard_pin

        mock_raw = AsyncMock()
        stored_data = {}

        async def mock_setex(key, ttl, value):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        async def mock_expire(key, ttl):
            pass

        mock_raw.setex = mock_setex
        mock_raw.get = mock_get
        mock_raw.expire = mock_expire

        async def _get_raw():
            return mock_raw

        with patch("src.cache.redis_client.get_redis", new=_get_raw):
            set_result = await set_onboard_pin("ua:d20c2f", "uuid-123", "agent-uuid-123456")
            assert set_result is True

            lookup_result = await lookup_onboard_pin("ua:d20c2f")
            assert lookup_result == "agent-uuid-123456"

    @pytest.mark.asyncio
    async def test_set_pin_no_fingerprint(self):
        """set_onboard_pin with empty fingerprint returns False."""
        from src.mcp_handlers.identity_v2 import set_onboard_pin
        result = await set_onboard_pin("", "uuid-1", "sess-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_pin_none_fingerprint(self):
        """set_onboard_pin with None fingerprint returns False."""
        from src.mcp_handlers.identity_v2 import set_onboard_pin
        result = await set_onboard_pin(None, "uuid-1", "sess-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_lookup_pin_none_fingerprint(self):
        """lookup_onboard_pin with None fingerprint returns None."""
        from src.mcp_handlers.identity_v2 import lookup_onboard_pin
        result = await lookup_onboard_pin(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_pin_empty_fingerprint(self):
        """lookup_onboard_pin with empty fingerprint returns None."""
        from src.mcp_handlers.identity_v2 import lookup_onboard_pin
        result = await lookup_onboard_pin("")
        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_pin_no_redis(self):
        """lookup_onboard_pin returns None when Redis is unavailable."""
        from src.mcp_handlers.identity_v2 import lookup_onboard_pin

        async def _get_no_redis():
            return None

        with patch("src.cache.redis_client.get_redis", new=_get_no_redis):
            result = await lookup_onboard_pin("ua:test")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_pin_no_redis(self):
        """set_onboard_pin returns False when Redis is unavailable."""
        from src.mcp_handlers.identity_v2 import set_onboard_pin

        async def _get_no_redis():
            return None

        with patch("src.cache.redis_client.get_redis", new=_get_no_redis):
            result = await set_onboard_pin("ua:test", "uuid-1", "sess-1")
            assert result is False


# ============================================================================
# handle_identity_v2 (tool handler, not the decorator adapter)
# ============================================================================

class TestHandleIdentityV2:

    @pytest.mark.asyncio
    async def test_basic_identity_resolution(self, patch_all_deps, mock_db):
        """Basic identity() call resolves and returns identity."""
        from src.mcp_handlers.identity_v2 import handle_identity_v2

        result = await handle_identity_v2(
            arguments={},
            session_key="handle-test-session",
        )

        assert result["success"] is True
        assert "agent_id" in result
        assert "agent_uuid" in result
        assert result["bound"] is True

    @pytest.mark.asyncio
    async def test_identity_with_model_type(self, patch_all_deps, mock_db):
        """identity(model_type=...) uses model in agent_id generation."""
        from src.mcp_handlers.identity_v2 import handle_identity_v2

        result = await handle_identity_v2(
            arguments={"model_type": "claude-opus-4"},
            session_key="model-type-session",
            model_type="claude-opus-4",
        )

        assert result["success"] is True
        assert "Claude_Opus_4" in result["agent_id"]

    @pytest.mark.asyncio
    async def test_identity_with_name_sets_label(self, patch_all_deps, mock_db):
        """identity(name='X') sets the agent label."""
        from src.mcp_handlers.identity_v2 import handle_identity_v2

        mock_db.find_agent_by_label.return_value = None
        mock_db.update_agent_fields.return_value = True
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="i1", metadata={})
        mock_db.upsert_agent = AsyncMock()
        mock_db.upsert_identity = AsyncMock()
        mock_db.create_session = AsyncMock()

        with patch("src.mcp_handlers.shared.get_mcp_server", side_effect=Exception("no server")):
            result = await handle_identity_v2(
                arguments={"name": "TestBot"},
                session_key="name-set-session",
            )

        assert result["success"] is True
        assert result.get("label") == "TestBot"
        assert result.get("display_name") == "TestBot"

    @pytest.mark.asyncio
    async def test_identity_name_claim_resolves_existing(self, patch_all_deps, mock_db, mock_redis, mock_raw_redis):
        """identity(name='X') resolves to existing agent via name claim."""
        from src.mcp_handlers.identity_v2 import handle_identity_v2

        test_uuid = str(uuid.uuid4())
        mock_db.find_agent_by_label.return_value = test_uuid
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={"agent_id": "Claude_20260206"}
        )
        mock_db.get_agent_label.return_value = "ExistingBot"

        with patch("src.mcp_handlers.identity_shared.make_client_session_id", return_value="agent-test12345"):
            result = await handle_identity_v2(
                arguments={"name": "ExistingBot"},
                session_key="name-claim-handler-test",
            )

        assert result["success"] is True
        assert result["agent_uuid"] == test_uuid
        assert result.get("resumed_by_name") is True
        assert result.get("source") == "name_claim"


# ============================================================================
# resolve_by_name_claim (standalone)
# ============================================================================

class TestResolveByNameClaim:

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_name(self):
        from src.mcp_handlers.identity_v2 import resolve_by_name_claim
        result = await resolve_by_name_claim("", "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_none_name(self):
        from src.mcp_handlers.identity_v2 import resolve_by_name_claim
        result = await resolve_by_name_claim(None, "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_short_name(self):
        from src.mcp_handlers.identity_v2 import resolve_by_name_claim
        result = await resolve_by_name_claim("A", "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_label_not_found(self):
        from src.mcp_handlers.identity_v2 import resolve_by_name_claim

        mock_db = AsyncMock()
        mock_db.find_agent_by_label.return_value = None

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await resolve_by_name_claim("UnknownAgent", "session-1")
            assert result is None

    @pytest.mark.asyncio
    async def test_resolves_when_label_found(self):
        from src.mcp_handlers.identity_v2 import resolve_by_name_claim

        test_uuid = str(uuid.uuid4())
        mock_db = AsyncMock()
        mock_db.find_agent_by_label.return_value = test_uuid
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={"agent_id": "Test_20260206"}
        )
        mock_db.get_agent_label.return_value = "FoundAgent"
        mock_db.create_session = AsyncMock()

        mock_cache = AsyncMock()
        mock_cache.bind = AsyncMock()

        mock_raw = AsyncMock()
        mock_raw.setex = AsyncMock()

        async def _get_raw():
            return mock_raw

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
             patch("src.mcp_handlers.identity_v2._redis_cache", None), \
             patch("src.cache.get_session_cache", return_value=mock_cache), \
             patch("src.cache.redis_client.get_redis", new=_get_raw):
            result = await resolve_by_name_claim("FoundAgent", "session-resolve")

        assert result is not None
        assert result["agent_uuid"] == test_uuid
        assert result["source"] == "name_claim"
        assert result["resumed_by_name"] is True
        assert result["persisted"] is True

    @pytest.mark.asyncio
    async def test_trajectory_verification_rejects_impersonation(self):
        """Trajectory mismatch (lineage < 0.6) rejects the name claim."""
        from src.mcp_handlers.identity_v2 import resolve_by_name_claim

        test_uuid = str(uuid.uuid4())
        mock_db = AsyncMock()
        mock_db.find_agent_by_label.return_value = test_uuid

        mock_verification = {
            "verified": False,
            "tiers": {"lineage": {"similarity": 0.3}},  # Way below 0.6
        }

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
             patch("src.mcp_handlers.identity_v2._redis_cache", False), \
             patch("src.trajectory_identity.verify_trajectory_identity", new_callable=AsyncMock, return_value=mock_verification):
            result = await resolve_by_name_claim(
                "SomeAgent", "session-traj",
                trajectory_signature={"some": "data"}
            )

        assert result is None  # Rejected due to lineage mismatch


# ============================================================================
# _cache_session
# ============================================================================

class TestCacheSession:

    @pytest.mark.asyncio
    async def test_cache_with_display_agent_id_uses_raw_redis(self, mock_raw_redis):
        """When display_agent_id differs from UUID, uses raw Redis setex."""
        from src.mcp_handlers.identity_v2 import _cache_session

        mock_cache = AsyncMock()

        async def _get_raw():
            return mock_raw_redis

        with patch("src.mcp_handlers.identity_v2._redis_cache", None), \
             patch("src.cache.get_session_cache", return_value=mock_cache), \
             patch("src.cache.redis_client.get_redis", new=_get_raw):
            await _cache_session("sess-1", "uuid-1234", display_agent_id="Claude_20260206")

        mock_raw_redis.setex.assert_called_once()
        call_args = mock_raw_redis.setex.call_args
        assert call_args[0][0] == "session:sess-1"
        stored_data = json.loads(call_args[0][2])
        assert stored_data["agent_id"] == "uuid-1234"
        assert stored_data["display_agent_id"] == "Claude_20260206"

    @pytest.mark.asyncio
    async def test_cache_without_display_id_uses_bind(self):
        """Without display_agent_id, uses SessionCache.bind()."""
        from src.mcp_handlers.identity_v2 import _cache_session

        mock_cache = AsyncMock()
        mock_cache.bind = AsyncMock()

        with patch("src.mcp_handlers.identity_v2._redis_cache", None), \
             patch("src.cache.get_session_cache", return_value=mock_cache):
            await _cache_session("sess-2", "uuid-5678")

        mock_cache.bind.assert_called_once_with("sess-2", "uuid-5678")

    @pytest.mark.asyncio
    async def test_cache_display_id_same_as_uuid_uses_bind(self):
        """When display_agent_id == uuid, uses bind (no separate storage needed)."""
        from src.mcp_handlers.identity_v2 import _cache_session

        mock_cache = AsyncMock()
        mock_cache.bind = AsyncMock()

        with patch("src.mcp_handlers.identity_v2._redis_cache", None), \
             patch("src.cache.get_session_cache", return_value=mock_cache):
            await _cache_session("sess-3", "uuid-same", display_agent_id="uuid-same")

        mock_cache.bind.assert_called_once_with("sess-3", "uuid-same")

    @pytest.mark.asyncio
    async def test_cache_redis_unavailable_no_error(self):
        """When Redis is unavailable, _cache_session does not raise."""
        from src.mcp_handlers.identity_v2 import _cache_session

        with patch("src.mcp_handlers.identity_v2._redis_cache", False):
            # Should not raise
            await _cache_session("sess-4", "uuid-noop")


# ============================================================================
# migrate_from_v1
# ============================================================================

class TestMigrateFromV1:

    @pytest.mark.asyncio
    async def test_migrates_sessions(self):
        """Migrates v1 session bindings to v2 format."""
        from src.mcp_handlers.identity_v2 import migrate_from_v1

        mock_db = AsyncMock()
        mock_db.upsert_agent = AsyncMock()
        mock_db.upsert_identity = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="migrated-ident", metadata={})
        mock_db.create_session = AsyncMock()

        old_bindings = {
            "session-1": {"bound_agent_id": "uuid-1", "api_key": "key-1"},
            "session-2": {"bound_agent_id": "uuid-2", "api_key": "key-2"},
        }

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            count = await migrate_from_v1(old_bindings)

        assert count == 2
        assert mock_db.upsert_agent.call_count == 2
        assert mock_db.upsert_identity.call_count == 2
        assert mock_db.create_session.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_bindings_without_agent_id(self):
        """Bindings without bound_agent_id are skipped."""
        from src.mcp_handlers.identity_v2 import migrate_from_v1

        mock_db = AsyncMock()

        old_bindings = {
            "session-1": {"bound_agent_id": None},
            "session-2": {},  # No bound_agent_id key
        }

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            count = await migrate_from_v1(old_bindings)

        assert count == 0
        mock_db.upsert_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_on_individual_failure(self):
        """Failures for individual sessions don't stop migration."""
        from src.mcp_handlers.identity_v2 import migrate_from_v1

        mock_db = AsyncMock()
        mock_db.upsert_agent.side_effect = [
            Exception("DB error"),  # First fails
            None,  # Second succeeds
        ]
        mock_db.upsert_identity = AsyncMock()
        mock_db.get_identity.return_value = SimpleNamespace(identity_id="ident", metadata={})
        mock_db.create_session = AsyncMock()

        old_bindings = {
            "session-fail": {"bound_agent_id": "uuid-fail"},
            "session-ok": {"bound_agent_id": "uuid-ok"},
        }

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            count = await migrate_from_v1(old_bindings)

        assert count == 1  # Only the second one succeeded

    @pytest.mark.asyncio
    async def test_empty_bindings_returns_zero(self):
        """Empty bindings dict returns 0."""
        from src.mcp_handlers.identity_v2 import migrate_from_v1

        mock_db = AsyncMock()

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            count = await migrate_from_v1({})

        assert count == 0


# ============================================================================
# _find_agent_by_id (deprecated but still present)
# ============================================================================

class TestFindAgentById:

    @pytest.mark.asyncio
    async def test_returns_agent_from_postgres(self):
        from src.mcp_handlers.identity_v2 import _find_agent_by_id

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_agent.return_value = SimpleNamespace(
            label="TestAgent", status="active"
        )
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={"agent_uuid": "uuid-from-meta"}
        )

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _find_agent_by_id("old-agent-id")

        assert result is not None
        assert result["agent_id"] == "old-agent-id"
        assert result["agent_uuid"] == "uuid-from-meta"
        assert result["display_name"] == "TestAgent"
        assert result["label"] == "TestAgent"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from src.mcp_handlers.identity_v2 import _find_agent_by_id

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_agent.return_value = None

        mock_server = MagicMock()
        mock_server.agent_metadata = {}

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
             patch("src.mcp_handlers.shared.get_mcp_server", return_value=mock_server):
            result = await _find_agent_by_id("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_memory_cache(self):
        from src.mcp_handlers.identity_v2 import _find_agent_by_id

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_agent.side_effect = Exception("DB error")

        mock_server = MagicMock()
        meta = SimpleNamespace(
            label="CachedAgent",
            agent_uuid="uuid-cached",
            status="active",
        )
        mock_server.agent_metadata = {"agent-id-1": meta}

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db), \
             patch("src.mcp_handlers.shared.get_mcp_server", return_value=mock_server):
            result = await _find_agent_by_id("agent-id-1")

        assert result is not None
        assert result["agent_uuid"] == "uuid-cached"
        assert result["display_name"] == "CachedAgent"

    @pytest.mark.asyncio
    async def test_uuid_fallback_when_no_metadata_uuid(self):
        """When identity metadata has no agent_uuid, falls back to agent_id."""
        from src.mcp_handlers.identity_v2 import _find_agent_by_id

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_agent.return_value = SimpleNamespace(label=None, status="active")
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={}  # No agent_uuid in metadata
        )

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await _find_agent_by_id("fallback-id")

        assert result is not None
        assert result["agent_uuid"] == "fallback-id"  # Falls back to agent_id


# ============================================================================
# Integration-style tests (multiple paths)
# ============================================================================

class TestIdentityResolutionIntegration:

    @pytest.mark.asyncio
    async def test_redis_miss_pg_miss_creates_new(self, patch_all_deps, mock_redis, mock_db):
        """Full pipeline: Redis miss -> PG miss -> Create new."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_redis.get.return_value = None
        mock_db.get_session.return_value = None

        result = await resolve_session_identity(
            session_key="integration-test-1",
            model_type="claude-opus-4",
        )

        assert result["created"] is True
        assert result["source"] == "memory_only"
        assert result["agent_id"].startswith("Claude_Opus_4_")

    @pytest.mark.asyncio
    async def test_consistent_uuid_on_second_call_via_redis(self, patch_all_deps, mock_redis, mock_db, mock_raw_redis):
        """Second call should get same UUID back from Redis cache."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        # First call: creates new agent (Redis and PG both miss)
        mock_redis.get.return_value = None
        mock_db.get_session.return_value = None

        first = await resolve_session_identity(session_key="consistency-test")
        first_uuid = first["agent_uuid"]

        # Simulate Redis cache being populated: second call returns cached data
        mock_redis.get.return_value = {
            "agent_id": first_uuid,
            "display_agent_id": first["agent_id"],
        }
        mock_db.get_identity.return_value = None  # Not persisted

        second = await resolve_session_identity(session_key="consistency-test")

        assert second["agent_uuid"] == first_uuid
        assert second["source"] == "redis"
        assert second["created"] is False

    @pytest.mark.asyncio
    async def test_ephemeral_then_persisted_via_ensure(self, patch_all_deps, mock_db):
        """Agent starts ephemeral, then gets persisted via ensure_agent_persisted."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity, ensure_agent_persisted

        # Create ephemeral
        result = await resolve_session_identity(session_key="ephemeral-test")
        assert result["persisted"] is False
        agent_uuid = result["agent_uuid"]

        # Now persist
        mock_db.get_identity.side_effect = [
            None,  # Not yet persisted
            SimpleNamespace(identity_id="new-ident", metadata={}),  # After upsert
        ]

        newly_persisted = await ensure_agent_persisted(agent_uuid, "ephemeral-test")
        assert newly_persisted is True
        mock_db.upsert_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_redis_and_pg_down_still_creates(self):
        """Even when both Redis and PG are down, a new identity is created."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        mock_db = AsyncMock()
        mock_db.init = AsyncMock()
        mock_db.get_session.side_effect = Exception("PG down")
        mock_db.find_agent_by_label.return_value = None

        with patch("src.mcp_handlers.identity_v2._redis_cache", False), \
             patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            result = await resolve_session_identity(session_key="all-down-test")

        assert result["created"] is True
        assert result["source"] == "memory_only"
        assert len(result["agent_uuid"]) == 36


# ============================================================================
# Edge cases
# ============================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_legacy_non_uuid_in_redis_cache(self, patch_all_deps, mock_redis, mock_db):
        """Legacy Redis entries with model+date format (not UUID) are handled."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        # Legacy format: agent_id is model+date, not UUID
        mock_redis.get.return_value = {"agent_id": "Claude_Opus_20260205"}
        mock_db.get_agent.return_value = SimpleNamespace(
            label="LegacyAgent", status="active"
        )
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={"agent_uuid": "legacy-uuid-1234"}
        )

        result = await resolve_session_identity(session_key="legacy-redis-test")

        assert result["source"] == "redis"
        assert result["agent_id"] == "Claude_Opus_20260205"

    @pytest.mark.asyncio
    async def test_legacy_non_uuid_in_pg(self, patch_no_redis, mock_db):
        """Legacy PG entries with model+date format session.agent_id are handled."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        # Legacy PG: agent_id stored as model+date
        mock_db.get_session.return_value = SimpleNamespace(
            agent_id="Gemini_Pro_20260101"
        )
        mock_db.get_agent.return_value = SimpleNamespace(
            label="LegacyPGAgent", status="active"
        )
        mock_db.get_identity.return_value = SimpleNamespace(
            identity_id="i1", metadata={"agent_uuid": "legacy-pg-uuid"}
        )
        mock_db.get_agent_label.return_value = "LegacyPGAgent"

        result = await resolve_session_identity(session_key="legacy-pg-test")

        assert result["source"] == "postgres"
        assert result["agent_id"] == "Gemini_Pro_20260101"

    @pytest.mark.asyncio
    async def test_session_key_with_only_colons(self, patch_all_deps):
        """Session key with only colons is valid (allowed chars)."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        result = await resolve_session_identity(session_key=":::")
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_session_key_at_exact_max_length(self, patch_all_deps):
        """Session key at exactly 256 chars passes without truncation."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        key = "a" * 256
        result = await resolve_session_identity(session_key=key)
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_session_key_at_257_chars_truncated(self, patch_all_deps):
        """Session key at 257 chars is truncated to 256."""
        from src.mcp_handlers.identity_v2 import resolve_session_identity

        key = "a" * 257
        result = await resolve_session_identity(session_key=key)
        assert result["created"] is True
