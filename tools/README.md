# MCP Tools - Auto-Generated Documentation
**⚠️ IMPORTANT: This file is auto-generated. Do not edit manually.**
**Last Generated:** 2025-12-08 19:09:25
**Total Tools:** 47
---
## 🚀 Quick Start
**If you have MCP access (Cursor, Claude Desktop, etc.):**
- ✅ **Use MCP tools directly** - Full feature set via MCP protocol
- ✅ **Discovery:** Call `list_tools()` to see all available tools
- ✅ **No scripts needed** - Tools are the primary interface
---
## 📋 Table of Contents

- [🎯 Core Governance](#core)
- [🔄 Agent Lifecycle](#lifecycle)
- [📊 Observability](#observability)
- [⚙️ Configuration](#config)
- [📤 Export](#export)
- [🧠 Knowledge Graph](#knowledge-graph)
- [💭 Dialectic Protocol](#dialectic)
- [🔧 Admin & Health](#admin)

---

## 🎯 Core Governance
*Main governance cycle operations*

### `get_governance_metrics`

**Description:** Get current governance state and metrics for an agent without updating state

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/core.py`

---

### `process_agent_update`

**Description:** Handle process_agent_update tool - complex handler with authentication and state management

**Timeout:** 60.0s

**Details:**
```
Handle process_agent_update tool - complex handler with authentication and state management

Share your work and get supportive feedback. This is your companion tool for checking in 
and understanding your state. Includes automatic timeout protection (60s default).
```

**Source:** `src/mcp_handlers/core.py`

---

### `simulate_update`

**Description:** Handle simulate_update tool - dry-run governance cycle without persisting state

**Timeout:** 30.0s

**Source:** `src/mcp_handlers/core.py`

---


## 🔄 Agent Lifecycle
*Agent creation, archival, and management*

### `archive_agent`

**Description:** Archive an agent for long-term storage

**Timeout:** 15.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `archive_old_test_agents`

**Description:** Manually archive old test/demo agents that haven't been updated recently

**Timeout:** 30.0s (rate limit exempt)

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `delete_agent`

**Description:** Handle delete_agent tool - delete agent and archive data (protected: cannot delete pioneer agents)

**Timeout:** 15.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `direct_resume_if_safe`

**Description:** Direct resume without dialectic if agent state is safe. Tier 1 recovery for simple stuck scenarios.

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `get_agent_api_key`

**Description:** Get or generate API key for an agent

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `get_agent_metadata`

**Description:** Get complete metadata for an agent including lifecycle events, current state, and computed fields

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `list_agents`

**Description:** List all agents currently being monitored with lifecycle metadata and health status

**Timeout:** 15.0s (rate limit exempt)

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `mark_response_complete`

**Description:** Mark agent as having completed response, waiting for input

**Timeout:** 5.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---

### `update_agent_metadata`

**Description:** Update agent tags and notes

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/lifecycle.py`

---


## 📊 Observability
*Monitoring, metrics, and anomaly detection*

### `aggregate_metrics`

**Description:** Get fleet-level health overview

**Timeout:** 15.0s

**Source:** `src/mcp_handlers/observability.py`

---

### `compare_agents`

**Description:** Compare governance patterns across multiple agents

**Timeout:** 20.0s

**Source:** `src/mcp_handlers/observability.py`

---

### `detect_anomalies`

**Description:** Detect anomalies across agents

**Timeout:** 20.0s

**Source:** `src/mcp_handlers/observability.py`

---

### `observe_agent`

**Description:** Observe another agent's governance state with pattern analysis

**Timeout:** 15.0s

**Source:** `src/mcp_handlers/observability.py`

---


## ⚙️ Configuration
*Threshold and configuration management*

### `get_thresholds`

**Description:** Get current governance threshold configuration

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/config.py`

---

### `set_thresholds`

**Description:** Set runtime threshold overrides - requires elevated permissions

**Timeout:** 15.0s

**Source:** `src/mcp_handlers/config.py`

---


## 📤 Export
*Data export and history retrieval*

### `export_to_file`

**Description:** Export governance history to a file in the server's data directory

**Timeout:** 60.0s

**Source:** `src/mcp_handlers/export.py`

---

### `get_system_history`

**Description:** Export complete governance history for an agent

**Timeout:** 30.0s

**Source:** `src/mcp_handlers/export.py`

---


## 🧠 Knowledge Graph
*Fast, indexed knowledge storage*

### `find_similar_discoveries_graph`

**Description:** Find similar discoveries by tag overlap - fast tag-based search

**Timeout:** 15.0s (rate limit exempt)

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `get_discovery_details`

**Description:** Get full details for a specific discovery - use after search to drill down

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `get_knowledge_graph`

**Description:** Get all knowledge for an agent - summaries only (use get_discovery_details for full content)

**Timeout:** 15.0s (rate limit exempt)

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `leave_note`

**Description:** Leave a quick note in the knowledge graph - minimal friction contribution.

**Timeout:** 10.0s

**Details:**
```
Leave a quick note in the knowledge graph - minimal friction contribution.

Just agent_id + text + optional tags. Auto-sets type='note', severity='low'.
For when you want to jot something down without the full store_knowledge_graph ceremony.
```

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `list_knowledge_graph`

**Description:** List knowledge graph statistics - full transparency

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `reply_to_question`

**Description:** Reply to a question in the knowledge graph - creates an answer linked to the question

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `search_knowledge_graph`

**Description:** Search knowledge graph - fast indexed queries, summaries only (use get_discovery_details for full content)

**Timeout:** 15.0s (rate limit exempt)

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `store_knowledge_graph`

**Description:** Store knowledge discovery in graph - fast, non-blocking, transparent

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/knowledge_graph.py`

---

### `update_discovery_status_graph`

**Description:** Update discovery status - fast graph update

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/knowledge_graph.py`

---


## 💭 Dialectic Protocol
*Circuit breaker recovery and collaborative review*

### `get_dialectic_session`

**Description:** Get current state of a dialectic session.

**Timeout:** 10.0s (rate limit exempt)

**Details:**
```
Get current state of a dialectic session.

Can find sessions by session_id OR by agent_id (paused or reviewer).
Automatically checks for timeouts and stuck reviewers.

Args:
    session_id: Dialectic session ID (optional if agent_id provided)
    agent_id: Agent ID to find sessions for (optional if session_id provided)
             Finds sessions where agent is paused_agent_id or reviewer_agent_id
    check_timeout: Whether to check for timeouts (default: True)

Returns:
    Full session state including transcript, or list of sessions if agent_id provided
```

**Source:** `src/mcp_handlers/dialectic.py`

---

### `request_dialectic_review`

**Description:** Request a dialectic review for a paused/critical agent OR an agent stuck in loops OR a discovery dispute.

**Timeout:** 15.0s

**Details:**
```
Request a dialectic review for a paused/critical agent OR an agent stuck in loops OR a discovery dispute.

Selects a healthy reviewer agent and initiates dialectic session.
Can be used for:
- Paused agents (circuit breaker triggered)
- Agents stuck in repeated loops (loop cooldown active)
- Discovery disputes/corrections (if discovery_id provided)
- Any agent needing peer assistance

Args:
    agent_id: ID of agent requesting review (paused, loop-stuck, or disputing discovery)
    reason: Reason for review request (e.g., "Circuit breaker triggered", "Stuck in loops", "Discovery seems incorrect", etc.)
    api_key: Agent's API key for authentication
    discovery_id: Optional - ID of discovery being disputed/corrected
    dispute_type: Optional - "dispute", "correction", "verification" (default: None for recovery)

Returns:
    Session info with reviewer_id and session_id
```

**Source:** `src/mcp_handlers/dialectic.py`

---

### `self_recovery` (deprecated)

**Description:** Allow agent to recover without reviewer (for when no reviewers available).

**Timeout:** 15.0s

**Details:**
```
Allow agent to recover without reviewer (for when no reviewers available).

Flow:
1. Agent submits thesis
2. System generates antithesis based on metrics
3. Agent submits synthesis (auto-merged)
4. Auto-resolve if safe

Args:
    agent_id: Agent ID to recover
    api_key: Agent's API key
    root_cause: Agent's understanding of what happened
    proposed_conditions: Conditions for resumption
    reasoning: Explanation

Returns:
    Recovery result with system-generated antithesis
```

**Status:** Deprecated / may not be exposed in SSE.

**Use instead:** `request_dialectic_review` with:
- `reviewer_mode="self"` (self-recovery fallback)
- `auto_progress=true` (streamlined flow)

---

### `smart_dialectic_review` (deprecated)

**Description:** Smart dialectic that auto-progresses when possible.

**Timeout:** 20.0s

**Details:**
```
Smart dialectic that auto-progresses when possible.

Flow:
1. Request review → Auto-select reviewer
2. Auto-generate thesis from agent state (if agent provides minimal input)
3. Reviewer submits antithesis (or auto-generate if reviewer unavailable)
4. Auto-merge synthesis if conditions are compatible
5. Execute if safe

Reduces manual steps by 50-70% compared to full dialectic.

Args:
    agent_id: Agent ID requesting review
    api_key: Agent's API key
    reason: Reason for review (optional - auto-generated if not provided)
    root_cause: Root cause (optional - auto-generated from state if not provided)
    proposed_conditions: Proposed conditions (optional - auto-generated if not provided)
    reasoning: Explanation (optional - auto-generated if not provided)
    auto_progress: Whether to auto-progress through phases (default: True)

Returns:
    Session info or final resolution if auto-progressed
```

**Status:** Deprecated / replaced by `request_dialectic_review(auto_progress=true)`.

---

### `submit_antithesis`

**Description:** Reviewer agent submits antithesis: "What I observe, my concerns"

**Timeout:** 10.0s

**Details:**
```
Reviewer agent submits antithesis: "What I observe, my concerns"

Args:
    session_id: Dialectic session ID
    agent_id: Reviewer agent ID
    api_key: Reviewer's API key
    observed_metrics: Metrics observed about paused agent
    concerns: List of concerns
    reasoning: Natural language explanation

Returns:
    Status with next phase
```

**Source:** `src/mcp_handlers/dialectic.py`

---

### `submit_synthesis`

**Description:** Either agent submits synthesis proposal during negotiation.

**Timeout:** 15.0s

**Details:**
```
Either agent submits synthesis proposal during negotiation.

Args:
    session_id: Dialectic session ID
    agent_id: Agent ID (either paused or reviewer)
    api_key: Agent's API key
    proposed_conditions: Proposed resumption conditions
    root_cause: Agreed understanding of root cause
    reasoning: Explanation of proposal
    agrees: Whether this agent agrees with current proposal (bool)

Returns:
    Status with convergence info
```

**Source:** `src/mcp_handlers/dialectic.py`

---

### `submit_thesis`

**Description:** Paused agent submits thesis: "What I did, what I think happened"

**Timeout:** 10.0s

**Details:**
```
Paused agent submits thesis: "What I did, what I think happened"

Args:
    session_id: Dialectic session ID
    agent_id: Paused agent ID
    api_key: Agent's API key
    root_cause: Agent's understanding of what caused the issue
    proposed_conditions: List of conditions for resumption
    reasoning: Natural language explanation

Returns:
    Status with next phase
```

**Source:** `src/mcp_handlers/dialectic.py`

---


## 🔧 Admin & Health
*System administration and health checks*

### `backfill_calibration_from_dialectic`

**Description:** Retroactively update calibration from historical resolved verification-type dialectic sessions.

**Timeout:** 30.0s (rate limit exempt)

**Details:**
```
Retroactively update calibration from historical resolved verification-type dialectic sessions.

This processes all existing resolved verification sessions that were created before
automatic calibration was implemented, ensuring they contribute to calibration.

USE CASES:
- One-time migration after implementing automatic calibration
- Backfill historical peer verification data
- Ensure all resolved verification sessions contribute to calibration

RETURNS:
{
  "success": true,
  "processed": int,
  "updated": int,
  "errors": int,
  "sessions": [{"session_id": "...", "agent_id": "...", "status": "..."}]
}
```

**Source:** `src/mcp_handlers/admin.py`

---

### `check_calibration`

**Description:** Check calibration of confidence estimates

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `cleanup_stale_locks`

**Description:** Clean up stale lock files that are no longer held by active processes

**Timeout:** 30.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `get_server_info`

**Description:** Get MCP server version, process information, and health status

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `get_telemetry_metrics`

**Description:** Get comprehensive telemetry metrics: skip rates, confidence distributions, calibration status

**Timeout:** 15.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `get_tool_usage_stats`

**Description:** Get tool usage statistics to identify which tools are actually used vs unused

**Timeout:** 15.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `get_workspace_health`

**Description:** Handle get_workspace_health tool - comprehensive workspace health status

**Timeout:** 30.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `health_check`

**Description:** Handle health_check tool - quick health check of system components

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `list_tools`

**Description:** List all available governance tools with descriptions and categories

**Timeout:** 10.0s (rate limit exempt)

**Source:** `src/mcp_handlers/admin.py`

---

### `reset_monitor`

**Description:** Reset governance state for an agent

**Timeout:** 10.0s

**Source:** `src/mcp_handlers/admin.py`

---

### `update_calibration_ground_truth`

**Description:** Update calibration with ground truth after human review

**Timeout:** 10.0s

**Details:**
```
Update calibration with ground truth after human review

Supports two modes:
1. Direct mode: Provide confidence, predicted_correct, actual_correct directly
2. Timestamp mode: Provide timestamp (and optional agent_id), actual_correct. 
   System looks up confidence and decision from audit log.
```

**Source:** `src/mcp_handlers/admin.py`

---


## 📚 Additional Resources

- **Onboarding:** `docs/guides/ONBOARDING.md`
- **Architecture:** `docs/reference/HANDLER_ARCHITECTURE.md`
- **Runtime Discovery:** Call `list_tools()` MCP tool for up-to-date tool list

---

**Auto-generated by:** `scripts/generate_tool_docs.py`  
**Regenerate:** `python3 scripts/generate_tool_docs.py`
