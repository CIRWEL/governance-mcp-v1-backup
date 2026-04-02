"""HTTP tool execution helpers.

Provides a narrow direct-call path for core tools whose handlers already accept
plain argument dicts. Everything else falls back to the MCP dispatch pipeline.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, Optional

from src.mcp_handlers.identity.handlers import (
    handle_identity_adapter,
    handle_onboard_v2,
)
from src.mcp_handlers.core import handle_process_agent_update
from src.mcp_handlers.utils import require_agent_id
from src.services.http_dispatch_fallback import execute_http_dispatch_fallback
from src.services.runtime_queries import get_governance_metrics_data, get_health_check_data

ToolHandler = Callable[[Dict[str, Any]], Awaitable[Any]]


def _normalize_direct_http_result(result: Any) -> Any:
    """Convert direct-handler MCP text output into plain data for HTTP callers."""
    if isinstance(result, (list, tuple)) and len(result) == 1 and hasattr(result[0], "text"):
        try:
            return json.loads(result[0].text)
        except (json.JSONDecodeError, TypeError):
            return result
    return result

async def _execute_http_get_governance_metrics(arguments: Dict[str, Any]) -> Any:
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    return await get_governance_metrics_data(agent_id, arguments)


async def _execute_http_health_check(arguments: Dict[str, Any]) -> Any:
    return await get_health_check_data(arguments)


_DIRECT_HTTP_TOOL_HANDLERS: Dict[str, ToolHandler] = {
    "get_governance_metrics": _execute_http_get_governance_metrics,
    "health_check": _execute_http_health_check,
    "identity": handle_identity_adapter,
    "onboard": handle_onboard_v2,
    "process_agent_update": handle_process_agent_update,
}


def get_direct_http_tool_handler(tool_name: str) -> Optional[ToolHandler]:
    """Return a direct handler for HTTP-safe core tools, if any."""
    return _DIRECT_HTTP_TOOL_HANDLERS.get(tool_name)


async def execute_http_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool for the HTTP API.

    Core governance tools use direct handlers so HTTP does not always depend on
    the full MCP dispatch path. All other tools use an HTTP-specific fallback
    that skips identity-resolution middleware because HTTP already set context.
    """
    handler = get_direct_http_tool_handler(tool_name)
    if handler is not None:
        result = await handler(arguments)
        return _normalize_direct_http_result(result)
    return await execute_http_dispatch_fallback(tool_name, arguments)
