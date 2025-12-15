# Risk Metrics Explained - December 10, 2025

## Overview

The system uses multiple risk-related metrics for different purposes. This document explains each one and when to use it.

## Risk Metrics

### 1. `attention_score` (Primary - Use This)
**What:** Current complexity/attention blend (70% phi-based + 30% traditional safety)  
**Range:** [0.0, 1.0]  
**When to use:** Primary metric for governance decisions  
**Note:** Renamed from `risk_score` to better reflect that it measures complexity/attention, not ethical risk

### 2. `risk_score` (Deprecated - Backward Compatibility Only)
**What:** Same as `attention_score` (kept for backward compatibility)  
**Range:** [0.0, 1.0]  
**When to use:** Don't use - use `attention_score` instead  
**Status:** DEPRECATED - will be removed in future versions

### 3. `current_risk` (Recent Trend)
**What:** Recent trend - mean of last 10 risk scores  
**Range:** [0.0, 1.0]  
**When to use:** Used for health status calculation (reflects current behavior, not all-time history)  
**Note:** More stable than point-in-time values, better for status checks

### 4. `mean_risk` (Historical Context)
**What:** Overall mean - all-time average of all risk scores  
**Range:** [0.0, 1.0]  
**When to use:** Historical context only, not for decisions  
**Note:** Shows long-term patterns, but doesn't reflect current state

### 5. `latest_attention_score` (Point-in-Time)
**What:** Point-in-time value from the most recent update  
**Range:** [0.0, 1.0]  
**When to use:** When you need the exact value from the last update (matches `process_agent_update` behavior)  
**Note:** Most accurate for current state, but can be noisy

## Which Metric to Use?

| Use Case | Recommended Metric | Why |
|----------|-------------------|-----|
| Governance decisions | `attention_score` | Primary signal, reflects current complexity |
| Health status checks | `current_risk` | Stable trend, used by health_checker |
| Current state queries | `latest_attention_score` | Most recent value |
| Historical analysis | `mean_risk` | Long-term patterns |
| Backward compatibility | `risk_score` | Deprecated, avoid |

## Consistency

All handlers now return the same risk metrics:
- ✅ `get_governance_metrics` - Returns all 5 metrics
- ✅ `process_agent_update` - Returns all 5 metrics (fixed Dec 10, 2025)
- ✅ `list_agents` - Returns all 5 metrics
- ✅ `compare_agents` - Returns all 5 metrics

## Values Relationship

Typically:
- `latest_attention_score` ≈ `attention_score` (both from last update)
- `current_risk` ≈ smoothed `latest_attention_score` (mean of last 10)
- `mean_risk` ≈ long-term average (all-time)
- `risk_score` = `attention_score` (deprecated alias)

## Migration Guide

**Old code:**
```python
risk = metrics.get("risk_score")
```

**New code:**
```python
risk = metrics.get("attention_score")  # Primary metric
# Or for recent trend:
risk = metrics.get("current_risk")  # Smoothed trend
```

## History

- **2025-12-10:** Standardized risk metrics across all handlers
- **Earlier:** `risk_score` renamed to `attention_score` to clarify meaning
- **Earlier:** Added `current_risk`, `mean_risk`, `latest_attention_score` for different use cases

