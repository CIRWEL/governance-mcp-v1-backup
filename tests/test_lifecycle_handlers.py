"""
Comprehensive tests for src/mcp_handlers/lifecycle.py - Agent lifecycle handlers.

Covers: handle_list_agents, handle_get_agent_metadata, handle_update_agent_metadata,
        handle_archive_agent, handle_delete_agent, handle_archive_old_test_agents,
        handle_archive_orphan_agents, handle_mark_response_complete,
        handle_direct_resume_if_safe, handle_self_recovery_review,
        handle_detect_stuck_agents, handle_ping_agent.
"""

import pytest
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# Helpers
# ============================================================================

def _parse(result):
    """Extract JSON from handler result."""
    if isinstance(result, (list, tuple)):
        return json.loads(result[0].text)
    return json.loads(result.text)


def make_agent_meta(
    status="active",
    label=None,
    display_name=None,
    purpose=None,
    total_updates=5,
    last_update=None,
    created_at=None,
    tags=None,
    notes="",
    trust_tier=None,
    preferences=None,
    parent_agent_id=None,
    spawn_reason=None,
    health_status=None,
    paused_at=None,
    structured_id=None,
    **kwargs,
):
    """Create a mock AgentMetadata SimpleNamespace."""
    if last_update is None:
        last_update = datetime.now(timezone.utc).isoformat()
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    meta = SimpleNamespace(
        status=status,
        label=label,
        display_name=display_name,
        purpose=purpose,
        total_updates=total_updates,
        last_update=last_update,
        created_at=created_at,
        tags=tags or [],
        notes=notes,
        trust_tier=trust_tier,
        archived_at=None,
        lifecycle_events=[],
        preferences=preferences,
        parent_agent_id=parent_agent_id,
        spawn_reason=spawn_reason,
        health_status=health_status,
        paused_at=paused_at,
        structured_id=structured_id,
        last_response_at=None,
        response_completed=False,
        **kwargs,
    )
    meta.add_lifecycle_event = MagicMock()
    meta.to_dict = MagicMock(return_value={
        "status": status, "label": label, "tags": tags or [],
        "notes": notes, "purpose": purpose, "total_updates": total_updates,
        "last_update": last_update, "created_at": created_at,
    })
    return meta


def make_mock_server(**overrides):
    """Create a standard mock MCP server."""
    server = MagicMock()
    server.agent_metadata = overrides.get("agent_metadata", {})
    server.monitors = overrides.get("monitors", {})
    server.load_metadata = MagicMock()
    server.load_metadata_async = AsyncMock()
    server.get_or_create_monitor = MagicMock()
    server.project_root = str(project_root)
    server.SERVER_VERSION = "test-1.0.0"
    server._metadata_cache_state = {"last_load_time": 0}
    return server


# ============================================================================
# handle_list_agents - Lite Mode
# ============================================================================

