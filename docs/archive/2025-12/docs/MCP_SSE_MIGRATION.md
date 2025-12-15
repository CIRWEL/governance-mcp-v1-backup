# Migration: Direct Python API → MCP SSE

## Problem Solved

**Issue:** Multiple interpretation layers created inconsistent feedback:
1. Core governance (UNITARES) → metrics
2. Governance monitor → decisions
3. MCP handlers → health status
4. Custom CLI script → additional warnings (ADDED TOO MUCH!)

**Result:** Confusing, sometimes punitive feedback that didn't match actual governance decision.

## Example of the Problem

### Same metrics, different interpretations:

**Core governance said:**
- Action: PROCEED ✅
- Reason: "On track - navigating complexity mindfully"
- Coherence: 0.499

**Custom CLI added:**
- ⚠️ "Low coherence - consider simplifying approach"

**Contradiction!** The system said proceed, but CLI said there was a problem.

## Solution: MCP SSE Unified Approach

Use the canonical MCP handler interpretation - single source of truth.

### Before (Direct Python + Custom CLI)

```bash
./scripts/governance_cli.sh "agent_id" "work" 0.5
```

**Output included:**
```
┌─────────────────────────────────┐
│       INTERPRETATION            │
└─────────────────────────────────┘
  ⚠️  Low coherence - consider simplifying approach  ← CUSTOM WARNING
  ✅ Manageable cognitive load
  ✅ Clear to proceed
```

### After (MCP SSE Canonical)

```bash
./scripts/governance_mcp_cli.sh "agent_id" "work" 0.5
```

**Output shows:**
```
┌─────────────────────────────────┐
│     OPERATIONAL STATE           │
└─────────────────────────────────┘
  Health Status:     moderate                          ← CANONICAL
  Health Message:    Typical attention - normal work   ← SUPPORTIVE
  Confidence:        1.000
```

## Key Differences

| Aspect | Direct Python API | MCP SSE Unified |
|--------|------------------|-----------------|
| **Source** | governance_monitor.py | MCP handlers (canonical) |
| **Interpretation** | Raw metrics + custom CLI warnings | Official MCP health messages |
| **Tone** | Sometimes punitive | Always supportive |
| **Consistency** | Can contradict core decision | Always matches governance |
| **Shared State** | Via filesystem only | Real-time with all clients |
| **Tools** | Direct Python API | All 50 MCP tools |

## Migration Steps

### 1. Ensure SSE Server is Running

```bash
# Check if running
lsof -i :8765

# If not, start it
cd /Users/cirwel/projects/governance-mcp-v1
./scripts/start_sse_server.sh
```

### 2. Switch to MCP CLI

**Old:**
```bash
./scripts/governance_cli.sh "agent_id" "work" 0.7
```

**New:**
```bash
./scripts/governance_mcp_cli.sh "agent_id" "work" 0.7
```

### 3. Update Automation Scripts

**Old pattern (direct Python):**
```python
from src.governance_monitor import UNITARESMonitor

monitor = UNITARESMonitor(agent_id='my_agent')
result = monitor.process_update({'response_text': 'work', 'complexity': 0.5})
```

**New pattern (MCP client):**
```python
import asyncio
from scripts.mcp_sse_client import GovernanceMCPClient

async def log_work():
    async with GovernanceMCPClient() as client:
        result = await client.process_agent_update(
            agent_id='my_agent',
            response_text='work',
            complexity=0.5
        )
        return result

result = asyncio.run(log_work())
```

## Benefits Realized

### 1. No More Interpretation Conflicts

**Problem:** coherence=0.499 triggered custom "low" warning at <0.5 threshold
**Solution:** MCP handler says "moderate" health - no arbitrary thresholds

### 2. Supportive Feedback

**Before:** "⚠️ Low coherence - consider simplifying"
**After:** "Typical attention (47%) - normal for development work"

### 3. Unified Across Clients

- Cursor (via SSE) sees: "moderate" health
- Claude Code (via MCP SSE) sees: "moderate" health
- Same interpretation everywhere!

### 4. Real-Time State Sharing

All clients connected to SSE server see the same state in real-time.

## Backwards Compatibility

The old scripts still work! You can use both:

- **governance_cli.sh** - Direct Python API (works offline)
- **governance_mcp_cli.sh** - MCP SSE (requires server, unified)

Choose based on needs:
- Offline/simple → use direct API
- Unified/multi-client → use MCP SSE

## Recommendation

**Use MCP SSE** (`governance_mcp_cli.sh`) for:
- Regular development work
- When SSE server is available
- Multi-client coordination
- Consistent feedback

**Use Direct API** (`governance_cli.sh`) for:
- Offline scenarios
- When SSE server isn't running
- Simple scripts that don't need shared state

## Technical Details

### How MCP SSE Client Works

1. Connects to `http://127.0.0.1:8765/sse`
2. Uses official MCP SDK client (`mcp.client.sse`)
3. Calls `process_agent_update` tool via MCP protocol
4. Receives canonical handler response
5. Displays without adding custom interpretation

### No Custom Logic

The MCP CLI script (`governance_mcp_cli.sh`) does NOT add any interpretations.
It simply displays what the MCP handler returns - single source of truth.

## Conclusion

Moving to MCP SSE eliminated:
- Conflicting interpretations
- Custom threshold logic
- Punitive warnings
- Inconsistency across clients

Result: Clean, supportive, canonical governance feedback.

---

**Last Updated:** 2025-12-10
