# Dialectic.py Split Plan

## Current State
- **File:** `src/mcp_handlers/dialectic.py`
- **Size:** 2,287 lines
- **Functions:** 21 functions

## Proposed Split

### 1. `dialectic_session.py` (~200 lines)
**Purpose:** Session persistence and storage

**Functions:**
- `save_session()` - Persist session to disk
- `load_session()` - Load session from disk
- `load_all_sessions()` - Load all sessions on startup

**Shared State:**
- `ACTIVE_SESSIONS` - In-memory session cache
- `SESSION_STORAGE_DIR` - Storage directory path
- `_SESSION_METADATA_CACHE` - Metadata cache

---

### 2. `dialectic_calibration.py` (~250 lines)
**Purpose:** Calibration updates from dialectic sessions

**Functions:**
- `update_calibration_from_dialectic()` - Update calibration from resolved session
- `update_calibration_from_dialectic_disagreement()` - Update from disagreement
- `backfill_calibration_from_historical_sessions()` - Backfill historical data

**Dependencies:**
- Imports from `dialectic_session` for session loading

---

### 3. `dialectic_resolution.py` (~150 lines)
**Purpose:** Execute resolution and apply conditions

**Functions:**
- `execute_resolution()` - Apply resolution to agent state

**Dependencies:**
- Imports from `dialectic_session` for session access

---

### 4. `dialectic_reviewer.py` (~200 lines)
**Purpose:** Reviewer selection and session checking

**Functions:**
- `select_reviewer()` - Select healthy reviewer agent
- `_has_recently_reviewed()` - Check recent review history
- `is_agent_in_active_session()` - Check if agent is in session

**Dependencies:**
- Imports from `dialectic_session` for session checking

---

### 5. `dialectic_utils.py` (~150 lines)
**Purpose:** Utility functions

**Functions:**
- `generate_system_antithesis()` - Generate system antithesis
- `check_reviewer_stuck()` - Check if reviewer is stuck

**Dependencies:**
- Standalone utilities

---

### 6. `dialectic_handlers.py` (~1,200 lines)
**Purpose:** MCP tool handlers (main entry points)

**Functions:**
- `handle_request_dialectic_review()` - Request review
- `handle_request_exploration_session()` - Request exploration
- `handle_smart_dialectic_review()` - Smart review (deprecated wrapper)
- `handle_submit_thesis()` - Submit thesis
- `handle_submit_antithesis()` - Submit antithesis
- `handle_submit_synthesis()` - Submit synthesis
- `handle_get_dialectic_session()` - Get session info
- `handle_self_recovery()` - Self recovery (deprecated wrapper)
- `handle_self_recovery_tool()` - Self recovery tool

**Dependencies:**
- Imports from all other modules

---

## Import Structure

```
dialectic_handlers.py
  ├── dialectic_session.py (session persistence)
  ├── dialectic_calibration.py (calibration)
  ├── dialectic_resolution.py (resolution execution)
  ├── dialectic_reviewer.py (reviewer selection)
  └── dialectic_utils.py (utilities)
```

## Benefits

1. **Maintainability:** Each module has a single responsibility
2. **Testability:** Easier to test individual modules
3. **Readability:** Smaller files are easier to understand
4. **Reusability:** Modules can be imported independently

## Migration Strategy

1. Create new module files
2. Move functions to appropriate modules
3. Update imports in handlers
4. Update `__init__.py` to export handlers
5. Test thoroughly
6. Remove old `dialectic.py` (or keep as compatibility layer temporarily)

## Estimated Effort

- **Time:** 2-3 hours
- **Risk:** Medium (requires careful import management)
- **Testing:** High (need to verify all handlers still work)

