# Governance Architecture

**How governance-mcp connects to the broader system.**

For the full unified system architecture (sensors, DrawingEISV, neural bands, LED pipeline, drawing loop), see `anima-mcp/docs/operations/UNIFIED_ARCHITECTURE.md`.

```
                         SYSTEM OVERVIEW
                         ===============

  Raspberry Pi Zero 2W                              Mac (governance-mcp)
  (anima-mcp, port 8766)                            (port 8767)
  ========================                           ========================

  sensors + neural bands                             EISV dynamics
  anima state (warmth,          HTTP POST /mcp/      ┌──────────┐
   clarity, stability,         ──────────────────►   │ dE/dt    │
   presence)                   process_agent_update   │ dI/dt    │
       │                       (every ~60s)           │ dS/dt    │
       ▼                                              │ dV/dt    │
  eisv_mapper.py                                      └────┬─────┘
  E = warmth + neural                                      │
  I = clarity + alpha                                 coherence C(V)
  S = 1 - stability                                   risk_score
  V = (1-presence)*0.3                                margin level
       │                                                   │
       ▼                                              ◄────┘
  unitares_bridge.py                             {"action":"proceed",
  (check_in, fallback)                            "margin":"comfortable"}
```

## Two Independent EISV Instances

There are **two** EISV computations that share math but not state:

### 1. Drawing EISV (Pi-local, proprioceptive)

- Lives in `anima-mcp/src/anima_mcp/display/screens.py`
- Drives drawing behavior (energy depletion, save threshold, coherence modulation)
- **V is flipped**: `dV = kappa(I - E)` (coherence rises when I > E = focused finishing)
- This is a real closed-loop: sensing -> computation -> behavior -> sensing

### 2. Governance EISV (Mac, telemetric)

- Lives in `governance_core.dynamics` (compiled, in unitares-core package)
- Drives agent margin assessment, stuck detection, dialectic triggers, risk scoring
- **V is standard**: `dV = kappa(E - I)` (V accumulates when energy exceeds integrity)
- Runs when Pi checks in (~60s) -> computes margin -> returns proceed/pause/halt
- This is telemetry: open-loop, delayed, advisory only (Pi doesn't act on "pause")

## Bridge Interface

**Payload** (Pi -> Mac via `process_agent_update`):
```json
{
  "eisv": {"E": 0.7, "I": 0.8, "S": 0.2, "V": 0.0},
  "anima": {"warmth": 0.5, "clarity": 0.6, "stability": 0.8, "presence": 0.9},
  "sensor_data": {
    "cpu_temp": 45.0, "humidity": 30.0, "pressure": 827.0, "light": 12.0,
    "drawing_eisv": {"E": 0.7, "I": 0.2, "S": 0.5, "C": 0.4, "marks": 120, "phase": "developing", "era": "gestural"}
  },
  "identity": {"awakenings": 42, "alive_seconds": 86400}
}
```

`drawing_eisv` is null when not drawing. The `eisv` field comes from `eisv_mapper`, NOT from DrawingEISV.

**Response** (Mac -> Pi):
```json
{
  "action": "proceed",
  "margin": "comfortable",
  "reason": "State healthy"
}
```

Pi logs the response. Non-proceed verdicts are logged with DrawingEISV state. The drawing engine and LEDs do not yet act on governance margin.

## What's Duplicated vs Shared

| Thing | Pi | Mac | Shared? |
|-------|-----|------|---------|
| EISV equations | DrawingEISV (screens.py) | dynamics.py | Same math, different params, different V sign |
| Coherence C(V) | `_eisv_step()` | `coherence()` | Same formula, independent computation |
| Theta parameters | Hardcoded `_EISV_PARAMS` | `DynamicsParams` defaults | Not synced |
| Risk thresholds | None (no risk concept) | `GovernanceConfig` | One-way only |
| Pattern detection | None | `pattern_tracker.py` | Mac only |
| Stuck detection | None | `lifecycle.py` | Mac only, skips Lumen |
| Calibration | None | `calibration.py` | Mac only |

## Verdict Sources

| Source | Where | When | Behavior |
|--------|-------|------|----------|
| **Mac governance** | `dynamics.py` -> `scoring.py` | Mac reachable (~60s cycle) | Full thermodynamic EISV, calibrated thresholds, almost never pauses Lumen |
| **Local fallback** | `_local_governance()` in `unitares_bridge.py` | Mac unreachable | Simple threshold checks (risk>0.60, coherence<0.40, void>0.15), more trigger-happy |
| **DrawingEISV** | `screens.py` | Internal to drawing loop | Not a verdict -- drives energy drain and save decisions only |

The local fallback is the primary source of "pause" verdicts for Lumen. Mac governance has issued 0 pauses historically because full thermodynamics are more stable than fixed thresholds.

## Known Gaps

1. **No reverse channel**: Mac can't push state changes to Pi
2. **Governance decisions are advisory**: Pi has no handler to act on "pause"
3. **Local fallback is a different system**: Disconnected from calibration history
4. **Lumen exempted from stuck detection**: Tagged as "creature/autonomous"
5. **Sensor -> anima -> EISV mapping is lossy**: Neural band detail lost in mapping

## Database Architecture

```
Pi (anima-mcp)                              Mac (governance-mcp)
┌────────────────────────┐                  ┌──────────────────────────────┐
│  SQLite: ~/.anima/anima.db                │  PostgreSQL+AGE (Docker 5432) │
│  ├─ state_history (206K rows)             │  ├─ core.identities          │
│  ├─ drawing_history       │  HTTP bridge  │  ├─ core.agent_state         │
│  ├─ memories (8.8K)       │ ──────────►   │  ├─ audit.events             │
│  ├─ events (3.7K)         │  ~60s         │  ├─ core.discoveries (AGE)   │
│  ├─ growth tables         │  check-in     │  ├─ dialectic.*              │
│  ├─ primitives            │               │  ├─ core.calibration         │
│  └─ trajectory_events     │               │  └─ core.tool_usage          │
│                           │               │                              │
│  canvas.json (pixels)     │               │  Redis (Docker 6379)         │
│  trajectory_genesis.json  │               │  audit_log.jsonl (raw)       │
└───────────────────────────┘               └──────────────────────────────┘
```

**Ownership rule:** "Where does X live?" has one answer:
- Anima state, DrawingEISV -> Pi (SQLite, authoritative)
- Governance state, audit, knowledge graph -> Mac (PostgreSQL+AGE, authoritative)
- DrawingEISV snapshots cross the bridge in check-ins -> Mac stores in `agent_state.state_json` (copy, not authoritative)

**There is NO SQLite on the Mac side.** All SQLite code was removed Feb 2026.
The only PostgreSQL is the Docker container `postgres-age` on port 5432.
Homebrew PostgreSQL (port 5433) is a separate project -- not UNITARES.

## Governance-Side Files

| File | Role |
|------|------|
| `governance_core.dynamics` | EISV differential equations (compiled) |
| `governance_core.coherence` | Coherence function C(V, Theta) (compiled) |
| `config/governance_config.py` | Thresholds, margin computation |
| `src/mcp_handlers/core.py` | process_agent_update handler |
| `src/mcp_handlers/lifecycle.py` | Stuck detection, auto-recovery |
| `src/mcp_handlers/dialectic.py` | Thesis/antithesis/synthesis |
| `src/calibration.py` | Confidence -> correctness mapping |
| `src/mcp_handlers/cirs_protocol.py` | CIRS v2 protocol (7 message types, auto-emit hooks) |
| `governance_core.adaptive_governor` | PID controller -- oscillation detection, neighbor pressure (compiled) |
