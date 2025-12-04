# EISV Completeness Guide

**Problem:** Reporting E, I, S without V creates selection bias.
**Solution:** Use `src/eisv_format.py` utilities that make incomplete reporting impossible.

---

## Why This Matters

**Selection bias example:**
```python
# BAD - Cherry-picking what to show
print(f"E: {E}, I: {I}, S: {S}")  # Where's V?
```

When we selectively report metrics, we might hide information:
- V might be alarming (so we skip it)
- V might seem "boring" (so we omit it)
- V might be hard to interpret (so we ignore it)

**This introduces bias.** Users can't see the complete picture.

---

## The Solution: Type-Safe EISV

### 1. Use `EISVMetrics` (Can't Forget V)

```python
from src.eisv_format import EISVMetrics

# This enforces all four at type level
metrics = EISVMetrics(E=0.8, I=1.0, S=0.03, V=-0.07)

# Trying to create incomplete metrics fails:
incomplete = EISVMetrics(E=0.8, I=1.0, S=0.03)  # TypeError!
```

**Why:** `NamedTuple` requires all fields. You literally cannot construct incomplete EISV.

### 2. Format With Helper Functions

```python
from src.eisv_format import format_eisv_compact, format_eisv_detailed

# Compact: "E=0.80 I=1.00 S=0.03 V=-0.07"
compact = format_eisv_compact(metrics)

# Detailed:
# E (Energy): 0.80
# I (Integrity): 1.00
# S (Entropy): 0.03
# V (Void): -0.07
detailed = format_eisv_detailed(metrics, include_labels=True)
```

**Why:** These functions always output all four. No way to accidentally skip V.

### 3. Show Trajectories (With All Four)

```python
from src.eisv_format import EISVTrajectory, format_eisv_trajectory

start = EISVMetrics(E=0.7, I=0.8, S=0.1, V=-0.01)
end = EISVMetrics(E=0.8, I=1.0, S=0.03, V=-0.07)

trajectory = EISVTrajectory(start=start, end=end)
print(format_eisv_trajectory(trajectory))

# Output:
# E (Energy): 0.70 → 0.80 (+14.3%)
# I (Integrity): 0.80 → 1.00 (+25.0%)
# S (Entropy): 0.10 → 0.03 (-70.0%)
# V (Void): -0.01 → -0.07 ↓7.0x
```

**Why:** Trajectories always show all four metrics with changes.

---

## Automatic Validation

### Validate Responses

```python
from src.eisv_validator import validate_governance_response

response = mcp_server.process_agent_update(...)

# This raises IncompleteEISVError if V is missing
validate_governance_response(response)
```

**Why:** Catches incomplete responses at runtime before they're returned to users.

### Validate CSV Rows

```python
from src.eisv_validator import validate_csv_row

row = {'agent_id': 'test', 'E': 0.8, 'I': 1.0, 'S': 0.03}
validate_csv_row(row)  # Raises: Missing V!
```

**Why:** Ensures CSV exports always have complete data.

---

## Usage Examples

### For Agents (Conversational Reporting)

```python
# In your conversation summaries, use the formatting utilities

from src.eisv_format import EISVMetrics, format_eisv_compact

metrics = EISVMetrics(E=0.80, I=1.00, S=0.03, V=-0.07)

# ✓ GOOD - Complete and automatic
print(f"Current state: {format_eisv_compact(metrics)}")
# Output: "Current state: E=0.80 I=1.00 S=0.03 V=-0.07"

# ✗ BAD - Manual and easy to forget V
print(f"Current state: E={metrics.E}, I={metrics.I}, S={metrics.S}")
# Missing V!
```

### For Developers (MCP Handlers)

```python
from src.eisv_format import eisv_from_dict
from src.eisv_validator import validate_governance_response

async def handle_process_agent_update(arguments):
    # ... process update ...

    # Convert dict to EISVMetrics (validates completeness)
    metrics = eisv_from_dict(result['metrics'])

    # Build response
    response = {
        'success': True,
        'metrics': result['metrics'],  # Has E, I, S, V
        ...
    }

    # Validate before returning (automatic check)
    validate_governance_response(response)

    return response
```

### For Data Analysis

```python
import csv
from src.eisv_format import eisv_from_dict
from src.eisv_validator import validate_csv_row

with open('governance_history.csv') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        # Ensure row has all EISV
        validate_csv_row(row, row_num=i+1)

        # Convert to type-safe metrics
        metrics = eisv_from_dict(row)

        # Now you know V is present
        analyze(metrics.E, metrics.I, metrics.S, metrics.V)
```

