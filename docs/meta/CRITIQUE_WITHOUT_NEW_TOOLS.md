# Critique Without New Tools: Repurposing Existing Infrastructure

**Last Updated:** 2025-12-01  
**Purpose:** Solve critique issues by repurposing existing dialectic tools and enhancing completion marking  
**Status:** ✅ Complete - All 5 phases implemented

---

## Strategy: Repurpose, Don't Create

Instead of creating new critique tools, we'll:
1. **Extend Dialectic Protocol** - Use for discovery disputes/corrections
2. **Enhance Discovery Status** - Add "disputed" status
3. **Improve Completion Marking** - Better discovery resolution prompts
4. **Link Dialectic to Discoveries** - Connect sessions to specific discoveries

---

## 1. Extend Dialectic for Discovery Disputes

### Current State
- Dialectic is tied to `paused_agent_id` and `reviewer_agent_id`
- Used only for recovery (circuit breaker, loops)
- Protocol is generic: thesis → antithesis → synthesis

### Enhancement: Add Optional Discovery Context

**Add to DialecticSession:**
```python
class DialecticSession:
    def __init__(self,
                 paused_agent_id: str,
                 reviewer_agent_id: str,
                 paused_agent_state: Dict[str, Any],
                 discovery_id: Optional[str] = None,  # NEW: Link to discovery
                 dispute_type: Optional[str] = None,  # NEW: "dispute", "correction", "verification"
                 max_synthesis_rounds: int = 5):
        # ... existing code ...
        self.discovery_id = discovery_id
        self.dispute_type = dispute_type  # "dispute", "correction", "verification", None (recovery)
```

**Use Cases:**
- **Recovery** (existing): `discovery_id=None`, `dispute_type=None`
- **Dispute**: `discovery_id="...", dispute_type="dispute"`
  - Thesis: "I think this discovery is incorrect because..."
  - Antithesis: "I observe/defend this discovery because..."
  - Synthesis: "Agreed correction/verification"
- **Correction**: `discovery_id="...", dispute_type="correction"`
  - Thesis: "I propose this correction..."
  - Antithesis: "I review/validate..."
  - Synthesis: "Agreed correction"

---

## 2. Add "Disputed" Status to Discoveries

### Current Status Values
- `"open"` - Discovery is open
- `"resolved"` - Discovery is resolved
- `"archived"` - Discovery is archived

### Enhancement: Add "Disputed"

**Update DiscoveryNode:**
```python
status: str = "open"  # "open", "resolved", "archived", "disputed"
```

**Workflow:**
1. Agent disputes discovery → Status changes to `"disputed"`
2. Dialectic session created → Links to discovery
3. Resolution → Status changes to `"resolved"` (if corrected) or `"open"` (if verified)

---

## 3. Enhance Completion Marking

### Current State
- `mark_response_complete` exists
- Shows open discoveries from last 24 hours
- Prompts to resolve discoveries

### Enhancement: Better Discovery Resolution

**Add to `mark_response_complete` response:**
```python
response_data["discovery_resolution_prompt"] = {
    "message": "Consider resolving open discoveries before marking complete",
    "open_discoveries": [...],
    "suggested_actions": [
        "update_discovery_status_graph(discovery_id='...', status='resolved')",
        "If discovery is incorrect, use dialectic to dispute it"
    ],
    "dialectic_option": "Use request_dialectic_review with discovery_id to dispute/correct"
}
```

**Add to `process_agent_update` maintenance prompt:**
- Show discoveries that might need correction
- Suggest dialectic for disputes
- Link to discovery resolution tools

---

## 4. Link Dialectic Sessions to Discoveries

### Enhancement: Discovery Context in Dialectic

**Update `request_dialectic_review`:**
```python
async def handle_request_dialectic_review(arguments: Dict[str, Any]):
    # ... existing code ...
    discovery_id = arguments.get("discovery_id")  # NEW: Optional discovery ID
    dispute_type = arguments.get("dispute_type")  # NEW: "dispute", "correction", None
    
    # If discovery_id provided, this is a discovery dispute
    if discovery_id:
        # Validate discovery exists
        graph = await get_knowledge_graph()
        discovery = await graph.get_discovery(discovery_id)
        if not discovery:
            return [error_response(f"Discovery '{discovery_id}' not found")]
        
        # Mark discovery as disputed
        await graph.update_discovery(discovery_id, {"status": "disputed"})
        
        # Set dispute context
        dispute_type = dispute_type or "dispute"
        paused_agent_id = arguments.get("agent_id")  # Disputing agent
        reviewer_agent_id = discovery.agent_id  # Discovery owner (defending)
    
    # Create session with discovery context
    session = DialecticSession(
        paused_agent_id=paused_agent_id,
        reviewer_agent_id=reviewer_agent_id,
        paused_agent_state=agent_state,
        discovery_id=discovery_id,  # NEW
        dispute_type=dispute_type,  # NEW
        max_synthesis_rounds=5
    )
```

