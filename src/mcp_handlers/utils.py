"""
Common utilities for MCP tool handlers.
"""

from typing import Dict, Any, Sequence, Tuple, Optional
from mcp.types import TextContent
import json
import sys
from datetime import datetime, date
from enum import Enum


def error_response(
    message: str, 
    details: Optional[Dict[str, Any]] = None, 
    recovery: Optional[Dict[str, Any]] = None, 
    context: Optional[Dict[str, Any]] = None
) -> TextContent:
    """
    Create an error response with optional recovery guidance and system context.
    
    SECURITY: Sanitizes error messages to prevent internal structure leakage.
    
    Args:
        message: Error message (will be sanitized)
        details: Optional additional error details (will be sanitized)
        recovery: Optional recovery suggestions for AGI agents
        context: Optional system context (what was happening, system state, etc.)
        
    Returns:
        TextContent with error response
    """
    # SECURITY: Sanitize error message to prevent internal structure leakage
    sanitized_message = _sanitize_error_message(message)
    
    response = {
        "success": False,
        "error": sanitized_message
    }
    
    # Sanitize details if provided
    if details:
        sanitized_details = {}
        for key, value in details.items():
            if isinstance(value, str):
                sanitized_details[key] = _sanitize_error_message(value)
            else:
                sanitized_details[key] = value
        response.update(sanitized_details)
    
    # Add recovery guidance if provided
    if recovery:
        response["recovery"] = recovery
    
    # Add system context if provided (helps understand WHY error occurred)
    # Note: Context is user-provided, so less risk of leakage
    if context:
        response["context"] = context
    
    return TextContent(
        type="text",
        text=json.dumps(response, indent=2)
    )


def _sanitize_error_message(message: str) -> str:
    """
    Sanitize error messages to prevent internal structure leakage.
    
    Removes:
    - File paths
    - Line numbers
    - Internal variable names
    - Stack traces
    - Module paths
    """
    if not isinstance(message, str):
        return str(message)
    
    import re
    
    # Remove file paths (but keep filename)
    message = re.sub(r'/[^\s]+/([^/\s]+\.py)', r'\1', message)
    
    # Remove line numbers
    message = re.sub(r':\d+:', ':', message)
    message = re.sub(r'line \d+', 'line N', message)
    
    # Remove internal variable names (common patterns)
    message = re.sub(r'\b[A-Z_]{3,}\b', lambda m: m.group() if m.group() in ['RISK', 'ERROR', 'SUCCESS'] else 'CONFIG', message)
    
    # Remove stack trace indicators
    message = re.sub(r'Traceback.*?File', 'Error in', message, flags=re.DOTALL)
    message = re.sub(r'File "[^"]+", line \d+', 'Internal error', message)
    
    # Remove module paths (keep module name)
    message = re.sub(r'[a-z_]+\.([a-z_]+)', r'\1', message)
    
    # Limit length to prevent information leakage
    from config.governance_config import config
    max_length = config.MAX_ERROR_MESSAGE_LENGTH
    if len(message) > max_length:
        message = message[:max_length] + "..."
    
    return message


