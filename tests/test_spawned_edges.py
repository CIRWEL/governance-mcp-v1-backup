"""Tests for SPAWNED edge creation in AGE graph."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.age_queries import create_spawned_edge, create_agent_node


class TestCreateSpawnedEdgeCypher:
    """Test query builder output for SPAWNED edges."""

    def test_basic_spawned_edge(self):
        """SPAWNED edge with no optional props."""
        cypher, params = create_spawned_edge("parent-123", "child-456")
        assert "MATCH (parent:Agent" in cypher
        assert "MATCH (child:Agent" in cypher
        assert "MERGE (parent)-[r:SPAWNED" in cypher
        assert params["parent_id"] == "parent-123"
        assert params["child_id"] == "child-456"

    def test_spawned_edge_with_reason(self):
        """SPAWNED edge includes spawn_reason property."""
        cypher, params = create_spawned_edge(
            "parent-123", "child-456", spawn_reason="thread_fork"
        )
        assert "spawn_reason" in cypher
        assert params["spawn_reason"] == "thread_fork"

    def test_spawned_edge_with_timestamp(self):
        """SPAWNED edge includes at property."""
        ts = datetime(2026, 3, 6, 12, 0, 0)
        cypher, params = create_spawned_edge(
            "parent-123", "child-456", at=ts
        )
        assert "at" in cypher
        assert params["at"] == "2026-03-06T12:00:00"

    def test_spawned_edge_with_all_props(self):
        """SPAWNED edge with both reason and timestamp."""
        ts = datetime(2026, 3, 6, 12, 0, 0)
        cypher, params = create_spawned_edge(
            "parent-123", "child-456",
            spawn_reason="escalation", at=ts
        )
        assert "spawn_reason" in cypher
        assert "at" in cypher
        assert params["spawn_reason"] == "escalation"
        assert params["at"] == "2026-03-06T12:00:00"

    def test_spawned_edge_returns_r(self):
        """Query returns the edge."""
        cypher, _ = create_spawned_edge("p", "c")
        assert "RETURN r" in cypher


class TestSpawnedEdgeBgTask:
    """Test the background task helper handles errors gracefully."""

    @pytest.mark.asyncio
    async def test_spawned_edge_bg_task_success(self):
        """Background task calls graph_query three times (2 nodes + 1 edge)."""
        mock_db = MagicMock()
        mock_db.graph_query = AsyncMock(return_value=[])

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            from src.mcp_handlers.identity_v2 import _create_spawned_edge_bg
            await _create_spawned_edge_bg("child-1", "parent-1", "test_reason")

        assert mock_db.graph_query.call_count == 3

    @pytest.mark.asyncio
    async def test_spawned_edge_bg_task_handles_errors(self):
        """Background task swallows exceptions (non-fatal)."""
        mock_db = MagicMock()
        mock_db.graph_query = AsyncMock(side_effect=Exception("DB unavailable"))

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            from src.mcp_handlers.identity_v2 import _create_spawned_edge_bg
            # Should not raise
            await _create_spawned_edge_bg("child-1", "parent-1", None)

    @pytest.mark.asyncio
    async def test_spawned_edge_bg_task_no_reason(self):
        """Background task works without spawn_reason."""
        mock_db = MagicMock()
        mock_db.graph_query = AsyncMock(return_value=[])

        with patch("src.mcp_handlers.identity_v2.get_db", return_value=mock_db):
            from src.mcp_handlers.identity_v2 import _create_spawned_edge_bg
            await _create_spawned_edge_bg("child-1", "parent-1", None)

        # Still creates 2 nodes + 1 edge
        assert mock_db.graph_query.call_count == 3
