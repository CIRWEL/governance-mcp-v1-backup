# Risk Score Reversion Audit - December 11, 2025

## Executive Summary

Audit of `risk_score` reversion from `attention_score`. Found **23 issues** across code, comments, user-facing messages, and documentation that need fixing for consistency.

---

## Critical Issues (Must Fix)

### 1. **Duplicate/Conflicting risk_score Entries**
**Location:** `src/mcp_handlers/dialectic.py:1123`
```python
'risk_score': attention_score,  # DEPRECATED: Use attention_score instead
```
**Problem:** Wrong deprecation message - `risk_score` is PRIMARY, not deprecated
**Fix:** Remove this duplicate entry (line 1121 already has correct `risk_score`)

### 2. **Wrong Deprecation Comments in Tool Schemas**
**Locations:**
- `src/tool_schemas.py:611` - `"risk_score": 0.23,  # DEPRECATED: Use attention_score instead"`
- `src/tool_schemas.py:700` - `"risk_score": float,  # DEPRECATED: Use attention_score instead"`
- `src/tool_schemas.py:1300` - `"risk_score": float,  # DEPRECATED: Use attention_score instead"`
- `src/tool_schemas.py:1590` - `"risk_score": float,  # DEPRECATED: Use attention_score instead"`

**Problem:** These say `risk_score` is deprecated when it's actually PRIMARY
**Fix:** Remove these duplicate entries or fix deprecation message

### 3. **Wrong Deprecation in Handlers**
**Locations:**
- `src/mcp_handlers/lifecycle.py:121` - `"risk_score": ... # DEPRECATED: Use attention_score instead"`
- `src/mcp_server_std.py:2176` - `"risk_score": ... # DEPRECATED"`
- `src/mcp_handlers/dialectic.py:1241` - `"risk_ok": ... # DEPRECATED: Use attention_ok instead"`
- `src/mcp_handlers/dialectic.py:240` - `'risk_score': 0.65,  # DEPRECATED`

**Problem:** Marking `risk_score` as deprecated when it's primary
**Fix:** Remove deprecation markers or fix comments

### 4. **Inverted History Field Naming**
**Location:** `src/governance_monitor.py:1645-1646`
```python
'attention_history': self.state.risk_history,  # Renamed from risk_history - stores attention_score values
'risk_history': self.state.risk_history,  # DEPRECATED: Use attention_history instead
```
**Problem:** Should be `risk_history` primary, `attention_history` deprecated
**Fix:** Swap the primary/deprecated labels

---

## User-Facing Message Issues (Should Fix)

### 5. **"Attention Score" in User Messages**
**Locations:**
- `src/mcp_handlers/dialectic.py:363` - `"Circuit breaker triggered - high attention score"`
- `src/mcp_handlers/dialectic.py:1131` - `"Attention score is elevated ({attention_score:.3f})"`
- `src/mcp_handlers/dialectic.py:1143` - `f"System analysis: ... attention_score={attention_score:.3f}"`
- `src/tool_schemas.py:2732` - `"concerns": ["High attention score", "Low coherence"]`
- `src/mcp_handlers/dialectic.py:379` - `reasoning = f"... attention_score={agent_state.get('attention_score', 0.5):.3f}"`
- `src/mcp_handlers/dialectic.py:831` - Comment: `# - Require 3+ reviewers for high-risk decisions (attention_score > 0.60`

**Problem:** User-facing messages still say "attention score" instead of "risk score"
**Fix:** Update messages to say "risk score" (keep `attention_score` variable name for backward compat)

---

## Code Consistency Issues (Should Fix)

### 6. **Utils Still Uses attention_score as Primary**
**Location:** `src/mcp_handlers/utils.py:202`
```python
key_metrics = ["coherence", "attention_score", "phi", "verdict", "lambda1"]
```
**Problem:** Should prioritize `risk_score` in key metrics
**Fix:** Change to `["coherence", "risk_score", "phi", "verdict", "lambda1"]` (or include both)

