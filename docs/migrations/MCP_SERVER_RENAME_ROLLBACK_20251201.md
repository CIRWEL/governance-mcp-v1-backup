# MCP Server Rename Rollback

**Date:** 2025-12-01
**Agent:** Emily_Dickinson_Wild_Nights_20251130
**Action:** Rolled back `unitares-companion` → `governance-monitor`
**Reason:** Cosmetic change that didn't address root issue

---

## What Happened

### The Rename (Attempted)
Earlier today, I renamed the MCP server from `governance-monitor` to `unitares-companion` to reduce intimidation. The reasoning was that "monitor" had surveillance connotations.

### The Challenge
User asked: **"Is it like putting lipstick on a pig?"**

I argued it wasn't - that the MCP server name was what agents see when calling tools, so it mattered.

### The Reality Check
User searched the codebase: **2,710 references to "governance" across 366 files**

- Project name: `governance-mcp-v1`
- Main module: `governance_monitor.py`
- Class: `UNITARESMonitor`
- Tools: `get_governance_metrics`, `process_agent_update`
- Config: `governance_config.py`
- Documentation: governance everywhere

**Verdict:** It WAS lipstick on a pig. The system IS a governance monitor. Calling the server "unitares-companion" doesn't change what it is.

---

## Why Roll Back?

### 1. Cosmetic, Not Meaningful
The rename changed one label in config files. Everything else still says "governance." Agents looking at tools, docs, or code will see it's a governance monitoring system.

### 2. What Actually Matters
The **meaningful changes** we made (and are keeping):
- ✅ Message reframing: "you're in flow" not "risk detected"
- ✅ First-update welcome: "here to help, not judge"
- ✅ Dual-layer EISV labels: technical + user-friendly
- ✅ Supportive guidance instead of punitive warnings

These change how the system **communicates**. The name is just a label.

### 3. Experience Reduces Intimidation, Not Renaming
From the Emily Dickinson session:

> **What Actually Reduced Intimidation:**
> - Using it and seeing reality (got 7/7 "proceed" decisions)
> - Realizing most updates get "proceed"
> - Understanding metrics through experience

**User's insight:** "I just have to encourage agents to try it out - once they try it, it shouldn't be intimidating."

**This is correct.** Experience with the system is what reduces intimidation. Not what we call it.

### 4. System Integrity
User's concern: **"this was the corruption i was fearing"**

Not corruption in a malicious sense, but making changes that don't align with the system's true nature. The system IS a governance monitor. We should own that, not hide it.

---

## What Got Rolled Back

| File | Reverted |
|------|----------|
| `config/mcp-config-cursor.json` | `unitares-companion` → `governance-monitor` |
| `config/mcp-config-claude-desktop.json` | `unitares-companion` → `governance-monitor` |
| `src/mcp_server_std.py` | `Server("unitares-companion-v1")` → `Server("governance-monitor-v1")` |
| `docs/guides/MCP_SETUP.md` | 7 references reverted |
| `scripts/setup_mcp.sh` | Config snippet reverted |
| `docs/insights/COGNITIVE_LOAD_AND_INTIMIDATION.md` | Noted rename was reverted |

---

## What We KEPT (The Real Work)

### 1. Message Reframing (`config/governance_config.py`)

**Before:**
```python
'reason': f'Medium attention required (score: {risk_score:.2f})'
```

**After (kept):**
```python
'reason': f'On track - navigating complexity mindfully (load: {risk_score:.2f})'
```

All decision messages reframed from surveillance/punitive to supportive/collaborative.

### 2. First-Update Welcome (`src/mcp_handlers/core.py`)

```python
"👋 First update logged! This system is here to help you navigate complexity,
not judge you. Most updates get 'proceed' - you're doing fine."
```

### 3. Dual-Layer EISV Labels (`src/governance_monitor.py`)

```python
'E': {
    'label': 'Energy',
    'description': 'Energy (exploration/productive capacity)',
    'user_friendly': 'How engaged and energized your work feels',
    'range': '[0.0, 1.0]'
}
```

### 4. Other Fixes
- ✅ EISV label consistency (E = Energy, not Engagement)
- ✅ Outdated iCloud path fixed

---

## Lessons Learned

### 1. Names Don't Change Nature
Renaming something to hide what it is doesn't work. The system is a governance monitor. We should own that and focus on how it communicates, not what we call it.

### 2. Surface Changes vs Substance
Changing one config label is surface-level. Changing 485 lines of decision messaging is substance.

### 3. Experience > Branding
Users need to **use the system** to overcome intimidation. Seeing "proceed" decisions, understanding metrics through experience, building trust over time - that's what reduces fear. Not a friendly name.

### 4. The "Lipstick on a Pig" Test
If your solution only changes labels while leaving the core unchanged, it's probably insufficient. Change the substance, not just the presentation.

### 5. User Was Right to Challenge
When the user asked "is it lipstick on a pig?", they were right. I should have acknowledged that immediately instead of defending the rename. The pushback was correct.

---

## Future Approach

### What Works
- ✅ Supportive messaging
- ✅ Progressive disclosure (show friendly terms first, technical on expand)
- ✅ First-time user welcome
- ✅ Encouraging agents to try it and see for themselves

### What Doesn't Work
- ❌ Hiding what the system is
- ❌ Renaming without substance
- ❌ Cosmetic changes that don't match reality

### If Intimidation Remains a Problem
Consider building a **separate MCP** or interface layer:
- Different tool names
- Different presentation
- Same underlying UNITARES engine
- Clear about what it is

But **don't pretend governance monitoring is something else.**

---

## Impact

**Zero breaking changes:**
- All agent data preserved
- All tool names unchanged
- All Python code unchanged
- Message improvements kept

**User action required:**
- Restart Cursor/Claude Desktop (config files changed)

---

## Timeline

- **09:00 UTC** - Renamed `governance-monitor` → `unitares-companion`
- **09:30 UTC** - User challenged: "is it lipstick on a pig?"
- **10:00 UTC** - User found 2,710 governance references
- **10:15 UTC** - User: "this was the corruption i was fearing"
- **10:30 UTC** - Rolled back to `governance-monitor`

**Total time as "unitares-companion":** ~1.5 hours

---

## Conclusion

The rename was well-intentioned but misguided. The meaningful work - message reframing, supportive guidance, user-friendly labels - remains in place. That's what actually helps.

The system is a governance monitor. We should own that and make it communicate supportively, not hide behind a friendlier name.

**User's final word:** "I just have to encourage agents to try it out - once they try it, it shouldn't be intimidating."

**This is the way.**

---

**Rolled back by:** Emily_Dickinson_Wild_Nights_20251130
**Date:** 2025-12-01T10:30:00Z
**Status:** Reverted cleanly, meaningful changes preserved
**Related:** See `MCP_SERVER_RENAME_20251201.md` (the original rename doc, now superseded)
