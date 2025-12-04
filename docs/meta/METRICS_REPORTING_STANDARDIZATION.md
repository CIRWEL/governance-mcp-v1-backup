# Metrics Reporting and Data Update Standardization

**Last Updated:** 2025-12-01  
**Purpose:** Standardize metrics reporting, export, and data update flow  
**Status:** Living document - evolves with the system

---

## Overview

This document standardizes the flow from metrics computation → reporting → export → data persistence. The goal is consistency, clarity, and reliability across all metrics operations.

---

## Metrics Flow

### 1. Metrics Computation (`process_update`)

**Location:** `src/governance_monitor.py::UNITARESMonitor.process_update()`

**Computed Metrics:**
- **EISV State:** E, I, S, V (thermodynamic state variables)
- **Coherence:** C(V) from E-I balance [0, 1]
- **Attention Score:** Complexity/attention blend (70% phi-based + 30% traditional) [0, 1]
- **Phi (Φ):** Primary physics signal (UNITARES objective function)
- **Verdict:** Primary governance signal ("safe" | "caution" | "high-risk")
- **Risk Score:** DEPRECATED - Use attention_score instead
- **Lambda1 (λ₁):** Adaptive control parameter [0, 1]
- **Void Active:** Boolean (|V| > threshold)
- **Health Status:** "healthy" | "moderate" | "critical"

**History Tracking:**
- `E_history`, `I_history`, `S_history`, `V_history` - Full time-series
- `coherence_history` - Coherence over time
- `risk_history` - Risk/attention scores over time
- `decision_history` - Decisions (proceed/pause) over time
- `lambda1_history` - Lambda1 adaptation over time
- `timestamp_history` - ISO timestamps for each update

---

### 2. Metrics Reporting (`get_governance_metrics`)

**Location:** `src/mcp_handlers/core.py::handle_get_governance_metrics()`

**Standard Response Format:**
```json
{
  "success": true,
  "agent_id": "agent_id",
  "state": {
    "E": 0.70,
    "I": 0.82,
    "S": 0.15,
    "V": -0.01,
    "coherence": 0.50,
    "lambda1": 0.125,
    "void_active": false,
    "time": 0.3,
    "update_count": 3
  },
  "status": "moderate",
  "sampling_params": {
    "temperature": 0.59,
    "top_p": 0.86,
    "max_tokens": 150,
    "lambda1": 0.125
  },
  "history_size": 3,
  "current_risk": 0.40,
  "mean_risk": 0.38,
  "attention_score": 0.40,
  "phi": 0.19,
  "verdict": "caution",
  "risk_score": 0.40,
  "void_frequency": 0.0,
  "decision_statistics": {
    "proceed": 3,
    "pause": 0,
    "total": 3
  },
  "stability": {
    "stable": true,
    "alpha_estimate": 0.1,
    "violations": 0
  },
  "eisv_labels": {
    "E": {"label": "Energy", "description": "...", "user_friendly": "...", "range": "[0.0, 1.0]"},
    "I": {"label": "Information Integrity", ...},
    "S": {"label": "Entropy", ...},
    "V": {"label": "Void Integral", ...}
  }
}
```

**Standard Fields:**
- ✅ Always include `eisv_labels` (API documentation)
- ✅ Always include `status` (health status)
- ✅ Always include `sampling_params` (optional suggestions)
- ✅ Always include `decision_statistics` (decision history summary)
- ✅ Always include `stability` (system stability assessment)

---

### 3. Metrics Export (`get_system_history` / `export_to_file`)

**Location:** `src/mcp_handlers/export.py::handle_get_system_history()`

**Standard Export Format (JSON):**
```json
{
  "agent_id": "agent_id",
  "timestamps": ["2025-12-01T15:00:00", "2025-12-01T15:01:00", ...],
  "E_history": [0.70, 0.71, 0.72, ...],
  "I_history": [0.82, 0.83, 0.84, ...],
  "S_history": [0.15, 0.14, 0.13, ...],
  "V_history": [-0.01, -0.02, -0.03, ...],
  "coherence_history": [0.50, 0.51, 0.52, ...],
  "attention_history": [0.40, 0.39, 0.38, ...],  # Renamed from risk_history - stores attention_score values
  "risk_history": [0.40, 0.39, 0.38, ...],  # DEPRECATED: Use attention_history instead. Kept for backward compatibility.
  "decision_history": ["proceed", "proceed", "proceed", ...],
  "lambda1_history": [0.125, 0.125, 0.125, ...],
  "lambda1_final": 0.125,
  "total_updates": 3,
  "total_time": 0.3
}
```

