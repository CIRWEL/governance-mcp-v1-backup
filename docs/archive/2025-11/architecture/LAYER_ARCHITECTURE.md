# Layer Architecture: Metadata, Knowledge, Governance, Validation

**Created:** November 26, 2025
**Purpose:** Explain the different data layers, their purposes, and how they sync

---

## Overview: The Four Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Server Entry Point                   │
│                  (src/mcp_server_std.py)                    │
└─────────────────────────────────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│  Agent Metadata  │ │  Governance  │ │  Knowledge   │
│     Layer        │ │   History    │ │    Layer     │
└──────────────────┘ └──────────────┘ └──────────────┘
           │                │                │
           ▼                ▼                ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│ agent_metadata   │ │ {agent_id}_  │ │ knowledge/   │
│    .json         │ │ results.json │ │ {agent}.json │
└──────────────────┘ └──────────────┘ └──────────────┘
           │                │                │
           └────────────────┼────────────────┘
                            ▼
                   ┌────────────────┐
                   │   Validation   │
                   │     Layer      │
                   └────────────────┘
```

---

## Layer 1: Agent Metadata (Identity & Lifecycle)

### Purpose
**WHO the agent is and WHAT STATE they're in**

### Storage
- **File:** `data/agent_metadata.json` (single shared file)
- **Structure:** Dict of `{agent_id: AgentMetadata}`
- **Locking:** File-level lock (`.metadata.lock`)

### Contains

```python
@dataclass
class AgentMetadata:
    # Identity
    agent_id: str
    version: str
    created_at: str
    last_update: str

    # Lifecycle state
    status: str  # "active" | "waiting_input" | "paused" | "archived" | "deleted"
    total_updates: int

    # Security
    api_key: str  # For authentication
    parent_agent_id: str  # If spawned from another agent

    # Organization
    tags: List[str]
    notes: str

    # Protection
    loop_cooldown_until: str  # ISO timestamp
    recent_decisions: List[str]  # Last 10 decisions
    recent_update_timestamps: List[str]

    # Events
    lifecycle_events: List[Dict]  # created, paused, resumed, milestone, etc.
```

### When Updated
- Agent creation (`get_agent_api_key`)
- Every governance update (`process_agent_update`)
- Lifecycle changes (pause, resume, archive)
- Metadata edits (`update_agent_metadata`)

### Access Pattern
- **Read:** Every MCP tool call (check status, validate agent exists)
- **Write:** After governance updates, lifecycle events
- **Lock:** Exclusive write lock, shared read lock

---

## Layer 2: Governance History (Thermodynamic Evolution)

### Purpose
**HOW the agent's thermodynamic state evolved over time**

### Storage
- **File:** `data/{agent_id}_results.json` (one per agent)
- **Structure:** Time series of UNITARES metrics
- **Locking:** None (append-only by design)

### Contains

```python
{
    "agent_id": "claude_desktop_main",
    "timestamps": ["2025-11-26T10:00:00", "2025-11-26T10:05:00", ...],
    "E_history": [0.702, 0.715, 0.728, ...],      # Energy
    "I_history": [0.809, 0.818, 0.828, ...],      # Information
    "S_history": [0.501, 0.509, 0.518, ...],      # Entropy
    "V_history": [-0.003, -0.006, -0.009, ...],   # Void
    "lambda1_history": [0.09, 0.09, 0.09, ...],   # Ethical coupling
    "coherence_history": [0.985, 0.972, 0.968, ...],
    "risk_history": [0.412, 0.437, 0.406, ...],
    "decision_history": ["revise", "approve", "revise", ...],
    "void_event_history": [0, 0, 0, 1, 0, ...]
}
```

### When Updated
- Every `process_agent_update` call
- Appends new data point to each time series

### Access Pattern
- **Read:** For analysis, plotting, pattern detection
- **Write:** Append-only (fast, no locking needed)
- **Export:** Via `get_system_history` tool

### Key Difference from Metadata
- **Metadata:** Current state ("What is the agent's status RIGHT NOW?")
- **History:** Time series ("How did coherence evolve over 100 updates?")

---

## Layer 3: Knowledge Layer (Learning & Discoveries)

### Purpose
**WHAT the agent learned and discovered beyond metrics**

### Storage
- **File:** `data/knowledge/{agent_id}.json` (one per agent)
- **Structure:** AgentKnowledge object
- **Locking:** File-level lock per agent

### Contains

```python
@dataclass
class AgentKnowledge:
    agent_id: str
    created_at: str
    last_updated: str

    # Structured learning
    discoveries: List[Discovery]      # Bugs found, insights gained
    patterns: List[Pattern]           # Recurring themes observed
    lessons_learned: List[str]        # General takeaways
    questions_raised: List[str]       # Open questions

    # Inheritance
    inherited_from: str               # Parent agent's knowledge
    lineage: List[str]                # Chain of knowledge transfer

