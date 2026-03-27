"""
Tests for Vigil's groundskeeper duties in heartbeat_agent.py.

Tests the _run_groundskeeper method, CLI flags, and change detection.
All MCP calls are mocked — no live server required.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add scripts to path so we can import heartbeat_agent
project_root = Path(__file__).parent.parent
scripts_dir = project_root / "scripts" / "ops"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(scripts_dir))

from heartbeat_agent import HeartbeatAgent, detect_changes


# =============================================================================
# Test helpers
# =============================================================================

def _make_agent(with_audit: bool = True) -> HeartbeatAgent:
    """Create a HeartbeatAgent with mocked identity."""
    agent = HeartbeatAgent(
        mcp_url="http://localhost:8767/mcp/",
        with_audit=with_audit,
    )
    agent.client_session_id = "test-session-id"
    return agent


def _make_call_tool_mock(responses: Dict[str, Dict[str, Any]] = None):
    """Create a mock call_tool that returns canned responses based on tool name."""
    if responses is None:
        responses = {}

    default_audit = {
        "success": True,
        "audit": {
            "buckets": {"healthy": 5, "aging": 2, "stale": 1, "candidate_for_archive": 0},
            "total_audited": 8,
            "model_assessment": None,
        },
    }
    default_cleanup = {
        "success": True,
        "cleanup_result": {"ephemeral_archived": 0, "discoveries_archived": 0},
    }
    default_orphan = {"success": True, "archived_count": 3}
    default_note = {"success": True}

    defaults = {
        "knowledge": default_audit,
        "archive_orphan_agents": default_orphan,
        "leave_note": default_note,
    }

    async def mock_call_tool(session, tool_name, arguments):
        # For knowledge tool, check the action
        if tool_name == "knowledge":
            action = arguments.get("action", "")
            if action == "cleanup":
                return responses.get("cleanup", default_cleanup)
            return responses.get("audit", default_audit)
        return responses.get(tool_name, defaults.get(tool_name, {"success": True}))

    return mock_call_tool


# =============================================================================
# Tests: _run_groundskeeper
# =============================================================================

class TestRunGroundskeeper:
    """Tests for the groundskeeper method."""

    @pytest.mark.asyncio
    async def test_groundskeeper_calls_audit(self):
        """Groundskeeper should call knowledge(action=audit)."""
        agent = _make_agent()
        calls: List[tuple] = []

        async def tracking_call_tool(session, tool_name, arguments):
            calls.append((tool_name, arguments.get("action")))
            if tool_name == "knowledge" and arguments.get("action") == "audit":
                return {
                    "success": True,
                    "audit": {
                        "buckets": {"healthy": 3, "aging": 0, "stale": 0, "candidate_for_archive": 0},
                        "total_audited": 3,
                    },
                }
            return {"success": True, "archived_count": 0}

        agent.call_tool = tracking_call_tool
        session = MagicMock()
        result = await agent._run_groundskeeper(session)

        audit_calls = [(t, a) for t, a in calls if t == "knowledge" and a == "audit"]
        assert len(audit_calls) == 1
        assert result["audit_run"] is True

    @pytest.mark.asyncio
    async def test_groundskeeper_triggers_cleanup_on_candidates(self):
        """When audit finds archive candidates, cleanup should be triggered."""
        agent = _make_agent()
        calls: List[tuple] = []

        async def tracking_call_tool(session, tool_name, arguments):
            calls.append((tool_name, arguments.get("action")))
            if tool_name == "knowledge" and arguments.get("action") == "audit":
                return {
                    "success": True,
                    "audit": {
                        "buckets": {"healthy": 2, "aging": 1, "stale": 1, "candidate_for_archive": 3},
                        "total_audited": 7,
                    },
                }
            if tool_name == "knowledge" and arguments.get("action") == "cleanup":
                return {
                    "success": True,
                    "cleanup_result": {"ephemeral_archived": 1, "discoveries_archived": 2},
                }
            return {"success": True, "archived_count": 0}

        agent.call_tool = tracking_call_tool
        session = MagicMock()
        result = await agent._run_groundskeeper(session)

        cleanup_calls = [(t, a) for t, a in calls if t == "knowledge" and a == "cleanup"]
        assert len(cleanup_calls) == 1
        assert result["archived"] == 3  # 1 ephemeral + 2 discoveries
        assert result["stale_found"] == 4  # 1 stale + 3 candidate

    @pytest.mark.asyncio
    async def test_groundskeeper_skips_cleanup_when_no_candidates(self):
        """When no archive candidates, cleanup should not be called."""
        agent = _make_agent()
        calls: List[tuple] = []

        async def tracking_call_tool(session, tool_name, arguments):
            calls.append((tool_name, arguments.get("action")))
            if tool_name == "knowledge" and arguments.get("action") == "audit":
                return {
                    "success": True,
                    "audit": {
                        "buckets": {"healthy": 5, "aging": 0, "stale": 0, "candidate_for_archive": 0},
                        "total_audited": 5,
                    },
                }
            return {"success": True, "archived_count": 0}

        agent.call_tool = tracking_call_tool
        session = MagicMock()
        await agent._run_groundskeeper(session)

        cleanup_calls = [(t, a) for t, a in calls if t == "knowledge" and a == "cleanup"]
        assert len(cleanup_calls) == 0

    @pytest.mark.asyncio
    async def test_groundskeeper_archives_orphan_agents(self):
        """Groundskeeper should call archive_orphan_agents."""
        agent = _make_agent()
        agent.call_tool = _make_call_tool_mock({"archive_orphan_agents": {"success": True, "archived_count": 5}})
        session = MagicMock()
        result = await agent._run_groundskeeper(session)

        assert result["orphans_archived"] == 5

    @pytest.mark.asyncio
    async def test_groundskeeper_leaves_note(self):
        """Groundskeeper should leave a summary note with correct tags."""
        agent = _make_agent()
        note_calls: List[Dict] = []

        async def tracking_call_tool(session, tool_name, arguments):
            if tool_name == "leave_note":
                note_calls.append(arguments)
                return {"success": True}
            if tool_name == "knowledge":
                return {
                    "success": True,
                    "audit": {
                        "buckets": {"healthy": 3, "aging": 0, "stale": 0, "candidate_for_archive": 0},
                        "total_audited": 3,
                    },
                }
            return {"success": True, "archived_count": 0}

        agent.call_tool = tracking_call_tool
        session = MagicMock()
        await agent._run_groundskeeper(session)

        assert len(note_calls) == 1
        assert "groundskeeper" in note_calls[0]["tags"]
        assert "vigil" in note_calls[0]["tags"]

    @pytest.mark.asyncio
    async def test_groundskeeper_handles_audit_failure(self):
        """Gracefully handles audit tool failure."""
        agent = _make_agent()

        async def failing_call_tool(session, tool_name, arguments):
            if tool_name == "knowledge" and arguments.get("action") == "audit":
                return {"success": False, "error": "Graph unavailable"}
            return {"success": True, "archived_count": 0}

        agent.call_tool = failing_call_tool
        session = MagicMock()
        result = await agent._run_groundskeeper(session)

        assert result["audit_run"] is False
        assert len(result["errors"]) > 0


# =============================================================================
# Tests: with_audit flag
# =============================================================================

class TestWithAuditFlag:
    """Tests for the --no-audit CLI flag."""

    def test_default_with_audit_true(self):
        """By default, with_audit should be True."""
        agent = HeartbeatAgent()
        assert agent.with_audit is True

    def test_with_audit_false(self):
        """with_audit=False should be settable."""
        agent = HeartbeatAgent(with_audit=False)
        assert agent.with_audit is False


# =============================================================================
# Tests: detect_changes with groundskeeper state
# =============================================================================

class TestDetectChangesGroundskeeper:
    """Tests for change detection with groundskeeper staleness tracking."""

    def test_stale_spike_generates_note(self):
        """Large stale increase (>10) should generate a drift note."""
        prev = {"groundskeeper_stale": 5}
        curr = {"groundskeeper_stale": 20}
        changes = detect_changes(prev, curr)

        gk_changes = [c for c in changes if "groundskeeper" in c.get("tags", [])]
        assert len(gk_changes) == 1
        assert "spike" in gk_changes[0]["summary"].lower()

    def test_stale_stable_no_note(self):
        """Stable stale count should not generate a note."""
        prev = {"groundskeeper_stale": 5}
        curr = {"groundskeeper_stale": 8}
        changes = detect_changes(prev, curr)

        gk_changes = [c for c in changes if "groundskeeper" in c.get("tags", [])]
        assert len(gk_changes) == 0

    def test_stale_decrease_no_note(self):
        """Decreasing stale count should not generate a note."""
        prev = {"groundskeeper_stale": 20}
        curr = {"groundskeeper_stale": 5}
        changes = detect_changes(prev, curr)

        gk_changes = [c for c in changes if "groundskeeper" in c.get("tags", [])]
        assert len(gk_changes) == 0

    def test_no_previous_stale_no_note(self):
        """First cycle with stale data should not generate a spike note."""
        prev = {}
        curr = {"groundskeeper_stale": 15}
        changes = detect_changes(prev, curr)

        gk_changes = [c for c in changes if "groundskeeper" in c.get("tags", [])]
        assert len(gk_changes) == 1  # 15 > 0 + 10
