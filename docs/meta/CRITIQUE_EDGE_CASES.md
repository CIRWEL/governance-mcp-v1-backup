# Critique Implementation: Edge Cases & Improvements

**Last Updated:** 2025-12-01  
**Status:** Minimal fixes only - avoid overengineering

---

## Philosophy: Fix Real Problems, Not Hypothetical Ones

Discovery disputes are a new feature. Dialectic sessions are rarely used. Let's keep it simple and fix issues as they arise, not preemptively.

---

## Minimal Fixes (Only If Needed)

### 1. Self-Dispute Prevention ⚠️ MAYBE
**Why:** Simple check, prevents obvious confusion  
**Fix:** 3 lines of code  
**Decision:** Only if self-disputes become a problem

### 2. Archived Discovery Prevention ⚠️ MAYBE  
**Why:** Prevents overwriting intentionally archived knowledge  
**Fix:** 2 lines of code  
**Decision:** Only if disputes of archived discoveries become a problem

---

## Everything Else: Wait and See

- **Already disputed?** - Let multiple disputes happen. If confusing, fix then.
- **Archived owner?** - Current error is fine. If common, fix then.
- **Missing context?** - Nice-to-have, not critical.
- **smart_dialectic_review?** - YAGNI (You Aren't Gonna Need It).
- **Race conditions?** - Fix if it becomes a real problem.

---

## Recommendation

**Don't implement any of these unless:**
1. Real users report confusion/problems
2. We see actual edge cases in production
3. The feature becomes commonly used

**Keep it simple. Fix real problems, not hypothetical ones.**

---

## Edge Cases Identified (For Reference)

### 1. Self-Dispute Prevention
**Issue:** No check to prevent an agent from disputing their own discovery.

**Current Behavior:**
- Agent can dispute their own discovery
- Discovery owner becomes reviewer (themselves)
- Creates a dialectic session with same agent on both sides

**Question:** Is this intentional (self-correction) or should we prevent it?

**Recommendation:** 
- **Option A:** Prevent self-disputes (simpler, cleaner)
- **Option B:** Allow but warn (self-correction is valid)
- **Option C:** Allow but use different reviewer (system-selected)

**Suggested Fix:**
```python
# In handle_request_dialectic_review, after getting discovery:
if discovery.agent_id == agent_id:
    return [error_response(
        "Cannot dispute your own discovery",
        recovery={
            "action": "Use update_discovery_status_graph to correct your own discovery",
            "related_tools": ["update_discovery_status_graph"]
        }
    )]
```

---

### 2. Already Disputed Discovery
**Issue:** No check if discovery is already "disputed" or has active dialectic session.

**Current Behavior:**
- Multiple agents can dispute the same discovery
- Discovery status overwritten to "disputed" each time
- Multiple dialectic sessions can exist for same discovery

**Question:** Should we prevent duplicate disputes or allow multiple concurrent disputes?

**Recommendation:**
- Check if discovery is already "disputed"
- If disputed, check for active dialectic session
- If active session exists, return error with session_id
- If no active session, allow new dispute (previous one may have failed)

**Suggested Fix:**
```python
# Check discovery status before disputing
if discovery.status == "disputed":
    # Check for active dialectic session
    active_session = await find_session_by_discovery(discovery_id)
    if active_session:
        return [error_response(
            f"Discovery already disputed - active session: {active_session.session_id}",
            recovery={
                "action": "Join existing dispute session or wait for resolution",
                "session_id": active_session.session_id,
                "related_tools": ["get_dialectic_session"]
            }
        )]
    # No active session - allow new dispute (previous may have failed)
```

---

### 3. Discovery Status Validation
**Issue:** No check if discovery is already resolved/archived before disputing.

**Current Behavior:**
- Can dispute resolved/archived discoveries
- May overwrite resolution status

**Question:** Should resolved/archived discoveries be disputable?

**Recommendation:**
- **Prevent disputing archived discoveries** (they're intentionally archived)
- **Allow disputing resolved discoveries** (corrections can be wrong)
- Add clear error messages

**Suggested Fix:**
```python
# Check discovery status
if discovery.status == "archived":
    return [error_response(
        "Cannot dispute archived discovery",
        recovery={
            "action": "Archived discoveries are intentionally closed",
            "related_tools": ["search_knowledge_graph"]
        }
    )]
# Allow disputed/resolved/open - all can be disputed
```

---

### 4. Discovery Owner Archived/Deleted
**Issue:** We check if owner exists, but what if they're archived?

**Current Behavior:**
- If owner not in metadata → error
- If owner archived → error (but maybe should allow?)

**Question:** Should archived agents' discoveries be disputable?

**Recommendation:**
- **Allow disputes of archived agents' discoveries** (knowledge correction is still valid)
- **Prevent disputes of deleted agents' discoveries** (no one to defend)
- Use system-selected reviewer if owner archived

**Suggested Fix:**
```python
# Check owner status
owner_meta = metadata.get(discovery_owner_id)
if not owner_meta:
    return [error_response(
        f"Discovery owner '{discovery_owner_id}' not found",
        recovery={"action": "Owner may have been deleted"}
    )]

if owner_meta.status == "deleted":
    return [error_response(
        "Cannot dispute discovery from deleted agent",
        recovery={"action": "Deleted agents cannot participate in dialectic"}
    )]

if owner_meta.status == "archived":
    # Use system-selected reviewer instead
    discovery_owner_id = None  # Fall back to system selection
    # Or allow but warn
```

---

### 5. get_dialectic_session Missing Discovery Context
**Issue:** `get_dialectic_session` doesn't show discovery context in response.

**Current Behavior:**
- Returns session info but doesn't highlight discovery context
- Discovery_id/dispute_type not prominently displayed

**Recommendation:**
- Add discovery context to session response
- Show discovery summary/details if discovery_id present

**Suggested Fix:**
```python
# In handle_get_dialectic_session, after getting session:
if session.discovery_id:
    from src.knowledge_graph import get_knowledge_graph
    graph = await get_knowledge_graph()
    discovery = await graph.get_discovery(session.discovery_id)
    if discovery:
        result["discovery_context"] = {
            "discovery_id": session.discovery_id,
            "dispute_type": session.dispute_type,
            "discovery_summary": discovery.summary,
            "discovery_status": discovery.status
        }
```

---

### 6. smart_dialectic_review Doesn't Support Discovery Disputes
**Issue:** `smart_dialectic_review` doesn't accept discovery_id parameter.

**Current Behavior:**
- Only supports recovery (paused agents)
- Cannot use smart dialectic for discovery disputes

**Question:** Should smart dialectic support discovery disputes?

**Recommendation:**
- **Yes** - Add discovery_id/dispute_type parameters
- Auto-generate thesis from discovery context
- Use discovery owner as reviewer (same as regular dialectic)

**Suggested Fix:**
- Add `discovery_id` and `dispute_type` parameters to `smart_dialectic_review`
- Pass through to `request_dialectic_review` internally
- Or implement discovery-specific logic

---

### 7. Race Condition: Concurrent Disputes
**Issue:** Two agents could dispute the same discovery simultaneously.

**Current Behavior:**
- Both mark discovery as "disputed"
- Both create dialectic sessions
- Discovery status overwritten

**Question:** How to handle concurrent disputes?

**Recommendation:**
- **Option A:** First one wins, second gets error with first session_id
- **Option B:** Allow multiple concurrent disputes (different reviewers)
- **Option C:** Use locking mechanism

**Suggested Fix:**
- Check discovery status atomically
- If already disputed, check for active session
- Return existing session_id if found

---

## Priority Ranking

1. **High Priority:**
   - Self-dispute prevention (#1)
   - Discovery status validation (#3)
   - Already disputed check (#2)

2. **Medium Priority:**
   - Discovery owner archived handling (#4)
   - get_dialectic_session discovery context (#5)

3. **Low Priority:**
   - smart_dialectic_review support (#6)
   - Race condition handling (#7)

---

## Implementation Notes

**Non-Breaking:** All fixes are backward compatible - they add validation/checks but don't change existing behavior for valid cases.

**Error Messages:** All fixes include helpful error messages with recovery guidance.

**Testing:** Should test:
- Self-dispute prevention
- Already disputed discovery
- Resolved/archived discovery disputes
- Archived owner handling
- Concurrent dispute attempts

---

## Related

- [CRITIQUE_IMPLEMENTATION_COMPLETE.md](CRITIQUE_IMPLEMENTATION_COMPLETE.md) - Implementation status
- [CRITIQUE_WITHOUT_NEW_TOOLS.md](CRITIQUE_WITHOUT_NEW_TOOLS.md) - Original proposal