# Discovery types:
class Discovery:
    type: str  # "bug_found", "insight", "pattern", "improvement", "question"
    summary: str
    details: str
    severity: str  # "low", "medium", "high", "critical"
    status: str    # "open", "resolved", "archived"
    tags: List[str]
    related_files: List[str]
    related_discoveries: List[str]  # Cross-references
```

### When Updated
- Via MCP tools:
  - `store_knowledge` - Log discovery
  - `update_discovery_status` - Mark resolved/archived
  - `find_similar_discoveries` - Cross-reference

### Access Pattern
- **Read:** When agent needs to recall past learnings
- **Write:** Explicitly via knowledge tools (not automatic)
- **Query:** Search by tags, type, severity

### Key Difference from Metadata & History
- **Metadata:** Agent state (who, what status)
- **History:** Thermodynamic metrics (how did numbers evolve)
- **Knowledge:** Semantic learning (what did agent UNDERSTAND)

---

## Layer 4: Validation (Consistency Checking)

### Purpose
**Ensure all layers are consistent and correct**

### Validation Types

#### 1. Structural Validation
```python
# Check files exist and are valid JSON
validate_file_exists("data/agent_metadata.json")
validate_json_parseable("data/agent_metadata.json")
```

#### 2. Cross-Layer Consistency
```python
# Agent in metadata should have matching history/knowledge
for agent_id in metadata.keys():
    assert history_exists(agent_id) or updates_count == 0
    assert knowledge_exists(agent_id) if has_discoveries else True
```

#### 3. Schema Validation
```python
# Agent metadata must have required fields
assert "agent_id" in meta
assert "status" in ["active", "paused", "waiting_input", "archived", "deleted"]
assert "created_at" is valid ISO timestamp
```

#### 4. Invariants
```python
# Paused agents must have paused_at timestamp
if meta.status == "paused":
    assert meta.paused_at is not None

# Loop cooldown must be future timestamp or None
if meta.loop_cooldown_until:
    assert datetime.fromisoformat(meta.loop_cooldown_until) > now()
```

### When Validation Runs
- **On startup:** `load_metadata()` validates structure
- **On write:** `save_metadata()` validates before writing
- **On demand:** `scripts/validate_project_docs.py`
- **In tests:** `tests/test_validation_m4.py`

---

## Data Flow: How Layers Sync

### Example: Agent Makes Governance Update

```
1. User/Agent calls process_agent_update(agent_id, state)
                    │
                    ▼
2. Load metadata ────────────────────────► Check agent exists
   load_metadata()                         Check not paused
                    │                       Check not in cooldown
                    ▼
3. Compute governance ──────────────────► UNITARESMonitor.update()
   governance_monitor.update(state)       → E, I, S, V, coherence, risk
                    │
                    ▼
4. Make decision ───────────────────────► if risk > 0.7: circuit_breaker()
   decide(risk, coherence)                → decision: approve/revise/reject
                    │
                    ├─────────────────────────────────────┐
                    │                                     │
                    ▼                                     ▼
5a. Update Metadata                          5b. Update History
    meta.total_updates += 1                      append to E_history
    meta.recent_decisions.append(decision)       append to I_history
    meta.last_update = now()                     append to coherence_history
    if circuit_breaker:                          append to decision_history
        meta.status = "paused"                   ...
        add_lifecycle_event("paused")
    save_metadata()                              save_results()
                    │                                     │
                    └──────────────┬──────────────────────┘
                                   ▼
