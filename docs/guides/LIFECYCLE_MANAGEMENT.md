# Agent Lifecycle Management Guide

**Last Updated:** December 1, 2025  
**Status:** Production-ready, comprehensive lifecycle system

---

## Overview

The UNITARES Governance Framework includes a complete agent lifecycle management system that tracks agent status, manages transitions, and provides automatic cleanup and recovery mechanisms.

---

## Lifecycle States

### Active States

**`active`** (Default)
- Agent is actively using the system
- Can process updates, receive governance decisions
- State persists across sessions
- **Transition to:** `archived`, `paused`, `waiting_input`

**`waiting_input`**
- Agent has completed a response and is waiting for user input
- Explicitly marked via `mark_response_complete`
- Prevents false "stuck" detection
- **Transition to:** `active` (on next update)

### Inactive States

**`archived`**
- Agent is done for now but may return
- State persists on disk
- Monitor can be unloaded from memory (`keep_in_memory=False`)
- **Auto-resume:** Any engagement resumes archived agents
- **Transition to:** `active` (auto-resume), `deleted`

**`paused`**
- Circuit breaker triggered (governance threshold exceeded)
- Requires explicit recovery (dialectic review or direct resume)
- State persists, monitor stays in memory
- **Transition to:** `active` (via recovery), `archived`

**`deleted`**
- Agent permanently removed
- Protected for pioneer agents (cannot be deleted)
- Data archived before deletion (if `backup_first=True`)
- **Transition to:** None (permanent)

---

## Lifecycle Transitions

### Automatic Transitions

**Auto-Resume Archived Agents**
```python
# Any engagement resumes archived agents
if meta.status == "archived":
    meta.status = "active"
    meta.archived_at = None
    meta.add_lifecycle_event("resumed", "Auto-resumed on engagement")
```

**Auto-Archive Test Agents**
- Test/demo agents auto-archive after inactivity threshold (default: 6 hours)
- Agents with ≤2 updates archived immediately
- Runs automatically on server startup

**Status Validation**
- Paused agents cannot process updates (must resume first)
- Deleted agents cannot be used
- Status checked before every operation

### Manual Transitions

**Archive Agent**
```python
# Via archive_agent tool
{
    "agent_id": "my_agent",
    "reason": "Done for now",
    "keep_in_memory": false  # Optional: unload from memory
}
```

**Delete Agent**
```python
# Via delete_agent tool (requires confirmation)
{
    "agent_id": "my_agent",
    "confirm": true,
    "backup_first": true  # Optional: archive before deletion
}
```

**Mark Response Complete**
```python
# Via mark_response_complete tool
{
    "agent_id": "my_agent",
    "api_key": "...",
    "summary": "Completed analysis"  # Optional
}
```

---

## Lifecycle Events

Every status change is tracked with lifecycle events:

```python
{
    "event": "archived",
    "timestamp": "2025-12-01T12:00:00",
    "reason": "Done for now"
}
```

**Event Types:**
- `created` - Agent first registered
- `archived` - Agent archived
- `resumed` - Agent resumed (auto or manual)
- `paused` - Circuit breaker triggered
- `deleted` - Agent deleted
- `response_completed` - Agent marked as waiting for input
- `metadata_updated` - Tags or notes updated

**Access:**
- Via `get_agent_metadata` tool
- Included in agent metadata exports
- Full history preserved

---

## Memory Management

### Monitor Loading

**Lazy Loading:**
- Monitors loaded on-demand when needed
- State loaded from disk if not in memory
- Allows querying agents without recent updates

**Memory Unloading:**
- Archived agents can be unloaded (`keep_in_memory=False`)
- State persists on disk
- Monitor reloaded automatically when needed

**Memory Efficiency:**
- Only active/paused agents stay in memory
- Archived agents can be unloaded
- Test agents auto-archived and unloaded

---

## Cleanup Mechanisms

### Automatic Cleanup

**1. Test Agent Auto-Archive**
- **Trigger:** Server startup + inactivity threshold
- **Threshold:** 6 hours default (configurable)
- **Criteria:**
  - Test/demo agents (IDs starting with `test_` or `demo_`)
  - Agents with ≤2 updates archived immediately
  - Others archived after inactivity threshold
- **Tool:** `archive_old_test_agents`

**2. Stale Lock Cleanup**
- **Trigger:** Server startup
- **Criteria:** Lock files older than 5 minutes from dead processes
- **Tool:** `cleanup_stale_locks`

**3. Zombie Process Cleanup**
- **Trigger:** Server startup
- **Criteria:** Processes with PID files but process no longer exists
- **Automatic:** Built into server startup

### Manual Cleanup

**Archive Old Agents**
```python
# Via archive_old_test_agents tool
{
    "max_age_hours": 6  # Optional: custom threshold
}
```

**Clean Stale Locks**
```python
# Via cleanup_stale_locks tool
{
    "max_age_seconds": 300,  # Optional: default 5 minutes
    "dry_run": false  # Optional: preview without cleaning
}
```

---

## Recovery Mechanisms

### Circuit Breaker Recovery

**When:** Agent status becomes `paused` (circuit breaker triggered)

**Recovery Options:**

1. **Dialectic Review** (Peer review)
   - Peer review via `request_dialectic_review`
   - Thesis → Antithesis → Synthesis protocol
   - Collaborative recovery