class TestListAgentsLite:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_empty_returns_empty_agents(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True})
            data = _parse(result)
            assert data["agents"] == []
            assert data["total_all"] == 0
            assert data["shown"] == 0
            assert data["matching"] == 0

    @pytest.mark.asyncio
    async def test_lists_active_agents_with_labels(self, server):
        server.agent_metadata = {
            "a1": make_agent_meta(label="Alpha", total_updates=10),
            "a2": make_agent_meta(label="Beta", total_updates=3),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True})
            data = _parse(result)
            assert data["total_all"] == 2
            assert len(data["agents"]) == 2
            labels = [a["label"] for a in data["agents"]]
            assert "Alpha" in labels
            assert "Beta" in labels

    @pytest.mark.asyncio
    async def test_filters_test_agents_by_default(self, server):
        server.agent_metadata = {
            "real-agent": make_agent_meta(label="Real", total_updates=5),
            "test_agent_1": make_agent_meta(label="Tester", total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "include_test_agents": False})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "real-agent" in ids
            assert "test_agent_1" not in ids

    @pytest.mark.asyncio
    async def test_includes_test_agents_when_requested(self, server):
        server.agent_metadata = {
            "real-agent": make_agent_meta(label="Real", total_updates=5),
            "test_agent_1": make_agent_meta(label="Tester", total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "include_test_agents": True})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "test_agent_1" in ids

    @pytest.mark.asyncio
    async def test_filters_archived_agents_by_default(self, server):
        server.agent_metadata = {
            "active-1": make_agent_meta(status="active", total_updates=5),
            "archived-1": make_agent_meta(status="archived", total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "active-1" in ids
            assert "archived-1" not in ids

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self, server):
        server.agent_metadata = {
            f"agent-{i}": make_agent_meta(label=f"Agent{i}", total_updates=i + 1)
            for i in range(10)
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "limit": 3})
            data = _parse(result)
            assert data["shown"] == 3
            assert len(data["agents"]) == 3

    @pytest.mark.asyncio
    async def test_filters_by_recency(self, server):
        recent = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        server.agent_metadata = {
            "recent-one": make_agent_meta(last_update=recent, total_updates=5),
            "old-one": make_agent_meta(last_update=old, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "recent_days": 7})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "recent-one" in ids
            assert "old-one" not in ids

    @pytest.mark.asyncio
    async def test_recent_days_zero_shows_all(self, server):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        server.agent_metadata = {
            "old-agent": make_agent_meta(last_update=old, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "recent_days": 0})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "old-agent" in ids

    @pytest.mark.asyncio
    async def test_min_updates_filter(self, server):
        server.agent_metadata = {
            "active-agent": make_agent_meta(total_updates=10),
            "ghost-agent": make_agent_meta(total_updates=0),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "min_updates": 5})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "active-agent" in ids
            assert "ghost-agent" not in ids

    @pytest.mark.asyncio
    async def test_named_only_true_filters_unlabeled(self, server):
        server.agent_metadata = {
            "labeled-agent": make_agent_meta(label="Named", total_updates=5),
            "unlabeled-agent": make_agent_meta(label=None, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({"lite": True, "named_only": True})
            data = _parse(result)
            ids = [a["id"] for a in data["agents"]]
            assert "labeled-agent" in ids
            assert "unlabeled-agent" not in ids


# ============================================================================
# handle_list_agents - Non-Lite (Full) Mode
# ============================================================================

class TestListAgentsFull:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_full_mode_with_grouped_output(self, server):
        server.agent_metadata = {
            "a1": make_agent_meta(status="active", label="One", total_updates=5, notes=""),
        }
        # Mock health_checker and get_or_create_monitor
        mock_monitor = MagicMock()
        mock_monitor.state = SimpleNamespace(
            E=0.7, I=0.3, S=0.5, V=0.0, coherence=0.8,
            lambda1=0.1, void_active=False
        )
        mock_monitor.get_metrics.return_value = {
            "risk_score": 0.3, "current_risk": 0.3,
            "phi": 0.5, "verdict": "safe", "mean_risk": 0.3,
        }
        server.monitors = {"a1": mock_monitor}
        health_status = MagicMock()
        health_status.value = "healthy"
        server.health_checker = MagicMock()
        server.health_checker.get_health_status.return_value = (health_status, {})

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({
                "lite": False, "grouped": True, "include_metrics": True,
            })
            data = _parse(result)
            assert data["success"] is True
            assert "agents" in data
            assert "summary" in data

    @pytest.mark.asyncio
    async def test_full_mode_summary_only(self, server):
        server.agent_metadata = {
            "a1": make_agent_meta(status="active", label="One", total_updates=5, notes=""),
        }
        health_status = MagicMock()
        health_status.value = "healthy"
        server.health_checker = MagicMock()
        server.health_checker.get_health_status.return_value = (health_status, {})

        mock_monitor = MagicMock()
        mock_monitor.state = SimpleNamespace(
            E=0.7, I=0.3, S=0.5, V=0.0, coherence=0.8,
            lambda1=0.1, void_active=False
        )
        mock_monitor.get_metrics.return_value = {
            "risk_score": 0.3, "current_risk": 0.3,
            "phi": 0.5, "verdict": "safe", "mean_risk": 0.3,
        }
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({
                "lite": False, "summary_only": True, "include_metrics": False,
            })
            data = _parse(result)
            assert "total" in data

    @pytest.mark.asyncio
    async def test_full_mode_pagination(self, server):
        server.agent_metadata = {
            f"a{i}": make_agent_meta(
                status="active", label=f"Agent{i}", total_updates=5, notes=""
            )
            for i in range(10)
        }
        health_status = MagicMock()
        health_status.value = "healthy"
        server.health_checker = MagicMock()
        server.health_checker.get_health_status.return_value = (health_status, {})

        mock_monitor = MagicMock()
        mock_monitor.state = SimpleNamespace(
            E=0.7, I=0.3, S=0.5, V=0.0, coherence=0.8,
            lambda1=0.1, void_active=False
        )
        mock_monitor.get_metrics.return_value = {
            "risk_score": 0.3, "current_risk": 0.3,
            "phi": 0.5, "verdict": "safe", "mean_risk": 0.3,
        }
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({
                "lite": False, "grouped": False, "include_metrics": False,
                "limit": 3, "offset": 2,
            })
            data = _parse(result)
            assert data["summary"]["returned"] == 3
            assert data["summary"]["total"] == 10
            assert data["summary"]["offset"] == 2
            assert data["summary"]["limit"] == 3

    @pytest.mark.asyncio
    async def test_full_mode_status_filter_all(self, server):
        server.agent_metadata = {
            "active-1": make_agent_meta(status="active", total_updates=3, notes=""),
            "archived-1": make_agent_meta(status="archived", total_updates=3, notes=""),
        }
        health_status = MagicMock()
        health_status.value = "healthy"
        server.health_checker = MagicMock()
        server.health_checker.get_health_status.return_value = (health_status, {})

        mock_monitor = MagicMock()
        mock_monitor.state = SimpleNamespace(
            E=0.7, I=0.3, S=0.5, V=0.0, coherence=0.8,
            lambda1=0.1, void_active=False
        )
        mock_monitor.get_metrics.return_value = {
            "risk_score": 0.3, "current_risk": 0.3,
            "phi": 0.5, "verdict": "safe", "mean_risk": 0.3,
        }
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_list_agents
            result = await handle_list_agents({
                "lite": False, "status_filter": "all", "include_metrics": False,
            })
            data = _parse(result)
            assert data["summary"]["total"] == 2


# ============================================================================
# handle_get_agent_metadata
# ============================================================================

class TestGetAgentMetadata:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_get_own_metadata(self, server):
        meta = make_agent_meta(label="TestAgent", total_updates=10)
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({})
            data = _parse(result)
            assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_metadata_by_target_uuid(self, server):
        meta = make_agent_meta(label="Alpha", total_updates=10)
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.cache.get_metadata_cache", side_effect=Exception("no cache")):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({"target_agent": "agent-1"})
            data = _parse(result)
            assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_metadata_by_label(self, server):
        meta = make_agent_meta(label="Alpha", total_updates=10)
        server.agent_metadata = {"uuid-123": meta}
        server.monitors = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.cache.get_metadata_cache", side_effect=Exception("no cache")):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({"target_agent": "Alpha"})
            data = _parse(result)
            assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_metadata_target_not_found(self, server):
        server.agent_metadata = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.cache.get_metadata_cache", side_effect=Exception("no cache")):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({"target_agent": "nonexistent"})
            data = _parse(result)
            assert data.get("success") is False or "not found" in data.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_get_metadata_not_registered(self, server):
        from mcp.types import TextContent
        error = TextContent(type="text", text='{"error": "not registered"}')

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=(None, error)):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({})
            assert "not registered" in result[0].text

    @pytest.mark.asyncio
    async def test_get_metadata_with_monitor_state(self, server):
        meta = make_agent_meta(label="Agent", total_updates=10)
        server.agent_metadata = {"agent-1": meta}

        mock_monitor = MagicMock()
        mock_monitor.state = SimpleNamespace(
            lambda1=0.1, coherence=0.8, void_active=False,
            E=0.7, I=0.3, S=0.5, V=0.0,
        )
        server.monitors = {"agent-1": mock_monitor}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({})
            data = _parse(result)
            assert "current_state" in data
            assert data["current_state"]["coherence"] == 0.8

    @pytest.mark.asyncio
    async def test_get_metadata_days_since_update(self, server):
        old_date = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        meta = make_agent_meta(label="Agent", total_updates=10, last_update=old_date)
        meta.to_dict.return_value["last_update"] = old_date
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_get_agent_metadata
            result = await handle_get_agent_metadata({})
            data = _parse(result)
            assert data.get("days_since_update") is not None
            assert data["days_since_update"] >= 2


# ============================================================================
# handle_update_agent_metadata
# ============================================================================

class TestUpdateAgentMetadata:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_update_tags(self, server):
        meta = make_agent_meta(tags=["old-tag"])
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "tags": ["new-tag"],
            })
            data = _parse(result)
            assert data["success"] is True
            assert data["tags"] == ["new-tag"]
            assert meta.tags == ["new-tag"]

    @pytest.mark.asyncio
    async def test_update_notes(self, server):
        meta = make_agent_meta(notes="old notes")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "notes": "new notes",
            })
            data = _parse(result)
            assert data["success"] is True
            assert data["notes"] == "new notes"
            assert meta.notes == "new notes"

    @pytest.mark.asyncio
    async def test_update_notes_append_mode(self, server):
        meta = make_agent_meta(notes="existing notes")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "notes": "appended", "append_notes": True,
            })
            data = _parse(result)
            assert data["success"] is True
            assert "existing notes" in meta.notes
            assert "appended" in meta.notes

    @pytest.mark.asyncio
    async def test_update_purpose(self, server):
        meta = make_agent_meta(purpose=None)
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "purpose": "Code review agent",
            })
            data = _parse(result)
            assert data["success"] is True
            assert data["purpose"] == "Code review agent"
            assert meta.purpose == "Code review agent"

    @pytest.mark.asyncio
    async def test_update_purpose_null_clears(self, server):
        meta = make_agent_meta(purpose="Old purpose")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "purpose": None,
            })
            data = _parse(result)
            assert data["success"] is True
            assert meta.purpose is None

    @pytest.mark.asyncio
    async def test_update_preferences_valid(self, server):
        meta = make_agent_meta(preferences=None)
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "preferences": {"verbosity": "minimal"},
            })
            data = _parse(result)
            assert data["success"] is True
            assert meta.preferences == {"verbosity": "minimal"}

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_verbosity(self, server):
        meta = make_agent_meta()
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1", "preferences": {"verbosity": "INVALID"},
            })
            data = _parse(result)
            assert data.get("success") is False or "invalid" in data.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_update_write_permission_denied(self, server):
        from mcp.types import TextContent
        perm_error = TextContent(type="text", text='{"error": "write permission denied"}')

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(False, perm_error)):
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({"agent_id": "agent-1"})
            assert "write permission denied" in result[0].text

    @pytest.mark.asyncio
    async def test_update_ownership_denied(self, server):
        meta = make_agent_meta()
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=False):
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({"agent_id": "agent-1"})
            data = _parse(result)
            assert data.get("success") is False or "auth" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_update_not_registered(self, server):
        from mcp.types import TextContent
        error = TextContent(type="text", text='{"error": "not registered"}')

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=(None, error)):
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({})
            assert "not registered" in result[0].text

    @pytest.mark.asyncio
    async def test_update_kwargs_unwrapping(self, server):
        meta = make_agent_meta(notes="")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.identity_shared.require_write_permission", return_value=(True, None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_update_agent_metadata
            result = await handle_update_agent_metadata({
                "agent_id": "agent-1",
                "kwargs": json.dumps({"notes": "from kwargs"}),
            })
            data = _parse(result)
            assert data["success"] is True
            assert meta.notes == "from kwargs"


