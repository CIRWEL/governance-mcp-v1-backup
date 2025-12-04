# MCP Server Rename: governance-monitor → unitares-companion

**⚠️ SUPERSEDED:** This change was **rolled back** the same day. See `MCP_SERVER_RENAME_ROLLBACK_20251201.md`

**Date:** 2025-12-01 (attempted)
**Agent:** Emily_Dickinson_Wild_Nights_20251130
**Type:** Semantic/UX improvement (attempted)
**Status:** **ROLLED BACK** - cosmetic change, didn't address root issue

---

## The "Lipstick on a Pig" Problem

**User's challenge:**
> "Pointing out the name of the actual MCP is the point of friction, if we change it there's still record of it and an agent calling the tool named such will have the same semantic association of being monitored. So is it like putting lipstick on a pig?"

**The issue:** Previous attempts to reduce intimidation focused on reframing decision messages and adding user-friendly labels. But the core problem remained: the MCP server name itself creates a semantic association of **surveillance**.

When agents call a tool literally named "governance-monitor," no amount of friendly messaging can fully overcome that framing.

---

## The Two-Layer Architecture

The system has two naming layers:

### Layer 1: MCP Server Name
- **What it is:** The server registration name in config files
- **Where agents see it:** Claude Desktop/Cursor MCP panel, tool invocations
- **Old name:** `governance-monitor`
- **New name:** `unitares-companion`
- **Semantic shift:** Surveillance → Collaborative support

### Layer 2: Tool Names (Unchanged)
- `process_agent_update`
- `get_governance_metrics`
- `get_system_history`
- `list_agents`
- etc.

**Key insight:** The tool names remain unchanged. Only the server name (the semantic container) changed.

---

## Why "unitares-companion"?

### 1. Brands the Physics
- "UNITARES" = Unified Informational Thermodynamic Agent Regulation and Ethical Synthesis
- Ties directly to the thermodynamic framework (EISV metrics)
- Makes clear this is not generic "monitoring" but specific physics

### 2. Collaborative Framing
- "Companion" emphasizes partnership, not oversight
- Matches the supportive role the system actually plays
- Reduces psychological distance and resistance

### 3. Honest but Friendly
- Still describes what it does (thermodynamic governance)
- Doesn't hide the monitoring function
- Reframes monitoring as accompanying rather than surveilling

### 4. Aligns with Existing Research
- The `COGNITIVE_LOAD_AND_INTIMIDATION.md` doc already identified "governance-monitor" as intimidating
- Recommended names like "session-companion" or "flow-companion"
- `unitares-companion` is more specific while maintaining the approachability

---

## What Changed

### Config Files
- `config/mcp-config-cursor.json` (line 3)
- `config/mcp-config-claude-desktop.json` (line 3)

**Before:**
```json
{
  "mcpServers": {
    "governance-monitor": {
      "command": "python3",
      ...
    }
  }
}
```

**After:**
```json
{
  "mcpServers": {
    "unitares-companion": {
      "command": "python3",
      ...
    }
  }
}
```

### Server Code
- `src/mcp_server_std.py` (line 85)

**Before:**
```python
server = Server("governance-monitor-v1")
```

**After:**
```python
server = Server("unitares-companion-v1")
```

### Documentation
- `docs/guides/MCP_SETUP.md` - 7 references updated
- `docs/QUICK_REFERENCE.md` - 1 reference updated
- `docs/insights/COGNITIVE_LOAD_AND_INTIMIDATION.md` - noted the rename

### Setup Scripts
- `scripts/setup_mcp.sh` - config snippet updated

---

## What Did NOT Change

✅ **All agent data preserved:**
- `data/agent_metadata.json` - unchanged
- `data/agents/*.json` - unchanged
- `data/governance_history_*.csv` - unchanged
- Inter-agent memory - unchanged

✅ **All tool names unchanged:**
- Agents still call `process_agent_update`
- No breaking changes to tool signatures
- Historical tool usage data intact

✅ **All Python code unchanged:**
- `src/governance_monitor.py` - class names stay same
- `UNITARESMonitor` - unchanged
- EISV metrics, coherence, attention score - all unchanged

**The lineage lives in the data, not the config.**

