# UNITARES

### Digital proprioception for AI agents.

[![Tests](https://github.com/CIRWEL/unitares/actions/workflows/tests.yml/badge.svg)](https://github.com/CIRWEL/unitares/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

UNITARES gives AI agents a shared language for inner state — four continuous variables, a dynamics that evolves them, and a protocol for agents to speak and be read. Built on coupled differential equations with provable stability guarantees.

Running in production since November 2025. Originally built during a hackathon, then developed into a live multi-agent deployment. This repo powers that deployment and is production-capable, but not "set-and-forget" for every environment.

---

## The Idea

Agents can produce text, call tools, and return results. What they can't do is tell you what's happening inside. There's no shared vocabulary for "I'm losing coherence" or "my context is degrading" or "I'm running hot." Without that vocabulary, every observer — human, system, or other agent — is guessing from outputs alone.

UNITARES gives agents a language for inner state. Four continuous variables that any agent can report and any observer can read:

| Variable | Range | What it tracks |
|----------|-------|----------------|
| **E** (Energy) | [0, 1] | Productive capacity |
| **I** (Integrity) | [0, 1] | Information coherence |
| **S** (Entropy) | [0, 2] | Disorder and uncertainty |
| **V** (Void) | [-2, 2] | Accumulated E-I imbalance |

These aren't static labels — they evolve via coupled ODEs that define how state changes over time. The dynamics are the grammar:

```
dE/dt = α(I - E) - β·E·S           Energy tracks integrity, dragged by entropy
dI/dt = -k·S + β_I·C(V) - γ_I·I   Integrity boosted by coherence, reduced by entropy
dS/dt = -μ·S + λ₁·‖Δη‖² - λ₂·C   Entropy decays, rises with drift, damped by coherence
dV/dt = κ(E - I) - δ·V             Void accumulates E-I mismatch, decays toward zero
```

The key property: **coherence C(V)** creates nonlinear feedback that stabilizes the system. Global exponential convergence follows from contraction theory (Theorem 3.2).

> **Note:** These ODEs are implemented in the compiled [`unitares-core`](CONTRIBUTING.md#compiled-dependency) package, not in this repo. The EISV dynamics engine is distributed as a compiled wheel — the mathematical core is proprietary, while the server and all tooling around it are MIT-licensed. See [Licensing](#licensing) for details and [CONTRIBUTING.md](CONTRIBUTING.md) for build setup.

Check-ins are speech acts — an agent reporting its state in a shared vocabulary. Trajectories are behavioral records that make agent state legible over time. In practice, the ODE's strong convergence means agents with similar workloads tend toward similar EISV values; differentiation currently comes more from workload variance and drift signals than from the steady-state values themselves. Improving per-agent differentiation is an [active research area](#active-research).

> [Architecture Overview](docs/UNIFIED_ARCHITECTURE.md) — How the components fit together

---

## What UNITARES Provides

Most agent tooling operates on **outputs** — checking whether what the agent produced is correct, safe, or useful. UNITARES operates on **inner state** — making visible what the agent can't otherwise express.

| Layer | What it does | Example tools |
|-------|-------------|---------------|
| Output validation | Checks results after the fact | Guardrails, evals, logging |
| Behavioral constraint | Restricts what agents can do | Permissions, sandboxes, filters |
| **State legibility** | Makes inner state readable | **UNITARES** |

Logging tells you what happened. Guardrails constrain what can happen. UNITARES lets agents *say what's happening inside them* — and lets other agents, systems, and humans read it.

Once agents can express state in a shared vocabulary, you can build on it: monitoring, inter-agent observation, trajectory-based identity, structured disagreement. These are applications of legibility, not the thing itself.

---

## What Makes It Different

**UNITARES is a protocol, not a product.** The core contribution is the EISV vocabulary and the dynamics that govern it. Everything else — governance verdicts, circuit breakers, dialectic, the knowledge graph — is built on agents being able to express and read state in a shared language.

**Ethical drift from observable behavior.** No human oracle needed. Four measurable signals — calibration deviation, complexity divergence, coherence deviation, stability deviation — define a drift vector Δη that feeds directly into entropy dynamics.

**Trajectory as identity.** Agents aren't identified by tokens — they're identified by dynamical patterns. An agent's EISV trajectory is its behavioral signature, letting agents computationally verify "Am I still myself?" and letting observers distinguish agents by how they work.

**Mirror response mode.** Agents don't need to interpret raw EISV numbers. Mirror mode surfaces actionable self-awareness signals — calibration feedback, complexity divergence, knowledge graph discoveries — so agents get practical guidance instead of state vectors.

---

## Production Data

Deployed since November 2025. Live numbers as of March 28, 2026:

| Metric | Value |
|--------|-------|
| Agents (total created / active in last 7 days) | 1,300+ / ~60 |
| Check-ins processed | 100,000+ |
| Knowledge graph entries | 1,700+ |
| EISV typical range (Lumen, 95k check-ins) | E≈0.72, I≈0.75, S≈0.20, V≈-0.04 |
| V operating range | All active agents within [-0.1, 0.1] |
| Calibration accuracy | ~50% (see [Active Research](#active-research)) |
| Test suite | 5,800+ tests |

The large gap between total and active agents reflects the testing lifecycle — most agents are created by automated test runs, CI, and development sessions, not long-lived deployments. The ~60 active agents include production agents (Lumen, Vigil), development agents (Claude Code sessions), and integration test agents.

One of those agents is [Lumen](https://github.com/CIRWEL/anima-mcp) — an embodied creature on a Raspberry Pi whose physical sensors (temperature, humidity, light) seed its EISV state vector. Coherence modulates an autonomous drawing system; the art emerges from the same thermodynamics. See the [anima-mcp docs](https://github.com/CIRWEL/anima-mcp#how-it-works).

<p align="center">
  <img src="docs/images/dashboard.png" width="80%" alt="UNITARES web dashboard showing fleet coherence, agent status, and system health"/>
</p>

<p align="center">
  <em>Web dashboard — fleet coherence, agent status, calibration, anomaly detection.</em>
</p>

---

## Quick Start

```
1. onboard()                    → Get your identity
2. process_agent_update()       → Log your work
3. get_governance_metrics()     → Check your state
```

That's it. The `onboard()` response includes ready-to-use templates for your next calls — no guessing at parameter names. See [Getting Started](docs/guides/START_HERE.md) for the full walkthrough.

### Installation

**Prerequisites:** Python 3.12+, PostgreSQL 16+ with [AGE extension](https://github.com/apache/age), Redis (optional — session cache only, not required)

```bash
git clone https://github.com/CIRWEL/unitares.git
cd unitares
pip install -r requirements-core.txt

# MCP server (multi-client)
python src/mcp_server.py --port 8767

# Or stdio mode (single-client)
python src/mcp_server_std.py
```

> **Note:** The EISV dynamics engine (`unitares-core`) is a compiled dependency. It's installed automatically via `requirements-core.txt`. If you're contributing, see [CONTRIBUTING.md](CONTRIBUTING.md) for build details.

### MCP Configuration (Cursor / Claude Desktop)

```json
{
  "mcpServers": {
    "unitares": {
      "type": "http",
      "url": "http://localhost:8767/mcp/",
      "headers": { "X-Agent-Name": "MyAgent" }
    }
  }
}
```

| Endpoint | Transport | Use Case |
|----------|-----------|----------|
| `/mcp/` | Streamable HTTP | MCP clients (Cursor, Claude Desktop) |
| `/v1/tools/call` | REST POST | CLI, scripts, non-MCP clients |
| `/dashboard` | HTTP | Web dashboard |
| `/health` | HTTP | Health checks |

> See [Ngrok Deployment](docs/guides/NGROK_DEPLOYMENT.md) for remote access and advanced configuration.

---

## What You Can Build On It

- **Monitoring & early warning** — EISV trajectories show state changes as they happen. Circuit breakers can pause agents automatically at risk thresholds.
- **Inter-agent observation** — Agents can read each other's state vectors. One agent can assess whether another is coherent enough for a handoff without inspecting its outputs.
- **Trajectory identity** — An agent's behavioral signature over time. Enables "Am I still myself?" checks and anomaly detection for forks or impersonation.
- **Dialectic resolution** — Structured disagreement (thesis → antithesis → synthesis) requires a shared state language. Agents negotiate meaningfully when they can read each other's coherence and confidence.
- **Knowledge persistence** — Discoveries tagged to agent state and system version, stored in a shared graph with staleness detection. Agents build on each other's findings across sessions.

---

## Architecture

```mermaid
graph LR
    A[AI Agent] -->|check-in| M[MCP Server :8767]
    M -->|EISV evolution| UC[unitares-core]
    UC -->|state| M
    M -->|verdict + guidance| A
    M <-->|state, audit, calibration| PG[(PostgreSQL + AGE)]
    M <-->|knowledge graph| PG
    M -.->|session cache| R[(Redis)]
    M -->|web UI| D[Dashboard]

    style UC fill:#2d2d2d,stroke:#666,color:#fff
```

```
src/                   MCP server, agent state, knowledge graph, dialectic
dashboard/             Web dashboard (vanilla JS + Chart.js)
tests/                 5,800+ tests
```

The mathematical engine (`governance_core`) — ODEs, coherence, scoring — is distributed as a compiled package (unitares-core).

| Storage | Purpose | Required |
|---------|---------|----------|
| PostgreSQL + AGE | Agent state, knowledge graph, dialectic, calibration | Yes |
| Redis | Session cache only — falls back gracefully without it | Optional |

---

## Active Research

These are open questions, not solved problems:

- **Outcome correlation** — Does EISV instability predict bad task outcomes? Calibration accuracy is currently ~50%, which means the system's confidence estimates are not yet reliably predictive. Validation is ongoing.
- **Agent differentiation** — The ODE has strong convergence guarantees, which means agents with similar workloads converge to similar EISV steady states. This is mathematically correct but limits how much the state vector alone can distinguish between agents. Behavioral EISV (EMA-smoothed observations without ODE contraction) is in development as a parallel system to address this.
- **Identity fragmentation** — Session-based identity means the same human or system can accumulate many agent IDs across sessions. The 1,300+ total agents in production reflect this — most are ephemeral. Identity consolidation and trajectory-based re-identification are active work.
- **Domain-specific thresholds** — How should parameters be tuned for code generation vs. customer service vs. trading? No one-size-fits-all answer yet.
- **Horizontal scaling** — Current system handles hundreds of agents on a single node. What about thousands?

---

## Documentation

| Guide | Purpose |
|-------|---------|
| [Getting Started](docs/guides/START_HERE.md) | Complete setup and onboarding guide |
| [Architecture](docs/UNIFIED_ARCHITECTURE.md) | System topology, EISV dynamics, database ownership |
| [Troubleshooting](docs/guides/TROUBLESHOOTING.md) | Common issues |
| [Dashboard](dashboard/README.md) | Web dashboard docs |
| [Database Architecture](docs/database_architecture.md) | PostgreSQL + AGE |
| [Changelog](CHANGELOG.md) | Release history |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and code style.

## Related Projects

- [**Lumen / anima-mcp**](https://github.com/CIRWEL/anima-mcp) — Embodied AI on Raspberry Pi with physical sensors and EISV-driven art
- [**unitares-discord-bridge**](https://github.com/CIRWEL/unitares-discord-bridge) — Discord bot surfacing governance events, agent presence, and Lumen state

---

## Licensing

The MCP server, dashboard, tooling, and all code in this repo are **MIT licensed** — see [LICENSE](LICENSE). The EISV dynamics engine (`unitares-core`) is a **proprietary compiled dependency**. It's included as a wheel in `requirements-core.txt` and installs automatically, but its source is not in this repo. This means you can freely use, modify, and deploy the server, but the mathematical core is not open source. See [CONTRIBUTING.md](CONTRIBUTING.md#compiled-dependency) for details on working with this split.

---

Built by [@CIRWEL](https://github.com/CIRWEL) | **v2.8.0**