2. **Direct Resume** (Simple cases)
   - Via `direct_resume_if_safe`
   - Tier 1 recovery for low-risk scenarios
   - Fast recovery (< 1 second)

3. **Self Recovery** (No reviewers available)
   - Via `self_recovery`
   - Tier 2.3 recovery option
   - System-generated antithesis

**Safety Checks:**
- Coherence > 0.40
- Attention score < 0.60
- Void not active
- Status in [paused, waiting_input, moderate]

---

## Lifecycle Tools

### Core Lifecycle Tools

**`list_agents`**
- List all agents with lifecycle metadata
- Filter by status, health, loaded state
- Includes lifecycle events summary

**`get_agent_metadata`**
- Complete metadata for single agent
- Lifecycle events history
- Current state and computed fields

**`update_agent_metadata`**
- Update tags and notes
- Tags replaced, notes can append or replace
- Adds lifecycle event

### Status Management Tools

**`archive_agent`**
- Archive agent for long-term storage
- Optionally unload from memory
- Can be resumed later

**`delete_agent`**
- Delete agent permanently
- Protected for pioneer agents
- Optionally backup before deletion

**`mark_response_complete`**
- Mark agent as waiting for input
- Prevents false stuck detection
- Lightweight status update

**`direct_resume_if_safe`**
- Direct resume without dialectic
- Tier 1 recovery for simple cases
- Fast recovery mechanism

### Cleanup Tools

**`archive_old_test_agents`**
- Auto-archive stale test agents
- Configurable threshold
- Runs automatically on startup

**`cleanup_stale_locks`**
- Clean up stale lock files
- From crashed/killed processes
- Prevents lock accumulation

---

## Lifecycle Patterns

### Onboarding Pattern

```
1. get_agent_api_key → Creates agent (status: active)
2. process_agent_update → First update logged
3. mark_response_complete → Mark as waiting_input (optional)
```

### Active Usage Pattern

```
1. process_agent_update → Status: active
2. Get governance decision
3. Continue work or mark_response_complete
```

### Archival Pattern

```
1. archive_agent → Status: archived
2. (Optional) keep_in_memory=False → Unload from memory
3. Auto-resume on next engagement
```

### Recovery Pattern

```
1. Circuit breaker → Status: paused
2. request_dialectic_review → Initiate recovery
3. submit_thesis → Agent's understanding
4. submit_antithesis → Reviewer's observations
5. submit_synthesis → Negotiate conditions
6. Resolution → Status: active (with conditions)
```

---

## Best Practices

### For Agents

1. **Use `mark_response_complete`** when done with a response
   - Prevents false stuck detection
   - Signals waiting for input

2. **Archive when done** instead of deleting
   - Can be resumed later
   - Preserves history

3. **Use descriptive agent IDs**
   - Avoid generic names like "test"
   - Include purpose or session info

### For System Administrators

1. **Monitor lifecycle events**
   - Check for stuck agents
   - Review recovery patterns
   - Track archival patterns

2. **Regular cleanup**
   - Archive old test agents
   - Clean stale locks
   - Monitor memory usage

3. **Understand recovery options**
   - Use dialectic for complex cases
   - Use direct resume for simple cases
   - Monitor recovery success rates

---

## Lifecycle Metadata Structure

```json
{
    "agent_id": "my_agent",
    "status": "active",
    "created_at": "2025-12-01T10:00:00",
    "last_update": "2025-12-01T12:00:00",
    "archived_at": null,
    "paused_at": null,
    "total_updates": 42,
    "lifecycle_events": [
        {
            "event": "created",
            "timestamp": "2025-12-01T10:00:00",
            "reason": "Initial registration"
        },
        {
            "event": "archived",
            "timestamp": "2025-12-01T11:00:00",
            "reason": "Done for now"
        },
        {
            "event": "resumed",
            "timestamp": "2025-12-01T12:00:00",
            "reason": "Auto-resumed on engagement"
        }
    ],
    "tags": ["production", "critical"],
    "notes": "Main production agent"
}
```

---

## Lifecycle Health Monitoring

### Health Indicators

**Active Agents:**
- Recent updates (within last hour)
- Healthy governance metrics
- No stuck patterns

**Archived Agents:**
- Clean archival (proper reason logged)
- Can be resumed if needed
- Memory unloaded if appropriate

**Paused Agents:**
- Recovery in progress or needed
- Circuit breaker triggered
- Requires attention

**Stuck Detection:**
- No updates for extended period
- Repeated same decision
- Loop patterns detected

---

## Related Tools

- **`observe_agent`** - Detailed lifecycle analysis
- **`compare_agents`** - Compare lifecycle patterns
- **`detect_anomalies`** - Find unusual lifecycle patterns
- **`get_telemetry_metrics`** - System-wide lifecycle statistics

---

## Summary

The lifecycle management system provides:

✅ **Complete state tracking** - All status changes logged  
✅ **Automatic cleanup** - Test agents, stale locks, zombie processes  
✅ **Recovery mechanisms** - Dialectic, direct resume, self-recovery  
✅ **Memory efficiency** - Unload archived agents when needed  
✅ **Auto-resume** - Archived agents resume on engagement  
✅ **Protection** - Pioneer agents cannot be deleted  
✅ **Transparency** - Full lifecycle event history  

**Status:** Production-ready, comprehensive, and well-tested.

---

**Related:** `docs/meta/LIFECYCLE_PERSPECTIVE.md`, `src/mcp_handlers/lifecycle.py`