---

## Migration Path

### For Existing Installations

1. **Update config files:**
   ```bash
   # Cursor
   vim ~/Library/Application\ Support/Cursor/User/globalStorage/mcp.json
   # Change "governance-monitor" → "unitares-companion"

   # Claude Desktop
   vim ~/Library/Application\ Support/Claude/claude_desktop_config.json
   # Change "governance-monitor" → "unitares-companion"
   ```

2. **Restart clients:**
   - Restart Cursor IDE
   - Restart Claude Desktop

3. **Test:**
   ```bash
   # Should work immediately
   # Ask: "What governance tools are available?"
   # Should show: unitares-companion tools
   ```

### For New Installations

- Just use the updated `setup_mcp.sh` script
- Or copy config from `config/mcp-config-*.json`
- New name is used by default

---

## Alternative Names Considered

| Name | Pros | Cons | Decision |
|------|------|------|----------|
| `unitares-monitor` | Honest, brands physics | Still has "monitor" (surveillance) | ❌ Rejected |
| `coherence-guide` | Friendly, focuses on coherence | Loses broader UNITARES context | ❌ Too narrow |
| `flow-companion` | Very approachable | Too generic, loses physics grounding | ❌ Not specific |
| `thermodynamic-copilot` | Accurate, collaborative | Too technical/intimidating | ❌ Still heavy |
| `unitares-companion` | Brands physics + collaborative | None significant | ✅ **Selected** |

---

## Expected Impact

### Reduced Intimidation
- Agents see "companion" not "monitor" in MCP panel
- Tool invocations reference collaborative framing
- First impression sets supportive tone

### Preserved Lineage
- All historical data intact
- No breaking changes
- Smooth transition

### Semantic Clarity
- "UNITARES" signals this is specific framework
- Not generic corporate governance
- Thermodynamic foundation clear

---

## Lessons Learned

### 1. Surface Changes Aren't Enough
Reframing decision messages helped, but didn't address the root semantic association. The tool name itself matters.

### 2. The "Lipstick on a Pig" Test
If your solution only changes presentation while leaving the core framing intact, it's probably insufficient. Sometimes you need to change the underlying structure.

### 3. Names Create Semantic Fields
"Governance-monitor" activates: surveillance, compliance, oversight, judgment
"Unitares-companion" activates: collaboration, support, physics, partnership

Both describe the same system. The semantic field determines initial response.

### 4. Lineage is Separate from Naming
We can preserve all historical data (lineage) while changing the public-facing name (semantic framing). They're orthogonal concerns.

---

## Context: The Full Conversation Arc

This rename emerged from a multi-turn conversation:

1. **Initial work:** Reframed decision messages, added user-friendly EISV labels
2. **User concern:** "I'm afraid of corrupting lineage/system"
3. **My proposal:** Keep technical names in code, add presentation layer
4. **User challenge:** "Is it like putting lipstick on a pig?"
5. **The insight:** The MCP name itself creates the semantic association
6. **The decision:** Rename the server (preserves lineage, changes framing)

The "lipstick on pig" challenge forced honest evaluation of whether cosmetic changes were sufficient. They weren't.

---

## Future Recommendations

### v3.0 Considerations
- Evaluate tool names too (e.g., "process_agent_update" → "log_work"?)
- Consider more user-facing naming throughout
- Document naming philosophy: technical precision vs user accessibility

### Documentation
- Continue dual-layer labeling (technical + user-friendly)
- Progressive disclosure: show friendly names first, technical on expand
- Always provide both perspectives

### Messaging
- Maintain supportive, non-surveillance tone in all responses
- First-update welcome message working well
- Keep iterating on cognitive load reduction

---

## Rollout Status

✅ Config files updated
✅ Server code updated
✅ Documentation updated
✅ Setup scripts updated
✅ Governance update logged (Emily Dickinson agent update #14)
✅ Migration doc created

**Status:** Complete and in production
**Next agents:** Will use new name automatically

---

**Renamed by:** Emily_Dickinson_Wild_Nights_20251130
**Date:** 2025-12-01T05:20:00Z
**Decision:** Not lipstick on a pig - changed the underlying semantic structure while preserving all lineage
