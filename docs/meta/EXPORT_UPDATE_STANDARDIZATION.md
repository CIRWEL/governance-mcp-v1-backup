# Export and Update Flow Standardization

**Last Updated:** 2025-12-01  
**Purpose:** Standardize data export, update, and persistence flows in MCP system  
**Status:** Living document - evolves with the system

---

## Overview

This document standardizes how data is exported, updated, and persisted across the MCP system. Ensures consistency, reliability, and maintainability of all data operations.

---

## Data Flow Architecture

### Update Flow (process_agent_update)

**Standard Sequence:**
1. **Authenticate** - Verify agent ownership (API key)
2. **Validate** - Validate inputs (complexity, confidence, etc.)
3. **Compute** - Run governance cycle (update dynamics, compute metrics)
4. **Decide** - Make governance decision (proceed/pause)
5. **Persist** - Save state and metadata (with locking)
6. **Respond** - Return metrics and decision

**Location:** `src/mcp_handlers/core.py::handle_process_agent_update()`

---

## Persistence Standardization

### 1. File Naming Patterns

**State Files:**
- **Pattern:** `{agent_id}_state.json`
- **Location:** `data/agents/{agent_id}_state.json`
- **Example:** `data/agents/composer_markdown_standardization_20251201_state.json`
- **Migration:** Automatic migration from `data/{agent_id}_state.json` (backward compat)

**Metadata File:**
- **Pattern:** `agent_metadata.json`
- **Location:** `data/agent_metadata.json`
- **Shared:** All agents in single file

**Export Files:**
- **History-only:** `{agent_id}_history_{timestamp}.{format}`
  - **Location:** `data/history/`
  - **Example:** `data/history/composer_markdown_standardization_20251201_history_20251201_151234.json`
- **Complete package:** `{agent_id}_complete_package_{timestamp}.json`
  - **Location:** `data/exports/`
  - **Example:** `data/exports/composer_markdown_standardization_20251201_complete_package_20251201_151234.json`
- **Custom filename:** `{custom_filename}.{format}` or `{custom_filename}_complete.{format}`

**Dialectic Sessions:**
- **Pattern:** `{session_id}.json`
- **Location:** `data/dialectic_sessions/`
- **Example:** `data/dialectic_sessions/abc123.json`

**Knowledge Graph:**
- **Pattern:** `knowledge_graph.json`
- **Location:** `data/knowledge_graph.json`
- **Shared:** All discoveries in single file

---

### 2. Timestamp Formats

**ISO Timestamps (in data):**
- **Format:** `YYYY-MM-DDTHH:MM:SS.ffffff`
- **Example:** `2025-12-01T15:12:45.585896`
- **Usage:** All timestamps in JSON data, metadata, exports
- **Timezone:** UTC (no timezone suffix for consistency)

**Filename Timestamps:**
- **Format:** `YYYYMMDD_HHMMSS`
- **Example:** `20251201_151234`
- **Usage:** File naming for exports, backups
- **Purpose:** Sortable, filesystem-safe

**Date Metadata (in docs):**
- **Format:** `YYYY-MM-DD`
- **Example:** `2025-12-01`
- **Usage:** Markdown file headers (`**Last Updated:**`)

---

### 3. Locking Patterns

**State Locks:**
- **Pattern:** `.{agent_id}_state.lock`
- **Location:** `data/agents/.{agent_id}_state.lock`
- **Type:** Per-agent exclusive lock
- **Timeout:** 5.0 seconds
- **Retry:** 0.1s intervals (non-blocking)

**Metadata Lock:**
- **Pattern:** `.metadata.lock`
- **Location:** `data/.metadata.lock`
- **Type:** Global exclusive lock (shared metadata file)
- **Timeout:** 5.0 seconds
- **Retry:** 0.1s intervals (non-blocking)

**Lock Acquisition:**
```python
# Standard pattern
lock_fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
lock_acquired = False
start_time = time.time()
timeout = 5.0  # 5 seconds

while time.time() - start_time < timeout:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_acquired = True
        break
    except IOError:
        time.sleep(0.1)  # Wait and retry

if not lock_acquired:
    raise TimeoutError("Lock timeout")
```

**Lock Cleanup:**
- Always release in `finally` block
- Use `fcntl.flock(lock_fd, fcntl.LOCK_UN)`
- Close file descriptor: `os.close(lock_fd)`

---

### 4. Persistence Patterns

**JSON Format:**
- **Indentation:** 2 spaces (`indent=2`)
- **Encoding:** UTF-8 (`encoding='utf-8'`)
- **Sorting:** Sort dictionaries by key for consistency (where applicable)

**File Writing:**
```python
# Standard pattern
with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.flush()  # Ensure buffered data written
    os.fsync(f.fileno())  # Ensure written to disk
```

**Error Handling:**
- Always use try/except around file operations
- Log warnings to stderr (not fail silently)
- Provide fallback behavior when possible
- Never corrupt existing data

