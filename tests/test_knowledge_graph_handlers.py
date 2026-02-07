"""
Tests for src/mcp_handlers/knowledge_graph.py - comprehensive handler coverage.

Tests cover:
- handle_store_knowledge_graph (single + batch)
- handle_search_knowledge_graph
- handle_get_knowledge_graph
- handle_list_knowledge_graph
- handle_update_discovery_status_graph
- handle_get_discovery_details
- handle_leave_note
- handle_cleanup_knowledge_graph
- handle_get_lifecycle_stats
- handle_answer_question
- _discovery_not_found helper
- _check_display_name_required helper
- _resolve_agent_display helper
"""

import pytest
import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.knowledge_graph import DiscoveryNode, ResponseTo


# ============================================================================
# Shared helpers
# ============================================================================

def parse_result(result):
    """Parse TextContent result into dict.

    Handles both Sequence[TextContent] (from success_response) and
    bare TextContent (from some error_response calls).
    """
    from mcp.types import TextContent
    if isinstance(result, TextContent):
        return json.loads(result.text)
    return json.loads(result[0].text)


def make_discovery(
    id="disc-1",
    agent_id="test-agent",
    type="note",
    summary="Test discovery",
    details="Some details",
    tags=None,
    severity="low",
    status="open",
    response_to=None,
    provenance=None,
    provenance_chain=None,
) -> DiscoveryNode:
    """Create a DiscoveryNode for testing."""
    return DiscoveryNode(
        id=id,
        agent_id=agent_id,
        type=type,
        summary=summary,
        details=details,
        tags=tags or [],
        severity=severity,
        status=status,
        response_to=response_to,
        provenance=provenance,
        provenance_chain=provenance_chain,
    )


# ============================================================================
# Shared fixtures
# ============================================================================

@pytest.fixture
def mock_mcp_server():
    """Mock the shared mcp_server module."""
    server = MagicMock()
    server.agent_metadata = {}
    server.monitors = {}
    server.save_metadata = MagicMock()
    return server


@pytest.fixture
def mock_graph():
    """Mock knowledge graph backend."""
    graph = AsyncMock()
    graph.add_discovery = AsyncMock(return_value=True)
    graph.find_similar = AsyncMock(return_value=[])
    graph.query = AsyncMock(return_value=[])
    graph.get_discovery = AsyncMock(return_value=None)
    graph.get_agent_discoveries = AsyncMock(return_value=[])
    graph.get_stats = AsyncMock(return_value={"total_discoveries": 0, "total_agents": 0})
    graph.update_discovery = AsyncMock(return_value=True)
    graph.full_text_search = AsyncMock(return_value=[])
    graph._get_db = AsyncMock()
    return graph


@pytest.fixture
def patch_common(mock_mcp_server, mock_graph):
    """Patch all common dependencies for knowledge graph handlers."""
    with patch("src.mcp_handlers.context.get_context_agent_id", return_value=None), \
         patch("src.mcp_handlers.shared.get_mcp_server", return_value=mock_mcp_server), \
         patch("src.mcp_handlers.knowledge_graph.get_mcp_server", return_value=mock_mcp_server), \
         patch("src.mcp_handlers.knowledge_graph.get_knowledge_graph", new_callable=AsyncMock, return_value=mock_graph), \
         patch("src.mcp_handlers.knowledge_graph.record_ms"):
        yield mock_mcp_server, mock_graph


@pytest.fixture
def registered_agent(mock_mcp_server):
    """Register a test agent in the mock server's metadata.

    Uses a valid UUID4 as the key so require_registered_agent can find it
    via direct UUID lookup in agent_metadata.
    """
    import uuid
    agent_uuid = str(uuid.uuid4())
    meta = MagicMock()
    meta.status = "active"
    meta.health_status = "healthy"
    meta.total_updates = 5
    meta.label = "TestAgent"
    meta.display_name = "TestAgent"
    meta.structured_id = "test_agent_opus"
    meta.parent_agent_id = None
    meta.spawn_reason = None
    meta.created_at = "2026-01-01T00:00:00"
    meta.paused_at = None
    mock_mcp_server.agent_metadata[agent_uuid] = meta
    return agent_uuid


# ============================================================================
# handle_store_knowledge_graph
# ============================================================================