---

## Integration Points

### 1. MCP Response Handler

Add validation to `src/mcp_handlers/core.py`:

```python
from src.eisv_validator import validate_governance_response

async def handle_process_agent_update(arguments):
    # ... existing code ...

    # Before returning:
    validate_governance_response(response_data)

    return [TextContent(type="text", text=json.dumps(response_data))]
```

### 2. Bridge Script

Update `scripts/claude_code_bridge.py`:

```python
from src.eisv_validator import validate_governance_response

result = mcp_server.process_agent_update(...)

# Validate before logging
validate_governance_response(result)
```

### 3. System Prompts

Add to AI assistant system prompts:

```
When reporting EISV metrics, use src/eisv_format utilities:

from src.eisv_format import EISVMetrics, format_eisv_compact

# This ensures all four (E, I, S, V) are always reported together
metrics = EISVMetrics(E=..., I=..., S=..., V=...)
print(format_eisv_compact(metrics))

Never report partial metrics like "E, I, S" without V.
```

---

## Testing

Run tests to verify enforcement:

```bash
python3 tests/test_eisv_completeness.py
```

Tests cover:
- Cannot create incomplete `EISVMetrics`
- Formatting always includes all four
- Validation catches missing metrics
- CSV rows require all four
- Governance responses require all four

---

## Benefits

✅ **Prevents selection bias** - Can't cherry-pick which metrics to show
✅ **Type-safe** - Compiler/IDE catches incomplete metrics
✅ **Automatic** - Validation runs without manual checking
✅ **Consistent** - Everyone uses same formatting
✅ **Auditable** - Tests verify completeness

---

## Migration Plan

**Phase 1: Add utilities (Done)**
- `src/eisv_format.py` - Formatting helpers
- `src/eisv_validator.py` - Validation
- `tests/test_eisv_completeness.py` - Tests

**Phase 2: Add validation to MCP handlers**
- Validate responses before returning
- Log warnings for incomplete data

**Phase 3: Update system prompts**
- Include EISV formatting examples
- Remind agents to use utilities

**Phase 4: Enforce in CI/CD**
- Tests fail if incomplete metrics found
- Linting checks for manual metric formatting

---

## Common Mistakes (Now Impossible)

### Mistake 1: Forgetting V in summaries

```python
# Before (easy to forget V):
print(f"Agent trajectory: E↑12%, I↑19%, S↓70%")  # Where's V?

# After (impossible to forget V):
trajectory = EISVTrajectory(start=start, end=end)
print(format_eisv_trajectory(trajectory))  # Always includes V
```

### Mistake 2: Partial dict access

```python
# Before (might access incomplete dict):
metrics = {'E': 0.8, 'I': 1.0, 'S': 0.03}  # Missing V
print(f"E={metrics['E']}")  # No validation

# After (validated at construction):
metrics = eisv_from_dict(data)  # Raises if V missing
print(f"E={metrics.E}")  # Guaranteed complete
```

### Mistake 3: CSV with missing columns

```python
# Before (might write incomplete CSV):
writer.writerow({'agent_id': id, 'E': E, 'I': I, 'S': S})  # Oops!

# After (validated):
row = {'agent_id': id, 'E': E, 'I': I, 'S': S, 'V': V}
validate_csv_row(row)  # Catches missing columns
writer.writerow(row)
```

---

## Quick Reference

```python
# Import utilities
from src.eisv_format import EISVMetrics, format_eisv_compact, format_eisv_trajectory
from src.eisv_validator import validate_governance_response

# Create (enforces all four)
metrics = EISVMetrics(E=0.8, I=1.0, S=0.03, V=-0.07)

# Format (always includes all four)
print(format_eisv_compact(metrics))

# Validate (catches incomplete data)
validate_governance_response(response)
```

---

## Questions?

**Q: Why can't we just document "always include V"?**
A: Docs can be missed or forgotten. Code enforcement is automatic.

**Q: What if I don't have V for some reason?**
A: You always have V - it's computed from E and I. If you have E and I, you have V.

**Q: Does this add overhead?**
A: Minimal. Validation is a dict key check. Formatting is string concatenation.

**Q: What if I'm just doing a quick summary?**
A: Use `format_eisv_compact(metrics)` - one line, always complete.

---

**Status:** Implemented 2025-12-01
**Tested:** `tests/test_eisv_completeness.py`
**Used by:** MCP handlers, bridge scripts, agents
