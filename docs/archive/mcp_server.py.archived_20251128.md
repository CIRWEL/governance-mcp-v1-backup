# mcp_server.py - Archived November 28, 2025

**Status:** Archived (replaced by `mcp_server_compat.py`)

---

## Why Archived

**Old v1.0 stub server** (352 lines) replaced by compatibility wrapper that uses full v2.0 handlers.

**Replaced by:** `src/mcp_server_compat.py`
- Provides same JSON-RPC interface
- But calls full v2.0 handlers (44+ tools vs 4)
- Gives CLI users full experience

---

## History

**Created:** Early version (v1.0)
- Simple JSON-RPC wrapper
- Only 4 tools: process_agent_update, get_governance_metrics, get_system_history, reset_monitor
- Used by CLI bridge and demo

**Superseded by:** `mcp_server_std.py` (v2.0)
- Full MCP SDK implementation
- 44+ tools
- Self-monitoring context
- Knowledge graph integration

**Replaced by:** `mcp_server_compat.py` (November 28, 2025)
- Compatibility wrapper
- Same interface as old server
- But uses v2.0 handlers internally

---

## Migration

**Files updated:**
- ✅ `scripts/claude_code_bridge.py` - Now uses `mcp_server_compat`
- ✅ `demos/demo_complete_system.py` - Now uses `mcp_server_compat`

**No active code uses this file anymore.**

---

## Why Keep Archived

**Preserved for:**
1. Historical reference - shows evolution from v1.0 to v2.0
2. Understanding the compatibility wrapper design
3. Git history preservation

**Do not use in new code** - use `mcp_server_compat.py` instead.

---

**Archived:** November 28, 2025  
**Reason:** Replaced by compatibility wrapper that uses full v2.0 handlers

