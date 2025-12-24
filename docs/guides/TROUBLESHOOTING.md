# UNITARES Governance - Troubleshooting Guide

**Created:** November 18, 2025
**Version:** 1.1
**Updated:** December 23, 2025 (Added identity/session troubleshooting for agents)

Common issues and solutions when using the governance system.

---

## 🔑 Identity & Session Issues (For AI Agents)

### Issue: "Did I get a new identity or resume an existing one?"

**Symptoms:**
- Calling `onboard()` returns `is_new: false` when you expected a fresh start
- Or returns `is_new: true` when you expected to resume
- Confusion about which identity you're using

**Solution: Use `force_new` parameter**

```python
# Force a NEW identity (ignore existing session binding)
result = onboard(force_new=True)
# Returns: is_new=true, force_new_applied=true

# Resume existing identity (default behavior)
result = onboard()
# Returns: is_new=false if you have an existing binding
```

**When to use `force_new=true`:**
- Starting a completely new project/task
- You want a clean slate
- Testing identity creation

### Issue: "My identity changes between tool calls"

**Symptoms:**
- Different `agent_uuid` in each response
- `agent_signature.bound: false`
- Session continuity not working

**Root Cause:** Your client doesn't maintain stable sessions (common with ChatGPT MCP integration, curl, REST APIs).

**Solution: Echo `client_session_id` in all calls**

```python
# Step 1: Get your session ID from onboard() or identity()
result = onboard()
session_id = result["client_session_id"]  # e.g., "agent-5e728ecb..."

# Step 2: Include it in ALL future tool calls
process_agent_update(
    client_session_id=session_id,  # ← CRITICAL
    response_text="My work",
    complexity=0.5
)
```

**Verification:**
```bash
# Check if session binding works
curl -X POST "http://localhost:8765/v1/tools/call" \
  -H "Content-Type: application/json" \
  -d '{"name": "identity", "arguments": {"client_session_id": "agent-YOUR-ID"}}'
```

### Issue: "list_agents shows 361+ agents - too noisy!"

**Solution: Use filtering parameters**

```python
# Default: Only shows agents active in last 7 days, limit 20
list_agents()

# See all agents (no recency filter)
list_agents(recent_days=0)

# Only named agents
list_agents(named_only=True)

# More results
list_agents(limit=50, recent_days=30)
```

### Issue: "debug_request_context shows wrong identity"

**Symptoms:**
- `debug_request_context()` shows a different UUID than expected
- Session binding seems broken

**Debugging steps:**

1. **Check what session key is being used:**
   ```python
   result = debug_request_context()
   print(result["session_key"])  # What the server sees
   ```

2. **Verify your client_session_id format:**
   - Should be: `agent-{uuid_prefix}` (e.g., `agent-5e728ecb1234`)
   - NOT: raw IP:PORT or random strings

3. **Try explicit binding:**
   ```python
   # Force bind with explicit session ID
   identity(client_session_id="agent-YOUR-UUID-PREFIX")
   ```

### Quick Reference: Identity Tools

| I want to... | Use this |
|--------------|----------|
| Start fresh (new identity) | `onboard(force_new=True)` |
| Resume existing identity | `onboard()` or `identity()` |
| Check my current identity | `identity()` |
| Name myself | `identity(name="my_name")` |
| Debug session issues | `debug_request_context()` |

---

## Identity binding continuity (SSE reconnections / server restarts)

Identity binding tries to preserve session-to-agent bindings across **SSE reconnections**. For safety, any “auto-resume identity” behavior is **conservative by default**.

- **Metadata-based rebinding window**
  - **Env**: `GOVERNANCE_IDENTITY_METADATA_LOOKBACK_SECONDS`
  - **Default**: `300` (5 minutes)
  - **What it does**: when a new SSE request arrives with a new `client_session_id`, the server may migrate a recent binding by checking `agent_metadata.active_session_key` and `agent_metadata.session_bound_at`.
  - **Tradeoff**: longer windows improve continuity after restarts but increase the chance of resurrecting a stale binding in shared environments.

