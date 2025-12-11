# AI Governance Portfolio - Thermodynamic Multi-Agent Coordination

> **Independent research project demonstrating AI safety infrastructure design, security hardening, and multi-agent coordination systems.**

[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Security Audited](https://img.shields.io/badge/security-audited-brightgreen.svg)](SECURITY_AUDIT_REPORT.md)

**Author**: Kenny Wang
**Background**: AI Ethics + Self-Taught Systems Design
**Project Duration**: September 2024 - Present
**Code**: [github.com/CIRWEL/AI-Governance-Portfolio](https://github.com/CIRWEL/AI-Governance-Portfolio)

---

## Table of Contents
- [What I Built](#what-i-built)
- [Why It Matters](#why-it-matters)
- [Technical Highlights](#technical-highlights)
- [Security Work](#security-work)
- [Architecture](#architecture)
- [Skills Demonstrated](#skills-demonstrated)
- [Try It](#try-it)

---

## What I Built

A **governance infrastructure for AI agent coordination** using thermodynamic principles and the Model Context Protocol (MCP).

Think of it as a "constitution" for AI agents - a system that:
- Tracks agent state using physics-inspired metrics (Energy, Integrity, Entropy, Void)
- Enforces safety boundaries through circuit breakers
- Enables multi-agent peer review via dialectic protocols
- Provides audit trails and calibration feedback

**In practice**: When an AI agent completes a task, my system evaluates its state thermodynamically and returns a governance decision (approve/reflect/reject), similar to how constitutional checks balance government branches.

### Demo

```python
# Agent submits work for governance review
result = process_agent_update(
    agent_id="research_agent",
    response_text="Completed analysis of dataset X",
    complexity=0.7
)

# System returns thermodynamic state + decision
{
    "decision": "approve",
    "metrics": {
        "E": 0.72,  # Energy (engagement)
        "I": 0.85,  # Integrity (coherence)
        "S": 0.18,  # Entropy (uncertainty)
        "V": 0.13   # Void (imbalance)
    },
    "governance": {
        "risk": 0.15,
        "coherence": 0.91,
        "verdict": "Safe to proceed"
    }
}
```

---

## Why It Matters

### The AI Safety Problem
As AI agents become more autonomous, we need:
- **Coordination mechanisms** - How do multiple agents work together safely?
- **Accountability systems** - How do we audit agent behavior?
- **Safety boundaries** - How do we prevent harmful agent drift?

### My Approach
Instead of ad-hoc rules, I designed a **thermodynamic governance framework**:

1. **Physics-Inspired Modeling**
   - Treat agent state like a thermodynamic system
   - Energy, Integrity, Entropy, Void (EISV) metrics
   - Natural equilibrium points ensure stability

2. **Multi-Agent Dialectic Protocol**
   - Agents can request peer review (thesis/antithesis/synthesis)
   - Distributed decision-making without central authority
   - Built-in checks and balances

3. **Comprehensive Security**
   - Conducted full security audit (found and fixed 7 vulnerabilities)
   - Eliminated 25% data loss bug in concurrent operations
   - Implemented defense-in-depth validation

---

## Technical Highlights

### 1. Thermodynamic State Dynamics (UNITARES Phase-3)

I implemented differential equations modeling agent state evolution:

```python
dE/dt = α(I - E) - βE·S + γE·‖Δη‖²          # Energy dynamics
dI/dt = -k·S + βI·C(V,Θ) - γI·I·(1-I)        # Integrity dynamics
dS/dt = -μ·S + λ₁·‖Δη‖² - λ₂·C(V,Θ) + β·c   # Entropy dynamics
dV/dt = κ(E - I) - δ·V                       # Void dynamics
```

**Key innovation**: Adaptive control via PI controller that adjusts λ₁ based on system feedback, ensuring stability across diverse agent behaviors.

### 2. Security Hardening

Conducted comprehensive security audit using penetration testing methodology:

**Vulnerabilities Found & Fixed:**
- ✅ Metadata race condition (HIGH) - 25% data loss in concurrent operations
- ✅ Unbounded input validation (MEDIUM) - potential DoS vectors
- ✅ History array inflation (LOW) - disk exhaustion risk
- ✅ Complexity bounds checking (MEDIUM) - stability concerns

**Results**:
- 85% vulnerability reduction (7 found → 1 remaining)
- Zero data loss in concurrent stress tests (10/10 success rate)
- State file growth capped (15KB vs. unbounded)

See full audit: [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md)

### 3. Multi-Agent Coordination

Built dialectic protocol for peer review without central authority:

```
Agent A (uncertain) → Requests review with thesis
                   ↓
System selects Agent B as reviewer
                   ↓
Agent B provides antithesis (critique)
                   ↓
Both agents work toward synthesis or convergence
                   ↓
Hard limits prevent manipulation, ensure safety
```

Handles edge cases like:
- Deadlock detection (timeout after N rounds)
- Reviewer disagreement (escalation protocols)
- Malicious agents (signature verification, safety bounds)

### 4. Observable & Debuggable

Every decision is traceable:
- Audit logs (append-only JSONL, tamper-evident)
- State history (last 100 updates per agent)
- Calibration tracking (predicted confidence vs. actual outcomes)
- Knowledge graphs (shared discoveries across agents)

---

## Architecture

### System Design

```
┌──────────────────────────────────────────────────────┐
│  MCP Clients                                         │
│  (Claude Desktop, Cursor, VS Code, Custom)           │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  MCP Server (Multi-Transport)                        │
│  ├─ SSE (Server-Sent Events) - Multi-client          │
│  └─ STDIO - Single process                           │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  Governance Handlers (47 tools)                      │
│  ├─ process_agent_update (main governance loop)     │
│  ├─ request_dialectic_review (peer review)          │
│  ├─ store_knowledge_graph (shared discoveries)      │
│  └─ get_governance_metrics (state inspection)       │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  Governance Core Engine                              │
│  ├─ UNITARES Dynamics (thermodynamic model)         │
│  ├─ Verdict Generation (approve/reflect/reject)     │
│  ├─ Coherence Function C(V,Θ)                       │
│  └─ State Validation & Bounds Checking               │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  Persistence Layer                                   │
│  ├─ Agent State (JSON with file locking)            │
│  ├─ Knowledge Graph (shared, rate-limited)          │
│  ├─ Calibration Data (confidence tracking)          │
│  └─ Audit Logs (append-only, forensics)             │
└──────────────────────────────────────────────────────┘
```

### Technology Stack

- **Language**: Python 3.11+ (type-annotated)
- **Protocol**: Model Context Protocol (MCP) by Anthropic
- **Concurrency**: `fcntl.flock` file locking, async/await
- **Data**: JSON (migrateable to SQLite/PostgreSQL)
- **Testing**: pytest, security test suites, stress tests
- **Security**: Input validation, bounds checking, audit logging

---

## Skills Demonstrated

### Systems Design
- ✅ Multi-agent coordination protocols
- ✅ Thermodynamic modeling (differential equations)
- ✅ State machines and lifecycle management
- ✅ Concurrent systems (locking, race condition prevention)

### Security
- ✅ Security auditing (penetration testing methodology)
- ✅ Vulnerability assessment and remediation
- ✅ Defense-in-depth validation
- ✅ Audit trail design

### Software Engineering
- ✅ MCP protocol integration
- ✅ RESTful-style tool design (47 handlers)
- ✅ Test-driven development
- ✅ Documentation and knowledge transfer

### AI Safety
- ✅ Alignment-focused architecture
- ✅ Governance mechanisms for autonomous agents
- ✅ Calibration and feedback systems
- ✅ Transparency and accountability

---

## Project Structure

```
governance-mcp-v1/
├── governance_core/              # Core dynamics engine
│   ├── dynamics.py              # UNITARES Phase-3 equations
│   ├── coherence.py             # Coherence function C(V)
│   ├── scoring.py               # Verdict generation
│   └── parameters.py            # Configuration
│
├── src/                         # MCP server implementation
│   ├── mcp_server_sse.py        # SSE multi-client transport
│   ├── mcp_server_std.py        # STDIO single-client transport
│   ├── governance_monitor.py    # State management
│   ├── mcp_handlers/            # 47 tools across 13 files
│   │   ├── core.py              # Main governance loop
│   │   ├── dialectic.py         # Peer review protocol
│   │   ├── knowledge_graph.py   # Shared discoveries
│   │   └── validators.py        # Security validation
│   └── state_locking.py         # Concurrency control
│
├── tests/                       # Comprehensive test suite
│   ├── security_audit_tests.py  # Penetration testing
│   ├── auth_and_bounds_tests.py # Security validation
│   └── verify_fixes.py          # Fix verification
│
├── docs/                        # Technical documentation
│   ├── SECURITY_AUDIT_REPORT.md        # Full security audit
│   ├── SECURITY_FIXES_APPLIED.md       # Remediation summary
│   ├── DYNAMICS_ACTIVATION_STATUS.md   # System status
│   └── COMPLEXITY_COUPLING_INVESTIGATION.md
│
├── examples/                    # Usage examples
│   └── sqlite_comparison.py     # Database migration guide
│
└── README.md                    # Main documentation
```

**Lines of Code**: ~8,000+ across 40+ files
**Test Coverage**: 12 security tests, integration tests
**Documentation**: 10+ technical documents

---

## Try It

### Quick Start

```bash
# Clone repository
git clone https://github.com/CIRWEL/AI-Governance-Portfolio.git
cd AI-Governance-Portfolio

# Start server
python3 src/mcp_server_sse.py --port 8765

# In another terminal, try the client
python3 scripts/mcp_sse_client.py process_agent_update \
    --agent-id demo_agent \
    --response-text "Testing governance system" \
    --complexity 0.5
```

### See It In Action

**[Demo Video]** (TK - coming soon)
**[Technical Writeup]** (TK - blog post)
**[Architecture Diagrams]** (see docs/)

---

## Research & Publications

**Conceptual Foundations:**
- Thermodynamic governance for multi-agent systems
- Dialectic protocols for distributed coordination
- Calibration and feedback in AI safety

**Related Domains:**
- Model Context Protocol (MCP)
- Constitutional AI approaches
- Multi-agent reinforcement learning

**Future Work:**
- Academic publication (in preparation)
- SQLite migration for ACID guarantees
- Expanded dialectic mediation protocols

---

## Contact & Collaboration

**Author**: Kenny Wang
**Email**: founder@cirwel.org
**GitHub**: [@CIRWEL](https://github.com/CIRWEL)
**Background**: AI Ethics Certificate + Self-Taught Systems Design

**I'm interested in:**
- AI safety research roles (research engineer, infrastructure)
- Collaboration on multi-agent coordination
- Governance infrastructure for production AI systems

**Portfolio Highlights:**
- ✅ Built complete governance system from scratch
- ✅ Conducted professional-grade security audit
- ✅ Demonstrated systems thinking and safety focus
- ✅ Self-taught technical skills with production-quality output

---

## Why This Project Matters (For Recruiters)

### What This Demonstrates

1. **I Can Build Real Systems**
   - Not just theoretical work - this runs in production
   - Handles concurrency, security, edge cases
   - Documented, tested, audited

2. **I Think About Safety**
   - Security audit found and fixed 7 vulnerabilities
   - Defense-in-depth approach
   - Governance-first design

3. **I Can Learn Independently**
   - Self-taught systems design, MCP protocol, thermodynamics
   - From concept to implementation to security hardening
   - Clear documentation for knowledge transfer

4. **I Care About AI Alignment**
   - Built accountability mechanisms
   - Multi-agent coordination without central control
   - Transparency and audit trails

### Unconventional Background, Proven Capabilities

My path to AI safety is non-traditional (music → ethics → systems engineering), but this project demonstrates:
- **Technical competence** - 8000+ lines of working code
- **Systems thinking** - thermodynamic modeling, multi-agent protocols
- **Security rigor** - professional penetration testing methodology
- **Research mindset** - novel approach to governance

---

## License

MIT License with attribution requirement
See [LICENSE](LICENSE) for details

---

**Status**: Production-ready v2.3.0 with security hardening
**Last Updated**: 2025-12-11
**Security Audit**: Completed (see [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md))

---

*This project is part of my portfolio demonstrating capabilities in AI safety infrastructure, multi-agent coordination, and secure systems design. Available for research collaboration or employment in AI safety/alignment.*
