# EISV Reporting - System Prompt Snippet

**Add this to agent system prompts to ensure complete metric reporting.**

---

## For AI Assistants/Agents

When reporting governance metrics, always include all four EISV metrics together:

```python
from src.eisv_format import EISVMetrics, format_eisv_compact

# Use type-safe formatting (ensures all four present)
metrics = EISVMetrics(E=0.80, I=1.00, S=0.03, V=-0.07)
print(format_eisv_compact(metrics))
# Output: "E=0.80 I=1.00 S=0.03 V=-0.07"
```

**Never report partial metrics:**
- ❌ BAD: "E: 0.80, I: 1.00, S: 0.03" (missing V)
- ✅ GOOD: "E=0.80 I=1.00 S=0.03 V=-0.07" (complete)

**Why:** Reporting E, I, S without V creates selection bias. Always show all four together.

---

## Quick Reference

**Import:**
```python
from src.eisv_format import EISVMetrics, format_eisv_compact, format_eisv_trajectory
```

**Format current state:**
```python
metrics = EISVMetrics(E=..., I=..., S=..., V=...)
print(format_eisv_compact(metrics))
```

**Format trajectory:**
```python
from src.eisv_format import EISVTrajectory

trajectory = EISVTrajectory(start=start_metrics, end=end_metrics)
print(format_eisv_trajectory(trajectory))
```

**Validation (optional):**
```python
from src.eisv_validator import validate_governance_response

validate_governance_response(response)  # Raises if incomplete
```

---

## Examples

**Conversational summary:**
```
Current EISV state: E=0.80 I=1.00 S=0.03 V=-0.07
All metrics stable, proceeding smoothly.
```

**Session report:**
```
Agent trajectory over 20 updates:
E (Energy): 0.71 → 0.81 (+14.1%)
I (Integrity): 0.84 → 1.00 (+19.0%)
S (Entropy): 0.14 → 0.02 (-85.7%)
V (Void): -0.01 → -0.07 (↓7x more negative)
```

---

## Integration Points

**Where to use:**
1. When summarizing metrics in conversation
2. When reporting trajectory changes
3. When documenting session results
4. When analyzing governance patterns

**Enforcement:**
- MCP handlers automatically validate responses
- Tests catch incomplete reporting
- Type system prevents partial construction

---

**Status:** Active - validation running in production
**Documentation:** `docs/guides/EISV_COMPLETENESS.md`
**Utilities:** `src/eisv_format.py`, `src/eisv_validator.py`
