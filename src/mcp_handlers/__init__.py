"""
MCP Tool Handlers

Handler registry pattern for elegant tool dispatch.
Each tool handler is a separate function for better testability and maintainability.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
import json

# Import all handlers
from .core import (
    handle_process_agent_update,
    handle_get_governance_metrics,
    handle_simulate_update,
)
from .config import (
    handle_get_thresholds,
    handle_set_thresholds,
)
from .observability import (
    handle_observe_agent,
    handle_compare_agents,
    handle_detect_anomalies,
    handle_aggregate_metrics,
)
from .lifecycle import (
    handle_list_agents,
    handle_get_agent_metadata,
    handle_update_agent_metadata,
    handle_archive_agent,
    handle_delete_agent,
    handle_archive_old_test_agents,
    handle_get_agent_api_key,
    handle_mark_response_complete,
    handle_direct_resume_if_safe,
)
from .export import (
    handle_get_system_history,
    handle_export_to_file,
)
from .admin import (
    handle_reset_monitor,
    handle_get_server_info,
    handle_health_check,
    handle_check_calibration,
    handle_update_calibration_ground_truth,
    handle_get_telemetry_metrics,
    handle_list_tools,
    handle_cleanup_stale_locks,
    handle_get_workspace_health,
    handle_get_tool_usage_stats,
)
# REMOVED: Knowledge layer handlers (archived November 28, 2025)
# See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
# from .knowledge import (
#     handle_store_knowledge,
#     handle_retrieve_knowledge,
#     handle_search_knowledge,
#     handle_list_knowledge,
#     handle_update_discovery_status,
#     handle_update_discovery,
#     handle_find_similar_discoveries,
# )
# Knowledge Graph (New - Fast, indexed, transparent)
from .knowledge_graph import (
    handle_store_knowledge_graph,
    handle_search_knowledge_graph,
    handle_get_knowledge_graph,
    handle_list_knowledge_graph,
    handle_update_discovery_status_graph,
    handle_find_similar_discoveries_graph,
)
# Dialectic (Circuit Breaker Recovery) - Enabled after fixing imports
from .dialectic import (
    handle_request_dialectic_review,
    handle_submit_thesis,
    handle_submit_antithesis,
    handle_submit_synthesis,
    handle_get_dialectic_session,
    handle_self_recovery,
    handle_smart_dialectic_review,
)

# Common utilities
from .utils import error_response, success_response


# Import decorator registry (auto-registered tools)
from .decorators import get_tool_registry as get_decorator_registry

# Handler registry (manual + decorator-registered)
# Decorator-registered tools are added automatically, manual entries are for backward compatibility
# NOTE: Most tools are now decorator-registered. Manual entries below are for:
# - Tools that need explicit ordering
# - Backward compatibility during migration
TOOL_HANDLERS: Dict[str, callable] = {
    # Core governance
    # All core tools now use decorators - entries removed as they're auto-registered
    
    # Configuration
    "get_thresholds": handle_get_thresholds,  # Decorator-registered
    "set_thresholds": handle_set_thresholds,  # Decorator-registered
    
    # Observability
    "observe_agent": handle_observe_agent,
    "compare_agents": handle_compare_agents,
    "detect_anomalies": handle_detect_anomalies,
    "aggregate_metrics": handle_aggregate_metrics,
    
    # Lifecycle
    "list_agents": handle_list_agents,  # Decorator-registered
    "get_agent_metadata": handle_get_agent_metadata,
    "update_agent_metadata": handle_update_agent_metadata,
    "archive_agent": handle_archive_agent,
    "delete_agent": handle_delete_agent,
    "archive_old_test_agents": handle_archive_old_test_agents,
    "get_agent_api_key": handle_get_agent_api_key,
    "mark_response_complete": handle_mark_response_complete,
    "direct_resume_if_safe": handle_direct_resume_if_safe,
    
    # Export
    "get_system_history": handle_get_system_history,
    "export_to_file": handle_export_to_file,
    
    # Admin
    "reset_monitor": handle_reset_monitor,
    "get_server_info": handle_get_server_info,
    "health_check": handle_health_check,
    "check_calibration": handle_check_calibration,
    "update_calibration_ground_truth": handle_update_calibration_ground_truth,
    "get_telemetry_metrics": handle_get_telemetry_metrics,
    "list_tools": handle_list_tools,
    "cleanup_stale_locks": handle_cleanup_stale_locks,
    "get_workspace_health": handle_get_workspace_health,
    "get_tool_usage_stats": handle_get_tool_usage_stats,
    
    # Knowledge layer handlers REMOVED (archived November 28, 2025)
    # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
    
    # Knowledge Graph (New - Fast, indexed, transparent)
    "store_knowledge_graph": handle_store_knowledge_graph,
    "search_knowledge_graph": handle_search_knowledge_graph,
    "get_knowledge_graph": handle_get_knowledge_graph,
    "list_knowledge_graph": handle_list_knowledge_graph,
    "update_discovery_status_graph": handle_update_discovery_status_graph,
    "find_similar_discoveries_graph": handle_find_similar_discoveries_graph,

    # Dialectic (Circuit Breaker Recovery) - Enabled
    "request_dialectic_review": handle_request_dialectic_review,
    "submit_thesis": handle_submit_thesis,
    "submit_antithesis": handle_submit_antithesis,
    "submit_synthesis": handle_submit_synthesis,
    "get_dialectic_session": handle_get_dialectic_session,
    "self_recovery": handle_self_recovery,
    "smart_dialectic_review": handle_smart_dialectic_review,
}

# Merge decorator-registered tools into registry (decorators take precedence)
decorator_registry = get_decorator_registry()
for tool_name, handler in decorator_registry.items():
    TOOL_HANDLERS[tool_name] = handler  # Decorator-registered tools override manual entries


async def dispatch_tool(name: str, arguments: Dict[str, Any]) -> Sequence[TextContent] | None:
    """
    Dispatch tool call to appropriate handler with timeout protection and rate limiting.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        
    Returns:
        Sequence of TextContent responses, or None if handler not found (fallback to legacy)
    """
    import asyncio
    from src.rate_limiter import get_rate_limiter
    from collections import defaultdict, deque
    import time
    
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return None  # Signal to fallback to legacy elif chain
    
    # Special rate limiting for expensive read-only tools (like list_agents)
    # These tools bypass general rate limiting but need protection against loops
    # Note: list_agents doesn't have agent_id parameter, so we use global tracking
    # This prevents any agent from looping, but one looping agent won't block others
    expensive_read_only_tools = {'list_agents'}
    if name in expensive_read_only_tools:
        # Use global tracking since list_agents doesn't have agent_id
        # Track by tool name only (prevents global loops)
        if not hasattr(dispatch_tool, '_tool_call_history'):
            dispatch_tool._tool_call_history = defaultdict(lambda: deque())
        
        now = time.time()
        tool_history = dispatch_tool._tool_call_history[name]
        
        # Clean up old calls (keep last 60 seconds)
        cutoff = now - 60
        while tool_history and tool_history[0] < cutoff:
            tool_history.popleft()
        
        # Check for rapid repeated calls (20+ calls in 60 seconds = loop)
        # Higher threshold since this is global (any agent calling)
        if len(tool_history) >= 20:
            return [error_response(
                f"Tool call loop detected: '{name}' called {len(tool_history)} times globally in the last 60 seconds. "
                f"This may indicate a stuck agent. Please wait 30 seconds before retrying.",
                recovery={
                    "action": "Wait 30 seconds before retrying this tool",
                    "related_tools": ["health_check", "get_governance_metrics"],
                    "workflow": "1. Wait 30 seconds 2. Check agent health 3. Retry if needed"
                },
                context={
                    "tool_name": name,
                    "calls_in_last_minute": len(tool_history),
                    "note": "Global rate limit (list_agents doesn't have agent_id parameter)"
                }
            )]
        
        # Record this call
        tool_history.append(now)
    
    # Rate limiting (skip for read-only tools like health_check, get_server_info)
    read_only_tools = {'health_check', 'get_server_info', 'list_tools', 'get_thresholds'}
    if name not in read_only_tools:
        agent_id = arguments.get('agent_id') or 'anonymous'
        rate_limiter = get_rate_limiter()
        allowed, error_msg = rate_limiter.check_rate_limit(agent_id)
        
        if not allowed:
            from .error_helpers import rate_limit_error
            return rate_limit_error(agent_id, rate_limiter.get_stats(agent_id))
    
    # Timeout protection is handled by @mcp_tool decorator
    # Decorators wrap handlers with appropriate timeouts (e.g., 60s for process_agent_update)
    # No need to wrap again here - decorator timeout will be effective
    try:
        # Call handler directly - decorator wrapper handles timeout protection
        result = await handler(arguments)
        # Check if handler returned stub error (not yet extracted)
        # result should be a Sequence[TextContent], but handle edge cases
        if result:
            # Handle both single TextContent and Sequence
            if isinstance(result, (list, tuple)) and len(result) > 0:
                text_content = result[0].text
                if "Handler not yet extracted" in text_content:
                    return None  # Fallback to legacy elif chain
            elif hasattr(result, 'text'):
                # Single TextContent object
                if "Handler not yet extracted" in result.text:
                    return None  # Fallback to legacy elif chain
        return result
    # TimeoutError is now handled by decorator wrapper, but catch here for safety
    except asyncio.TimeoutError:
        # This should rarely happen since decorator handles timeout, but keep for safety
        from .error_helpers import timeout_error
        from src.logging_utils import get_logger
        logger = get_logger(__name__)
        # Try to get actual timeout from decorator if available
        from .decorators import get_tool_timeout
        actual_timeout = get_tool_timeout(name)
        logger.warning(f"Tool '{name}' timed out after {actual_timeout}s (decorator timeout)")
        return timeout_error(name, actual_timeout)
    except Exception as e:
        from .error_helpers import system_error
        import traceback
        from src.logging_utils import get_logger
        logger = get_logger(__name__)
        # SECURITY: Don't expose full traceback to clients - log internally only
        logger.error(f"Tool '{name}' error: {e}", exc_info=True)
        return system_error(name, e)