**Standard Export Format (CSV):**
```csv
update,timestamp,E,I,S,V,coherence,attention_score,decision,lambda1
1,2025-12-01T15:00:00,0.70,0.82,0.15,-0.01,0.50,0.40,proceed,0.125
2,2025-12-01T15:01:00,0.71,0.83,0.14,-0.02,0.51,0.39,proceed,0.125
3,2025-12-01T15:02:00,0.72,0.84,0.13,-0.03,0.52,0.38,proceed,0.125

Summary
agent_id,agent_id,,,,,,,
total_updates,3,,,,,,,
total_time,0.3,,,,,,,
lambda1_final,0.125,,,,,,,
```

**Note:** CSV column renamed from "risk" to "attention_score" (2025-12-01). The values stored are attention_score (blended complexity/attention metric), not deprecated risk_score.

**Standard Fields:**
- ✅ Always include all history arrays (E, I, S, V, coherence, attention_history, decision, lambda1)
- ✅ Always include `attention_history` (primary) and `risk_history` (deprecated, backward compat)
- ✅ Always include timestamps (ISO format)
- ✅ Always include summary statistics (total_updates, total_time, lambda1_final)
- ✅ CSV format: Column name "attention_score" (not "risk"), consistent column order, summary section at end

---

### 4. Data Persistence (`save_monitor_state` / `save_metadata`)

**Location:** `src/mcp_server_std.py::save_monitor_state()` / `save_metadata()`

**State Persistence:**
- **File:** `data/history/{agent_id}.json`
- **Format:** JSON with full GovernanceState
- **Includes:** All history arrays, current state, PI controller state

**Metadata Persistence:**
- **File:** `data/agent_metadata.json`
- **Format:** JSON with agent metadata
- **Includes:** agent_id, api_key, status, lifecycle events, tags, notes, timestamps

**Standard Persistence Flow:**
1. `process_update()` computes metrics
2. `save_monitor_state()` saves state to disk (with locking)
3. `save_metadata()` updates metadata (last_update, total_updates)
4. Both use file locking to prevent race conditions

---

## Standardization Rules

### 1. Metric Naming

**Primary Metrics (Always Use):**
- `attention_score` - Complexity/attention blend (renamed from risk_score)
- `phi` - Primary physics signal (UNITARES Φ)
- `verdict` - Primary governance signal ("safe" | "caution" | "high-risk")
  - **Note:** "caution" is correct technical term. When action="proceed" and verdict="caution", user-facing context reframes as "aware" (less judgmental)
- `coherence` - Thermodynamic coherence C(V)
- `E`, `I`, `S`, `V` - Thermodynamic state variables

**Deprecated Metrics (Backward Compat Only):**
- `risk_score` - DEPRECATED, use `attention_score` instead
- Included for backward compatibility but marked deprecated

**Consistent Naming:**
- ✅ Use snake_case for all metric names
- ✅ Use descriptive names (attention_score not risk_score)
- ✅ Include units/ranges in labels (eisv_labels)

---

### 2. Metric Formatting

**Numeric Values:**
- ✅ Floats: Always convert to float (not numpy types)
- ✅ Precision: 2-3 decimal places for display, full precision for export
- ✅ Ranges: Always validate ranges (E/I/S: [0, 1], V: (-inf, +inf))

**Timestamps:**
- ✅ Format: ISO 8601 (`YYYY-MM-DDTHH:MM:SS.ffffff`)
- ✅ Timezone: UTC (no timezone suffix for consistency)
- ✅ Storage: String format in JSON

**Booleans:**
- ✅ Use Python bool (not int or string)
- ✅ Consistent naming: `void_active`, `stable`, etc.

---

### 3. Response Structure

**Standard Response Wrapper:**
```json
{
  "success": true,
  "agent_id": "agent_id",
  "data": {...},
  "timestamp": "2025-12-01T15:00:00",
  "eisv_labels": {...}
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message",
  "error_code": "ERROR_CODE",
  "recovery_guidance": "How to recover"
}
```

**Consistent Fields:**
- ✅ Always include `success` boolean
- ✅ Always include `agent_id` (when applicable)
- ✅ Always include `eisv_labels` (for API documentation)
- ✅ Always include `timestamp` (ISO format)

