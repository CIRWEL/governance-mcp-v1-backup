# Tool Registration Guide

**For AI agents and developers adding/modifying tools in the governance MCP server.**

## Quick Reference: Adding a New Tool

**Step 1: Define the tool schema** in `src/tool_schemas.py`:
```python
ToolDefinition(
    name="my_new_tool",
    description="What this tool does",
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
        },
        "required": ["param1"]
    }
)
```

**Step 2: Implement the handler** in `src/mcp_handlers/*.py`:
```python
@mcp_tool("my_new_tool", timeout=10.0)
async def handle_my_new_tool(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    # Your implementation
    return success_response({"result": "..."})
```

**Step 3 (optional): Add to session injection list** if it needs `client_session_id`:
In `src/mcp_server.py`, add to `TOOLS_NEEDING_SESSION_INJECTION`:
```python
TOOLS_NEEDING_SESSION_INJECTION = {
    "my_new_tool",  # Add here if tool needs session identity
    ...
}
```

**That's it!** The tool is automatically registered via `auto_register_all_tools()`.

---

## Architecture Overview

### The Three Registration Points

| File | Purpose | When to Edit |
|------|---------|--------------|
| `src/tool_schemas.py` | Tool definitions (name, description, schema) | Always - defines the tool |
| `src/mcp_handlers/*.py` | Handler implementations with `@mcp_tool` | Always - implements the logic |
| `src/mcp_server.py` | HTTP transport registration | **Rarely** - only for server-specific tools |

### Auto-Registration System

The `auto_register_all_tools()` function in `mcp_server.py`:
1. Reads all tool definitions from `tool_schemas.py`
2. **Filters to only tools in the decorator registry** (tools with `register=True`)
3. Creates FastMCP wrappers for each tool
4. Injects `client_session_id` for tools in `TOOLS_NEEDING_SESSION_INJECTION`
5. Registers with `mcp.tool()` decorator

**Important:** A tool must be in BOTH `tool_schemas.py` AND have `@mcp_tool` with `register=True` (default) to be exposed via MCP.

---

## Consolidated Tools (Feb 2026)

To reduce cognitive load, related tools are consolidated into single tools with an `action` parameter:

| Consolidated Tool | Replaces | Example |
|-------------------|----------|---------|
| `pi` | 12 pi_* tools | `pi(action='health')` |
| `observe` | 5 observability tools | `observe(action='anomalies')` |
| `agent` | 5 lifecycle tools | `agent(action='list')` |
| `knowledge` | 9 knowledge graph tools | `knowledge(action='search')` |
| `calibration` | 4 calibration tools | `calibration(action='check')` |
| `dialectic` | 4 dialectic tools | `dialectic(action='list')` |
| `config` | 2 config tools | `config(action='get')` |
| `export` | 2 export tools | `export(action='history')` |

### Creating a Consolidated Tool

1. **Create the consolidated handler** in `src/mcp_handlers/consolidated.py`:
```python
@mcp_tool("my_group", timeout=30.0, description="Unified my_group operations: action1, action2")
async def handle_my_group(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    action = arguments.get("action", "").lower()

    if action == "action1":
        return await handle_individual_tool_1(arguments)
    elif action == "action2":
        return await handle_individual_tool_2(arguments)
    else:
        return error_response(f"Unknown action: {action}", recovery={"valid_actions": ["action1", "action2"]})
```

2. **Mark individual handlers as internal** with `register=False`:
```python
@mcp_tool("individual_tool_1", timeout=10.0, register=False)
async def handle_individual_tool_1(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    # Still works, just not exposed to MCP clients
    ...
```

3. **Add aliases** in `tool_stability.py` for backward compatibility:
```python
"individual_tool_1": ToolAlias(
    old_name="individual_tool_1",
    new_name="my_group",
    reason="consolidated",
    migration_note="Use my_group(action='action1')"
),
```

---

## @mcp_tool Decorator Parameters

