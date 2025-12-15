# Tool Audit - December 10, 2025

## Summary

**Current State:**
- **Schema tools (`tool_schemas.py`):** 51 tools
- **Runtime tools (`list_tools`):** 51 tools  
- **Handler registry (`TOOL_HANDLERS`):** 51 tools
- **SSE server:** Should have 52 tools (51 shared + 1 SSE-only: `get_connected_clients`)

## Findings

### ✅ Consistency Check
All three sources (schema, runtime, handlers) match perfectly - **no discrepancies**.

### ⚠️ SSE Server Issue
**Problem:** `get_connected_clients` is registered with FastMCP but NOT included in `list_tools` output.

**Details:**
- `get_connected_clients` is registered with `@mcp.tool` decorator in `mcp_server_sse.py` (line 568)
- `http_list_tools` only calls `get_tool_definitions()` which returns 51 shared tools
- `handle_list_tools` also only uses `get_tool_definitions()` 
- Result: SSE server shows 51 tools instead of 52

**Impact:**
- Tool is available via MCP protocol (FastMCP exposes it)
- Tool is NOT listed in `list_tools` output
- Tool is NOT listed in HTTP `/v1/tools` endpoint
- Tool works when called directly via MCP

### Tool Count History
- **Earlier:** 48-49 tools
- **After tool mode removal:** 49 tools
- **After exploration session:** 50 tools (`request_exploration_session` added)
- **Current:** 51 tools

### All 51 Tools (Alphabetical)

1. aggregate_metrics
2. archive_agent
3. archive_old_test_agents
4. backfill_calibration_from_dialectic
5. check_calibration
6. cleanup_stale_locks
7. compare_agents
8. compare_me_to_similar
9. delete_agent
10. detect_anomalies
11. direct_resume_if_safe
12. export_to_file
13. find_similar_discoveries_graph
14. get_agent_api_key
15. get_agent_metadata
16. get_dialectic_session
17. get_discovery_details
18. get_governance_metrics
19. get_knowledge_graph
20. get_server_info
21. get_system_history
22. get_telemetry_metrics
23. get_thresholds
24. get_tool_usage_stats
25. get_workspace_health
26. health_check
27. leave_note
28. list_agents
29. list_knowledge_graph
30. list_tools
31. mark_response_complete
32. observe_agent
33. process_agent_update
34. reply_to_question
35. request_dialectic_review
36. request_exploration_session
37. reset_monitor
38. search_knowledge_graph
39. self_recovery
40. set_thresholds
41. simulate_update
42. smart_dialectic_review
43. store_knowledge_graph
44. store_knowledge_graph_batch
45. submit_antithesis
46. submit_synthesis
47. submit_thesis
48. update_agent_metadata
49. update_calibration_ground_truth
50. update_discovery_status_graph
51. validate_file_path

**SSE-only (not in schema):**
- get_connected_clients

## Recommendations

### 1. Fix SSE `list_tools` to Include `get_connected_clients`
**Priority:** Medium  
**Impact:** Tool discovery completeness

**Solution:**
- Modify `http_list_tools` in `mcp_server_sse.py` to append `get_connected_clients` to the tool list
- Modify `handle_list_tools` to detect SSE transport and include SSE-only tools

**Code Change:**
```python
# In http_list_tools (mcp_server_sse.py)
mcp_tools = get_tool_definitions()

# Add SSE-only tools
sse_only_tools = [
    Tool(
        name="get_connected_clients",
        description="Get information about connected clients (SSE-only feature)..."
    )
]
all_tools = mcp_tools + sse_only_tools
```

### 2. Document Tool Count Expectations
**Priority:** Low  
**Impact:** Clarity

Update documentation to reflect:
- stdio server: 51 tools
- SSE server: 52 tools (51 shared + 1 SSE-only)

### 3. Consider Tool Registration Pattern
**Priority:** Low  
**Impact:** Maintainability

Current pattern:
- Shared tools: Defined in `tool_schemas.py`
- SSE-only tools: Registered with `@mcp.tool` decorator in `mcp_server_sse.py`

**Alternative:** Create `sse_tool_schemas.py` for SSE-only tools, import in both places.

## Conclusion

**Status:** ✅ **No unexpected tools found**

The 51 tools are all expected and properly registered. The only issue is that `get_connected_clients` (SSE-only) is not included in `list_tools` output, which is a minor discovery issue but doesn't affect functionality.

**Action Items:**
1. ✅ Audit complete - no unexpected tools
2. ⚠️ Fix `list_tools` to include SSE-only tools (optional improvement)
3. 📝 Update documentation with correct tool counts

