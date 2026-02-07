"""
HTTP endpoint tests using Starlette TestClient.

Tests the HTTP layer contract (JSON request/response, headers, error handling)
using a minimal test ASGI app that mirrors mcp_server.py endpoints.
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.http_test_app import create_test_app


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_dispatch():
    """Create a mock dispatch function."""
    from mcp.types import TextContent
    dispatch = AsyncMock()
    dispatch.return_value = [
        TextContent(type="text", text=json.dumps({"success": True, "tool": "test"}))
    ]
    return dispatch


@pytest.fixture
def mock_list_tools():
    """Create a mock list_tools function."""
    return lambda: [
        {"name": "health_check", "description": "Check health"},
        {"name": "list_tools", "description": "List tools"},
    ]


@pytest.fixture
def client(mock_dispatch, mock_list_tools):
    """Create a Starlette TestClient with mocked dispatch."""
    app = create_test_app(mock_dispatch, mock_list_tools)
    return TestClient(app)


# ============================================================================
# Health Endpoint
# ============================================================================

class TestHealthEndpoint:

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"


# ============================================================================
# List Tools Endpoint
# ============================================================================

class TestListToolsEndpoint:

    def test_list_tools_returns_200(self, client):
        response = client.get("/v1/tools/list")
        assert response.status_code == 200

    def test_list_tools_returns_array(self, client):
        response = client.get("/v1/tools/list")
        data = response.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) == 2

    def test_list_tools_has_tool_names(self, client):
        response = client.get("/v1/tools/list")
        tools = response.json()["tools"]
        names = [t["name"] for t in tools]
        assert "health_check" in names


# ============================================================================
# Call Tool Endpoint
# ============================================================================

class TestCallToolEndpoint:

    def test_call_tool_returns_200(self, client, mock_dispatch):
        response = client.post("/v1/tools/call", json={
            "tool_name": "health_check",
            "arguments": {}
        })
        assert response.status_code == 200
        mock_dispatch.assert_called_once()

    def test_call_tool_dispatches_correct_name(self, client, mock_dispatch):
        client.post("/v1/tools/call", json={
            "tool_name": "process_agent_update",
            "arguments": {"confidence": 0.8}
        })
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "process_agent_update"

    def test_call_tool_passes_arguments(self, client, mock_dispatch):
        client.post("/v1/tools/call", json={
            "tool_name": "test_tool",
            "arguments": {"key": "value", "count": 42}
        })
        call_args = mock_dispatch.call_args
        assert call_args[0][1]["key"] == "value"
        assert call_args[0][1]["count"] == 42

    def test_call_tool_accepts_name_field(self, client, mock_dispatch):
        """Should accept 'name' as alternative to 'tool_name'."""
        client.post("/v1/tools/call", json={
            "name": "alt_tool",
            "arguments": {}
        })
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "alt_tool"

    def test_missing_tool_name_returns_400(self, client):
        response = client.post("/v1/tools/call", json={
            "arguments": {}
        })
        assert response.status_code == 400
        data = response.json()
        assert data["error"] is True

    def test_invalid_json_returns_400(self, client):
        response = client.post(
            "/v1/tools/call",
            content=b"not valid json {{{",
            headers={"content-type": "application/json"}
        )
        assert response.status_code == 400

    def test_session_header_propagated(self, client, mock_dispatch):
        """X-Session-ID header should be injected into arguments."""
        client.post(
            "/v1/tools/call",
            json={"tool_name": "test_tool", "arguments": {}},
            headers={"x-session-id": "my-session-123"}
        )
        call_args = mock_dispatch.call_args
        arguments = call_args[0][1]
        assert arguments.get("client_session_id") == "my-session-123"

    def test_empty_arguments_defaults_to_dict(self, client, mock_dispatch):
        """Missing arguments field should default to empty dict."""
        client.post("/v1/tools/call", json={
            "tool_name": "test_tool"
        })
        call_args = mock_dispatch.call_args
        assert isinstance(call_args[0][1], dict)