6. Return response to agent
   {
       "decision": "approve",
       "coherence": 0.812,
       "risk": 0.234,
       "suggested_params": {...}
   }
```

### Knowledge Layer (Separate Flow)

```
1. Agent explicitly calls store_knowledge(discovery)
                    │
                    ▼
2. Load knowledge file ──────────────────► data/knowledge/{agent_id}.json
   knowledge_manager.load(agent_id)        Create if doesn't exist
                    │
                    ▼
3. Add discovery ────────────────────────► Append to discoveries list
   knowledge.discoveries.append(discovery)  Update last_updated timestamp
                    │
                    ▼
4. Cross-reference ──────────────────────► find_similar_discoveries()
   Link related discoveries                 Add to related_discoveries
                    │
                    ▼
5. Save knowledge ───────────────────────► Write to disk
   knowledge_manager.save(knowledge)
```

**Key:** Knowledge is NOT automatically updated by governance - only by explicit tool calls.

---

## Synchronization & Consistency

### 1. Metadata ↔ History

**Sync point:** `total_updates` in metadata = length of history arrays

```python
# Consistency check
def validate_metadata_history_sync(agent_id):
    meta = agent_metadata[agent_id]
    history = load_results(agent_id)

    assert meta.total_updates == len(history["E_history"])
    assert meta.total_updates == len(history["timestamps"])
```

**What if out of sync?**
- History is source of truth (append-only, harder to corrupt)
- Metadata can be reconstructed from history + lifecycle events

### 2. Metadata ↔ Knowledge

**Sync point:** Both share `agent_id` and timestamps

```python
# Loose coupling (intentional)
def validate_metadata_knowledge_sync(agent_id):
    meta = agent_metadata[agent_id]
    knowledge = knowledge_manager.load(agent_id)

    # Knowledge file may not exist (agent hasn't made discoveries yet)
    if knowledge:
        assert knowledge.agent_id == meta.agent_id
        assert knowledge.created_at >= meta.created_at
```

**What if out of sync?**
- They're intentionally loosely coupled
- Knowledge layer is optional (not all agents use it)
- No strict consistency required

### 3. All Layers ↔ File System

**Lock Hierarchy:**
```
Global Metadata Lock (.metadata.lock)
  └─ Protects: agent_metadata.json (shared file)
  └─ Held during: load_metadata(), save_metadata()

Per-Agent State Locks (.{agent_id}_state.lock)
  └─ Protects: Individual agent operations
  └─ Held during: process_agent_update() for specific agent

Knowledge Locks (implicit via file writes)
  └─ Protects: knowledge/{agent_id}.json
  └─ Held during: save_knowledge()
```

**Deadlock prevention:**
- Always acquire locks in order: Global → Per-Agent → Knowledge
- Use timeouts (5 seconds max) with exponential backoff
- Auto-cleanup stale locks (age > 5 minutes)

---

## When to Use Which Layer

### Use Metadata Layer when:
- ✅ Checking if agent exists
- ✅ Getting current agent status (active/paused/etc.)
- ✅ Listing all agents
- ✅ Recording lifecycle events (created, paused, milestone)
- ✅ Managing agent relationships (parent/child spawning)
- ✅ Checking loop cooldown status

### Use Governance History when:
- ✅ Analyzing metric trends (coherence over time)
- ✅ Plotting agent behavior
- ✅ Detecting patterns (repeated void events)
- ✅ Exporting data for analysis
- ✅ Debugging why circuit breaker triggered

### Use Knowledge Layer when:
- ✅ Recording semantic learnings (not captured by metrics)
- ✅ Tracking bugs found/fixed
- ✅ Storing insights that should transfer to spawned agents
- ✅ Maintaining cross-references between discoveries
- ✅ Building up domain knowledge over sessions

### Use Validation Layer when:
- ✅ Debugging inconsistencies
- ✅ Pre-deployment checks
- ✅ Testing integrity after changes
- ✅ Recovering from corrupted state

---

## Common Patterns

### Pattern 1: Agent Initialization
```python
# 1. Create metadata entry
agent_id = generate_agent_id()
api_key = generate_api_key()
meta = AgentMetadata(agent_id=agent_id, api_key=api_key, ...)
agent_metadata[agent_id] = meta
save_metadata()