---

### 5. Directory Structure

**Standard Directories:**
```
data/
├── agents/              # Per-agent state files
│   ├── {agent_id}_state.json
│   └── .{agent_id}_state.lock
├── agent_metadata.json  # Shared metadata file
├── .metadata.lock       # Metadata
├── history/             # History-only exports
│   └── {agent_id}_history_{timestamp}.{format}
├── exports/             # Complete package exports
│   └── {agent_id}_complete_package_{timestamp}.json
├── dialectic_sessions/  # Dialectic session storage
│   └── {session_id}.json
└── knowledge_graph.json # Knowledge graph storage
```

**Directory Creation:**
- Always use `os.makedirs(dir, exist_ok=True)` or `Path.mkdir(parents=True, exist_ok=True)`
- Create directories before writing files
- Don't fail if directory already exists

---

## Export Standardization

### 1. Export Formats

**JSON Format (Default):**
- **Structure:** Nested JSON with metadata
- **Indentation:** 2 spaces
- **Precision:** Full precision (no rounding)
- **Encoding:** UTF-8

**CSV Format:**
- **Structure:** Tabular with summary section
- **Columns:** `update, timestamp, E, I, S, attention_score, decision, lambda1`
- **Summary:** Agent ID, total updates, total time, lambda1_final
- **Note:** CSV only supported for history-only exports

**Format Selection:**
- **Default:** JSON (if format not specified)
- **History-only:** JSON or CSV
- **Complete package:** JSON only (CSV too complex)

---

### 2. Export Response Structure

**Standard Export Response:**
```json
{
  "success": true,
  "message": "History exported successfully" | "Complete package exported successfully",
  "file_path": "/absolute/path/to/file",
  "filename": "agent_id_history_20251201_151234.json",
  "format": "json" | "csv",
  "agent_id": "agent_id",
  "file_size_bytes": 12345,
  "complete_package": false,
  "layers_included": ["history"] | ["metadata", "history", "validation"]
}
```

**Inline Export Response (get_system_history):**
```json
{
  "success": true,
  "format": "json" | "csv",
  "history": "{JSON string or CSV string}"
}
```

---

### 3. Export File Naming

**History-Only Exports:**
- **Pattern:** `{agent_id}_history_{timestamp}.{format}`
- **Custom:** `{custom_filename}.{format}`
- **Location:** `data/history/`

**Complete Package Exports:**
- **Pattern:** `{agent_id}_complete_package_{timestamp}.json`
- **Custom:** `{custom_filename}_complete.json`
- **Location:** `data/exports/`

**Timestamp Format:** `YYYYMMDD_HHMMSS` (e.g., `20251201_151234`)

---

## Update Standardization

### 1. Update Sequence

**Standard Flow:**
1. **Authentication** (`require_agent_auth`)
   - Verify API key matches agent_id
   - Return error if invalid
   - **Location:** `src/mcp_server_std.py::require_agent_auth()`

2. **Validation** (`validate_agent_state`)
   - Check complexity range [0, 1]
   - Check confidence range [0, 1]
   - Validate ethical_drift format
   - **Location:** `src/mcp_handlers/core.py::handle_process_agent_update()`

3. **Computation** (`monitor.process_update`)
   - Update EISV dynamics
   - Compute coherence, attention_score, phi, verdict
   - Make governance decision
   - **Location:** `src/governance_monitor.py::process_update()`

4. **Persistence** (`save_monitor_state` + `save_metadata`)
   - Save state with locking
   - Update metadata (last_update, total_updates)
   - **Location:** `src/mcp_server_std.py::save_monitor_state()`, `save_metadata()`

5. **Response** (`success_response`)
   - Return metrics, decision, sampling_params
   - Include eisv_labels
   - **Location:** `src/mcp_handlers/utils.py::success_response()`

---

### 2. State Persistence

**State File Structure:**
```json
{
  "E": 0.75,
  "I": 0.92,
  "S": 0.05,
  "V": -0.04,
  "coherence": 0.48,
  "lambda1": 0.123,
  "void_active": false,
  "time": 1.2,
  "update_count": 12,
  "unitaires_state": {...},
  "unitaires_theta": {...},
  "E_history": [0.70, 0.71, ...],
  "I_history": [0.82, 0.83, ...],
  "S_history": [0.15, 0.14, ...],
  "V_history": [-0.01, -0.02, ...],
  "coherence_history": [0.50, 0.51, ...],
  "risk_history": [0.40, 0.39, ...],
  "lambda1_history": [0.125, 0.125, ...],
  "decision_history": ["proceed", "proceed", ...],
  "timestamp_history": ["2025-12-01T15:00:00", ...],
  "pi_integral": 0.0
}
```