class TestStoreKnowledgeGraph:

    @pytest.mark.asyncio
    async def test_store_happy_path(self, patch_common, registered_agent):
        """Store a single discovery successfully."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Found a caching bug",
            "discovery_type": "bug_found",
            "tags": ["cache", "perf"],
            "severity": "medium",
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "discovery_id" in data
        assert "Discovery stored" in data["message"]
        mock_graph.add_discovery.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_missing_summary(self, patch_common, registered_agent):
        """Store fails when summary is missing."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "discovery_type": "insight",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "summary" in data["error"].lower() or "missing" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_store_defaults_to_note_type(self, patch_common, registered_agent):
        """Discovery type defaults to 'note' when not specified."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Quick note about something",
        })

        data = parse_result(result)
        assert data["success"] is True
        # The stored discovery should have type "note"
        call_args = mock_graph.add_discovery.call_args
        discovery = call_args[0][0]
        assert discovery.type == "note"

    @pytest.mark.asyncio
    async def test_store_truncates_long_summary(self, patch_common, registered_agent):
        """Long summaries are truncated to 300 chars."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        long_summary = "A" * 500
        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": long_summary,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "_truncated" in data
        assert "summary" in data["_truncated"]

    @pytest.mark.asyncio
    async def test_store_truncates_long_details(self, patch_common, registered_agent):
        """Long details are truncated to 2000 chars."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        long_details = "B" * 3000
        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Test",
            "details": long_details,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "_truncated" in data
        assert "details" in data["_truncated"]

    @pytest.mark.asyncio
    async def test_store_with_related_discoveries(self, patch_common, registered_agent):
        """Similar discoveries are linked when auto_link_related is True."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        similar = make_discovery(id="related-1", summary="Related item")
        mock_graph.find_similar = AsyncMock(return_value=[similar])

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Something related",
            "auto_link_related": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "related_discoveries" in data
        assert len(data["related_discoveries"]) == 1

    @pytest.mark.asyncio
    async def test_store_graph_exception(self, patch_common, registered_agent):
        """Exception from graph backend returns error response."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        mock_graph.add_discovery = AsyncMock(side_effect=Exception("Database connection lost"))

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "This will fail",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to store" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_store_rate_limit_error(self, patch_common, registered_agent):
        """ValueError with 'rate limit' triggers rate limit error response."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        mock_graph.add_discovery = AsyncMock(side_effect=ValueError("Rate limit exceeded: max 10 per minute"))

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Rate limited",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "rate limit" in data["error"].lower()
        assert "recovery" in data

    @pytest.mark.asyncio
    async def test_store_invalid_discovery_type(self, patch_common, registered_agent):
        """Invalid discovery_type returns validation error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Test",
            "discovery_type": "invalid_type_xyz",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_store_with_param_aliases(self, patch_common, registered_agent):
        """Parameter aliases (e.g. 'insight' -> 'summary') work correctly."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "insight": "My key insight about the system",
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_store_no_agent_id_auto_generates(self, patch_common):
        """When no agent_id and no session binding, one is auto-generated."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "summary": "Note without agent",
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_store_high_severity_requires_registered_agent(self, patch_common):
        """High severity discoveries require registered agent."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        # No agent registered - high severity should require registration
        result = await handle_store_knowledge_graph({
            "agent_id": "unregistered-agent",
            "summary": "Critical issue found",
            "severity": "high",
        })

        data = parse_result(result)
        # Should fail because agent not registered for high severity
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_store_with_response_to(self, patch_common, registered_agent):
        """Store with response_to linking to parent discovery."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Follow-up to parent",
            "response_to": {
                "discovery_id": "2026-01-01T00:00:00.000000",
                "response_type": "extend",
            },
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_store_batch_happy_path(self, patch_common, registered_agent):
        """Batch store multiple discoveries successfully."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "discoveries": [
                {"discovery_type": "note", "summary": "Note 1"},
                {"discovery_type": "insight", "summary": "Insight 1"},
            ],
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["success_count"] == 2
        assert data["error_count"] == 0

    @pytest.mark.asyncio
    async def test_store_batch_empty_list(self, patch_common, registered_agent):
        """Batch store with empty list returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "discoveries": [],
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "empty" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_store_batch_too_many(self, patch_common, registered_agent):
        """Batch store with >10 items returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        discoveries = [{"discovery_type": "note", "summary": f"Note {i}"} for i in range(11)]
        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "discoveries": discoveries,
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "10" in data["error"]

    @pytest.mark.asyncio
    async def test_store_batch_partial_failure(self, patch_common, registered_agent):
        """Batch store with some invalid items stores valid ones and reports errors."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "discoveries": [
                {"discovery_type": "note", "summary": "Good one"},
                {"discovery_type": "note"},  # Missing summary
                "not a dict",  # Invalid type
            ],
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["success_count"] == 1
        assert data["error_count"] == 2

    @pytest.mark.asyncio
    async def test_store_batch_not_a_list(self, patch_common, registered_agent):
        """Batch store with non-list value returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "discoveries": "not a list",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "list" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_store_paused_agent_blocked(self, patch_common, registered_agent, mock_mcp_server):
        """Paused agents cannot store knowledge (circuit breaker)."""
        mock_mcp_server.agent_metadata[registered_agent].status = "paused"
        mock_mcp_server.agent_metadata[registered_agent].paused_at = "2026-01-01T00:00:00"

        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Should be blocked",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "paused" in data["error"].lower()


# ============================================================================
# handle_search_knowledge_graph
# ============================================================================