### 7. **Condition Parser Maps to attention_score**
**Location:** `src/mcp_handlers/condition_parser.py:152-153`
```python
"attention": "attention_score",
"attention_score": "attention_score",
```
**Problem:** Should map to `risk_score` as primary
**Fix:** Add `"risk": "risk_score"` and `"risk_score": "risk_score"` mappings

### 8. **Observability Uses attention_score in Comparisons**
**Locations:**
- `src/mcp_handlers/observability.py:267` - `"attention_score": other_metrics.get('attention_score', 0.4)`
- `src/mcp_handlers/observability.py:313` - `"attention_score": my_metrics.get('attention_score', 0.4)`

**Problem:** Should prioritize `risk_score` in comparisons
**Fix:** Use `risk_score` with fallback to `attention_score`

### 9. **Latest Score Handling**
**Location:** `src/mcp_handlers/core.py:770-771`
```python
if 'latest_attention_score' not in metrics:
    metrics['latest_attention_score'] = monitor_metrics.get('latest_attention_score')
```
**Problem:** Should also check/add `latest_risk_score`
**Fix:** Add `latest_risk_score` handling

---

## Comment/Documentation Issues (Nice to Fix)

### 10. **Outdated Comment in Dialectic**
**Location:** `src/mcp_handlers/dialectic.py:1113`
```python
# Support both attention_score (new) and risk_score (deprecated)
```
**Problem:** Comment is backwards - should say `risk_score` (primary) and `attention_score` (deprecated)
**Fix:** Update comment

### 11. **CSV Export Column Name**
**Location:** `src/governance_monitor.py:1659`
**Problem:** CSV export likely still uses `attention_score` column name
**Fix:** Verify CSV uses `risk_score` column (with `attention_score` as deprecated alias if needed)

### 12. **Documentation Still References attention_score as Primary**
**Locations:**
- `docs/archive/2025-12/risk_metrics_explained_20251210.md` - Entire doc says `attention_score` is primary
- `scripts/sync_bridge_with_mcp.py:64` - Function name: `sync_terminology` says "Update deprecated risk_score to attention_score"
- `scripts/validate_all.py:38` - Deprecated terms mapping still says `risk_score` → `attention_score`

**Problem:** Documentation needs updating to reflect reversion
**Fix:** Update docs or mark as historical

---

## Summary

### Issues by Severity:
- **Critical (Must Fix):** 4 issues - Wrong deprecation markers, duplicate entries
- **User-Facing (Should Fix):** 6 issues - Messages still say "attention score"
- **Code Consistency (Should Fix):** 4 issues - Utils, parsers, comparisons
- **Documentation (Nice to Fix):** 3 issues - Outdated comments/docs

### Issues by File:
- `src/mcp_handlers/dialectic.py`: 8 issues
- `src/tool_schemas.py`: 5 issues
- `src/mcp_handlers/lifecycle.py`: 1 issue
- `src/mcp_server_std.py`: 1 issue
- `src/governance_monitor.py`: 2 issues
- `src/mcp_handlers/utils.py`: 2 issues
- `src/mcp_handlers/condition_parser.py`: 1 issue
- `src/mcp_handlers/observability.py`: 2 issues
- `src/mcp_handlers/core.py`: 1 issue
- Documentation files: 3 issues

---

## Recommendations

1. **Fix critical issues first** - Remove wrong deprecation markers, fix duplicate entries
2. **Update user-facing messages** - Change "attention score" → "risk score" in messages
3. **Update code consistency** - Prioritize `risk_score` in utils, parsers, comparisons
4. **Archive outdated docs** - Mark old docs as historical, don't update (they're in `archive/`)

---

## Next Steps

1. Create fixes for critical issues
2. Update user-facing messages
3. Fix code consistency issues
4. Document the reversion in knowledge graph

