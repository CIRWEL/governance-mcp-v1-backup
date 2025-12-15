# Tools Server Separation Proposal

**Date**: 2025-12-12  
**Status**: Proposal  
**Author**: Architecture Analysis

## Executive Summary

The current architecture bundles 53 tools with the governance server, creating tight coupling and scalability limitations. This proposal outlines a strategy to separate tools into their own server(s) for better modularity, scalability, and maintainability.

## Current State Analysis

### Architecture Overview

- **53 tools** across 9 categories
- **~10,145 lines** of handler code across 21 files
- **152 direct references** to `mcp_server` singleton
- **Tight coupling** via `shared.py` module

### Tool Usage Patterns (Last 168 Hours)

**Heavy Usage (80% of calls):**
- `process_agent_update`: 230 calls (14.4%)
- `store_knowledge_graph`: 169 calls (10.6%)
- `search_knowledge_graph`: 118 calls (7.4%)
- `get_agent_api_key`: 85 calls (5.3%)
- `list_agents`: 83 calls (5.2%)

**Light Usage (20% of calls):**
- Many tools have <10 calls total
- Some tools only 1-2 calls in 168 hours

### Dependencies

All tools depend on `mcp_server` singleton for:
- `agent_metadata` dict (agent lifecycle data)
- `monitors` dict (governance state)
- `get_or_create_monitor()` (state management)
- `load_metadata()` (data loading)
- `schedule_metadata_save()` (persistence)

## Problems with Current Architecture

1. **Tight Coupling**: Tools can't exist without governance server
2. **Scalability**: Can't scale tools independently
3. **Resource Isolation**: Tool failures affect entire server
4. **Deployment**: All tools must be deployed together
5. **Performance**: Lightweight tools carry full governance overhead
6. **Maintainability**: Hard to add/modify tools without touching core

## Proposed Architecture

### Option 1: Single Tools Server (Recommended)

**Structure:**
```
governance-server (core)
  ├── process_agent_update
  ├── get_governance_metrics
  └── simulate_update

tools-server (all other tools)
  ├── Knowledge Graph tools
  ├── Lifecycle tools
  ├── Observability tools
  ├── Admin tools
  ├── Export tools
  └── Dialectic tools
```

**Benefits:**
- Simple separation (2 servers)
- Tools server can scale independently
- Governance server stays focused on core EISV logic
- Easier to deploy tools closer to users

**Challenges:**
- Tools server still needs access to governance state
- Need API/interface between servers

### Option 2: Microservices Architecture

**Structure:**
```
governance-server (core)
tools-server (lightweight tools)
knowledge-server (knowledge graph tools)
admin-server (admin/workspace tools)
export-server (export tools)
```

**Benefits:**
- Maximum flexibility
- Each service can scale independently
- Clear separation of concerns

**Challenges:**
- More complex deployment
- More inter-service communication
- Overhead for small services

### Option 3: Hybrid (Recommended for Phase 1)

**Structure:**
```
governance-server (core + stateful tools)
  ├── process_agent_update
  ├── get_governance_metrics
  ├── simulate_update
  ├── list_agents
  ├── get_agent_metadata
  └── get_agent_api_key

tools-server (stateless/read-only tools)
  ├── Knowledge Graph (read-only)
  ├── Observability (read-only)
  ├── Admin (read-only)
  └── Export
```

**Benefits:**
- Clear separation: stateful vs stateless
- Tools server can be truly stateless
- Easier migration path
- Tools server can cache/optimize independently

## Implementation Plan

### Phase 1: Identify Stateless Tools

**Stateless/Read-Only Tools (can be separated):**
- `search_knowledge_graph` - Read-only queries
- `get_knowledge_graph` - Read-only queries
- `list_knowledge_graph` - Read-only stats
- `get_discovery_details` - Read-only
- `get_related_discoveries_graph` - Read-only
- `get_response_chain_graph` - Read-only
- `find_similar_discoveries_graph` - Read-only
- `observe_agent` - Read-only (reads state)
- `compare_agents` - Read-only
- `compare_me_to_similar` - Read-only
- `detect_anomalies` - Read-only
- `aggregate_metrics` - Read-only
- `get_governance_metrics` - Read-only (but needs monitor)
- `get_system_history` - Read-only export
- `export_to_file` - Read-only export
- `get_server_info` - Read-only
- `health_check` - Read-only
- `get_telemetry_metrics` - Read-only
- `get_thresholds` - Read-only
- `get_workspace_health` - Read-only
- `list_tools` - Read-only
- `get_tool_usage_stats` - Read-only
- `get_dialectic_session` - Read-only

