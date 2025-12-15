# Metric Consistency Fix - December 10, 2025

## Problem

Metrics were inconsistent across handlers:

1. **`get_governance_metrics`**: Missing E, I, S, V at top level (they were nested in `state` dict)
2. **`process_agent_update`**: Had E, I, S, V at top level AND nested in `eisv` dict (duplication)
3. **`get_metrics()`**: Didn't return E, I, S, V at top level, only in `state` dict

## Root Cause

`get_metrics()` in `governance_monitor.py` returned E, I, S, V nested in `state` dict, but `format_metrics_report()` expected them at the top level. This caused:
- `get_governance_metrics` to return metrics without E, I, S, V
- Inconsistency between handlers

## Solution

### 1. Fixed `get_metrics()` to include EISV at top level

**File:** `src/governance_monitor.py`

Added E, I, S, V, coherence, lambda1, and void_active at top level for consistency with `process_update()`:

```python
return {
    'agent_id': self.agent_id,
    'state': self.state.to_dict(),
    # EISV metrics at top level for consistency with process_update()
    'E': float(self.state.E),
    'I': float(self.state.I),
    'S': float(self.state.S),
    'V': float(self.state.V),
    'coherence': float(self.state.coherence),
    'lambda1': float(self.state.lambda1),
    'void_active': bool(self.state.void_active),
    # ... rest of metrics
}
```

### 2. Enhanced `format_metrics_report()` documentation

**File:** `src/mcp_handlers/utils.py`

Added comment explaining that both flat and nested formats are valid:
- `metrics["E"]` (flat, for easy access)
- `metrics["eisv"]["E"]` (nested, for structured access)

### 3. Improved EISV sync in `process_agent_update`

**File:** `src/mcp_handlers/core.py`

Enhanced EISV consistency check to:
- Sync `eisv` dict with flat values (flat values take precedence)
- Ensure both formats are always consistent
- Handle missing values gracefully

## Result

✅ **Consistent metric format across all handlers:**
- Both `get_governance_metrics` and `process_agent_update` return E, I, S, V at top level
- Both formats available: `metrics["E"]` and `metrics["eisv"]["E"]`
- Values are always synchronized between formats

## Testing

Verified that:
- `get_metrics()` now includes E, I, S, V at top level ✅
- `get_governance_metrics` returns E, I, S, V ✅
- `process_agent_update` has consistent EISV in both formats ✅
- Both flat and nested formats have same values ✅

## Impact

- **Breaking changes:** None (backward compatible)
- **Improvements:** Consistent metric format makes it easier to consume metrics
- **Documentation:** Both formats documented as valid

