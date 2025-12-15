# Standardized Metric Reporting

## Overview

All metric reports must include `agent_id` and other pertinent context for traceability and debugging.

## Standard Format

### Required Fields

Every metric report must include:

1. **`agent_id`** (required) - Agent identifier
2. **`timestamp`** (optional, default: True) - ISO format timestamp
3. **EISV metrics** (if available) - E, I, S, V values
4. **Health status** (if available) - Current health state

### Standardized Functions

Use these functions to ensure consistent formatting:

#### `format_metrics_report()`

Standardizes metrics dict with agent_id and context.

```python
from src.mcp_handlers.utils import format_metrics_report

metrics = {"E": 0.8, "I": 0.9, "S": 0.1, "V": -0.05}
standardized = format_metrics_report(
    metrics=metrics,
    agent_id="agent_123",
    include_timestamp=True,
    include_context=True
)
# Returns: {
#   "agent_id": "agent_123",
#   "timestamp": "2025-12-10T18:30:00.123456",
#   "E": 0.8, "I": 0.9, "S": 0.1, "V": -0.05,
#   "eisv": {"E": 0.8, "I": 0.9, "S": 0.1, "V": -0.05},
#   ...
# }
```

#### `print_metrics()`

Prints metrics with standardized format (for scripts/CLI).

```python
from src.mcp_handlers.utils import print_metrics

print_metrics("agent_123", metrics, title="Governance Metrics")
# Output:
# Governance Metrics:
# ------------------------------------------------------------
# Agent: agent_123
# Timestamp: 2025-12-10T18:30:00.123456
# Health: moderate
# EISV: E=0.800 I=0.900 S=0.100 V=-0.050
# coherence: 0.750
# attention_score: 0.450
# ------------------------------------------------------------
```

#### `log_metrics()`

Logs metrics with standardized format (for logging).

```python
from src.mcp_handlers.utils import log_metrics

log_metrics("agent_123", metrics, level="info")
# Logs: [agent_123] EISV: E=0.80 I=0.90 S=0.10 V=0.00 coherence=0.750 attention=0.450 health=moderate
```

## Usage Examples

### In Handlers

```python
from src.mcp_handlers.utils import format_metrics_report

# Get metrics
metrics = monitor.get_metrics()

# Standardize with agent_id
standardized = format_metrics_report(
    metrics=metrics,
    agent_id=agent_id,
    include_timestamp=True,
    include_context=True
)

# Return standardized metrics
return success_response(standardized)
```

### In Scripts

```python
from src.mcp_handlers.utils import print_metrics

# After getting result from process_agent_update
result = await client.process_agent_update(...)
agent_id = result.get('agent_id')
metrics = result.get('metrics', {})

# Print with standardized format
print_metrics(agent_id, metrics, title="Governance Metrics")
```

### In Logging

```python
from src.mcp_handlers.utils import log_metrics

# Log metrics with agent_id
log_metrics(agent_id, metrics, level="info")
```

## Benefits

1. **Traceability** - Always know which agent metrics belong to
2. **Consistency** - Same format everywhere
3. **Debugging** - Easy to correlate metrics with agent actions
4. **Context** - Timestamp and health status always included

## Migration Guide

### Before (Inconsistent)

```python
# ❌ Missing agent_id
print(f"E: {metrics['E']:.3f}")
print(f"I: {metrics['I']:.3f}")

# ❌ Missing timestamp
print(f"Metrics: {metrics}")

# ❌ Inconsistent format
logger.info(f"Coherence: {coherence}")
```

### After (Standardized)

```python
# ✅ Includes agent_id, timestamp, context
print_metrics(agent_id, metrics, title="Metrics")

# ✅ Logs with agent_id
log_metrics(agent_id, metrics, level="info")

# ✅ Standardized dict format
standardized = format_metrics_report(metrics, agent_id)
```

## Implementation Status

- ✅ `format_metrics_report()` - Created
- ✅ `print_metrics()` - Created  
- ✅ `log_metrics()` - Created
- ✅ `handle_get_governance_metrics` - Updated
- ✅ `handle_process_agent_update` - Updated
- ⏳ Scripts migration - In progress
- ⏳ Documentation - Complete