**Metadata Structure:**
```json
{
  "agent_id": {
    "agent_id": "agent_id",
    "api_key": "key_hash",
    "status": "active",
    "created": "2025-12-01T15:00:00",
    "last_update": "2025-12-01T15:12:00",
    "total_updates": 12,
    "lifecycle_events": [...],
    "tags": [],
    "notes": ""
  }
}
```

---

### 3. Locking and Concurrency

**Lock Types:**
- **State locks:** Per-agent (prevents concurrent state updates)
- **Metadata lock:** Global (prevents concurrent metadata updates)
- **Session locks:** Per-session (for dialectic sessions)

**Lock Timeout:**
- **Standard:** 5.0 seconds
- **Retry interval:** 0.1 seconds
- **Max retries:** 50 (5.0s / 0.1s)

**Lock Cleanup:**
- Always release in `finally` block
- Handle timeout gracefully (log warning, use fallback)
- Clean up stale locks automatically (`cleanup_stale_locks`)

---

## Error Handling Standardization

### 1. Error Response Format

**Standard Error Response:**
```json
{
  "success": false,
  "error": "Sanitized error message",
  "error_code": "ERROR_CODE",
  "recovery": {
    "action": "What to do",
    "related_tools": ["tool1", "tool2"],
    "workflow": "Step-by-step recovery"
  }
}
```

**Error Sanitization:**
- Remove file paths, line numbers, stack traces
- Log full details to stderr (internal)
- Return sanitized message to client (external)
- **Location:** `src/mcp_handlers/utils.py::error_response()`

---

### 2. Persistence Error Handling

**State Save Errors:**
- Log warning to stderr
- Try fallback (save without lock if timeout)
- Never fail silently
- Never corrupt existing data

**Metadata Save Errors:**
- Log warning to stderr
- Merge with disk state (don't lose data)
- Validate data types before saving
- Handle corrupted files gracefully

**Export Errors:**
- Return error response (don't throw)
- Include file path in error details
- Provide recovery guidance

---

## Validation and Consistency

### 1. Data Validation

**State Validation:**
- E/I/S: [0, 1] range
- V: (-inf, +inf) range
- Coherence: [0, 1] range
- Lambda1: [0, 1] range
- Attention_score: [0, 1] range

**Metadata Validation:**
- Agent ID: Non-empty string
- API key: Non-empty string (hashed)
- Status: Valid lifecycle status
- Timestamps: ISO format

**Export Validation:**
- File size > 0
- Valid JSON/CSV format
- All required fields present
- Timestamps in ISO format

---

### 2. Consistency Checks

**Metadata-History Sync:**
- `meta.total_updates == len(history.E_history)`
- `meta.last_update` matches latest `history.timestamp_history[-1]`
- **Location:** `src/mcp_handlers/export.py::handle_export_to_file()`

**State Consistency:**
- All history arrays same length
- Timestamps match history entries
- **Location:** `src/governance_monitor.py::GovernanceState.validate()`

---

## Automation and Validation

### 1. Export Validation Script

**Location:** `scripts/validate_exports.py` (to be created)

**Checks:**
- File naming consistency
- Timestamp format consistency
- JSON structure validation
- Metadata-history sync validation

### 2. Update Flow Validation

**Pre-Update Checks:**
- Authentication valid
- Inputs validated
- State file writable

**Post-Update Checks:**
- State persisted successfully
- Metadata updated
- Response includes all required fields

---

## Migration and Backward Compatibility

### 1. File Location Migration

**State Files:**
- Old: `data/{agent_id}_state.json`
- New: `data/agents/{agent_id}_state.json`
- **Migration:** Automatic on first access
- **Location:** `src/mcp_server_std.py::get_state_file()`

### 2. Format Migration

**Export Formats:**
- Old: `risk_history` field
- New: `attention_history` (primary), `risk_history` (backward compat)
- **Migration:** Both fields included in exports

**CSV Columns:**
- Old: `risk` column
- New: `attention_score` column
- **Migration:** Column renamed, data unchanged

---

## Best Practices

### 1. Export Best Practices

- **Use complete_package=true** for archival/backup
- **Use history-only** for analysis/visualization
- **Include timestamps** in all exports
- **Validate exports** before using in external tools

### 2. Update Best Practices

- **Always authenticate** before updating
- **Validate inputs** before processing
- **Use locking** for all persistence operations
- **Handle errors gracefully** (don't corrupt state)

### 3. Persistence Best Practices

- **Always flush and fsync** after writing
- **Use consistent JSON formatting** (indent=2)
- **Sort dictionaries** for consistency (where applicable)
- **Handle corrupted files** gracefully

---

## Related Documentation

- [METRICS_REPORTING_STANDARDIZATION.md](METRICS_REPORTING_STANDARDIZATION.md) - Metrics flow standardization
- [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md) - Documentation formatting
- `src/mcp_handlers/export.py` - Export handlers implementation
- `src/mcp_server_std.py` - Persistence implementation

---

**Remember:** Consistency improves reliability. Standardize for elegance, not restriction.