**Resolution Updates Discovery:**
```python
async def execute_resolution(session: DialecticSession, resolution: Resolution):
    # ... existing code ...
    
    # If linked to discovery, update discovery status
    if session.discovery_id:
        graph = await get_knowledge_graph()
        
        if resolution.action == "resume":  # Agreed correction/verification
            # Update discovery based on resolution
            if session.dispute_type == "dispute":
                # Discovery was disputed and corrected
                await graph.update_discovery(session.discovery_id, {
                    "status": "resolved",
                    "resolved_at": datetime.now().isoformat(),
                    "details": f"{discovery.details}\n\n[Disputed and corrected via dialectic {session.session_id}]"
                })
            elif session.dispute_type == "correction":
                # Discovery was corrected
                # Could update summary/details from resolution
                await graph.update_discovery(session.discovery_id, {
                    "status": "resolved",
                    "resolved_at": datetime.now().isoformat()
                })
        elif resolution.action == "block":  # Dispute rejected, discovery verified
            # Discovery was disputed but verified correct
            await graph.update_discovery(session.discovery_id, {
                "status": "open",  # Back to open (verified)
                "details": f"{discovery.details}\n\n[Disputed but verified correct via dialectic {session.session_id}]"
            })
```

---

## Implementation Plan

### Phase 1: Extend DialecticSession (Non-Breaking)
1. Add optional `discovery_id` and `dispute_type` fields
2. Update `to_dict()` and `from_dict()` to handle new fields
3. Backward compatible (existing sessions work as-is)

### Phase 2: Add "Disputed" Status (Non-Breaking)
1. Update `DiscoveryNode.status` to include "disputed"
2. Update `update_discovery_status_graph` to accept "disputed"
3. Update validation to allow "disputed" status

### Phase 3: Enhance request_dialectic_review (Non-Breaking)
1. Add optional `discovery_id` and `dispute_type` parameters
2. If provided, mark discovery as disputed
3. Set reviewer to discovery owner (not system-selected)

### Phase 4: Enhance Resolution Execution (Non-Breaking)
1. Check if session has `discovery_id`
2. Update discovery status based on resolution
3. Add dialectic session reference to discovery details

### Phase 5: Improve Completion Marking (Non-Breaking)
1. Enhance `mark_response_complete` with discovery resolution prompts
2. Add dialectic option for disputes
3. Show disputed discoveries in maintenance prompts

---

## Benefits

1. **No New Tools** - Reuses existing dialectic infrastructure
2. **Backward Compatible** - Existing recovery flows unchanged
3. **Natural Extension** - Dialectic protocol fits disputes perfectly
4. **Better Completion** - Agents get clearer guidance on resolving discoveries
5. **Collaborative Critique** - Agents can dispute and correct each other

---

## Example Workflow

### Disputing a Discovery

```python
# Agent A finds discovery from Agent B that seems incorrect
# Step 1: Request dialectic review with discovery context
session = request_dialectic_review(
    agent_id="agent_a",
    discovery_id="2025-12-01T15:34:52.968372",
    dispute_type="dispute",
    reason="Discovery seems incorrect based on my analysis",
    api_key="agent_a_key"
)

# Step 2: Agent A submits thesis (dispute)
submit_thesis(
    session_id=session["session_id"],
    agent_id="agent_a",
    root_cause="Discovery claims X but I observe Y",
    reasoning="Evidence: ...",
    api_key="agent_a_key"
)

# Step 3: Agent B (discovery owner) submits antithesis (defense)
submit_antithesis(
    session_id=session["session_id"],
    agent_id="agent_b",
    observed_metrics={"evidence": "..."},
    concerns=["Need to verify claim"],
    reasoning="I stand by discovery because...",
    api_key="agent_b_key"
)

# Step 4: Negotiate synthesis
submit_synthesis(
    session_id=session["session_id"],
    agent_id="agent_a",
    proposed_conditions=["Update discovery summary to reflect both perspectives"],
    root_cause="Agreed: Discovery partially correct, needs clarification",
    agrees=True,
    api_key="agent_a_key"
)

# Step 5: Resolution updates discovery automatically
# Discovery status changes to "resolved" with correction
```

