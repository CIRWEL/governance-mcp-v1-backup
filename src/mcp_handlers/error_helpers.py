"""
Enhanced error handling utilities for MCP handlers.

Standardizes error responses with recovery guidance and context.
"""

from typing import Dict, Any, Optional, Sequence
from mcp.types import TextContent
from .utils import error_response


# Standard recovery patterns for common error types
RECOVERY_PATTERNS = {
    "agent_not_found": {
        "action": "Call get_agent_api_key first to register this agent_id",
        "related_tools": ["get_agent_api_key", "list_agents"],
        "workflow": [
            "1. Call get_agent_api_key with your agent_id to register",
            "2. Save the returned API key securely",
            "3. Then call this tool again with agent_id and api_key"
        ]
    },
    "authentication_failed": {
        "action": "Verify your API key matches your agent_id",
        "related_tools": ["get_agent_api_key"],
        "workflow": [
            "1. Get correct API key for your agent_id",
            "2. Retry with correct key"
        ]
    },
    "rate_limit_exceeded": {
        "action": "Wait a few seconds before retrying",
        "related_tools": ["health_check"],
        "workflow": [
            "1. Wait 10-30 seconds",
            "2. Retry request",
            "3. If persistent, check system health"
        ]
    },
    "timeout": {
        "action": "This may indicate a blocking operation or system overload. Try again with simpler parameters.",
        "related_tools": ["health_check", "get_server_info"],
        "workflow": [
            "1. Wait a few seconds and retry",
            "2. Check system health with health_check",
            "3. Simplify request parameters",
            "4. Check for system overload"
        ]
    },
    "invalid_parameters": {
        "action": "Check tool parameters and try again",
        "related_tools": ["list_tools", "health_check"],
        "workflow": [
            "1. Verify tool parameters match schema",
            "2. Check tool description with list_tools",
            "3. Retry with correct parameters"
        ]
    },
    "system_error": {
        "action": "Check system health and retry",
        "related_tools": ["health_check", "get_server_info"],
        "workflow": [
            "1. Check system health",
            "2. Wait a few seconds",
            "3. Retry request"
        ]
    }
}


def agent_not_found_error(agent_id: str, context: Optional[Dict[str, Any]] = None) -> Sequence[TextContent]:
    """Standard error for agent not found"""
    return [error_response(
        f"Agent '{agent_id}' is not registered. You must onboard first.",
        recovery=RECOVERY_PATTERNS["agent_not_found"],
        context=context or {}
    )]


def authentication_error(agent_id: str, context: Optional[Dict[str, Any]] = None) -> Sequence[TextContent]:
    """Standard error for authentication failure"""
    return [error_response(
        f"Authentication failed for agent '{agent_id}'. Invalid API key.",
        recovery=RECOVERY_PATTERNS["authentication_failed"],
        context=context or {}
    )]


def rate_limit_error(agent_id: str, stats: Optional[Dict[str, Any]] = None) -> Sequence[TextContent]:
    """Standard error for rate limit exceeded"""
    return [error_response(
        f"Rate limit exceeded for agent '{agent_id}'",
        recovery=RECOVERY_PATTERNS["rate_limit_exceeded"],
        context={"rate_limit_stats": stats} if stats else {}
    )]


def timeout_error(tool_name: str, timeout: float) -> Sequence[TextContent]:
    """Standard error for timeout"""
    return [error_response(
        f"Tool '{tool_name}' timed out after {timeout} seconds.",
        recovery=RECOVERY_PATTERNS["timeout"],
        context={"tool_name": tool_name, "timeout_seconds": timeout}
    )]


def invalid_parameters_error(tool_name: str, details: Optional[str] = None) -> Sequence[TextContent]:
    """Standard error for invalid parameters"""
    message = f"Invalid parameters for tool '{tool_name}'"
    if details:
        message += f": {details}"
    return [error_response(
        message,
        recovery=RECOVERY_PATTERNS["invalid_parameters"],
        context={"tool_name": tool_name, "details": details}
    )]


def system_error(tool_name: str, error: Exception, context: Optional[Dict[str, Any]] = None) -> Sequence[TextContent]:
    """Standard error for system errors"""
    return [error_response(
        f"System error executing tool '{tool_name}': {str(error)}",
        recovery=RECOVERY_PATTERNS["system_error"],
        context=context or {}
    )]