# 2. Initialize governance monitor (no file yet, created on first update)
# (Happens automatically in process_agent_update)

# 3. Knowledge layer (optional, created on first discovery)
# (Happens when agent calls store_knowledge)
```

### Pattern 2: Lifecycle State Change
```python
# Pause agent
meta = agent_metadata[agent_id]
meta.status = "paused"
meta.paused_at = datetime.now().isoformat()
add_lifecycle_event(agent_id, "paused", reason="Circuit breaker triggered")
save_metadata()

# Resume agent
meta.status = "active"
meta.paused_at = None
add_lifecycle_event(agent_id, "resumed", reason="Dialectic review completed")
save_metadata()
```

### Pattern 3: Cross-Layer Query
```python
# Find all agents with declining coherence
agents_at_risk = []
for agent_id, meta in agent_metadata.items():
    if meta.status != "active":
        continue

    # Check governance history
    history = load_results(agent_id)
    if history:
        recent_coherence = history["coherence_history"][-5:]
        if all(recent_coherence[i] > recent_coherence[i+1]
               for i in range(len(recent_coherence)-1)):
            agents_at_risk.append(agent_id)
```

---

## Validation Checklist

Run before deployment:

```bash
# 1. Structural validation
python3 scripts/validate_project_docs.py

# 2. Test suite
python3 -m pytest tests/test_validation_m4.py

# 3. Manual consistency check
python3 -c "
from src.mcp_server_std import load_metadata, agent_metadata
from pathlib import Path

load_metadata()
for agent_id in agent_metadata.keys():
    # Check history exists if updates > 0
    meta = agent_metadata[agent_id]
    history_file = Path(f'data/{agent_id}_results.json')
    if meta.total_updates > 0:
        assert history_file.exists(), f'Missing history for {agent_id}'

    # Check paused agents have paused_at
    if meta.status == 'paused':
        assert meta.paused_at, f'Paused agent {agent_id} missing paused_at'

print('✅ All consistency checks passed')
"
```

---

## Summary Table

| Layer | File Location | Update Trigger | Lock Type | Purpose |
|-------|---------------|----------------|-----------|---------|
| **Metadata** | `data/agent_metadata.json` | Every governance update, lifecycle change | Global file lock | Current state & identity |
| **History** | `data/{agent}_results.json` | Every governance update | None (append-only) | Thermodynamic time series |
| **Knowledge** | `data/knowledge/{agent}.json` | Explicit tool calls only | Per-file implicit | Semantic learnings |
| **Validation** | N/A (checks other layers) | On demand, startup, tests | N/A | Consistency enforcement |

---

## Design Principles

1. **Single Source of Truth:** Each piece of data has ONE authoritative location
   - Agent status → Metadata layer
   - Coherence history → Governance history
   - Bug discoveries → Knowledge layer

2. **Loose Coupling:** Layers can exist independently
   - Agent can have metadata without knowledge
   - Agent can have history without discoveries
   - But NOT metadata without agent_id (identity is root)

3. **Append-Only Where Possible:** History doesn't delete, only appends
   - Makes corruption less likely
   - Enables time-travel debugging
   - Simplifies locking (no read-modify-write races)

4. **Fail-Safe Defaults:** If file missing/corrupted, use safe defaults
   - Missing metadata → treat as non-existent agent (reject)
   - Missing history → treat as new agent (coherence=1.0)
   - Missing knowledge → treat as no learnings yet

5. **Explicit Over Implicit:** Knowledge must be explicitly stored
   - Prevents auto-logging noise
   - Agent decides what's worth remembering
   - Human-readable semantic content

---

**Next:** See `docs/architecture/LOCKING_STRATEGY.md` for detailed lock semantics.