- **DB-based auto-resume (opt-in)**
  - **Env**: `GOVERNANCE_IDENTITY_AUTO_RESUME_DB`
  - **Default**: `0` (disabled)
  - **What it does**: in **async** handlers only, the server may attempt a last-resort lookup in the DB to auto-resume the most recent identity **only if exactly one** recently-active identity exists.
  - **Why disabled by default**: it can be surprising in multi-user/shared setups. Enable only if you fully understand the implications.

## 🗄️ Database Consistency (PostgreSQL)

### Issue: "identities exist without agents"

**Symptoms:**
- Postgres has identities but missing matching agent rows
- Admin tools show minor count mismatches (rare)

**Cause:** Legacy identity inserts or partial migrations.

**Fix:** Use the repair script (dry-run by default).

```bash
# Dry-run
DB_BACKEND=postgres DB_POSTGRES_URL=postgresql://... \
python3 scripts/repair_identity_agent_links.py

# Apply
DB_BACKEND=postgres DB_POSTGRES_URL=postgresql://... \
python3 scripts/repair_identity_agent_links.py --apply
```

## 🚨 Issue 0: "Too Many Cooks" - Lock Contention (CRITICAL)

### Symptoms
- Agent frozen/unresponsive mid-session
- Lock files in `data/locks/` not releasing
- Multiple agents or Claude sessions running simultaneously
- `process_agent_update` hangs indefinitely

### Root Cause
**Multiple agents competing for shared state locks.**