**Stateful Tools (must stay with governance):**
- `process_agent_update` - Core governance cycle
- `simulate_update` - Core governance (dry-run)
- `store_knowledge_graph` - Writes to knowledge graph
- `update_discovery_status_graph` - Writes
- `reply_to_question` - Writes
- `leave_note` - Writes
- `list_agents` - Reads metadata (but needed for auth)
- `get_agent_metadata` - Reads metadata (but needed for auth)
- `update_agent_metadata` - Writes metadata
- `archive_agent` - Writes metadata
- `delete_agent` - Writes metadata
- `archive_old_test_agents` - Writes metadata
- `get_agent_api_key` - Reads/writes metadata
- `mark_response_complete` - Writes metadata
- `direct_resume_if_safe` - Writes state
- `set_thresholds` - Writes config
- `reset_monitor` - Writes state
- `cleanup_stale_locks` - Writes filesystem
- `request_dialectic_review` - Writes dialectic state
- `request_exploration_session` - Writes dialectic state
- `submit_thesis` - Writes dialectic state
- `submit_antithesis` - Writes dialectic state
- `submit_synthesis` - Writes dialectic state
- `update_calibration_ground_truth` - Writes calibration
- `check_calibration` - Reads calibration (but writes cache)
- `backfill_calibration_from_dialectic` - Writes calibration
- `bind_identity` - Writes session state
- `recall_identity` - Reads session state
- `spawn_agent` - Writes metadata
- `validate_file_path` - Read-only (but policy check)

### Phase 2: Create Tools Server Interface

**API Design:**
```python
# tools_server.py
class ToolsServer:
    def __init__(self, governance_client):
        self.governance_client = governance_client  # HTTP/gRPC client
    
    async def search_knowledge_graph(self, arguments):
        # Read-only: Query knowledge graph via governance client
        return await self.governance_client.query_knowledge_graph(arguments)
    
    async def observe_agent(self, arguments):
        # Read-only: Get agent metrics via governance client
        return await self.governance_client.get_agent_metrics(arguments)
```

**Governance Server API:**
```python
# governance_server_api.py
class GovernanceServerAPI:
    async def query_knowledge_graph(self, arguments):
        # Internal: Direct access to knowledge graph
        return await handle_search_knowledge_graph(arguments)
    
    async def get_agent_metrics(self, arguments):
        # Internal: Direct access to monitors
        monitor = mcp_server.get_or_create_monitor(arguments['agent_id'])
        return monitor.get_metrics()
```

### Phase 3: Migration Strategy

1. **Create tools server** with read-only tools
2. **Add API layer** to governance server
3. **Update clients** to use tools server for read-only operations
4. **Monitor performance** and usage
5. **Gradually migrate** more tools as needed

## Benefits

1. **Scalability**: Tools server can scale independently
2. **Performance**: Lightweight tools don't carry governance overhead
3. **Resource Isolation**: Tool failures don't affect governance server
4. **Deployment**: Can deploy tools closer to users
5. **Maintainability**: Easier to add/modify tools
6. **Testing**: Can test tools independently

## Risks & Mitigation

**Risk**: Tools server needs governance state  
**Mitigation**: Use API/interface layer, not direct access

**Risk**: Increased latency  
**Mitigation**: Tools server can cache frequently accessed data

**Risk**: More complex deployment  
**Mitigation**: Start with single tools server, add complexity gradually

**Risk**: Breaking changes  
**Mitigation**: Maintain backward compatibility during migration

## Next Steps

1. **Review & Approve**: Get feedback on proposal
2. **Prototype**: Build minimal tools server with 2-3 read-only tools
3. **Test**: Verify performance and functionality
4. **Iterate**: Expand based on learnings
5. **Document**: Update architecture docs

## Questions

1. Should tools server use HTTP/gRPC or shared memory?
2. How should authentication work across servers?
3. Should tools server cache governance state?
4. What's the performance target for tools server?
5. Should we support both servers in parallel during migration?

