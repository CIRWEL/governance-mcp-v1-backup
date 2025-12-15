# Deprecated Scripts - Archived 2025-12-10

## Why These Scripts Were Deprecated

These scripts were replaced with the MCP SSE approach to solve the "too many interpretation layers" problem.

## Files in This Archive

### governance_cli_deprecated.sh
**Original name:** `governance_cli.sh`
**Deprecated:** 2025-12-10
**Reason:** Added custom interpretation layer that contradicted canonical MCP handlers

**Problem:**
- Used direct Python API (`UNITARESMonitor`)
- Added custom warning at coherence < 0.5
- Could show "⚠️ Low coherence" when governance said "PROCEED"
- Inconsistent with feedback other MCP clients received

**Example contradiction:**
```
Governance: "PROCEED, coherence 0.499, on track"
Custom CLI: "⚠️ Low coherence - consider simplifying"
```

**Replaced by:** `governance_mcp_cli.sh` (canonical MCP SSE)

### cli_helper.py
**Deprecated:** 2025-12-10
**Reason:** Bypassed MCP handlers, used direct Python API

**Problem:**
- Direct access to `UNITARESMonitor` class
- No access to canonical MCP handler interpretations
- Missed health_status, health_message from handlers
- Not part of shared SSE state

**Replaced by:** `mcp_sse_client.py` (MCP protocol client)

## What Replaced Them

**New approach:** MCP SSE Client
- **Script:** `governance_mcp_cli.sh` (with symlink `governance_cli.sh`)
- **Python:** `mcp_sse_client.py`
- **Protocol:** MCP over SSE
- **Server:** http://127.0.0.1:8765/sse

**Benefits:**
- ✅ Canonical MCP handler interpretations
- ✅ No custom threshold logic
- ✅ Consistent with Cursor, Claude Desktop
- ✅ Shared state across all MCP clients
- ✅ Supportive, not punitive feedback

## Migration

**Old:**
```bash
./governance_cli.sh "agent_id" "work" 0.5
# → Custom warnings, direct Python API
```

**New:**
```bash
./governance_cli.sh "agent_id" "work" 0.5
# → Same command! Now symlinked to MCP version
# → Canonical feedback, no custom warnings
```

The command stayed the same, but now uses MCP SSE under the hood!

## Can These Be Used?

**Technically yes**, but not recommended:

```bash
# If you really need the old behavior
../archive/deprecated_20251210/governance_cli_deprecated.sh "id" "work" 0.5
```

But you'll get:
- Custom interpretation layers
- Potential contradictions with governance
- No shared state with MCP clients
- Inconsistent feedback

**Better:** Use the new MCP approach.

## Historical Context

**Timeline:**
1. **Initial implementation:** Direct Python API + simple CLI
2. **Problem discovered:** Custom thresholds caused confusing warnings
3. **User feedback:** "too much different system" (conflicting interpretations)
4. **Solution:** Built MCP SSE client for single source of truth
5. **Result:** Deprecated old scripts, archived here

**Key lesson:** Don't add custom interpretation layers on top of canonical systems. Trust the MCP handlers - they understand context.

## Documentation

See full migration story:
- [../../docs/MCP_SSE_MIGRATION.md](../../docs/MCP_SSE_MIGRATION.md)
- [../../CLAUDE_CODE_START_HERE.md](../../CLAUDE_CODE_START_HERE.md)
- [../../.agent-guides/FUTURE_CLAUDE_CODE_AGENTS.md](../../.agent-guides/FUTURE_CLAUDE_CODE_AGENTS.md)

---

**Archived by:** Claude Code
**Date:** 2025-12-10
**Reason:** Migration to MCP SSE for canonical governance feedback
