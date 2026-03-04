"""Tests for gateway.client — GovernanceMCPClient with circuit breaker."""

import json
import time
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from src.gateway.client import GovernanceMCPClient, MCPError, CircuitOpenError


# -- parse_mcp_result --

class TestParseMCPResult:
    def test_unwrap_content_text(self):
        """MCP wraps results in content[0]["text"] as JSON string."""
        raw = {
            "result": {
                "content": [{"type": "text", "text": '{"action": "proceed", "coherence": 0.5}'}]
            }
        }
        result = GovernanceMCPClient.parse_mcp_result(raw)
        assert result == {"action": "proceed", "coherence": 0.5}

    def test_unwrap_non_json_text(self):
        """Non-JSON text content returned as-is."""
        raw = {"result": {"content": [{"type": "text", "text": "plain text response"}]}}
        result = GovernanceMCPClient.parse_mcp_result(raw)
        assert result == "plain text response"

    def test_error_raises(self):
        """MCP errors raise MCPError."""
        raw = {"error": {"code": -32600, "message": "Invalid request"}}
        with pytest.raises(MCPError, match="Invalid request"):
            GovernanceMCPClient.parse_mcp_result(raw)

    def test_plain_result_passthrough(self):
        """Result without content wrapper passes through."""
        raw = {"result": {"action": "proceed"}}
        result = GovernanceMCPClient.parse_mcp_result(raw)
        assert result == {"action": "proceed"}

    def test_empty_content_list(self):
        """Empty content list returns result as-is."""
        raw = {"result": {"content": []}}
        result = GovernanceMCPClient.parse_mcp_result(raw)
        assert result == {"content": []}

    def test_no_result_key(self):
        """If no result or error key, returns input as-is."""
        raw = {"action": "proceed"}
        result = GovernanceMCPClient.parse_mcp_result(raw)
        assert result == {"action": "proceed"}


# -- Circuit breaker --

class TestCircuitBreaker:
    def test_starts_closed(self):
        client = GovernanceMCPClient()
        assert not client._is_circuit_open()

    def test_opens_after_threshold(self):
        client = GovernanceMCPClient()
        client._record_failure()
        assert not client._is_circuit_open()
        client._record_failure()  # Threshold = 2
        assert client._is_circuit_open()

    def test_resets_on_success(self):
        client = GovernanceMCPClient()
        client._record_failure()
        client._record_failure()
        assert client._is_circuit_open()
        client._record_success()
        assert not client._is_circuit_open()
        assert client._circuit_failures == 0

    def test_exponential_backoff(self):
        client = GovernanceMCPClient()
        # First open: 15s
        client._record_failure()
        client._record_failure()
        assert client._circuit_current_backoff == 30.0  # Doubled for next time

        # Reset and fail again
        client._record_success()
        client._record_failure()
        client._record_failure()
        # Backoff was reset to base on success
        assert client._circuit_current_backoff == 30.0

    def test_backoff_capped(self):
        client = GovernanceMCPClient()
        # Force backoff to max
        client._circuit_current_backoff = 120.0
        client._record_failure()
        client._record_failure()
        assert client._circuit_current_backoff == 120.0  # Capped


# -- call_tool --

class TestCallTool:
    @pytest.mark.asyncio
    async def test_successful_call(self):
        client = GovernanceMCPClient()
        mock_response = httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": '{"action": "proceed"}'}]
                },
            },
            request=httpx.Request("POST", "http://localhost:8767/mcp/"),
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            result = await client.call_tool("get_governance_metrics", {"agent_id": "test"})
            assert result == {"action": "proceed"}

    @pytest.mark.asyncio
    async def test_circuit_open_raises(self):
        client = GovernanceMCPClient()
        client._circuit_failures = 2
        client._circuit_open_until = time.monotonic() + 100

        with pytest.raises(CircuitOpenError):
            await client.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_connection_error_records_failure(self):
        client = GovernanceMCPClient()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            with pytest.raises(ConnectionError):
                await client.call_tool("test_tool")

            assert client._circuit_failures == 1

    @pytest.mark.asyncio
    async def test_sse_response_parsed(self):
        client = GovernanceMCPClient()
        sse_text = 'data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"{\\"ok\\": true}"}]}}\n\n'
        mock_response = httpx.Response(
            200,
            text=sse_text,
            headers={"content-type": "text/event-stream"},
            request=httpx.Request("POST", "http://localhost:8767/mcp/"),
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            result = await client.call_tool("test_tool")
            assert result == {"ok": True}


# -- parse_sse --

class TestParseSSE:
    def test_valid_sse(self):
        text = 'data: {"result": "ok"}\n\n'
        assert GovernanceMCPClient._parse_sse(text) == {"result": "ok"}

    def test_no_data_lines(self):
        assert GovernanceMCPClient._parse_sse("event: ping\n\n") is None

    def test_invalid_json(self):
        assert GovernanceMCPClient._parse_sse("data: not json\n\n") is None
