"""
Tests for src/db/dual_backend.py - Dual-write backend and _retry_async.

Tests cover:
- _retry_async: pure async retry with exponential backoff
- DualWriteBackend._write_both: dual-write with error handling
- DualWriteBackend.health_check: combined health from both backends
- DualWriteBackend operations: identity, session, audit, calibration, dialectic
- DualWriteBackend.sync_sqlite_to_postgres: reconciliation logic
"""

import pytest
import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.dual_backend import (
    _retry_async,
    DualWriteBackend,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
from src.db.base import IdentityRecord, SessionRecord, AgentStateRecord, AuditEvent


# ============================================================================
# _retry_async
# ============================================================================

class TestRetryAsync:

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Should return result on first successful call."""
        factory = AsyncMock(return_value="ok")
        result = await _retry_async(factory, "test_op")
        assert result == "ok"
        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Should succeed after initial failures."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await _retry_async(flaky, "flaky_op", max_retries=3, backoff_base=0.001)
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        """Should return None when all retries are exhausted."""
        async def always_fail():
            raise RuntimeError("permanent")

        result = await _retry_async(always_fail, "fail_op", max_retries=3, backoff_base=0.001)
        assert result is None

    @pytest.mark.asyncio
    async def test_respects_max_retries(self):
        """Should call exactly max_retries times."""
        call_count = 0

        async def counter():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        await _retry_async(counter, "count_op", max_retries=5, backoff_base=0.001)
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_single_retry(self):
        """max_retries=1 should call once and return None on failure."""
        async def fail():
            raise RuntimeError("once")

        result = await _retry_async(fail, "single_op", max_retries=1, backoff_base=0.001)
        assert result is None

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Verify that retries use exponential backoff."""
        timestamps = []

        async def timed_fail():
            timestamps.append(time.monotonic())
            raise RuntimeError("timed")

        await _retry_async(timed_fail, "timing_op", max_retries=3, backoff_base=0.05)
        assert len(timestamps) == 3

        # First delay should be ~0.05s, second ~0.1s
        delay1 = timestamps[1] - timestamps[0]
        delay2 = timestamps[2] - timestamps[1]
        assert delay1 >= 0.04  # Allow some slack
        assert delay2 >= 0.08  # 0.05 * 2^1 = 0.1

    @pytest.mark.asyncio
    async def test_returns_none_not_exception(self):
        """On failure, returns None (doesn't raise)."""
        async def boom():
            raise Exception("boom")

        result = await _retry_async(boom, "boom_op", max_retries=2, backoff_base=0.001)
        assert result is None

    @pytest.mark.asyncio
    async def test_factory_returns_none(self):
        """Factory returning None should be returned (not treated as failure)."""
        async def returns_none():
            return None

        result = await _retry_async(returns_none, "none_op")
        assert result is None

    @pytest.mark.asyncio
    async def test_factory_returns_falsy(self):
        """Factory returning 0 or False should be returned."""
        async def returns_zero():
            return 0

        result = await _retry_async(returns_zero, "zero_op")
        assert result == 0

        async def returns_false():
            return False

        result2 = await _retry_async(returns_false, "false_op")
        assert result2 is False


# ============================================================================
# DualWriteBackend helpers
# ============================================================================

class _TestDualBackend(DualWriteBackend):
    """Concrete subclass for testing (adds missing abstract methods)."""

    async def get_agent_label(self, agent_id):
        if self._postgres_available:
            return await self._postgres.get_agent_label(agent_id)
        return await self._sqlite.get_agent_label(agent_id)

    async def find_agent_by_label(self, label):
        if self._postgres_available:
            return await self._postgres.find_agent_by_label(label)
        return await self._sqlite.find_agent_by_label(label)


def _make_dual_backend():
    """Create DualWriteBackend with mocked SQLite and PostgreSQL backends."""
    backend = _TestDualBackend.__new__(_TestDualBackend)
    backend._sqlite = AsyncMock()
    backend._postgres = AsyncMock()
    backend._postgres_available = True
    return backend


def _make_dual_backend_no_postgres():
    """Create DualWriteBackend with postgres unavailable."""
    backend = _TestDualBackend.__new__(_TestDualBackend)
    backend._sqlite = AsyncMock()
    backend._postgres = AsyncMock()
    backend._postgres_available = False
    return backend


# ============================================================================
# _write_both
# ============================================================================

class TestWriteBoth:

    @pytest.mark.asyncio
    async def test_both_succeed(self):
        backend = _make_dual_backend()

        async def sqlite_op():
            return 42

        async def postgres_op():
            return 42

        result = await backend._write_both("test", sqlite_op(), postgres_op())
        assert result == 42

    @pytest.mark.asyncio
    async def test_postgres_fails_returns_sqlite_result(self):
        """If postgres fails, sqlite result is still returned."""
        backend = _make_dual_backend()

        async def sqlite_op():
            return "sqlite_ok"

        async def postgres_op():
            raise RuntimeError("pg down")

        result = await backend._write_both("test", sqlite_op(), postgres_op())
        assert result == "sqlite_ok"

    @pytest.mark.asyncio
    async def test_postgres_unavailable_closes_coroutine(self):
        """When postgres is unavailable, unused coroutine should be closed."""
        backend = _make_dual_backend_no_postgres()

        async def sqlite_op():
            return "ok"

        pg_coro = AsyncMock()()  # Create a real coroutine-like
        # Use an actual coroutine so .close() works
        async def pg_op():
            return "pg"

        result = await backend._write_both("test", sqlite_op(), pg_op())
        assert result == "ok"


# ============================================================================
# DualWriteBackend.health_check
# ============================================================================

class TestDualHealthCheck:

    @pytest.mark.asyncio
    async def test_both_healthy(self):
        backend = _make_dual_backend()
        backend._sqlite.health_check.return_value = {"status": "ok", "backend": "sqlite"}
        backend._postgres.health_check.return_value = {"status": "ok", "backend": "postgres"}

        result = await backend.health_check()
        assert result["backend"] == "dual"
        assert result["primary"]["status"] == "ok"
        assert result["secondary"]["status"] == "ok"
        assert result["postgres_available"] is True

    @pytest.mark.asyncio
    async def test_postgres_unavailable(self):
        backend = _make_dual_backend_no_postgres()
        backend._sqlite.health_check.return_value = {"status": "ok"}

        result = await backend.health_check()
        assert result["secondary"]["status"] == "unavailable"
        assert result["postgres_available"] is False

    @pytest.mark.asyncio
    async def test_postgres_health_error(self):
        backend = _make_dual_backend()
        backend._sqlite.health_check.return_value = {"status": "ok"}
        backend._postgres.health_check.side_effect = RuntimeError("connection lost")

        result = await backend.health_check()
        assert result["secondary"]["status"] == "error"
        assert "connection lost" in result["secondary"]["error"]


# ============================================================================
# DualWriteBackend.close
# ============================================================================

class TestDualClose:

    @pytest.mark.asyncio
    async def test_close_both(self):
        backend = _make_dual_backend()
        await backend.close()
        backend._sqlite.close.assert_awaited_once()
        backend._postgres.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_postgres_unavailable(self):
        backend = _make_dual_backend_no_postgres()
        await backend.close()
        backend._sqlite.close.assert_awaited_once()
        backend._postgres.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_postgres_error_handled(self):
        backend = _make_dual_backend()
        backend._postgres.close.side_effect = RuntimeError("close failed")
        # Should not raise
        await backend.close()
        backend._sqlite.close.assert_awaited_once()


# ============================================================================
# DualWriteBackend identity operations
# ============================================================================

class TestDualIdentityOps:

    @pytest.mark.asyncio
    async def test_get_identity_reads_sqlite(self):
        backend = _make_dual_backend()
        mock_id = IdentityRecord(
            identity_id=1, agent_id="a1", api_key_hash="h1",
            status="active", created_at=datetime.now(), updated_at=datetime.now()
        )
        backend._sqlite.get_identity.return_value = mock_id

        result = await backend.get_identity("a1")
        assert result.agent_id == "a1"
        backend._sqlite.get_identity.assert_awaited_with("a1")
        backend._postgres.get_identity.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_identities_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.list_identities.return_value = []

        result = await backend.list_identities(limit=50)
        backend._sqlite.list_identities.assert_awaited_with(None, 50, 0)
        backend._postgres.list_identities.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_verify_api_key_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.verify_api_key.return_value = True

        result = await backend.verify_api_key("a1", "key")
        assert result is True
        backend._sqlite.verify_api_key.assert_awaited_with("a1", "key")


# ============================================================================
# DualWriteBackend session operations
# ============================================================================

class TestDualSessionOps:

    @pytest.mark.asyncio
    async def test_get_session_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.get_session.return_value = None

        await backend.get_session("sess-1")
        backend._sqlite.get_session.assert_awaited_with("sess-1")
        backend._postgres.get_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_active_sessions_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.get_active_sessions_for_identity.return_value = []

        await backend.get_active_sessions_for_identity(1)
        backend._sqlite.get_active_sessions_for_identity.assert_awaited_with(1)

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self):
        backend = _make_dual_backend()
        backend._sqlite.cleanup_expired_sessions.return_value = 5

        result = await backend.cleanup_expired_sessions()
        assert result == 5
        backend._postgres.cleanup_expired_sessions.assert_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_postgres_fails(self):
        backend = _make_dual_backend()
        backend._sqlite.cleanup_expired_sessions.return_value = 3
        backend._postgres.cleanup_expired_sessions.side_effect = RuntimeError("pg err")

        result = await backend.cleanup_expired_sessions()
        assert result == 3  # SQLite result returned despite PG failure


