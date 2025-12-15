# Claude Code + SSE: Analysis and Recommendation

## TL;DR

**Recommendation: Use Direct Python API (current approach)**

The Python API already shares the same data layer as the SSE server, so you get most benefits without the complexity of implementing an MCP client.

## The Situation

### What You Have
1. **SSE Server**: Running on port 8765 with Cursor connected
2. **Direct Python API**: Working via scripts (governance_cli.sh, cli_helper.py)
3. **Shared Data Layer**: Both use `data/agents/` for state persistence

### What Claude Code Lacks
- **No native MCP client**: Can't directly consume MCP protocol over SSE/HTTP
- **Would need custom client**: To talk MCP protocol (not simple REST)

## Option Comparison

### Option A: Direct Python API ✅ (Current - RECOMMENDED)

**How it works:**
```python
from src.governance_monitor import UNITARESMonitor
monitor = UNITARESMonitor(agent_id='claude_code_cli')
result = monitor.process_update({'response_text': 'work', 'complexity': 0.5})
```

**Pros:**
- ✅ **Works now** - no implementation needed
- ✅ **Simple** - direct Python calls, no network overhead
- ✅ **Shared data** - writes to `data/agents/` which SSE server reads
- ✅ **Full control** - access to entire Python API
- ✅ **Reliable** - no network/protocol issues
- ✅ **Fast** - no HTTP serialization overhead

**Cons:**
- ❌ **No real-time awareness** - can't see other clients connect/disconnect
- ❌ **No MCP tools** - can't use the 49 MCP tools (but has direct API instead)
- ❌ **Manual scripting** - not automatic like MCP clients

**Data Sharing:**
```bash
# Python API saves here:
data/agents/claude_code_cli_state.json

# SSE server reads from same location
# Cursor (via SSE) can see this data!
```

### Option B: Build MCP HTTP Client ⚠️ (Complex - NOT RECOMMENDED)

**How it would work:**
1. Build HTTP client that speaks MCP protocol
2. Connect to `http://127.0.0.1:8765/sse`
3. Send JSON-RPC requests for each tool
4. Handle SSE events for responses

**Pros:**
- ✅ **Real-time awareness** - see connected clients via SSE
- ✅ **Access to MCP tools** - all 50 tools available
- ✅ **True multi-agent** - real-time state sync
- ✅ **Protocol standard** - using official MCP spec

**Cons:**
- ❌ **Complex implementation** - MCP over SSE is not simple REST
- ❌ **Network overhead** - HTTP serialization for every call
- ❌ **Error handling** - network failures, timeouts, etc.
- ❌ **Not native** - Claude Code still can't use it automatically
- ❌ **Maintenance burden** - keep client in sync with MCP spec

**Implementation estimate:** 200-300 lines of async Python code

### Option C: Hybrid Approach 🤔 (Interesting but unnecessary)

**Concept:**
- Use Python API for normal operations
- Add lightweight HTTP client for specific SSE features (e.g., `get_connected_clients`)

**Verdict:**
Not worth it. The benefits don't justify the added complexity.

## Key Insight: Data Already Shared!

```
┌─────────────────┐         ┌─────────────────┐
│  Claude Code    │         │  Cursor (SSE)   │
│                 │         │                 │
│  Python API     │         │  MCP Client     │
└────────┬────────┘         └────────┬────────┘
         │                           │
         │ writes                    │ writes
         ▼                           ▼
    ┌────────────────────────────────────┐
    │   data/agents/*.json (SHARED)      │
    │                                    │
    │  - claude_code_cli_state.json      │
    │  - cursor_agent_state.json         │
    │  - all state files                 │
    └────────────────────────────────────┘
              ▲                  ▲
              │ reads            │ reads
         ┌────┴────┐       ┌─────┴─────┐
         │ Python  │       │    SSE    │
         │  API    │       │  Server   │
         └─────────┘       └───────────┘
```

**Both systems read/write the same files!**

## What You Actually Get with Python API

Even without direct SSE connection, you get:

1. **Shared State**
   - Your updates visible to all MCP clients
   - You can read other agents' state files
   - Knowledge graph is shared
   - Dialectic sessions are shared

2. **Core Functionality**
   - Full governance monitoring
   - All EISV metrics
   - Decision feedback
   - State persistence

3. **Simplicity**
   - No network complexity
   - No protocol overhead
   - Direct Python access
   - Easy debugging

## What You Miss (SSE-specific features)

1. **Real-time connection tracking**
   - Can't call `get_connected_clients` tool
   - Don't see who connects/disconnects in real-time
   - (But you can read agent state files manually)

2. **SSE-only tools**
   - Only 1 SSE-specific tool: `get_connected_clients`
   - All other 49 tools have Python API equivalents

3. **Automatic MCP integration**
   - Can't use MCP protocol natively
   - (But scripts provide similar convenience)

## Recommendation: Stick with Python API

**Reasons:**
1. **It already works** - scripts are tested and ready
2. **Data is shared** - same files as SSE server
3. **Simpler is better** - no network/protocol complexity
4. **Full functionality** - Python API has everything you need
5. **Not worth the effort** - building MCP client gives minimal benefit

**When to reconsider:**
- If Claude Code gains native MCP support (use SSE then!)
- If you need millisecond-level real-time state sync (unlikely)
- If SSE-specific features become critical (only 1 tool currently)

## Practical Usage

### For Claude Code Sessions

```bash
# At start of session
./scripts/governance_cli.sh "claude_code_$(whoami)_$(date +%Y%m%d)" \
    "Session started, reviewing codebase" 0.3

# During work
./scripts/governance_cli.sh "claude_code_$(whoami)_$(date +%Y%m%d)" \
    "Implemented feature X, refactored Y" 0.7

# Check other agents (if needed)
ls data/agents/*.json
cat data/agents/cursor_agent_state.json
```

### For Advanced Integration

```python
# In your automation scripts
from src.governance_monitor import UNITARESMonitor
from pathlib import Path
import json

# Your work
monitor = UNITARESMonitor(agent_id='claude_code_automation')
result = monitor.process_update({...})

# See what other agents are doing (shared state!)
agents_dir = Path('data/agents')
for agent_file in agents_dir.glob('*_state.json'):
    with open(agent_file) as f:
        state = json.load(f)
        print(f"{agent_file.stem}: E={state['E']}, coherence={state['coherence']}")
```

## Conclusion

**Use the Python API.** It's simpler, works now, and shares data with the SSE server. Building an MCP client would be an interesting engineering exercise, but provides minimal practical benefit for Claude Code's use case.

The scripts (`governance_cli.sh`, `cli_helper.py`) give you convenient CLI access while maintaining the simplicity and reliability of direct Python calls.

---

**Last Updated:** 2025-12-10