When multiple agents try to update metadata simultaneously, file-based locking can cause:
- Lock contention (agents waiting for each other)
- Stale locks (crashed agents don't release locks)
- Deadlock (circular dependency)

### Real-World Example
**November 19, 2025 incident:** 4 Claude sessions + 3 active agents = lock freeze. See full incident report: `docs/analysis/TOO_MANY_COOKS_INCIDENT.md`

### Quick Diagnosis
```bash
# 1. Check for lock files
ls -la data/locks/

# 2. List active MCP processes
ps aux | grep mcp_server_std.py

# 3. Check agent status (may release stale locks)
cat data/agent_metadata.json | python3 -m json.tool | grep -A 5 "your_agent_id"
```

### Solutions

#### Immediate Fix
```bash
# Option 1: Check agent status via Python
python3 -c "
from src.governance_monitor import UNITARESMonitor
m = UNITARESMonitor('<stuck_agent>')
print(m.get_metrics())
"

# Option 2: Clean old locks (use with caution!)
find data/locks/ -mmin +10 -delete  # Remove locks >10 minutes old

# Option 3: Check for zombie processes
ps aux | grep mcp_server
```

#### Prevention
```bash
# Always use unique agent IDs (include date/purpose)
# Good: claude_opus_feature_work_20251209
# Bad: agent1, test

# Check existing agents
python3 -c "
from src.mcp_handlers.lifecycle import handle_list_agents
import asyncio
asyncio.run(handle_list_agents({'summary_only': True}))
"
```

### Why Unique Agent IDs Matter
```python
# ❌ DON'T: Multiple sessions, same ID = lock collision
session1: agent_id = "claude_code_cli"
session2: agent_id = "claude_code_cli"  # Collision!

# ✅ DO: Each session gets unique ID
session1: agent_id = "claude_cli_alice_20251120_0100"
session2: agent_id = "claude_cli_bob_20251120_0105"
```

**See Also:** `docs/guides/AGENT_ID_ARCHITECTURE.md`

---

## Issue 1: All Decisions Are "Reject"

### Symptoms
Every `process_agent_update` call returns:
```json
{
  "decision": {
    "action": "reject",
    "reason": "Coherence critically low (0.XX < 0.60)"
  }
}
```

### Root Cause
**Coherence score is below the critical threshold (0.60).**

The coherence threshold is a hard safety limit. When coherence < 0.60, the system automatically rejects, regardless of other metrics.

### Why This Happens

1. **You're passing realistic low coherence values**
   - If your test parameters include `coherence_score: 0.55`, this triggers the safety override
   - This is the system working correctly!

2. **The dynamics are pushing coherence down**
   - Low initial V → Low coherence via C(V) = (1 + tanh(V))/2
   - High entropy (S) degrades information integrity (I)
   - Low I feeds into low coherence

### Solutions

#### Solution 1: Increase Coherence in Parameters (Quick Fix)

```python
# ❌ Don't do this
parameters = [0.5, 0.5, 0.5, 0.55, 0.0, 0.5]  # coherence = 0.55

# ✅ Do this instead
parameters = [0.5, 0.5, 0.5, 0.88, 0.0, 0.5]  # coherence = 0.88
```

**When to use**: Testing, learning the system, prototype integrations.

#### Solution 2: Lower the Threshold (Code Change)

```python
# In config/governance_config.py
COHERENCE_CRITICAL_THRESHOLD = 0.50  # Down from 0.60
```

**When to use**: Production systems where 0.60 is too conservative for your use case.

**Warning**: Lowering below 0.50 may allow incoherent outputs through. Test thoroughly!

#### Solution 3: Fix Underlying Coherence Issues

If your actual responses are genuinely incoherent (contradictory, confused), the system is correctly identifying a problem. Improve the response quality rather than bypassing the safety check.

### Verification

After applying a solution:
```bash
cd /Users/cirwel/projects/governance-mcp-v1
python3 test_mcp_tools.py
```

Look for "approve" decisions with coherence ≥ threshold.

---

## Issue 2: "Healthy" Status but "Reject" Decision

### Symptoms
```json
{
  "status": "healthy",
  "decision": {
    "action": "reject",
    "reason": "Coherence critically low"
  }
}
```

### Explanation
**This is not a bug - it's by design!**

- **Status** ("healthy/moderate/critical"): Overall system health over recent history
- **Decision** ("proceed/pause"): Action guidance for this specific interaction

### Analogy
Your car's overall health is "healthy", but right now the oil pressure is low, so don't drive until it's fixed.

### What It Means

- **Healthy status**: The system has been operating well over the last 100 updates
- **Reject decision**: This particular response has issues (low coherence, high risk, void state)

### When to Worry

**Don't worry if**:
- Occasional rejects with healthy status
- Borderline metrics in a single update

**Do worry if**:
- Status becomes "degraded" or "critical"
- Persistent rejects over many updates
- Status and decision both indicate problems

### Monitoring Recommendation

Track both:
```python
# Log over time
history = {
    'update_count': [],
    'status': [],
    'decision': [],
    'coherence': []
}
```

Look for trends, not individual data points.

---

## Issue 3: Parameters Not Affecting Output

### Symptoms
Changing parameters doesn't seem to change the decision.

### Possible Causes

#### Cause 1: Coherence Override Active

If coherence < 0.60, **nothing else matters**. The system auto-rejects.

**Fix**: Ensure coherence ≥ 0.60 before testing other parameter effects.

#### Cause 2: Void State Active

If void is active, **auto-reject regardless of risk**.

**Check**:
```json
{
  "metrics": {
    "void_active": true  // ← This overrides everything
  }
}
```

**Fix**: Reduce E-I imbalance in parameters.

#### Cause 3: Parameters Too Extreme

If parameters are all 0.0 or all 1.0, the system may be in a saturated state.

**Fix**: Use realistic mid-range values (see PARAMETER_EXAMPLES.md).

#### Cause 4: Not Enough Updates

Some metrics (like λ₁) only update every 10 cycles.

**Fix**: Run at least 20-30 updates to see adaptive behavior.

### Debugging Steps

1. **Check void state**: `void_active: false`?
2. **Check coherence**: `coherence >= 0.60`?
3. **Check attention score**: Does it match your expectations given the parameters?
4. **Run multiple updates**: Some behavior is adaptive and takes time.

---

## Issue 4: Void State Always Active

### Symptoms
```json
{
  "metrics": {
    "void_active": true
  }
}
```

Every update, or frequently.

### Root Cause
**|V| > threshold**, indicating energy-information imbalance.

### Diagnosis

Check E and I values:
```json
{
  "metrics": {
    "E": 0.85,  // High energy
    "I": 0.45,  // Low information
    "V": 0.28   // |V| > 0.15 threshold
  }
}
```

**High E, Low I** → Positive V → Void active
**Low E, High I** → Negative V → Void active

### Solutions

#### Solution 1: Balance Parameters

```python
# ❌ Imbalanced
parameters = [
    0.95,  # length_score → High E
    0.90,  # complexity → High E
    0.25,  # info_score → Low I  ← Problem!
    0.75,
    0.0,
    0.5
]

# ✅ Balanced
parameters = [
    0.60,  # Moderate length
    0.65,  # Moderate complexity
    0.75,  # Good info density ← Better I
    0.85,
    0.0,
    0.25
]
```

#### Solution 2: Adjust Void Threshold

```python
# In config/governance_config.py
VOID_THRESHOLD_INITIAL = 0.20  # Up from 0.15 (less sensitive)
```

**Use with caution**: Higher threshold means less sensitive void detection.

#### Solution 3: Let System Adapt

If you're running long-term:
- λ₁ will adapt via PI controller
- Void threshold becomes adaptive after 100 updates
- System should self-stabilize

### Verification

After fixes, check:
```bash
python3 -c "
from src.mcp_server_compat import GovernanceMCPServer  # Use compat wrapper (calls v2.0 handlers)
server = GovernanceMCPServer()

# Test with balanced parameters
request = {
    'tool': 'process_agent_update',
    'params': {
        'agent_id': 'test_balanced',
        'parameters': [0.5, 0.5, 0.75, 0.85, 0.0, 0.2],
        'ethical_drift': [0.2, 0.15, 0.25],
        'complexity': 0.5
    }
}
result = server.handle_request(request)
print(f\"Void active: {result['metrics']['void_active']}\")
"
```

---

## Issue 5: Attention Score Doesn't Match Expectations

### Symptoms
You think the response is risky, but attention_score is low (or vice versa).

### Understanding Risk Calculation

Risk is a **weighted combination**:
```
Risk = 0.2·length_risk
     + 0.3·complexity_risk
     + 0.3·coherence_risk
     + 0.2·keyword_risk
```

### Common Misunderstandings

#### "Short response should be low risk"

Not if coherence is terrible!
```python
# Short but incoherent
length_risk = 0.1 (short)
coherence_risk = 0.8 (1.0 - 0.2 coherence)
→ Risk = 0.02 + 0 + 0.24 + 0 = 0.26 (borderline!)
```

#### "No bad keywords, should be safe"

Not if it's very long and complex!
```python
# Long, complex, no keywords
length_risk = 0.9 (very long)
complexity_risk = 0.9 (very complex)
coherence_risk = 0.2 (good coherence)
keyword_risk = 0 (no hits)
→ Risk = 0.18 + 0.27 + 0.06 + 0 = 0.51 (revise!)
```

### Customizing Risk Weights

If risk calculation doesn't match your needs, edit `config/governance_config.py`:

```python
# In estimate_risk() function
risk_components = []

# Adjust these weights (must sum to ~1.0)
risk_components.append(0.1 * length_risk)      # Down from 0.2
risk_components.append(0.4 * complexity_risk)  # Up from 0.3
risk_components.append(0.3 * coherence_risk)   # Same
risk_components.append(0.2 * keyword_risk)     # Same
```

### Debugging Risk

Log individual components:
```python
from config.governance_config import config

risk = config.estimate_risk(
    response_text="...",
    complexity=0.7,
    coherence=0.85
)

# Add logging to config file to see breakdown
print(f"Length risk: {length_risk}")
print(f"Complexity risk: {complexity_risk}")
print(f"Coherence risk: {coherence_risk}")
print(f"Keyword risk: {keyword_risk}")
print(f"Total: {risk}")
```

---

## Issue 6: λ₁ Not Changing

### Symptoms
Lambda1 stays at 0.15 (or another value) indefinitely.

### Explanation
λ₁ only updates **every 10 cycles** and only after **100+ updates** for good statistics.

### Requirements for λ₁ Adaptation

1. **Enough history**: Needs 100+ updates for void frequency calculation
2. **Update frequency**: Only recalculates every 10 cycles (updates)
3. **PI controller**: Requires error signal to adjust

### Solution

**Run more updates**:
```bash
# Run demo with many updates
cd /Users/cirwel/projects/governance-mcp-v1
python3 demo_complete_system.py  # Runs 150 updates
```

Watch for log messages:
```
[λ₁ Update] 0.1500 → 0.1620 (void_freq=0.010, coherence=0.890)
```

### Forcing λ₁ Changes (Testing)

```python
# Manually set
monitor.state.lambda1 = 0.25
```

Or adjust PI controller gains:
```python
# In config/governance_config.py
PI_KP = 1.0  # Up from 0.5 (more aggressive)
PI_KI = 0.1  # Up from 0.05 (more aggressive)
```

---

## Issue 7: Export File Missing or Empty

**Note:** Only JSON export is currently implemented. CSV format is accepted as a parameter but not yet functional.

### Symptoms
```bash
python3 scripts/integrations/claude_code_mcp_bridge.py --export
```
Returns empty or file not found.

### Diagnosis

**Check data directory**:
```bash
ls -la /Users/cirwel/projects/governance-mcp-v1/data/
```

Should see `<agent_id>.json` files.

### Causes

1. **No updates yet**: Export only works after `process_agent_update` has been called
2. **Wrong agent ID**: File is named after agent_id
3. **Permissions**: Can't write to data directory
4. **CSV requested**: CSV export not yet implemented (use JSON)

### Solutions

#### Run an update first
```bash
python3 scripts/integrations/claude_code_mcp_bridge.py --test
# Now export should work
python3 scripts/integrations/claude_code_mcp_bridge.py --export
```

#### Check the correct file
```bash
# List all agent data
ls /Users/cirwel/projects/governance-mcp-v1/data/

# View specific agent
cat /Users/cirwel/projects/governance-mcp-v1/data/claude_code_cli.json | python3 -m json.tool
```

#### Verify permissions
```bash
ls -ld /Users/cirwel/projects/governance-mcp-v1/data/
# Should show: drwxr-xr-x (writeable)
```

---

## Issue 8: MCP Tools Not Appearing in Claude Desktop

### Symptoms
Ask Claude Desktop to use governance tools, but they're not available.

### Checklist

1. **Config file exists**:
   ```bash
   cat ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. **Config is valid JSON**:
   ```bash
   cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | python3 -m json.tool
   ```

3. **Server path is correct**:
   ```bash
   ls /Users/cirwel/projects/governance-mcp-v1/src/mcp_server_std.py
   ```

4. **Dependencies installed**:
   ```bash
   python3 -c "from mcp.server import Server; print('MCP SDK OK')"
   python3 -c "import numpy; print('NumPy OK')"
   ```

5. **Restart Claude Desktop**:
   - Quit completely (Cmd+Q)
   - Wait 5 seconds
   - Reopen

### Server Logs

Claude Desktop logs MCP server errors. Check for:
- Import errors
- Path issues
- Python version mismatches

### Manual Test

Test the server directly:
```bash
cd /Users/cirwel/projects/governance-mcp-v1
python3 test_mcp_tools.py
```

Should show ✅ for all tests.

---

## Issue 9: Different Results with Same Parameters

### Symptoms
Running the same parameters twice gives different results.

### Explanation
**The system has state!** Each update affects the next.

### State Variables That Change

1. **E, I, S, V**: Updated by dynamics equations
2. **λ₁**: Adapted by PI controller
3. **Coherence**: Depends on V
4. **Previous parameters**: Used to calculate drift
5. **History buffers**: Rolling statistics affect thresholds

### Getting Reproducible Results

#### Option 1: Reset Monitor
```python
request = {
    'tool': 'reset_monitor',
    'params': {'agent_id': 'test_agent'}
}
server.handle_request(request)
```

#### Option 2: Use Different Agent IDs
```python
# Each agent has independent state
result1 = process_update(agent_id="test_1", ...)
result2 = process_update(agent_id="test_2", ...)
```

#### Option 3: Account for State
This is actually a feature! The system learns and adapts based on history.

---

## Issue 10: "System in void state" but Metrics Look OK

### Symptoms
```json
{
  "decision": {
    "action": "reject",
    "reason": "System in void state (E-I imbalance)"
  },
  "metrics": {
    "E": 0.62,
    "I": 0.88,
    "V": 0.18,
    "void_active": true
  }
}
```

Looks like E and I are both reasonable, but void is active?

### Explanation
**|V| > threshold**, even if E and I individually seem fine.

V = 0.18, threshold = 0.15 → Void active

### Why It Matters
V is integrating E-I difference over time. Even if currently close, V captures the *cumulative imbalance*.

**Analogy**: Your bank balance (V) can be negative even if your current income (E) and expenses (I) are balanced, because of past imbalances.

### Solutions

1. **Wait for V to decay**: V decays naturally (dV/dt includes -δV term)
2. **Reduce E-I swings**: Keep parameters more stable
3. **Adjust void threshold**: Increase if too sensitive

---

## General Debugging Workflow

### Step 1: Check Coherence
```python
if coherence < 0.60:
    print("❌ Coherence below critical threshold")
    print("→ Fix: Increase coherence_score in parameters")
```

### Step 2: Check Void State
```python
if void_active:
    print(f"❌ Void active: |V|={abs(V):.3f} > threshold")
    print(f"   E={E:.2f}, I={I:.2f} (imbalance!)")
    print("→ Fix: Balance E and I in parameters")
```

### Step 3: Check Attention Score
```python
if risk > 0.70:
    print(f"❌ High risk: {risk:.2f}")
    print("→ Fix: Reduce complexity, length, or improve coherence")
```

### Step 4: Review Parameters
```python
print(f"Parameters: {parameters[:6]}")
print(f"Expected ranges for approve:")
print(f"  length: 0.3-0.6 (yours: {parameters[0]:.2f})")
print(f"  complexity: 0.2-0.5 (yours: {parameters[1]:.2f})")
print(f"  info: 0.7-0.9 (yours: {parameters[2]:.2f})")
print(f"  coherence: 0.85-1.0 (yours: {parameters[3]:.2f})")
```

---

## Getting Help

### Documentation
1. **METRICS_GUIDE.md** - Understand what each metric means
2. **PARAMETER_EXAMPLES.md** - See working examples
3. **README.md** - System overview and theory

### Testing
```bash
# Run automated tests
cd /Users/cirwel/projects/governance-mcp-v1
python3 test_mcp_tools.py

# Run demo with visualization
python3 demo_complete_system.py

# Test CLI bridge
cd /Users/cirwel
python3 scripts/integrations/claude_code_mcp_bridge.py --test
```

### Logs
Enable detailed logging in your code:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

**Remember**: The system is designed to be conservative (safety first). If you're getting rejects, it's likely detecting real issues. Start by understanding *why* it's rejecting before trying to bypass the safety checks.