# ============================================================================
# handle_archive_agent
# ============================================================================

class TestArchiveAgent:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_archive_success(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["success"] is True
            assert data["lifecycle_status"] == "archived"
            assert meta.status == "archived"
            assert meta.archived_at is not None
            meta.add_lifecycle_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_already_archived(self, server):
        meta = make_agent_meta(status="archived")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({"agent_id": "agent-1"})
            text = result[0].text
            assert "already archived" in text.lower()

    @pytest.mark.asyncio
    async def test_archive_not_found(self, server):
        server.agent_metadata = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({"agent_id": "agent-1"})
            text = result[0].text
            assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_archive_ownership_denied(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=False):
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({"agent_id": "agent-1"})
            text = result[0].text
            assert "auth" in text.lower()

    @pytest.mark.asyncio
    async def test_archive_not_registered(self, server):
        from mcp.types import TextContent
        error = TextContent(type="text", text='{"error": "not registered"}')

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=(None, error)):
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({})
            assert "not registered" in result[0].text

    @pytest.mark.asyncio
    async def test_archive_with_custom_reason(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({
                "agent_id": "agent-1", "reason": "Session ended",
            })
            data = _parse(result)
            assert data["reason"] == "Session ended"

    @pytest.mark.asyncio
    async def test_archive_keep_in_memory(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {"agent-1": MagicMock()}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({
                "agent_id": "agent-1", "keep_in_memory": True,
            })
            data = _parse(result)
            assert data["kept_in_memory"] is True
            assert "agent-1" in server.monitors  # kept

    @pytest.mark.asyncio
    async def test_archive_unloads_monitor(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {"agent-1": MagicMock()}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_agent
            result = await handle_archive_agent({
                "agent_id": "agent-1", "keep_in_memory": False,
            })
            data = _parse(result)
            assert data["kept_in_memory"] is False
            assert "agent-1" not in server.monitors  # removed


# ============================================================================
# handle_delete_agent
# ============================================================================

class TestDeleteAgent:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_delete_requires_confirm(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({"agent_id": "agent-1", "confirm": False})
            text = result[0].text
            assert "confirm" in text.lower()

    @pytest.mark.asyncio
    async def test_delete_default_no_confirm(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({"agent_id": "agent-1"})
            text = result[0].text
            assert "confirm" in text.lower()

    @pytest.mark.asyncio
    async def test_delete_pioneer_blocked(self, server):
        meta = make_agent_meta(status="active", tags=["pioneer"])
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({"agent_id": "agent-1", "confirm": True})
            text = result[0].text
            assert "pioneer" in text.lower() or "cannot delete" in text.lower()

    @pytest.mark.asyncio
    async def test_delete_success_no_backup(self, server):
        meta = make_agent_meta(status="active", tags=[])
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.delete_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({
                "agent_id": "agent-1", "confirm": True, "backup_first": False,
            })
            data = _parse(result)
            assert data["success"] is True
            assert meta.status == "deleted"
            meta.add_lifecycle_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, server):
        server.agent_metadata = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({"agent_id": "agent-1", "confirm": True})
            text = result[0].text
            assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_delete_ownership_denied(self, server):
        meta = make_agent_meta(status="active", tags=[])
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=False):
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({
                "agent_id": "agent-1", "confirm": True,
            })
            text = result[0].text
            assert "auth" in text.lower()

    @pytest.mark.asyncio
    async def test_delete_removes_monitor(self, server):
        meta = make_agent_meta(status="active", tags=[])
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {"agent-1": MagicMock()}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.delete_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({
                "agent_id": "agent-1", "confirm": True, "backup_first": False,
            })
            assert "agent-1" not in server.monitors

    @pytest.mark.asyncio
    async def test_delete_not_registered(self, server):
        from mcp.types import TextContent
        error = TextContent(type="text", text='{"error": "not registered"}')

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=(None, error)):
            from src.mcp_handlers.lifecycle import handle_delete_agent
            result = await handle_delete_agent({"confirm": True})
            assert "not registered" in result[0].text


# ============================================================================
# handle_archive_old_test_agents
# ============================================================================

class TestArchiveOldTestAgents:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_dry_run_returns_preview(self, server):
        old = (datetime.now() - timedelta(hours=12)).isoformat()
        server.agent_metadata = {
            "test_agent_1": make_agent_meta(status="active", last_update=old, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({"dry_run": True})
            data = _parse(result)
            assert data["dry_run"] is True
            assert data["archived_count"] >= 1
            mock_storage.archive_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_archives_low_update_test_agents(self, server):
        recent = datetime.now(timezone.utc).isoformat()
        server.agent_metadata = {
            "test_ping_1": make_agent_meta(status="active", last_update=recent, total_updates=1),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({})
            data = _parse(result)
            assert data["archived_count"] >= 1
            archived_ids = [a["id"] for a in data["archived_agents"]]
            assert "test_ping_1" in archived_ids

    @pytest.mark.asyncio
    async def test_skips_already_archived(self, server):
        server.agent_metadata = {
            "test_old": make_agent_meta(status="archived", total_updates=1),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({})
            data = _parse(result)
            assert data["archived_count"] == 0

    @pytest.mark.asyncio
    async def test_skips_non_test_agents(self, server):
        old = (datetime.now() - timedelta(hours=12)).isoformat()
        server.agent_metadata = {
            "production-agent": make_agent_meta(status="active", last_update=old, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({})
            data = _parse(result)
            assert data["archived_count"] == 0

    @pytest.mark.asyncio
    async def test_include_all_archives_non_test(self, server):
        old = (datetime.now() - timedelta(days=5)).isoformat()
        server.agent_metadata = {
            "production-agent": make_agent_meta(status="active", last_update=old, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({"include_all": True})
            data = _parse(result)
            assert data["include_all"] is True
            assert data["archived_count"] >= 1

    @pytest.mark.asyncio
    async def test_max_age_hours_too_small_returns_error(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({"max_age_hours": 0.01})
            text = result[0].text
            assert "must be at least" in text.lower() or "0.1" in text

    @pytest.mark.asyncio
    async def test_max_age_days_conversion(self, server):
        old = (datetime.now() - timedelta(days=10)).isoformat()
        server.agent_metadata = {
            "test_old": make_agent_meta(status="active", last_update=old, total_updates=5),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_old_test_agents
            result = await handle_archive_old_test_agents({"max_age_days": 7})
            data = _parse(result)
            assert data["max_age_days"] == 7.0
            assert data["archived_count"] >= 1


# ============================================================================
# handle_archive_orphan_agents
# ============================================================================

class TestArchiveOrphanAgents:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_archives_uuid_zero_update_agents(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        server.agent_metadata = {
            "12345678-1234-1234-1234-123456789abc": make_agent_meta(
                status="active", total_updates=0, last_update=old, label=None
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            assert data["archived_count"] >= 1

    @pytest.mark.asyncio
    async def test_preserves_labeled_agents_with_updates(self, server):
        """Labeled UUID agents with 2+ updates are preserved (Rule 3 requires unlabeled)."""
        old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        server.agent_metadata = {
            "12345678-1234-1234-1234-123456789abc": make_agent_meta(
                status="active", total_updates=5, last_update=old, label="Important"
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            assert data["archived_count"] == 0

    @pytest.mark.asyncio
    async def test_preserves_pioneer_agents(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        server.agent_metadata = {
            "12345678-1234-1234-1234-123456789abc": make_agent_meta(
                status="active", total_updates=0, last_update=old, tags=["pioneer"]
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            assert data["archived_count"] == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_archive(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        server.agent_metadata = {
            "12345678-1234-1234-1234-123456789abc": make_agent_meta(
                status="active", total_updates=0, last_update=old, label=None
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({"dry_run": True})
            data = _parse(result)
            assert data["dry_run"] is True
            assert data["archived_count"] >= 1
            mock_storage.archive_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_already_archived(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        server.agent_metadata = {
            "12345678-1234-1234-1234-123456789abc": make_agent_meta(
                status="archived", total_updates=0, last_update=old, label=None
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            assert data["archived_count"] == 0

    @pytest.mark.asyncio
    async def test_unlabeled_low_update_agents(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=15)).isoformat()
        server.agent_metadata = {
            "some-non-uuid-agent": make_agent_meta(
                status="active", total_updates=1, last_update=old, label=None
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            assert data["archived_count"] >= 1

    @pytest.mark.asyncio
    async def test_stale_uuid_with_many_updates(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        server.agent_metadata = {
            "12345678-1234-1234-1234-123456789abc": make_agent_meta(
                status="active", total_updates=5, last_update=old, label=None
            ),
        }
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            # UUID-named, unlabeled, 5 updates, 30h old > 24h threshold
            assert data["archived_count"] >= 1

    @pytest.mark.asyncio
    async def test_thresholds_in_response(self, server):
        server.agent_metadata = {}
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage:
            mock_storage.archive_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_archive_orphan_agents
            result = await handle_archive_orphan_agents({})
            data = _parse(result)
            assert "thresholds" in data
            assert "zero_update_hours" in data["thresholds"]
            assert "low_update_hours" in data["thresholds"]
            assert "unlabeled_hours" in data["thresholds"]


# ============================================================================
# handle_mark_response_complete
# ============================================================================

class TestMarkResponseComplete:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_mark_complete_success(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True), \
             patch("src.knowledge_graph.get_knowledge_graph", new_callable=AsyncMock, side_effect=Exception("no graph")):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_mark_response_complete
            result = await handle_mark_response_complete({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["success"] is True
            assert data["status"] == "waiting_input"
            assert meta.status == "waiting_input"

    @pytest.mark.asyncio
    async def test_mark_complete_with_summary(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True), \
             patch("src.knowledge_graph.get_knowledge_graph", new_callable=AsyncMock, side_effect=Exception("no graph")):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_mark_response_complete
            result = await handle_mark_response_complete({
                "agent_id": "agent-1", "summary": "Done with refactoring",
            })
            data = _parse(result)
            assert data["success"] is True
            meta.add_lifecycle_event.assert_called_once()
            call_args = meta.add_lifecycle_event.call_args
            assert "Done with refactoring" in str(call_args)

    @pytest.mark.asyncio
    async def test_mark_complete_not_registered(self, server):
        from mcp.types import TextContent
        error = TextContent(type="text", text='{"error": "not registered"}')

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=(None, error)):
            from src.mcp_handlers.lifecycle import handle_mark_response_complete
            result = await handle_mark_response_complete({})
            assert "not registered" in result[0].text

    @pytest.mark.asyncio
    async def test_mark_complete_ownership_denied(self, server):
        meta = make_agent_meta(status="active")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=False):
            from src.mcp_handlers.lifecycle import handle_mark_response_complete
            result = await handle_mark_response_complete({"agent_id": "agent-1"})
            text = result[0].text
            assert "auth" in text.lower()


# ============================================================================
# handle_direct_resume_if_safe
# ============================================================================

class TestDirectResumeIfSafe:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    def _make_monitor(self, coherence=0.8, mean_risk=0.3, void_active=False):
        monitor = MagicMock()
        monitor.state = SimpleNamespace(
            coherence=coherence, void_active=void_active,
            E=0.7, I=0.3, S=0.5, V=0.0, lambda1=0.1,
        )
        monitor.get_metrics.return_value = {"mean_risk": mean_risk}
        return monitor

    @pytest.mark.asyncio
    async def test_resume_success(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor()

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            mock_storage.update_agent = AsyncMock()
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["success"] is True
            assert data["action"] == "resumed"
            assert meta.status == "active"
            assert "deprecation_warning" in data

    @pytest.mark.asyncio
    async def test_resume_not_safe_low_coherence(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor(coherence=0.2)

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            text = result[0].text
            assert "not safe" in text.lower() or "failed" in text.lower()
            assert meta.status == "paused"  # not resumed

    @pytest.mark.asyncio
    async def test_resume_not_safe_high_risk(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor(mean_risk=0.8)

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            text = result[0].text
            assert "not safe" in text.lower() or "failed" in text.lower()

    @pytest.mark.asyncio
    async def test_resume_not_safe_void_active(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor(void_active=True)

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            text = result[0].text
            assert "not safe" in text.lower() or "failed" in text.lower()

    @pytest.mark.asyncio
    async def test_resume_not_safe_wrong_status(self, server):
        meta = make_agent_meta(status="active")  # not paused
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor()

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            text = result[0].text
            assert "not safe" in text.lower() or "failed" in text.lower()

    @pytest.mark.asyncio
    async def test_resume_not_found(self, server):
        server.agent_metadata = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)):
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            text = result[0].text
            assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_resume_ownership_denied(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=False):
            from src.mcp_handlers.lifecycle import handle_direct_resume_if_safe
            result = await handle_direct_resume_if_safe({"agent_id": "agent-1"})
            text = result[0].text
            assert "auth" in text.lower()


# ============================================================================
# handle_self_recovery_review
# ============================================================================

class TestSelfRecoveryReview:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    def _make_monitor(self, coherence=0.8, mean_risk=0.3, void_active=False, V=0.0):
        monitor = MagicMock()
        monitor.state = SimpleNamespace(
            coherence=coherence, void_active=void_active,
            E=0.7, I=0.3, S=0.5, V=V, lambda1=0.1,
        )
        monitor.get_metrics.return_value = {"mean_risk": mean_risk}
        return monitor

    @pytest.mark.asyncio
    async def test_recovery_success(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor()

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True), \
             patch("src.mcp_handlers.lifecycle.GovernanceConfig") as mock_config:
            mock_storage.update_agent = AsyncMock()
            mock_config.compute_proprioceptive_margin.return_value = {"margin": "comfortable"}
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1",
                "reflection": "I got stuck in a loop and should have stepped back",
            })
            data = _parse(result)
            assert data["success"] is True
            assert data["action"] == "resumed"
            assert meta.status == "active"

    @pytest.mark.asyncio
    async def test_recovery_requires_reflection(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1", "reflection": "",
            })
            text = result[0].text
            assert "reflection" in text.lower()

    @pytest.mark.asyncio
    async def test_recovery_reflection_too_short(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True):
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1", "reflection": "short",
            })
            text = result[0].text
            assert "reflection" in text.lower() or "20" in text

    @pytest.mark.asyncio
    async def test_recovery_not_safe_metrics(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor(
            coherence=0.2, mean_risk=0.8
        )

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.lifecycle.agent_storage") as mock_storage, \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True), \
             patch("src.mcp_handlers.lifecycle.GovernanceConfig") as mock_config:
            mock_storage.update_agent = AsyncMock()
            mock_config.compute_proprioceptive_margin.return_value = {"margin": "critical"}
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1",
                "reflection": "I reflected deeply on what went wrong here",
            })
            data = _parse(result)
            assert data["success"] is False
            assert data["action"] == "not_resumed"
            assert len(data["failed_checks"]) > 0
            assert meta.status == "paused"  # not resumed

    @pytest.mark.asyncio
    async def test_recovery_rejects_dangerous_conditions(self, server):
        meta = make_agent_meta(status="paused")
        server.agent_metadata = {"agent-1": meta}
        server.get_or_create_monitor.return_value = self._make_monitor()

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True), \
             patch("src.mcp_handlers.lifecycle.GovernanceConfig") as mock_config:
            mock_config.compute_proprioceptive_margin.return_value = {"margin": "comfortable"}
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1",
                "reflection": "I reflected deeply on what went wrong here",
                "proposed_conditions": ["disable safety checks"],
            })
            text = result[0].text
            assert "dangerous" in text.lower() or "unsafe" in text.lower()

    @pytest.mark.asyncio
    async def test_recovery_ownership_denied(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=False):
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1",
                "reflection": "I reflected deeply on what went wrong here",
            })
            text = result[0].text
            assert "auth" in text.lower()

    @pytest.mark.asyncio
    async def test_recovery_not_found(self, server):
        server.agent_metadata = {}
        server.get_or_create_monitor.return_value = self._make_monitor()

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle.require_registered_agent", return_value=("agent-1", None)), \
             patch("src.mcp_handlers.utils.verify_agent_ownership", return_value=True), \
             patch("src.mcp_handlers.lifecycle.GovernanceConfig") as mock_config:
            mock_config.compute_proprioceptive_margin.return_value = {"margin": "comfortable"}
            from src.mcp_handlers.lifecycle import handle_self_recovery_review
            result = await handle_self_recovery_review({
                "agent_id": "agent-1",
                "reflection": "I reflected deeply on what went wrong here",
            })
            text = result[0].text
            assert "not found" in text.lower()


# ============================================================================
# handle_detect_stuck_agents
# ============================================================================

class TestDetectStuckAgents:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_detects_stuck_agent(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        meta = make_agent_meta(status="active", last_update=old, total_updates=5)
        meta.created_at = old
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle._detect_stuck_agents", return_value=[
                 {"agent_id": "agent-1", "reason": "activity_timeout", "age_minutes": 60.0,
                  "details": "No updates in 60.0 minutes"}
             ]):
            from src.mcp_handlers.lifecycle import handle_detect_stuck_agents
            result = await handle_detect_stuck_agents({})
            data = _parse(result)
            assert data["summary"]["total_stuck"] >= 1
            assert len(data["stuck_agents"]) >= 1

    @pytest.mark.asyncio
    async def test_no_stuck_agents(self, server):
        server.agent_metadata = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle._detect_stuck_agents", return_value=[]):
            from src.mcp_handlers.lifecycle import handle_detect_stuck_agents
            result = await handle_detect_stuck_agents({})
            data = _parse(result)
            assert data["summary"]["total_stuck"] == 0
            assert data["stuck_agents"] == []

    @pytest.mark.asyncio
    async def test_custom_timeout_parameters(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.lifecycle._detect_stuck_agents", return_value=[]) as mock_detect:
            from src.mcp_handlers.lifecycle import handle_detect_stuck_agents
            result = await handle_detect_stuck_agents({
                "max_age_minutes": 60.0,
                "critical_margin_timeout_minutes": 10.0,
                "tight_margin_timeout_minutes": 20.0,
            })
            data = _parse(result)
            assert "summary" in data
            assert data["summary"]["total_stuck"] == 0


# ============================================================================
# _detect_stuck_agents (internal function)
# ============================================================================

class TestDetectStuckAgentsInternal:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    def test_skips_archived_agents(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        meta = make_agent_meta(status="archived", last_update=old, total_updates=5)
        meta.created_at = old
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import _detect_stuck_agents
            result = _detect_stuck_agents()
            assert len(result) == 0

    def test_skips_autonomous_agents(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        meta = make_agent_meta(
            status="active", last_update=old, total_updates=5, tags=["autonomous"]
        )
        meta.created_at = old
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import _detect_stuck_agents
            result = _detect_stuck_agents()
            assert len(result) == 0

    def test_skips_low_update_agents(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        meta = make_agent_meta(
            status="active", last_update=old, total_updates=0
        )
        meta.created_at = old
        server.agent_metadata = {"agent-1": meta}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import _detect_stuck_agents
            result = _detect_stuck_agents(min_updates=1)
            assert len(result) == 0

    def test_detects_timeout(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        meta = make_agent_meta(status="active", last_update=old, total_updates=5)
        meta.created_at = old
        server.agent_metadata = {"agent-1": meta}
        server.monitors = {}
        server.load_monitor_state = MagicMock(return_value=None)

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import _detect_stuck_agents
            result = _detect_stuck_agents(max_age_minutes=30)
            assert len(result) >= 1
            assert result[0]["reason"] == "activity_timeout"


# ============================================================================
# handle_ping_agent
# ============================================================================

class TestPingAgent:

    @pytest.fixture
    def server(self):
        return make_mock_server()

    @pytest.mark.asyncio
    async def test_ping_alive_agent(self, server):
        recent = datetime.now(timezone.utc).isoformat()
        meta = make_agent_meta(status="active", last_update=recent)
        meta.created_at = recent
        server.agent_metadata = {"agent-1": meta}

        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"E": 0.7}
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["responsive"] is True
            assert data["status"] == "alive"
            assert data["agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_ping_stuck_agent(self, server):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        meta = make_agent_meta(status="active", last_update=old)
        meta.created_at = old
        server.agent_metadata = {"agent-1": meta}

        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"E": 0.7}
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["responsive"] is True
            assert data["status"] == "stuck"

    @pytest.mark.asyncio
    async def test_ping_unresponsive_agent(self, server):
        recent = datetime.now(timezone.utc).isoformat()
        meta = make_agent_meta(status="active", last_update=recent)
        meta.created_at = recent
        server.agent_metadata = {"agent-1": meta}

        mock_monitor = MagicMock()
        mock_monitor.get_metrics.side_effect = RuntimeError("cannot get metrics")
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["responsive"] is False
            assert data["status"] == "unresponsive"

    @pytest.mark.asyncio
    async def test_ping_not_found(self, server):
        server.agent_metadata = {}

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({"agent_id": "nonexistent"})
            text = result[0].text
            assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_ping_no_agent_id(self, server):
        with patch("src.mcp_handlers.lifecycle.mcp_server", server), \
             patch("src.mcp_handlers.identity_shared.get_bound_agent_id", return_value=None):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({})
            text = result[0].text
            assert "agent_id" in text.lower()

    @pytest.mark.asyncio
    async def test_ping_no_agent_id_returns_error(self, server):
        """When no agent_id given, handler returns error (broken import of get_bound_agent_id in source)."""
        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({})
            text = result[0].text
            # Returns an error since it can't resolve bound agent
            assert "error" in text.lower() or "agent_id" in text.lower()

    @pytest.mark.asyncio
    async def test_ping_includes_lifecycle_status(self, server):
        recent = datetime.now(timezone.utc).isoformat()
        meta = make_agent_meta(status="paused", last_update=recent)
        meta.created_at = recent
        server.agent_metadata = {"agent-1": meta}

        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"E": 0.7}
        server.get_or_create_monitor.return_value = mock_monitor

        with patch("src.mcp_handlers.lifecycle.mcp_server", server):
            from src.mcp_handlers.lifecycle import handle_ping_agent
            result = await handle_ping_agent({"agent_id": "agent-1"})
            data = _parse(result)
            assert data["lifecycle_status"] == "paused"
