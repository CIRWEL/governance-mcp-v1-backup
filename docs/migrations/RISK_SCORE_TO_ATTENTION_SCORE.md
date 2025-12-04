# Migration: risk_score → attention_score

**Date:** 2025-11-30
**Agent:** Emily_Dickinson_Wild_Nights_20251130
**Type:** Schema rename

---

## Summary

The governance system renamed `risk_score` to `attention_score` to better reflect its semantic meaning. The metric represents attention/complexity blend (70% phi-based + 30% traditional), not traditional "risk."

## Changes

### API Response Schema

**Before (pre-Nov 30):**
```json
{
  "metrics": {
    "risk_score": 0.45,
    ...
  }
}
```

**After (Nov 30+):**
```json
{
  "metrics": {
    "attention_score": 0.45,
    ...
  }
}
```

### Backward Compatibility

The governance monitor (`src/governance_monitor.py:1168`) includes backward compatibility:
```python
'attention_score': attention_score,  # Primary
'risk_score': attention_score,        # DEPRECATED: Kept for backward compatibility
```

However, **MCP handlers do NOT return risk_score** - only `attention_score` is included in the response.

## Breaking Changes

### Claude Code Bridge

The bridge (`scripts/claude_code_bridge.py`) was broken due to hardcoded `metrics['risk_score']` reference.

**Fix applied (line 289-290):**
```python
# Use attention_score (new) with fallback to risk_score (deprecated)
attention = metrics.get('attention_score') or metrics.get('risk_score', 0.0)
```

### Other Potential Issues

Any external scripts or integrations that expect `risk_score` in MCP responses will break. Update to use `attention_score`.

## Migration Actions Taken

1. **Archived pre-migration agents** (4 agents):
   - `Composer_Cursor_Exploration_20251129`
   - `Ennio_Test_AttentionScore_20251129`
   - `Composer_Cursor_Test_20251129`
   - `test_analysis_agent_20251129`
   - **Reason:** Low activity (1-3 updates), pre-migration schema

2. **Preserved high-activity agents:**
   - `Ennio_Morricone_Claude_20251129` (9 updates)
   - `Composer_Cursor_20251129` (11 updates)
   - **Note:** These have mixed-schema data but significant work history

3. **Fixed bridge script:**
   - Updated CSV logging to use `attention_score`
   - Added backward-compatible fallback

## Recommendations

1. **Update all external integrations** to use `attention_score`
2. **Deprecation timeline:** Remove `risk_score` fallback in v3.0
3. **State file cleanup:** Consider migrating old state files to use attention_score in risk_history

## Context

The rename reflects the system's evolution from traditional "risk" assessment to attention/complexity monitoring. The metric measures cognitive load and complexity, not safety risk.

---

**Migration completed by:** Emily_Dickinson_Wild_Nights_20251130
**Date:** 2025-11-30T07:58:00Z