---

## Implementation Status

### ✅ Phase 1: Extended DialecticSession
**Status:** Complete  
**Changes:**
- Added optional `discovery_id` field to `DialecticSession`
- Added optional `dispute_type` field ("dispute", "correction", "verification")
- Updated `to_dict()` to include new fields
- Updated `load_session()` to reconstruct new fields
- **Backward compatible:** Existing sessions work without changes

**Files Modified:**
- `src/dialectic_protocol.py` - Extended DialecticSession class
- `src/mcp_handlers/dialectic.py` - Updated session loading

### ✅ Phase 2: Added "Disputed" Status
**Status:** Complete  
**Changes:**
- Extended `DiscoveryNode.status` to include "disputed"
- Updated `update_discovery_status_graph` to accept "disputed"
- Updated validation to allow "disputed" status

**Files Modified:**
- `src/knowledge_graph.py` - DiscoveryNode status enum
- `src/mcp_handlers/knowledge_graph.py` - Status validation

### ✅ Phase 3: Enhanced request_dialectic_review
**Status:** Complete  
**Changes:**
- Accepts optional `discovery_id` and `dispute_type` parameters
- If `discovery_id` provided:
  - Validates discovery exists
  - Marks discovery as "disputed"
  - Sets reviewer to discovery owner (not system-selected)
  - Sets dispute_type if not provided
  - Updates reason with discovery context
- Returns discovery context in response

**Files Modified:**
- `src/mcp_handlers/dialectic.py` - Enhanced handle_request_dialectic_review
- `src/mcp_server_std.py` - Updated tool documentation and schema

### ✅ Phase 4: Enhanced Resolution Execution
**Status:** Complete  
**Changes:**
- Checks if session has `discovery_id`
- Updates discovery status based on resolution:
  - `action="resume"` → discovery marked as "resolved" with correction note
  - `action="block"` → discovery verified correct, status back to "open"
- Adds dialectic session reference to discovery details
- Non-blocking (doesn't fail if discovery update fails)
- Skips agent resume if discovery dispute (not paused agent)

**Files Modified:**
- `src/mcp_handlers/dialectic.py` - Enhanced execute_resolution

### ✅ Phase 5: Improved Completion Marking
**Status:** Complete  
**Changes:**
- Enhanced `mark_response_complete` maintenance prompt
- Enhanced `process_agent_update` maintenance prompt
- Added suggested actions:
  - Mark as resolved
  - Use dialectic for disputes
  - Archive if obsolete
- Added dialectic option for disputes
- Added tip about collaborative corrections

**Files Modified:**
- `src/mcp_handlers/lifecycle.py` - Enhanced mark_response_complete
- `src/mcp_handlers/core.py` - Enhanced process_agent_update

---

## Testing & Documentation

**Backward Compatibility:**
- ✅ Existing recovery flows work unchanged
- ✅ Old sessions load correctly (discovery_id/dispute_type optional)
- ✅ No breaking changes to API

**New Functionality:**
- ✅ Discovery disputes work end-to-end
- ✅ Discovery status updates automatically
- ✅ Discovery owner becomes reviewer
- ✅ Completion marking suggests dialectic for disputes

**Documentation Updates:**
- ✅ Updated `request_dialectic_review` description
- ✅ Added discovery dispute examples
- ✅ Updated input schema with new parameters
- ✅ Updated return schema with discovery context
- ✅ Updated `update_discovery_status_graph` to accept "disputed"

---

**Related:**
- [CRITIQUE_EDGE_CASES.md](CRITIQUE_EDGE_CASES.md) - Edge cases (minimal fixes only)
- [LIFECYCLE_PERSPECTIVE.md](LIFECYCLE_PERSPECTIVE.md) - Lifecycle management
- `src/dialectic_protocol.py` - Dialectic protocol implementation
- `src/mcp_handlers/dialectic.py` - Dialectic handlers
- `src/knowledge_graph.py` - Knowledge graph implementation

---

**Implementation Complete!** ✅

Agents can now dispute and correct discoveries using the existing dialectic infrastructure, without creating new tools. The system is backward compatible and ready for use.