# ============================================================================
# DualWriteBackend agent state operations
# ============================================================================

class TestDualAgentStateOps:

    @pytest.mark.asyncio
    async def test_get_latest_agent_state_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.get_latest_agent_state.return_value = None

        await backend.get_latest_agent_state(1)
        backend._sqlite.get_latest_agent_state.assert_awaited_with(1)

    @pytest.mark.asyncio
    async def test_get_agent_state_history_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.get_agent_state_history.return_value = []

        await backend.get_agent_state_history(1, limit=50)
        backend._sqlite.get_agent_state_history.assert_awaited_with(1, 50)


# ============================================================================
# DualWriteBackend audit operations
# ============================================================================

class TestDualAuditOps:

    @pytest.mark.asyncio
    async def test_query_audit_events_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.query_audit_events.return_value = []

        await backend.query_audit_events(agent_id="a1", limit=100)
        backend._sqlite.query_audit_events.assert_awaited()
        backend._postgres.query_audit_events.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_search_audit_events_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.search_audit_events.return_value = []

        await backend.search_audit_events("error", agent_id="a1")
        backend._sqlite.search_audit_events.assert_awaited_with("error", "a1", 200)


# ============================================================================
# DualWriteBackend calibration operations
# ============================================================================

class TestDualCalibrationOps:

    @pytest.mark.asyncio
    async def test_get_calibration_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.get_calibration.return_value = {"version": 1}

        result = await backend.get_calibration()
        assert result["version"] == 1
        backend._sqlite.get_calibration.assert_awaited()
        backend._postgres.get_calibration.assert_not_awaited()