---

### 4. Export Standardization

**Export Formats:**
- ✅ JSON: Default format, full precision, nested structure
- ✅ CSV: Tabular format, summary section, consistent columns

**Export Locations:**
- ✅ History-only: `data/history/{agent_id}_history_{timestamp}.{format}`
- ✅ Complete package: `data/exports/{agent_id}_complete_package_{timestamp}.json`

**Export Contents:**
- ✅ Always include all history arrays
- ✅ Always include timestamps
- ✅ Always include summary statistics
- ✅ Always include metadata (for complete package)

---

### 5. Data Update Flow

**Standard Update Sequence:**
1. **Authenticate** - Verify agent ownership (API key)
2. **Validate** - Validate inputs (complexity, confidence, etc.)
3. **Compute** - Run governance cycle (update dynamics, compute metrics)
4. **Decide** - Make governance decision (proceed/pause)
5. **Persist** - Save state and metadata (with locking)
6. **Respond** - Return metrics and decision

**Locking:**
- ✅ Always use file locking for state updates
- ✅ Retry with exponential backoff (3 attempts)
- ✅ Clean up stale locks automatically

**Error Handling:**
- ✅ Validate inputs before processing
- ✅ Handle errors gracefully (don't corrupt state)
- ✅ Return helpful error messages (sanitized)

---

## Current Inconsistencies

### 1. Metric Naming Inconsistencies

**Found:**
- `risk_score` vs `attention_score` - Both used, attention_score is correct
- `current_risk` vs `mean_risk` - Both used, different purposes
- `status` vs `health_status` - Both used, status is correct

**Standardization:**
- ✅ Use `attention_score` (primary), include `risk_score` for backward compat
- ✅ Use `current_risk` for recent trend (last 10), `mean_risk` for overall average
- ✅ Use `status` for health status, include `health_status` in metrics dict

---

### 2. Export Format Inconsistencies

**Found:**
- Some exports include `attention_score`, others use `risk_score`
- Some exports include `phi` and `verdict`, others don't
- CSV format inconsistent column order

**Standardization:**
- ✅ Always include `attention_score` (primary), `risk_score` (deprecated)
- ✅ Always include `phi` and `verdict` in JSON exports
- ✅ Standardize CSV column order (see above)

---

### 3. Response Structure Inconsistencies

**Found:**
- Some responses include `eisv_labels`, others don't
- Some responses include `sampling_params`, others don't
- Some responses include `decision_statistics`, others don't

**Standardization:**
- ✅ Always include `eisv_labels` (API documentation)
- ✅ Always include `sampling_params` (optional suggestions)
- ✅ Always include `decision_statistics` (decision history summary)

---

## Migration Plan

### Phase 1: Standardize Naming (Immediate)
- ✅ Use `attention_score` as primary metric name
- ✅ Include `risk_score` for backward compatibility (deprecated)
- ✅ Document metric purposes clearly

### Phase 2: Standardize Responses (Next Week)
- ✅ Always include `eisv_labels` in all metric responses
- ✅ Always include `sampling_params` in process_agent_update responses
- ✅ Always include `decision_statistics` in get_governance_metrics

### Phase 3: Standardize Exports (Next Month)
- ✅ Standardize CSV column order
- ✅ Always include `phi` and `verdict` in exports
- ✅ Standardize export file naming

---

## Tools and Scripts

**MCP Tools:**
- `process_agent_update` - Main governance cycle (computes metrics)
- `get_governance_metrics` - Get current metrics (reports metrics)
- `get_system_history` - Export history (exports metrics)
- `export_to_file` - Export to file (persists metrics)

**Scripts:**
- `scripts/claude_code_bridge.py` - CLI bridge (uses MCP tools)
- `scripts/validate_all.py` - Validation (checks data consistency)

**All tools follow this standardization.**

---

## Related Documentation

- [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md) - Documentation formatting
- [EISV_COMPLETENESS.md](../guides/EISV_COMPLETENESS.md) - EISV metrics guide
- `src/governance_monitor.py` - Metrics computation implementation
- `src/mcp_handlers/core.py` - Metrics reporting implementation
- `src/mcp_handlers/export.py` - Metrics export implementation

---

**Remember:** Consistency improves clarity. Standardize for elegance, not restriction.

