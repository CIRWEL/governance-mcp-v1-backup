# Wiggum Research Findings

This file tracks research iterations on the UNITARES governance-mcp codebase. Each iteration investigates one area and implements one improvement when a safe, impactful change is identified.

## Iteration 1: Consolidate health_check DB round-trips (4 → 1)

**File:** `src/db/postgres_backend.py`, lines 250-261
**Category:** Performance
**Date:** 2026-03-07

### Problem

The `PostgresBackend.health_check()` method made 4 sequential database round-trips using individual `fetchval` calls over a single connection. Each call was a separate network round-trip to the PostgreSQL server:

1. `SELECT 1` — basic connectivity test
2. `SELECT MAX(version) FROM core.schema_migrations` — retrieve the current schema migration version
3. `SELECT COUNT(*) FROM core.identities` — count total registered agent identities
4. `SELECT COUNT(*) FROM core.sessions WHERE is_active = TRUE` — count currently active sessions

The first query (`SELECT 1`) is entirely redundant because if any of the subsequent queries succeed, connectivity is already proven. The remaining three queries are independent scalar queries that can be combined into a single SQL statement using scalar subqueries, which PostgreSQL evaluates efficiently within a single round-trip.

While the health_check endpoint is not on the hottest path (it is not called on every `process_agent_update`), it is called by the admin health check handler, by the parallel health check drill tests, and by monitoring integrations. Reducing 4 round-trips to 1 provides a measurable latency improvement for these callers — roughly 3x fewer network round-trips per health check invocation.

### Investigation

Before making the change, the following investigation was performed:

- Verified that no unit tests mock the individual `fetchval` calls within `health_check`. The only tests that exercise this method are integration tests in `test_postgres_backend_integration.py` which use a live database and check the response shape (keys and value types), not the number of internal queries.
- Confirmed that the response dictionary shape is identical after the change — all keys (`status`, `backend`, `pool_size`, `pool_idle`, `pool_free`, `pool_max`, `schema_version`, `identity_count`, `active_session_count`, `age_available`, `age_graph`) remain unchanged.
- Verified that asyncpg's `fetchrow` method returns a `Record` object that supports dictionary-style key access, making the transition from `fetchval` to `fetchrow` straightforward.
- Checked that the scalar subquery pattern (`SELECT (SELECT ...) AS name, (SELECT ...) AS name2`) is standard PostgreSQL and works correctly when any individual subquery returns NULL (e.g., empty `schema_migrations` table).

### Fix

Replaced all 4 sequential `fetchval` calls with a single `fetchrow` call using scalar subqueries:

```sql
SELECT
    (SELECT MAX(version) FROM core.schema_migrations) AS schema_version,
    (SELECT COUNT(*) FROM core.identities) AS identity_count,
    (SELECT COUNT(*) FROM core.sessions WHERE is_active = TRUE) AS active_session_count
```

The results are then extracted from the row using dictionary key access:

```python
row = await conn.fetchrow(query)
version = row["schema_version"]
identity_count = row["identity_count"]
session_count = row["active_session_count"]
```

**Before:** 4 DB round-trips per health check
**After:** 1 DB round-trip per health check (plus 1 for the AGE `LOAD` test)
**Risk:** None — response shape unchanged, no unit tests mock the individual calls
**Tests:** 5478 passed, 35 skipped

### Additional findings catalogued for future iterations

The following findings were identified during research but not actioned in this iteration, either because they require broader changes or have lower impact:

**Dead code in production (tested but unused):**
- `interpret_eisv_quick()` in `src/governance_state.py:577` — defined and tested but never called from any production code path. Only imported in `tests/test_governance_state.py`.
- `explain_anomaly()` and `generate_recovery_coaching()` in `src/mcp_handlers/llm_delegation.py:185,225` — defined and tested but never called from production handlers.
- `create_model_inference_client()` in `src/mcp_handlers/model_inference.py:351` — factory function with no production callers.
- Dead import of `_generate_coherence_recommendation` in `src/mcp_handlers/cirs_protocol.py:99` — imported but never used within that module.
- `auto_archive_old_test_agents()` in `src/agent_lifecycle.py:40` — defined but never called in any production code path.
- Several functions in `src/mcp_handlers/tool_stability.py` (lines 389-414): `get_tool_aliases`, `get_migration_guide`, `is_stable_tool`, `is_experimental_tool` have no external callers in production.

**Code duplication:**
- `_safe_float` helper is duplicated in `src/mcp_handlers/lifecycle.py:39` (default=0.0) and `src/mcp_handlers/self_recovery.py:61` (default=0.5) with different default values. Both are used within their respective modules.

**Intentional design (not a bug):**
- `pool_free` and `pool_idle` both return `self._pool.get_idle_size()` in the health check response (lines 276-277). The comment documents this as an intentional alias for backward compatibility.