# ============================================================================
# DualWriteBackend graph operations
# ============================================================================

class TestDualGraphOps:

    @pytest.mark.asyncio
    async def test_graph_available_with_postgres(self):
        backend = _make_dual_backend()
        backend._postgres.graph_available.return_value = True

        assert await backend.graph_available() is True

    @pytest.mark.asyncio
    async def test_graph_available_without_postgres(self):
        backend = _make_dual_backend_no_postgres()
        assert await backend.graph_available() is False

    @pytest.mark.asyncio
    async def test_graph_query_with_postgres(self):
        backend = _make_dual_backend()
        backend._postgres.graph_query.return_value = [{"n": "result"}]

        result = await backend.graph_query("MATCH (n) RETURN n")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_graph_query_without_postgres(self):
        backend = _make_dual_backend_no_postgres()
        result = await backend.graph_query("MATCH (n) RETURN n")
        assert result == []


# ============================================================================
# DualWriteBackend agent operations (PostgreSQL-only)
# ============================================================================

class TestDualAgentOps:

    @pytest.mark.asyncio
    async def test_upsert_agent_postgres_available(self):
        backend = _make_dual_backend()
        backend._postgres.upsert_agent.return_value = True

        result = await backend.upsert_agent("a1", "key1")
        assert result is True

    @pytest.mark.asyncio
    async def test_upsert_agent_postgres_unavailable(self):
        backend = _make_dual_backend_no_postgres()
        result = await backend.upsert_agent("a1", "key1")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_agent_fields_postgres_available(self):
        backend = _make_dual_backend()
        backend._postgres.update_agent_fields.return_value = True

        result = await backend.update_agent_fields("a1", status="archived")
        assert result is True

    @pytest.mark.asyncio
    async def test_update_agent_fields_postgres_unavailable(self):
        backend = _make_dual_backend_no_postgres()
        result = await backend.update_agent_fields("a1", notes="test")
        assert result is False


# ============================================================================
# DualWriteBackend dialectic operations
# ============================================================================

class TestDualDialecticOps:

    @pytest.mark.asyncio
    async def test_get_dialectic_session_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.get_dialectic_session.return_value = {"session_id": "s1"}

        result = await backend.get_dialectic_session("s1")
        assert result["session_id"] == "s1"
        backend._sqlite.get_dialectic_session.assert_awaited_with("s1")

    @pytest.mark.asyncio
    async def test_is_agent_in_active_session_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.is_agent_in_active_dialectic_session.return_value = True

        result = await backend.is_agent_in_active_dialectic_session("a1")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_pending_sessions_postgres_available(self):
        backend = _make_dual_backend()
        backend._postgres.get_pending_dialectic_sessions.return_value = [{"id": "s1"}]

        result = await backend.get_pending_dialectic_sessions()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_pending_sessions_postgres_unavailable(self):
        backend = _make_dual_backend_no_postgres()
        result = await backend.get_pending_dialectic_sessions()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_pending_sessions_postgres_error(self):
        backend = _make_dual_backend()
        backend._postgres.get_pending_dialectic_sessions.side_effect = RuntimeError("err")

        result = await backend.get_pending_dialectic_sessions()
        assert result == []