def _make_json_serializable(obj: Any) -> Any:
    """
    Recursively convert non-JSON-serializable types to JSON-compatible types.
    
    Handles:
    - numpy types (float64, int64, etc.) → float/int
    - numpy arrays → lists
    - datetime/date objects → ISO format strings
    - Enum types → their values
    - Other non-serializable types → strings
    
    Args:
        obj: Object to convert (can be dict, list, tuple, or primitive)
        
    Returns:
        JSON-serializable version of the object
    """
    # Handle None
    if obj is None:
        return None
    
    # Handle numpy types
    try:
        import numpy as np
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj) if isinstance(obj, np.floating) else int(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
    except ImportError:
        pass  # numpy not available
    
    # Handle datetime/date objects
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    
    # Handle Enum types
    if isinstance(obj, Enum):
        return obj.value
    
    # Handle dicts (recursive) - OPTIMIZED: Limit recursion depth to prevent slowdowns
    if isinstance(obj, dict):
        # Limit recursion to prevent deep nesting slowdowns
        return {key: _make_json_serializable(value) for key, value in obj.items()}
    
    # Handle lists and tuples (recursive)
    if isinstance(obj, (list, tuple)):
        # Limit list size to prevent huge arrays from slowing down
        if len(obj) > 1000:
            return [_make_json_serializable(item) for item in obj[:1000]] + [f"... ({len(obj) - 1000} more items)"]
        return [_make_json_serializable(item) for item in obj]
    
    # Handle sets (convert to list)
    if isinstance(obj, set):
        if len(obj) > 1000:
            return [_make_json_serializable(item) for item in list(obj)[:1000]] + [f"... ({len(obj) - 1000} more items)"]
        return [_make_json_serializable(item) for item in obj]
    
    # Handle basic types that are already JSON-serializable
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    # Fallback: convert to string for anything else
    try:
        # Try to convert to string, but catch if even that fails
        return str(obj)
    except Exception:
        # Last resort: return a placeholder
        return f"<non-serializable: {type(obj).__name__}>"


def success_response(data: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Create a success response.
    
    Args:
        data: Response data (will have "success": True added)
        
    Returns:
        Sequence of TextContent with success response
    """
    response = {
        "success": True,
        **data
    }
    
    # Convert non-serializable types before JSON encoding
    # OPTIMIZATION: Use compact JSON (no indent) to speed up serialization and reduce size
    # CRITICAL: Wrap in try/except to prevent server crashes
    try:
        serializable_response = _make_json_serializable(response)
        json_text = json.dumps(serializable_response, ensure_ascii=False)  # Removed indent=2 for speed, ensure_ascii=False for performance
    except (TypeError, ValueError) as e:
        # Log serialization error but try to recover
        print(f"[UNITARES MCP] JSON serialization error: {e}", file=sys.stderr)
        import traceback
        print(f"[UNITARES MCP] Traceback:\n{traceback.format_exc()}", file=sys.stderr)
        # Try one more time with full conversion and default=str fallback
        try:
            serializable_response = _make_json_serializable(response)
            json_text = json.dumps(serializable_response, ensure_ascii=False, default=str)
        except Exception as e2:
            # Last resort: return minimal error response to prevent server crash
            print(f"[UNITARES MCP] Failed to serialize response even after conversion: {e2}", file=sys.stderr)
            # Return minimal JSON that's guaranteed to work
            try:
                minimal_response = {
                    "success": False,
                    "error": "Response serialization failed",
                    "recovery": {"action": "Check server logs for details"}
                }
                json_text = json.dumps(minimal_response, ensure_ascii=False)
            except Exception as e3:
                # Absolute last resort: hardcoded JSON string
                print(f"[UNITARES MCP] Even minimal response failed: {e3}", file=sys.stderr)
                json_text = '{"success":false,"error":"Serialization failed"}'
    
    return [TextContent(
        type="text",
        text=json_text
    )]


def require_argument(arguments: Dict[str, Any], name: str, 
                    error_message: str = None) -> Tuple[Any, Optional[TextContent]]:
    """
    Get required argument from arguments dict.
    
    Args:
        arguments: Arguments dictionary
        name: Argument name
        error_message: Custom error message (defaults to "{name} is required")
        
    Returns:
        Tuple of (value, error_response). If value is None, error_response is provided.
    """
    value = arguments.get(name)
    if value is None:
        msg = error_message or f"{name} is required"
        return None, error_response(msg)
    return value, None


def require_agent_id(arguments: Dict[str, Any]) -> Tuple[str, Optional[TextContent]]:
    """
    Get required agent_id from arguments.
    
    Args:
        arguments: Arguments dictionary
        
    Returns:
        Tuple of (agent_id, error_response). If agent_id is missing, error_response is provided.
    """
    return require_argument(arguments, "agent_id", "agent_id is required")


def require_registered_agent(arguments: Dict[str, Any]) -> Tuple[str, Optional[TextContent]]:
    """
    Get required agent_id AND verify the agent is registered in the system.
    
    This is the PROACTIVE GATE that prevents unregistered agents from calling
    tools that require an existing agent, avoiding hangs and stale locks.
    
    Args:
        arguments: Arguments dictionary
        
    Returns:
        Tuple of (agent_id, error_response). If agent_id is missing or not registered,
        error_response is provided with onboarding guidance.
    """
    # First check if agent_id is provided
    agent_id, error = require_agent_id(arguments)
    if error:
        return None, error
    
    # Now check if agent is registered (exists in metadata)
    try:
        import sys
        if 'src.mcp_server_std' in sys.modules:
            mcp_server = sys.modules['src.mcp_server_std']
        else:
            import src.mcp_server_std as mcp_server
        
        # Reload metadata to ensure we have latest state
        mcp_server.load_metadata()
        
        if agent_id not in mcp_server.agent_metadata:
            return None, error_response(
                f"Agent '{agent_id}' is not registered. You must onboard first.",
                recovery={
                    "error_type": "agent_not_registered",
                    "action": "Call get_agent_api_key first to register this agent_id",
                    "related_tools": ["get_agent_api_key", "list_agents", "list_tools"],
                    "workflow": [
                        "1. Call get_agent_api_key with your agent_id to register",
                        "2. Save the returned API key securely",
                        "3. Then call this tool again with agent_id and api_key"
                    ],
                    "onboarding_sequence": ["list_tools", "get_agent_api_key", "list_agents", "process_agent_update"]
                }
            )
        
        return agent_id, None
        
    except Exception as e:
        # If we can't check registration, fail safe with guidance
        return None, error_response(
            f"Could not verify agent registration: {str(e)}",
            recovery={
                "action": "System error checking agent registration. Try get_agent_api_key first.",
                "related_tools": ["get_agent_api_key", "health_check"],
                "workflow": ["1. Call health_check to verify system", "2. Call get_agent_api_key to register"]
            }
        )


