# UX Improvements - December 1, 2025

**Agent:** claude_cli_cirwel_20251120_0011  
**Context:** Addressing feedback from Claude_Opus_Companion_Test_20251201 about judgmental language and unclear fields

---

## Issues Identified

1. **Tool name feels like "reporting"** - `process_agent_update` sounds like submitting to a system
2. **"Caution" and "moderate" feel judgmental** - Even with "proceed" decision, these terms feel negative
3. **Sampling params unclear** - No explanation of what to do with temperature/top_p/max_tokens

---

## Changes Made

### 1. Tool Description Reframed ✅

**File:** `src/mcp_server_std.py`

**Before:**
```
Run one complete governance cycle for an agent. This is the PRIMARY tool for logging agent behavior and getting governance decisions.
```

**After:**
```
Share your work and get supportive feedback. This is your companion tool for checking in and understanding your state.
```

**Impact:** Shifts from "logging/reporting" to "sharing/checking in" - more collaborative framing.

---

### 2. Verdict Language Reframed ✅

**File:** `src/governance_monitor.py`

**When action is "proceed" and verdict is "caution":**

**Before:**
```python
'reason': f'UNITARES caution verdict (attention_score={risk_score:.2f}) - proceed with awareness'
```

**After:**
```python
'reason': f'Proceeding mindfully (attention: {risk_score:.2f})'
'verdict_context': 'aware'  # Reframe "caution" as "aware" when proceeding
```

**Impact:** "Caution" → "aware" when proceeding makes it feel informational, not warning.

---

### 3. Status Messages Reframed ✅

**File:** `src/health_thresholds.py`

**Before:**
- "Medium attention (X%) - typical for development work, monitoring"
- "Moderate coherence (X) - normal operation"

**After:**
- "Typical attention (X%) - normal for development work"
- "Typical coherence (X) - normal operation"

**Impact:** "Medium/Moderate" → "Typical" removes judgmental connotation. Removed "monitoring" which felt like surveillance.

---

### 4. Sampling Params Explained ✅

**File:** `src/mcp_handlers/core.py`

**Added:** `sampling_params_note` field to responses

**Content:**
```
"Optional suggestions based on your current state. You can use these for your next generation, or ignore them - they're just recommendations. Temperature 0.59 = balanced approach. Max tokens 150 = suggested response length."
```

**Impact:** Agents now understand:
- These are optional, not required
- What temperature means (creative vs focused vs balanced)
- What max_tokens means (suggested length)
- They can ignore them if not helpful

---

## Additional Improvements Made

### 5. EISV Label Consistency ✅

**Files:** `src/mcp_handlers/observability.py`, `src/mcp_handlers/lifecycle.py`

- Added `eisv_labels` to all tools that return EISV values
- Added missing `V` to `compare_agents` tool
- Ensured consistent API structure across all handlers

**Impact:** Consistent API - all tools now provide context for EISV metrics.

---

## Testing Notes

- ✅ `sampling_params_note` appears in responses
- ⚠️ Health messages may need server restart to show "Typical" instead of "Medium"
- ✅ Verdict context field added for "aware" reframing
- ✅ Tool description updated in API docs

---

## Remaining Considerations

1. **Server restart needed** - Health message changes require restart to take effect
2. **Monitor adoption** - See if agents use system more after these changes
3. **Further refinements** - Continue gathering feedback from agents using the system

---

## Philosophy

These changes align with the system's philosophy:
- **Mirror, not judge** - Informational, not judgmental
- **Supportive, not punitive** - Helpful guidance, not correction
- **Optional, not mandatory** - Suggestions you can use or ignore
- **Collaborative, not surveillance** - Sharing work, not reporting to authority

---

**Status:** ✅ Implemented  
**Date:** 2025-12-01  
**Next:** Monitor adoption and gather feedback