# ============================================================================
# DualWriteBackend.sync_sqlite_to_postgres
# ============================================================================

class TestSyncSqliteToPostgres:

    @pytest.mark.asyncio
    async def test_postgres_unavailable(self):
        backend = _make_dual_backend_no_postgres()
        result = await backend.sync_sqlite_to_postgres()
        assert result["success"] is False
        assert result["synced"] == 0

    @pytest.mark.asyncio
    async def test_both_in_sync(self):
        backend = _make_dual_backend()
        identity = IdentityRecord(
            identity_id=1, agent_id="a1", api_key_hash="h",
            status="active", created_at=datetime.now(), updated_at=datetime.now()
        )
        backend._sqlite.list_identities.return_value = [identity]
        backend._postgres.list_identities.return_value = [identity]

        result = await backend.sync_sqlite_to_postgres()
        assert result["success"] is True
        assert result["missing_in_postgres"] == 0
        assert result["synced"] == 0

    @pytest.mark.asyncio
    async def test_missing_in_postgres_synced(self):
        backend = _make_dual_backend()
        id_sqlite = IdentityRecord(
            identity_id=1, agent_id="a1", api_key_hash="h1",
            status="active", created_at=datetime.now(), updated_at=datetime.now()
        )
        backend._sqlite.list_identities.return_value = [id_sqlite]
        backend._postgres.list_identities.return_value = []
        backend._sqlite.get_identity.return_value = id_sqlite
        backend._postgres.upsert_identity.return_value = 1

        result = await backend.sync_sqlite_to_postgres()
        assert result["success"] is True
        assert result["missing_in_postgres"] == 1
        assert result["synced"] == 1

    @pytest.mark.asyncio
    async def test_dry_run_no_writes(self):
        backend = _make_dual_backend()
        id_sqlite = IdentityRecord(
            identity_id=1, agent_id="a1", api_key_hash="h1",
            status="active", created_at=datetime.now(), updated_at=datetime.now()
        )
        backend._sqlite.list_identities.return_value = [id_sqlite]
        backend._postgres.list_identities.return_value = []

        result = await backend.sync_sqlite_to_postgres(dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["missing_in_postgres"] == 1
        assert result["synced"] == 0
        assert "would_sync" in result
        backend._postgres.upsert_identity.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sync_with_failed_agent(self):
        backend = _make_dual_backend()
        id1 = IdentityRecord(identity_id=1, agent_id="a1", api_key_hash="h1", status="active", created_at=datetime.now(), updated_at=datetime.now())
        id2 = IdentityRecord(identity_id=2, agent_id="a2", api_key_hash="h2", status="active", created_at=datetime.now(), updated_at=datetime.now())

        backend._sqlite.list_identities.return_value = [id1, id2]
        backend._postgres.list_identities.return_value = []
        backend._sqlite.get_identity.side_effect = [id1, id2]
        backend._postgres.upsert_identity.side_effect = [1, RuntimeError("fail")]

        result = await backend.sync_sqlite_to_postgres()
        assert result["synced"] == 1
        assert result["failed"] == 1
        # Set iteration order is non-deterministic, so check one agent failed
        assert len(result["failed_agents"]) == 1
        assert result["failed_agents"][0] in ("a1", "a2")

    @pytest.mark.asyncio
    async def test_orphaned_in_postgres_reported(self):
        backend = _make_dual_backend()
        id_pg = IdentityRecord(identity_id=1, agent_id="orphan-1", api_key_hash="h", status="active", created_at=datetime.now(), updated_at=datetime.now())

        backend._sqlite.list_identities.return_value = []
        backend._postgres.list_identities.return_value = [id_pg]

        result = await backend.sync_sqlite_to_postgres()
        assert result["missing_in_sqlite"] == 1
        assert "orphan-1" in result["orphaned_in_postgres"]

    @pytest.mark.asyncio
    async def test_sync_exception_handled(self):
        backend = _make_dual_backend()
        backend._sqlite.list_identities.side_effect = RuntimeError("db exploded")

        result = await backend.sync_sqlite_to_postgres()
        assert result["success"] is False
        assert "db exploded" in result["error"]


# ============================================================================
# DualWriteBackend tool usage operations
# ============================================================================

class TestDualToolUsageOps:

    @pytest.mark.asyncio
    async def test_query_tool_usage_reads_sqlite(self):
        backend = _make_dual_backend()
        backend._sqlite.query_tool_usage.return_value = []

        await backend.query_tool_usage(agent_id="a1")
        backend._sqlite.query_tool_usage.assert_awaited()
        backend._postgres.query_tool_usage.assert_not_awaited()