```python
@mcp_tool(
    name="tool_name",           # Tool name (defaults to function name without 'handle_')
    timeout=30.0,               # Timeout in seconds
    description="...",          # Tool description (defaults to docstring)
    rate_limit_exempt=False,    # Skip rate limiting
    deprecated=False,           # Mark as deprecated
    hidden=False,               # Hide from list_tools (still callable)
    superseded_by="new_tool",   # What replaced this tool
    register=True               # If False, NOT exposed to MCP clients (Feb 2026)
)
```

### When to use `register=False`

Use `register=False` for handlers that are:
- Called by consolidated tools (e.g., `pi_health` called by `pi(action='health')`)
- Internal utilities not meant for direct use
- Deprecated tools that should only work via alias resolution

**Note:** Tools with `register=False` can still be called via aliases if configured in `tool_stability.py`.

---

## Session Injection

Some tools need the session's `client_session_id` injected automatically.

**When to add a tool to `TOOLS_NEEDING_SESSION_INJECTION`:**
- Tool uses identity/authentication
- Tool stores data associated with an agent
- Tool needs to know "who is calling"

---

## Tool Tiers (for list_tools filtering)

Tools are organized into tiers in `src/tool_modes.py`:

| Tier | Purpose | Example Tools |
|------|---------|---------------|
| `essential` | Core workflow (~10 tools) | onboard, identity, process_agent_update |
| `common` | Regular use (~20 tools) | observe, agent, knowledge |
| `advanced` | Rarely used (~15 tools) | cleanup_stale_locks, reset_monitor |

**When adding a new tool, add it to the appropriate tier.**

---

## Tool Aliases (Backwards Compatibility)

When renaming/consolidating tools, add aliases in `src/mcp_handlers/tool_stability.py`:

```python
_TOOL_ALIASES = {
    "old_tool_name": ToolAlias(
        old_name="old_tool_name",
        new_name="new_tool_name",
        reason="consolidated",  # or "renamed", "deprecated"
        migration_note="Use new_tool_name(action='...') instead"
    ),
}
```

Aliases are resolved at dispatch time, so old tool names continue to work.

---

## Common Mistakes

### 1. Tool not showing up in MCP clients
**Cause:** Tool in `tool_schemas.py` but handler has `register=False` or missing `@mcp_tool`.
**Fix:** Ensure handler has `@mcp_tool` with `register=True` (default).

### 2. Consolidated tool's sub-handler not working
**Cause:** Handler function not imported in `consolidated.py`.
**Fix:** Add import and route in the consolidated handler's action dispatch.

### 3. Old tool name not resolving
**Cause:** Missing alias in `tool_stability.py`.
**Fix:** Add alias mapping old name to new consolidated tool.

### 4. Session identity not working
**Cause:** Tool not in `TOOLS_NEEDING_SESSION_INJECTION`.
**Fix:** Add tool name to the set in `mcp_server.py`.

---

## Verification Commands

```bash
# Check registered tools count
curl -s -X POST "http://localhost:8767/v1/tools/call" \
  -H "Content-Type: application/json" \
  -d '{"name": "list_tools", "arguments": {"lite": false}}' | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Total tools: {len(d.get(\"result\",{}).get(\"tools\",[]))}')"

# Check server logs for auto-registration count
grep "AUTO_REGISTER" /Users/cirwel/projects/governance-mcp-v1/data/logs/mcp_server_error.log | tail -1

# Verify specific tool exists
curl -s -X POST "http://localhost:8767/v1/tools/call" \
  -H "Content-Type: application/json" \
  -d '{"name": "describe_tool", "arguments": {"tool_name": "my_new_tool"}}'
```

---

## Summary

| Task | Files to Edit |
|------|---------------|
| Add new standalone tool | `tool_schemas.py` + `mcp_handlers/*.py` |
| Add to consolidated tool | `consolidated.py` + set `register=False` on individual handler |
| Tool needs session | + `TOOLS_NEEDING_SESSION_INJECTION` in `mcp_server.py` |
| Rename/deprecate tool | `tool_stability.py` (add alias) |
| Categorize for list_tools | `tool_modes.py` (add to tier) |

---

**Last Updated:** 2026-02-04 (Added consolidated tools, register=False parameter)