class TestSearchKnowledgeGraph:

    @pytest.mark.asyncio
    async def test_search_no_filters(self, patch_common):
        """Search with no filters returns indexed filter results."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        discoveries = [make_discovery(id=f"d-{i}", summary=f"Item {i}") for i in range(3)]
        mock_graph.query = AsyncMock(return_value=discoveries)

        result = await handle_search_knowledge_graph({})

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 3
        assert data["search_mode_used"] == "indexed_filters"

    @pytest.mark.asyncio
    async def test_search_with_query_text_fts(self, patch_common):
        """Search with query text uses FTS when available."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        # Make graph have full_text_search but no semantic_search
        mock_graph.full_text_search = AsyncMock(return_value=[
            make_discovery(id="fts-1", summary="Matching result"),
        ])
        # Remove semantic_search to force FTS path
        if hasattr(mock_graph, 'semantic_search'):
            del mock_graph.semantic_search

        result = await handle_search_knowledge_graph({
            "query": "matching",
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 1
        assert data["search_mode_used"] == "fts"

    @pytest.mark.asyncio
    async def test_search_with_filters(self, patch_common):
        """Search with metadata filters."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        discoveries = [make_discovery(id="d-1", type="bug_found", severity="high")]
        mock_graph.query = AsyncMock(return_value=discoveries)

        result = await handle_search_knowledge_graph({
            "discovery_type": "bug_found",
            "severity": "high",
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_search_empty_results(self, patch_common):
        """Search returning no results includes helpful hints."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        mock_graph.query = AsyncMock(return_value=[])

        result = await handle_search_knowledge_graph({
            "query": "nonexistent stuff",
            "semantic": False,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_search_with_include_details(self, patch_common):
        """Search with include_details=True returns full content."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        discoveries = [make_discovery(id="d-1", details="Full details here")]
        mock_graph.query = AsyncMock(return_value=discoveries)

        result = await handle_search_knowledge_graph({
            "include_details": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        if data["count"] > 0:
            assert "details" in data["discoveries"][0]

    @pytest.mark.asyncio
    async def test_search_exception_handling(self, patch_common):
        """Exception from graph backend returns error response."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        mock_graph.query = AsyncMock(side_effect=Exception("DB down"))

        result = await handle_search_knowledge_graph({})

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to search" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_search_substring_scan_fallback(self, patch_common):
        """When no FTS/semantic available, falls back to substring scan."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        # Remove both search methods to trigger substring scan
        mock_graph_spec = AsyncMock()
        mock_graph_spec.query = AsyncMock(return_value=[
            make_discovery(id="d-1", summary="Contains keyword here"),
        ])
        # Make hasattr return False for semantic_search and full_text_search
        del mock_graph_spec.semantic_search
        del mock_graph_spec.full_text_search

        with patch("src.mcp_handlers.knowledge_graph.get_knowledge_graph", new_callable=AsyncMock, return_value=mock_graph_spec):
            result = await handle_search_knowledge_graph({
                "query": "keyword",
            })

        data = parse_result(result)
        assert data["success"] is True
        assert data["search_mode_used"] == "substring_scan"

    @pytest.mark.asyncio
    async def test_search_with_agent_id_filter(self, patch_common):
        """Search filtered by agent_id."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        discoveries = [make_discovery(id="d-1", agent_id="specific-agent")]
        mock_graph.query = AsyncMock(return_value=discoveries)

        result = await handle_search_knowledge_graph({
            "agent_id": "specific-agent",
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_search_with_tags(self, patch_common):
        """Search filtered by tags."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        discoveries = [make_discovery(id="d-1", tags=["python", "bug"])]
        mock_graph.query = AsyncMock(return_value=discoveries)

        result = await handle_search_knowledge_graph({
            "tags": ["python"],
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_search_param_aliases(self, patch_common):
        """Parameter aliases work (e.g. 'search' -> 'query')."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        # "search" is an alias for "query" in PARAM_ALIASES
        mock_graph.query = AsyncMock(return_value=[])
        # Remove semantic/FTS to test substring path
        del mock_graph.semantic_search
        del mock_graph.full_text_search

        result = await handle_search_knowledge_graph({
            "search": "test query",
        })

        data = parse_result(result)
        assert data["success"] is True
        # The query should have been resolved
        assert data.get("query") == "test query"

    @pytest.mark.asyncio
    async def test_search_with_provenance(self, patch_common):
        """Search with include_provenance=True returns provenance data."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        disc = make_discovery(
            id="d-1",
            provenance={"agent_state": {"status": "active"}},
            provenance_chain=[{"agent_id": "parent", "relationship": "direct_parent"}],
        )
        mock_graph.query = AsyncMock(return_value=[disc])

        result = await handle_search_knowledge_graph({
            "include_provenance": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 1
        assert "provenance" in data["discoveries"][0]
        assert "provenance_chain" in data["discoveries"][0]


# ============================================================================
# handle_get_knowledge_graph
# ============================================================================

class TestGetKnowledgeGraph:

    @pytest.mark.asyncio
    async def test_get_happy_path(self, patch_common, registered_agent):
        """Get discoveries for a registered agent."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_knowledge_graph

        discoveries = [
            make_discovery(id="d-1", agent_id=registered_agent, summary="First"),
            make_discovery(id="d-2", agent_id=registered_agent, summary="Second"),
        ]
        mock_graph.get_agent_discoveries = AsyncMock(return_value=discoveries)

        result = await handle_get_knowledge_graph({
            "agent_id": registered_agent,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_get_unregistered_agent(self, patch_common):
        """Get for unregistered agent returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_knowledge_graph

        result = await handle_get_knowledge_graph({
            "agent_id": "nonexistent-agent",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_get_empty_results(self, patch_common, registered_agent):
        """Get returns empty list when no discoveries found."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_knowledge_graph

        mock_graph.get_agent_discoveries = AsyncMock(return_value=[])

        result = await handle_get_knowledge_graph({
            "agent_id": registered_agent,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 0
        assert data["discoveries"] == []

    @pytest.mark.asyncio
    async def test_get_with_limit(self, patch_common, registered_agent):
        """Get respects limit parameter."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_knowledge_graph

        mock_graph.get_agent_discoveries = AsyncMock(return_value=[])

        result = await handle_get_knowledge_graph({
            "agent_id": registered_agent,
            "limit": 5,
        })

        # Verify limit was passed to the graph backend
        mock_graph.get_agent_discoveries.assert_awaited_once_with(registered_agent, limit=5)

    @pytest.mark.asyncio
    async def test_get_exception_handling(self, patch_common, registered_agent):
        """Exception from graph backend returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_knowledge_graph

        mock_graph.get_agent_discoveries = AsyncMock(side_effect=Exception("DB error"))

        result = await handle_get_knowledge_graph({
            "agent_id": registered_agent,
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to retrieve" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_get_with_include_details(self, patch_common, registered_agent):
        """Get with include_details=True includes details in output."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_knowledge_graph

        disc = make_discovery(id="d-1", agent_id=registered_agent, details="Full details content")
        mock_graph.get_agent_discoveries = AsyncMock(return_value=[disc])

        result = await handle_get_knowledge_graph({
            "agent_id": registered_agent,
            "include_details": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["count"] == 1
        assert "details" in data["discoveries"][0]


# ============================================================================
# handle_list_knowledge_graph
# ============================================================================

class TestListKnowledgeGraph:

    @pytest.mark.asyncio
    async def test_list_happy_path(self, patch_common):
        """List returns graph statistics."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_list_knowledge_graph

        mock_graph.get_stats = AsyncMock(return_value={
            "total_discoveries": 42,
            "total_agents": 5,
        })

        result = await handle_list_knowledge_graph({})

        data = parse_result(result)
        assert data["success"] is True
        assert data["stats"]["total_discoveries"] == 42
        assert data["stats"]["total_agents"] == 5
        assert "42" in data["message"]
        assert "5" in data["message"]

    @pytest.mark.asyncio
    async def test_list_empty_graph(self, patch_common):
        """List returns zero counts for empty graph."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_list_knowledge_graph

        mock_graph.get_stats = AsyncMock(return_value={
            "total_discoveries": 0,
            "total_agents": 0,
        })

        result = await handle_list_knowledge_graph({})

        data = parse_result(result)
        assert data["success"] is True
        assert data["stats"]["total_discoveries"] == 0

    @pytest.mark.asyncio
    async def test_list_exception_handling(self, patch_common):
        """Exception from graph backend returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_list_knowledge_graph

        mock_graph.get_stats = AsyncMock(side_effect=Exception("Stats error"))

        result = await handle_list_knowledge_graph({})

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to list" in data["error"].lower()


# ============================================================================
# handle_update_discovery_status_graph
# ============================================================================

class TestUpdateDiscoveryStatusGraph:

    @pytest.mark.asyncio
    async def test_update_happy_path(self, patch_common, registered_agent):
        """Update discovery status successfully."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        disc = make_discovery(id="2026-01-01T00:00:00.000000", severity="low", agent_id=registered_agent)
        mock_graph.get_discovery = AsyncMock(return_value=disc)
        mock_graph.update_discovery = AsyncMock(return_value=True)

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "discovery_id": "2026-01-01T00:00:00.000000",
            "status": "resolved",
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "resolved" in data["message"]

    @pytest.mark.asyncio
    async def test_update_missing_discovery_id(self, patch_common, registered_agent):
        """Update fails when discovery_id is missing."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "status": "resolved",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_update_missing_status(self, patch_common, registered_agent):
        """Update fails when status is missing."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "discovery_id": "2026-01-01T00:00:00.000000",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_update_discovery_not_found(self, patch_common, registered_agent):
        """Update fails when discovery doesn't exist."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        mock_graph.get_discovery = AsyncMock(return_value=None)
        # Mock _get_db for the _discovery_not_found helper
        mock_db = AsyncMock()
        mock_db.graph_query = AsyncMock(return_value=[])
        mock_graph._get_db = AsyncMock(return_value=mock_db)

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "discovery_id": "2026-01-01T00:00:00.000000",
            "status": "resolved",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_update_unregistered_agent(self, patch_common):
        """Update fails for unregistered agent."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        result = await handle_update_discovery_status_graph({
            "agent_id": "unregistered",
            "discovery_id": "2026-01-01T00:00:00.000000",
            "status": "resolved",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_update_invalid_status(self, patch_common, registered_agent):
        """Update fails with invalid status value."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "discovery_id": "2026-01-01T00:00:00.000000",
            "status": "invalid_status",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_update_exception_handling(self, patch_common, registered_agent):
        """Exception from graph backend returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        mock_graph.get_discovery = AsyncMock(side_effect=Exception("Connection error"))

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "discovery_id": "2026-01-01T00:00:00.000000",
            "status": "resolved",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to update" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_update_resolved_sets_timestamp(self, patch_common, registered_agent):
        """Updating to 'resolved' sets resolved_at timestamp."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_update_discovery_status_graph

        disc = make_discovery(id="2026-01-01T00:00:00.000000", severity="low", agent_id=registered_agent)
        mock_graph.get_discovery = AsyncMock(return_value=disc)
        mock_graph.update_discovery = AsyncMock(return_value=True)

        result = await handle_update_discovery_status_graph({
            "agent_id": registered_agent,
            "discovery_id": "2026-01-01T00:00:00.000000",
            "status": "resolved",
        })

        # Verify update_discovery was called with resolved_at
        call_args = mock_graph.update_discovery.call_args
        updates = call_args[0][1]
        assert "resolved_at" in updates
        assert updates["status"] == "resolved"


# ============================================================================
# handle_get_discovery_details
# ============================================================================

class TestGetDiscoveryDetails:

    @pytest.mark.asyncio
    async def test_get_details_happy_path(self, patch_common):
        """Get full details for a discovery."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        disc = make_discovery(id="2026-01-01T00:00:00.000000", details="Full details content here")
        mock_graph.get_discovery = AsyncMock(return_value=disc)

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "discovery" in data
        assert "Full details" in data["message"]

    @pytest.mark.asyncio
    async def test_get_details_missing_id(self, patch_common):
        """Get details fails when discovery_id is missing."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        result = await handle_get_discovery_details({})

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_get_details_not_found(self, patch_common):
        """Get details for nonexistent discovery returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        mock_graph.get_discovery = AsyncMock(return_value=None)
        # Mock _get_db for the _discovery_not_found helper
        mock_db = AsyncMock()
        mock_db.graph_query = AsyncMock(return_value=[])
        mock_graph._get_db = AsyncMock(return_value=mock_db)

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_get_details_with_pagination(self, patch_common):
        """Get details with pagination (offset/length)."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        long_details = "A" * 5000
        disc = make_discovery(id="2026-01-01T00:00:00.000000", details=long_details)
        mock_graph.get_discovery = AsyncMock(return_value=disc)

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
            "offset": 100,
            "length": 500,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "pagination" in data
        assert data["pagination"]["offset"] == 100
        assert data["pagination"]["total_length"] == 5000
        assert data["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_details_short_content_no_pagination(self, patch_common):
        """Short details don't trigger pagination."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        disc = make_discovery(id="2026-01-01T00:00:00.000000", details="Short content")
        mock_graph.get_discovery = AsyncMock(return_value=disc)

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "pagination" not in data

    @pytest.mark.asyncio
    async def test_get_details_with_response_chain(self, patch_common):
        """Get details with response chain traversal."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        disc = make_discovery(id="2026-01-01T00:00:00.000000", details="Details")
        chain_disc = make_discovery(id="2026-01-02T00:00:00.000000", summary="Response")
        mock_graph.get_discovery = AsyncMock(return_value=disc)
        mock_graph.get_response_chain = AsyncMock(return_value=[disc, chain_disc])

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
            "include_response_chain": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "response_chain" in data
        assert data["response_chain"]["count"] == 2

    @pytest.mark.asyncio
    async def test_get_details_response_chain_not_supported(self, patch_common):
        """Response chain gracefully handles unsupported backend."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        disc = make_discovery(id="2026-01-01T00:00:00.000000", details="Details")
        mock_graph.get_discovery = AsyncMock(return_value=disc)
        # Remove get_response_chain to simulate unsupported backend
        del mock_graph.get_response_chain

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
            "include_response_chain": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "response_chain" in data
        assert "error" in data["response_chain"]

    @pytest.mark.asyncio
    async def test_get_details_exception_handling(self, patch_common):
        """Exception from graph backend returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        mock_graph.get_discovery = AsyncMock(side_effect=Exception("Timeout"))

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to get discovery" in data["error"].lower()


# ============================================================================
# handle_leave_note
# ============================================================================

class TestLeaveNote:

    @pytest.mark.asyncio
    async def test_leave_note_happy_path(self, patch_common, registered_agent):
        """Leave a note successfully."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": "Quick observation about caching",
            "tags": ["cache"],
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "note_id" in data
        assert data["visibility"] == "shared"
        mock_graph.add_discovery.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_leave_note_missing_text(self, patch_common, registered_agent):
        """Leave note fails without content."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        result = await handle_leave_note({
            "agent_id": registered_agent,
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_leave_note_param_aliases(self, patch_common, registered_agent):
        """Note content can use aliases (text, note, content, etc.)."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        # "text" is an alias for "summary"
        result = await handle_leave_note({
            "agent_id": registered_agent,
            "text": "Using text alias",
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_leave_note_truncation(self, patch_common, registered_agent):
        """Long notes are truncated to 500 chars."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        long_text = "X" * 600
        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": long_text,
        })

        data = parse_result(result)
        assert data["success"] is True
        # The stored discovery's summary should be truncated
        call_args = mock_graph.add_discovery.call_args
        discovery = call_args[0][0]
        assert len(discovery.summary) <= 504  # 500 + "..."

    @pytest.mark.asyncio
    async def test_leave_note_auto_links_with_tags(self, patch_common, registered_agent):
        """Notes with tags auto-link to similar discoveries."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        similar = make_discovery(id="similar-1")
        mock_graph.find_similar = AsyncMock(return_value=[similar])

        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": "Tagged note",
            "tags": ["important"],
        })

        data = parse_result(result)
        assert data["success"] is True
        mock_graph.find_similar.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_leave_note_unregistered_agent(self, patch_common):
        """Leave note fails for unregistered agent."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        result = await handle_leave_note({
            "agent_id": "nonexistent-agent",
            "summary": "Should fail",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_leave_note_paused_agent(self, patch_common, registered_agent, mock_mcp_server):
        """Paused agents cannot leave notes (circuit breaker)."""
        mock_mcp_server.agent_metadata[registered_agent].status = "paused"
        mock_mcp_server.agent_metadata[registered_agent].paused_at = "2026-01-01T00:00:00"

        from src.mcp_handlers.knowledge_graph import handle_leave_note

        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": "Should be blocked",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "paused" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_leave_note_with_response_to(self, patch_common, registered_agent):
        """Leave note with response_to for threading."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": "A threaded note",
            "response_to": {
                "discovery_id": "2026-01-01T00:00:00.000000",
                "response_type": "extend",
            },
        })

        data = parse_result(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_leave_note_exception_handling(self, patch_common, registered_agent):
        """Exception from graph backend returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        mock_graph.add_discovery = AsyncMock(side_effect=Exception("Write error"))

        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": "Will fail",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to leave note" in data["error"].lower()


# ============================================================================
# handle_cleanup_knowledge_graph
# ============================================================================

class TestCleanupKnowledgeGraph:

    @pytest.mark.asyncio
    async def test_cleanup_dry_run(self, patch_common):
        """Cleanup in dry run mode previews changes without applying."""
        mock_mcp_server, mock_graph = patch_common

        mock_cleanup = AsyncMock(return_value={"archived": 3, "total_processed": 10})
        # The import is local: from src.knowledge_graph_lifecycle import run_kg_lifecycle_cleanup
        import src.knowledge_graph_lifecycle as lifecycle_mod
        with patch.object(lifecycle_mod, "run_kg_lifecycle_cleanup", mock_cleanup):
            from src.mcp_handlers.knowledge_graph import handle_cleanup_knowledge_graph
            result = await handle_cleanup_knowledge_graph({"dry_run": True})

        data = parse_result(result)
        assert data["success"] is True
        assert "DRY RUN" in data["message"]

    @pytest.mark.asyncio
    async def test_cleanup_execute(self, patch_common):
        """Cleanup actually executes when dry_run=False."""
        mock_mcp_server, mock_graph = patch_common

        mock_cleanup = AsyncMock(return_value={"archived": 5, "total_processed": 20})
        import src.knowledge_graph_lifecycle as lifecycle_mod
        with patch.object(lifecycle_mod, "run_kg_lifecycle_cleanup", mock_cleanup):
            from src.mcp_handlers.knowledge_graph import handle_cleanup_knowledge_graph
            result = await handle_cleanup_knowledge_graph({"dry_run": False})

        data = parse_result(result)
        assert data["success"] is True
        assert "DRY RUN" not in data["message"]

    @pytest.mark.asyncio
    async def test_cleanup_defaults_to_dry_run(self, patch_common):
        """Cleanup defaults to dry_run=True when not specified."""
        mock_mcp_server, mock_graph = patch_common

        mock_cleanup = AsyncMock(return_value={"archived": 0})
        import src.knowledge_graph_lifecycle as lifecycle_mod
        with patch.object(lifecycle_mod, "run_kg_lifecycle_cleanup", mock_cleanup):
            from src.mcp_handlers.knowledge_graph import handle_cleanup_knowledge_graph
            result = await handle_cleanup_knowledge_graph({})

        mock_cleanup.assert_awaited_once_with(dry_run=True)

    @pytest.mark.asyncio
    async def test_cleanup_exception_handling(self, patch_common):
        """Exception from lifecycle cleanup returns error."""
        mock_mcp_server, mock_graph = patch_common

        mock_cleanup = AsyncMock(side_effect=Exception("Cleanup failed"))
        import src.knowledge_graph_lifecycle as lifecycle_mod
        with patch.object(lifecycle_mod, "run_kg_lifecycle_cleanup", mock_cleanup):
            from src.mcp_handlers.knowledge_graph import handle_cleanup_knowledge_graph
            result = await handle_cleanup_knowledge_graph({})

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to run lifecycle" in data["error"].lower()


# ============================================================================
# handle_get_lifecycle_stats
# ============================================================================

class TestGetLifecycleStats:

    @pytest.mark.asyncio
    async def test_lifecycle_stats_happy_path(self, patch_common):
        """Get lifecycle stats successfully."""
        mock_mcp_server, mock_graph = patch_common

        stats_data = {
            "by_status": {"open": 10, "resolved": 5, "archived": 2},
            "by_policy": {"permanent": 3, "standard": 12, "ephemeral": 2},
        }
        import src.knowledge_graph_lifecycle as lifecycle_mod
        with patch.object(lifecycle_mod, "get_kg_lifecycle_stats",
                          AsyncMock(return_value=stats_data)):
            from src.mcp_handlers.knowledge_graph import handle_get_lifecycle_stats
            result = await handle_get_lifecycle_stats({})

        data = parse_result(result)
        assert data["success"] is True
        assert "stats" in data
        assert data["stats"]["by_status"]["open"] == 10

    @pytest.mark.asyncio
    async def test_lifecycle_stats_exception_handling(self, patch_common):
        """Exception returns error response."""
        mock_mcp_server, mock_graph = patch_common

        import src.knowledge_graph_lifecycle as lifecycle_mod
        with patch.object(lifecycle_mod, "get_kg_lifecycle_stats",
                          AsyncMock(side_effect=Exception("Stats unavailable"))):
            from src.mcp_handlers.knowledge_graph import handle_get_lifecycle_stats
            result = await handle_get_lifecycle_stats({})

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to get lifecycle" in data["error"].lower()


# ============================================================================
# handle_answer_question
# ============================================================================

class TestAnswerQuestion:

    @pytest.mark.asyncio
    async def test_answer_question_happy_path(self, patch_common, registered_agent):
        """Answer a matching question successfully."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        question_disc = make_discovery(
            id="q-1",
            type="question",
            summary="What is the meaning of life?",
            agent_id="other-agent",
        )
        mock_graph.query = AsyncMock(return_value=[question_disc])

        result = await handle_answer_question({
            "agent_id": registered_agent,
            "question": "What is the meaning of life?",
            "answer": "42",
        })

        data = parse_result(result)
        assert data["success"] is True
        assert "answer_id" in data
        assert data["question"]["id"] == "q-1"
        mock_graph.add_discovery.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_answer_question_missing_question(self, patch_common, registered_agent):
        """Answer fails without question text."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        result = await handle_answer_question({
            "agent_id": registered_agent,
            "answer": "42",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_answer_question_missing_answer(self, patch_common, registered_agent):
        """Answer fails without answer text."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        result = await handle_answer_question({
            "agent_id": registered_agent,
            "question": "What is the meaning?",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_answer_question_no_match(self, patch_common, registered_agent):
        """Answer fails when no matching question found."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        mock_graph.query = AsyncMock(return_value=[])

        result = await handle_answer_question({
            "agent_id": registered_agent,
            "question": "Something completely unrelated",
            "answer": "My answer",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "no matching question" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_answer_question_with_resolve(self, patch_common, registered_agent):
        """Answer resolves question when resolve_question=True."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        question_disc = make_discovery(
            id="q-1",
            type="question",
            summary="How does caching work?",
        )
        mock_graph.query = AsyncMock(return_value=[question_disc])

        result = await handle_answer_question({
            "agent_id": registered_agent,
            "question": "How does caching work?",
            "answer": "It uses LRU eviction policy",
            "resolve_question": True,
        })

        data = parse_result(result)
        assert data["success"] is True
        assert data["question"]["status"] == "resolved"
        # update_discovery should have been called to resolve the question
        mock_graph.update_discovery.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_answer_question_unregistered_agent(self, patch_common):
        """Answer fails for unregistered agent."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        result = await handle_answer_question({
            "agent_id": "nonexistent-agent",
            "question": "What?",
            "answer": "Nothing",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_answer_question_exception_handling(self, patch_common, registered_agent):
        """Exception from graph backend returns error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        mock_graph.query = AsyncMock(side_effect=Exception("Query error"))

        result = await handle_answer_question({
            "agent_id": registered_agent,
            "question": "What?",
            "answer": "Something",
        })

        data = parse_result(result)
        assert data["success"] is False
        assert "failed to answer" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_answer_question_truncates_long_answer(self, patch_common, registered_agent):
        """Long answers are truncated to 2000 chars."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_answer_question

        question_disc = make_discovery(
            id="q-1",
            type="question",
            summary="Tell me everything",
        )
        mock_graph.query = AsyncMock(return_value=[question_disc])

        long_answer = "Z" * 3000
        result = await handle_answer_question({
            "agent_id": registered_agent,
            "question": "Tell me everything",
            "answer": long_answer,
        })

        data = parse_result(result)
        assert data["success"] is True
        # Verify the stored answer's details were truncated
        call_args = mock_graph.add_discovery.call_args
        answer_disc = call_args[0][0]
        assert len(answer_disc.details) <= 2020  # 2000 + "... [truncated]"


# ============================================================================
# _discovery_not_found helper
# ============================================================================

class TestDiscoveryNotFound:

    @pytest.mark.asyncio
    async def test_not_found_no_suggestions(self, patch_common):
        """Returns plain not-found error when no prefix matches."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import _discovery_not_found

        mock_db = AsyncMock()
        mock_db.graph_query = AsyncMock(return_value=[])
        mock_graph._get_db = AsyncMock(return_value=mock_db)

        result = await _discovery_not_found("2026-nonexistent", mock_graph)

        data = json.loads(result.text)
        assert data["success"] is False
        assert "not found" in data["error"].lower()
        assert "recovery" not in data

    @pytest.mark.asyncio
    async def test_not_found_with_suggestions(self, patch_common):
        """Returns suggestions when prefix matches exist."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import _discovery_not_found

        mock_db = AsyncMock()
        mock_db.graph_query = AsyncMock(return_value=[
            {"d.id": "2026-01-01T00:00:00.123456"},
            {"d.id": "2026-01-01T00:00:00.789012"},
        ])
        mock_graph._get_db = AsyncMock(return_value=mock_db)

        result = await _discovery_not_found("2026", mock_graph)

        data = json.loads(result.text)
        assert data["success"] is False
        assert "did you mean" in data["error"].lower()
        assert "recovery" in data
        assert len(data["recovery"]["matching_ids"]) == 2

    @pytest.mark.asyncio
    async def test_not_found_db_error_graceful(self, patch_common):
        """Falls back to plain error when DB query fails."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import _discovery_not_found

        mock_graph._get_db = AsyncMock(side_effect=Exception("DB unavailable"))

        result = await _discovery_not_found("2026-missing", mock_graph)

        data = json.loads(result.text)
        assert data["success"] is False
        assert "not found" in data["error"].lower()


# ============================================================================
# _check_display_name_required helper
# ============================================================================

class TestCheckDisplayNameRequired:

    def test_has_real_display_name(self, patch_common, registered_agent, mock_mcp_server):
        """Returns (None, None) when agent has a meaningful display_name."""
        from src.mcp_handlers.knowledge_graph import _check_display_name_required

        error, warning = _check_display_name_required(registered_agent, {})

        assert error is None
        assert warning is None

    def test_auto_generates_for_uuid_display_name(self, patch_common, mock_mcp_server):
        """Auto-generates display_name when current one is a UUID."""
        import uuid
        agent_id = str(uuid.uuid4())
        meta = MagicMock()
        meta.status = "active"
        meta.display_name = agent_id  # Display name is the UUID itself
        meta.label = agent_id
        mock_mcp_server.agent_metadata[agent_id] = meta

        from src.mcp_handlers.knowledge_graph import _check_display_name_required

        with patch("src.mcp_handlers.knowledge_graph._check_display_name_required.__module__"):
            error, warning = _check_display_name_required(agent_id, {})

        assert error is None
        # Warning should mention auto-generated
        if warning:
            assert "auto-generated" in warning.lower()

    def test_no_metadata_graceful(self, patch_common):
        """Gracefully handles agents not in metadata."""
        from src.mcp_handlers.knowledge_graph import _check_display_name_required

        error, warning = _check_display_name_required("unknown-agent", {})

        # Should not error - just auto-generate
        assert error is None


# ============================================================================
# _resolve_agent_display helper
# ============================================================================

class TestResolveAgentDisplay:

    def test_resolve_known_agent(self, patch_common, registered_agent, mock_mcp_server):
        """Resolves agent display info from metadata."""
        from src.mcp_handlers.knowledge_graph import _resolve_agent_display

        result = _resolve_agent_display(registered_agent)

        assert "agent_id" in result
        assert "display_name" in result
        assert result["display_name"] == "TestAgent"

    def test_resolve_unknown_agent(self, patch_common):
        """Returns agent_id as fallback for unknown agents."""
        from src.mcp_handlers.knowledge_graph import _resolve_agent_display

        result = _resolve_agent_display("unknown-agent-xyz")

        assert result["agent_id"] == "unknown-agent-xyz"
        assert result["display_name"] == "unknown-agent-xyz"

    def test_resolve_by_structured_id(self, patch_common, mock_mcp_server):
        """Resolves agent by structured_id (not UUID key)."""
        meta = MagicMock()
        meta.structured_id = "opus_agent_20260101"
        meta.display_name = "Opus Agent"
        meta.label = "Opus Agent"
        mock_mcp_server.agent_metadata["uuid-123"] = meta

        from src.mcp_handlers.knowledge_graph import _resolve_agent_display

        result = _resolve_agent_display("opus_agent_20260101")

        assert result["display_name"] == "Opus Agent"


# ============================================================================
# Integration-level edge cases
# ============================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_store_with_invalid_severity(self, patch_common, registered_agent):
        """Invalid severity returns validation error."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "Test",
            "severity": "super_critical",
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_store_with_empty_summary(self, patch_common, registered_agent):
        """Empty string summary is treated as missing."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": None,
        })

        data = parse_result(result)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_search_limit_respected(self, patch_common):
        """Custom limit parameter is respected in search."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_search_knowledge_graph

        mock_graph.query = AsyncMock(return_value=[])

        result = await handle_search_knowledge_graph({
            "limit": 5,
        })

        mock_graph.query.assert_awaited_once()
        call_kwargs = mock_graph.query.call_args
        assert call_kwargs[1]["limit"] == 5

    @pytest.mark.asyncio
    async def test_leave_note_sets_type_to_note(self, patch_common, registered_agent):
        """Leave note always creates discoveries with type='note'."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_leave_note

        result = await handle_leave_note({
            "agent_id": registered_agent,
            "summary": "A quick note",
        })

        data = parse_result(result)
        assert data["success"] is True
        call_args = mock_graph.add_discovery.call_args
        discovery = call_args[0][0]
        assert discovery.type == "note"
        assert discovery.severity == "low"

    @pytest.mark.asyncio
    async def test_store_no_auto_link(self, patch_common, registered_agent):
        """Store with auto_link_related=False skips similarity search."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_store_knowledge_graph

        result = await handle_store_knowledge_graph({
            "agent_id": registered_agent,
            "summary": "No linking please",
            "auto_link_related": False,
        })

        data = parse_result(result)
        assert data["success"] is True
        mock_graph.find_similar.assert_not_awaited()
        assert "related_discoveries" not in data

    @pytest.mark.asyncio
    async def test_get_details_response_chain_error(self, patch_common):
        """Response chain traversal error is non-fatal."""
        mock_mcp_server, mock_graph = patch_common
        from src.mcp_handlers.knowledge_graph import handle_get_discovery_details

        disc = make_discovery(id="2026-01-01T00:00:00.000000", details="Details")
        mock_graph.get_discovery = AsyncMock(return_value=disc)
        mock_graph.get_response_chain = AsyncMock(side_effect=Exception("Chain broken"))

        result = await handle_get_discovery_details({
            "discovery_id": "2026-01-01T00:00:00.000000",
            "include_response_chain": True,
        })

        data = parse_result(result)
        assert data["success"] is True  # Main request succeeded
        assert "response_chain" in data
        assert "error" in data["response_chain"]  # Chain error is noted
