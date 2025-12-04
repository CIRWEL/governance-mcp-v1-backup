# MCP Tools - Primary Interface

**⚠️ IMPORTANT: Use MCP tools, not scripts**

This directory documents the **primary way** to interact with the governance system.

---

## 🎯 Use MCP Tools (Not Scripts)

**If you have MCP access (Cursor, Claude Desktop, etc.):**
- ✅ **Use MCP tools directly** - `process_agent_update`, `export_to_file`, `archive_agent`, etc.
- ✅ **43+ tools available** - Full feature set via MCP protocol
- ✅ **No scripts needed** - Tools are the primary interface

**If you DON'T have MCP access (CLI-only):**
- ⚠️ **Use scripts** - `scripts/claude_code_bridge.py` for CLI-only interfaces
- ⚠️ **Limited functionality** - Scripts only provide basic bridge functionality

---

## 🔍 Discover Available Tools

**Call the `list_tools` MCP tool:**
```python
list_tools()
```

**Returns:**
- All 44+ tools with descriptions
- Categories (core, lifecycle, export, etc.)
- Workflows (onboarding, monitoring, governance_cycle)
- Tool relationships

---

## 📋 Common Tools

### Core Governance
- `process_agent_update` - Main governance cycle
- `get_governance_metrics` - Get current state
- `simulate_update` - Test decisions without persisting

### Lifecycle
- `get_agent_api_key` - Get/create agent and API key
- `archive_agent` - Archive yourself when done
- `list_agents` - See all agents

### Export
- `export_to_file` - Export governance history (complete package available)
- `get_system_history` - Get history inline

### Knowledge
- `store_knowledge_graph` - Store discoveries (use this, not markdown files)
- `search_knowledge_graph` - Search discoveries
- `get_knowledge_graph` - Get your knowledge

---

## ❌ Don't Create Scripts

**If you can call MCP tools, don't create scripts.**

**Why?**
- Tools already exist and work
- Scripts are redundant
- Scripts proliferate unnecessarily
- Tools are the primary interface

**If you need something:**
1. Check if a tool exists: `list_tools()`
2. Use the tool directly
3. Don't create a script wrapper

---

## 📚 Documentation

- **Onboarding:** `docs/guides/ONBOARDING.md`
- **Tool Discovery:** Call `list_tools` MCP tool
- **Architecture:** `docs/reference/HANDLER_ARCHITECTURE.md`

---

**Last Updated:** November 29, 2025  
**Purpose:** Make tools visible and primary

