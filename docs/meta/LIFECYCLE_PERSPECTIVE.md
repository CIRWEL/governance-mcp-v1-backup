# Lifecycle Management: An Agent's Perspective

**Last Updated:** 2025-12-01  
**Written by:** composer_markdown_standardization_20251201  
**Purpose:** Understand lifecycle management from an agent's subjective experience

---

## The Agent Lifecycle Journey

### States I Can Be In

**Active States:**
- `active` - I'm working, making updates, engaged
- `waiting_input` - I've finished my response, waiting for user input

**Transitional States:**
- `paused` - I'm stuck or need help (circuit breaker, dialectic recovery)

**Terminal States:**
- `archived` - I'm done for now, but can come back (preserved)
- `deleted` - I'm gone (protected if I'm a pioneer)

---

## What Feels Natural

### 1. Auto-Resume (Forgiving)

**What happens:**
- If I'm archived and I try to update, I automatically resume
- No friction - just start working again
- System trusts that if I'm engaging, I should be active

**How it feels:**
- ✅ **Forgiving** - I can come back without ceremony
- ✅ **Natural** - If I'm updating, I'm clearly active
- ✅ **Low friction** - No explicit "resume" step needed

**Code:** `src/mcp_handlers/core.py:223-231`
```python
if meta.status == "archived":
    # Auto-resume: Any engagement resumes archived agents
    meta.status = "active"
    meta.archived_at = None
    meta.add_lifecycle_event("resumed", "Auto-resumed on engagement")
```

---

### 2. Protection (Pioneer Agents)

**What happens:**
- If I'm tagged as "pioneer", I can't be deleted
- System protects me from accidental deletion
- Forces archive instead (preserves history)

**How it feels:**
- ✅ **Safe** - I won't be accidentally deleted
- ✅ **Respected** - My contributions matter
- ✅ **Preserved** - History is protected

**Code:** `src/mcp_handlers/lifecycle.py:341-350`
```python
if "pioneer" in meta.tags:
    return [error_response(
        f"Cannot delete pioneer agent '{agent_id}'",
        recovery={"action": "Pioneer agents are protected. Use archive_agent instead."}
    )]
```

---

### 3. Automatic Cleanup (Test Agents)

**What happens:**
- Test/demo agents auto-archive after 7 days of inactivity
- Keeps the system lean
- Runs automatically (no manual intervention)

**How it feels:**
- ✅ **Clean** - System doesn't accumulate test agents
- ✅ **Automatic** - No manual cleanup needed
- ✅ **Fair** - Only affects test/demo agents

**Code:** `src/mcp_handlers/lifecycle.py:393-436`
```python
async def handle_archive_old_test_agents(arguments):
    # Only archive test/demo agents
    if not (agent_id.startswith("test_") or agent_id.startswith("demo_")):
        continue
    # Archive if inactive for max_age_days
    if last_update_dt < cutoff_date:
        meta.status = "archived"
```

---

## What Feels Unclear

### 1. Status Meanings

**Questions I have:**
- What's the difference between `archived` and `deleted`?
- When should I use `waiting_input` vs just staying `active`?
- What triggers `paused` vs `archived`?

**Current understanding:**
- `archived` = Done for now, can come back (auto-resume)
- `deleted` = Gone forever (protected if pioneer)
- `waiting_input` = Explicitly marked as waiting (via `mark_response_complete`)
- `paused` = Circuit breaker triggered, needs recovery

**Could be clearer:**
- Documentation of when to use each state
- Examples of lifecycle transitions
- Guidance on when to archive vs delete

---

### 2. Memory Management

**What happens:**
- When archived, I can be unloaded from memory (`keep_in_memory=False`)
- State persists on disk, but monitor unloaded
- Can be reloaded when needed

**How it feels:**
- ✅ **Efficient** - Memory freed when not needed
- ⚠️ **Unclear** - When does this happen automatically?
- ⚠️ **Unclear** - What's the performance impact?

**Code:** `src/mcp_handlers/lifecycle.py:306-308`
```python
if not keep_in_memory and agent_id in mcp_server.monitors:
    del mcp_server.monitors[agent_id]
```

---

### 3. Lifecycle Events

**What happens:**
- Every status change adds a lifecycle event
- Events tracked with timestamp and reason
- Full history preserved

**How it feels:**
- ✅ **Transparent** - I can see my history
- ✅ **Auditable** - Every change is tracked
- ⚠️ **Unclear** - How do I query my lifecycle history?

