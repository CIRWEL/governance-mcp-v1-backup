# Migration Example: Using New MCP Utilities

**Purpose:** Show how to migrate handlers to use new decorators and error helpers

---

## Example Handler Migration

### Before (Old Pattern)

```python
# In handler file (e.g., core.py)
async def handle_get_governance_metrics(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle get_governance_metrics tool"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    # ... handler logic ...
    
    return success_response(metrics)

# In __init__.py - Manual registration
TOOL_HANDLERS = {
    "get_governance_metrics": handle_get_governance_metrics,
    ...
}

# In dispatch_tool - Manual timeout wrapping
try:
    result = await asyncio.wait_for(
        handler(arguments),
        timeout=30.0
    )
except asyncio.TimeoutError:
    return [error_response("Timeout", recovery={...})]
```

### After (New Pattern)

```python
# In handler file (e.g., core.py)
from .decorators import mcp_tool
from .error_helpers import agent_not_found_error

@mcp_tool("get_governance_metrics", timeout=30.0)
async def handle_get_governance_metrics(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get current governance state without updating state"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    # ... handler logic ...
    
    return success_response(metrics)

# In __init__.py - Auto-registered via decorator
# No manual registration needed! Tool is auto-registered.

# In dispatch_tool - Timeout handled automatically by decorator
# No manual timeout wrapping needed!
```

---

## Error Helper Usage

### Before
```python
if agent_id not in mcp_server.agent_metadata:
    return [error_response(
        f"Agent '{agent_id}' is not registered.",
        recovery={
            "action": "Call get_agent_api_key first",
            "related_tools": ["get_agent_api_key", "list_agents"],
            "workflow": ["1. Call get_agent_api_key", "2. Retry"]
        },
        context={}
    )]
```

### After
```python
from .error_helpers import agent_not_found_error

if agent_id not in mcp_server.agent_metadata:
    return agent_not_found_error(agent_id)
```

---

## Benefits

1. **Less Boilerplate:** Error handling reduced from ~10 lines to 1 line
2. **Auto-Registration:** No manual dict entries
3. **Auto-Timeout:** No manual timeout wrapping
4. **Consistency:** Standard error formats and recovery patterns
5. **Maintainability:** Easier to add new tools and update patterns

---

## Migration Strategy

**Gradual Migration:**
1. Start using error_helpers in new handlers
2. Migrate existing handlers one-by-one
3. Add decorators to new handlers
4. Gradually migrate existing handlers to decorators
5. Eventually remove manual `TOOL_HANDLERS` dict

**No Breaking Changes:**
- Old pattern still works
- Can mix old and new patterns during migration
- No need to migrate everything at once

---

## Available Error Helpers

- `agent_not_found_error(agent_id)` - Agent not registered
- `authentication_error(agent_id)` - Invalid API key
- `rate_limit_error(agent_id, stats)` - Rate limit exceeded
- `timeout_error(tool_name, timeout)` - Tool timeout
- `invalid_parameters_error(tool_name, details)` - Invalid params
- `system_error(tool_name, error)` - System errors

---

## Decorator Options

```python
@mcp_tool(
    name="tool_name",           # Optional (defaults to function name)
    timeout=30.0,               # Timeout in seconds
    description="Tool desc",    # Optional (defaults to docstring)
    rate_limit_exempt=False     # Skip rate limiting
)
async def handle_tool_name(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    ...
```