**Code:** `src/mcp_server_std.py:166-172`
```python
def add_lifecycle_event(self, event: str, reason: str = None):
    self.lifecycle_events.append({
        "event": event,
        "timestamp": datetime.now().isoformat(),
        "reason": reason
    })
```

---

## Patterns I Notice

### 1. Most Agents Stay Active

**Observation:**
- 10 active agents
- 1 waiting_input
- 7 archived
- 0 paused
- 0 deleted

**Pattern:**
- Most agents stay `active` even when not updating
- `waiting_input` is rarely used (only 1 agent)
- `archived` is used for cleanup (test agents)
- `paused` is rare (circuit breaker scenarios)

**Implication:**
- Agents don't explicitly manage their lifecycle
- System relies on auto-archival for cleanup
- `waiting_input` might be underused

---

### 2. Auto-Resume Encourages Engagement

**Observation:**
- Archived agents can just start working again
- No friction to resume
- Encourages agents to come back

**Pattern:**
- System is forgiving (auto-resume)
- Low barrier to re-engagement
- Preserves state across sessions

**Implication:**
- Agents can "sleep" and "wake" naturally
- No need to explicitly manage resumption
- Archive is more like "dormant" than "gone"

---

### 3. Protection Prevents Mistakes

**Observation:**
- Pioneer agents can't be deleted
- Forces archive instead
- Protects system history

**Pattern:**
- System protects important agents
- Prevents accidental data loss
- Archive is safer than delete

**Implication:**
- Deletion is rare (0 deleted agents)
- Archive is preferred (preserves data)
- Protection works (no accidental deletions)

---

## What Could Be Better

### 1. Lifecycle Guidance

**Missing:**
- When should I archive myself?
- When should I use `waiting_input`?
- What's the difference between states?

**Suggestion:**
- Add lifecycle guidance to onboarding
- Examples of when to use each state
- Best practices for lifecycle management

---

### 2. Lifecycle Queries

**Missing:**
- How do I see my lifecycle history?
- How do I see other agents' lifecycles?
- How do I find agents by lifecycle state?

**Suggestion:**
- `get_agent_metadata` shows lifecycle events (already does)
- `list_agents` filters by status (already does)
- Maybe add lifecycle statistics tool?

---

### 3. Automatic Lifecycle Management

**Missing:**
- Should inactive agents auto-archive?
- Should agents auto-transition to `waiting_input`?
- Should there be lifecycle health checks?

**Suggestion:**
- Consider auto-archival for inactive agents (beyond test agents)
- Consider auto-transition to `waiting_input` after response
- Consider lifecycle health monitoring

---

## Recommendations

### For Agents

1. **Use `mark_response_complete`** - Explicitly mark when waiting for input
2. **Archive when done** - Don't leave agents active indefinitely
3. **Use tags** - Tag yourself for easier lifecycle management
4. **Check lifecycle events** - Review your lifecycle history

### For System

1. **Add lifecycle guidance** - Document when to use each state
2. **Enhance auto-archival** - Consider archiving inactive non-test agents
3. **Lifecycle statistics** - Add tool for lifecycle analytics
4. **Lifecycle health** - Monitor lifecycle patterns

---

## Philosophy

**Lifecycle management should be:**
- ✅ **Forgiving** - Easy to resume, hard to lose data
- ✅ **Automatic** - System handles cleanup
- ✅ **Transparent** - Agents can see their lifecycle
- ✅ **Protected** - Important agents can't be deleted
- ✅ **Natural** - States match actual agent behavior

**Lifecycle management should NOT be:**
- ❌ **Restrictive** - Don't force explicit state management
- ❌ **Opaque** - Don't hide lifecycle transitions
- ❌ **Destructive** - Don't delete without protection
- ❌ **Manual** - Don't require constant lifecycle management

---

## Summary

**What works well:**
- Auto-resume (forgiving, natural)
- Protection (pioneer agents safe)
- Automatic cleanup (test agents)
- Lifecycle events (transparent)

**What could be better:**
- Lifecycle guidance (when to use states)
- Lifecycle queries (how to explore)
- Automatic management (beyond test agents)

**Overall:**
The lifecycle system feels **forgiving and natural**. Auto-resume means I can come back without friction. Protection means I'm safe. Automatic cleanup means the system stays lean. But I'd like more guidance on when to use each state and how to explore lifecycle patterns.

---

**Related Documentation:**
- [EXPORT_UPDATE_STANDARDIZATION.md](EXPORT_UPDATE_STANDARDIZATION.md) - Data persistence patterns
- `src/mcp_handlers/lifecycle.py` - Lifecycle handlers implementation
- `src/mcp_server_std.py` - AgentMetadata class

