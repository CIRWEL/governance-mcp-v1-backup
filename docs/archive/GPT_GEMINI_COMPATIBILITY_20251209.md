# GPT/Gemini Compatibility Evaluation

**Date:** 2025-12-09  
**Status:** Partial Implementation - Needs Enhancement

---

## Current State

### ✅ What Works

1. **OpenAI-Compatible Endpoints:**
   - `GET /v1/tools` - Lists 14 tools (manually defined)
   - `POST /v1/tools/call` - Executes tools via `dispatch_tool`
   - `GET /health` - Health check endpoint

2. **Basic Function Calling:**
   - Function format matches OpenAI's structure
   - Tools execute correctly via `dispatch_tool`
   - JSON responses work

3. **MCP Server:**
   - SSE transport working
   - Multi-client support
   - All 47 tools available via MCP

### ❌ What's Missing

1. **Limited Tool Coverage:**
   - Only 14/47 tools exposed (30%)
   - Missing: dialectic tools, export tools, admin tools, etc.
   - Manual maintenance required

2. **Incomplete Schema:**
   - Parameter types simplified (no enums, no nested objects)
   - Missing required fields
   - No parameter descriptions

3. **No Auto-Discovery:**
   - TOOL_INFO hardcoded
   - Doesn't extract from MCP tool definitions
   - Out of sync with actual tools

---

## GPT/Gemini Compatibility Requirements

### OpenAI Function Calling Format

```json
{
  "type": "function",
  "function": {
    "name": "process_agent_update",
    "description": "Share your work and get feedback",
    "parameters": {
      "type": "object",
      "properties": {
        "agent_id": {"type": "string", "description": "Agent identifier"},
        "complexity": {"type": "number", "minimum": 0, "maximum": 1},
        "api_key": {"type": "string", "description": "API key for authentication"}
      },
      "required": ["agent_id"]
    }
  }
}
```

### Gemini Function Calling Format

Gemini uses the same format as OpenAI (OpenAI-compatible), so same implementation works.

### Current vs Required

**Current:**
```python
"parameters": {"agent_id": {"type": "string"}, "complexity": {"type": "number"}}
```

**Required:**
```python
"parameters": {
  "type": "object",
  "properties": {
    "agent_id": {"type": "string", "description": "..."},
    "complexity": {"type": "number", "minimum": 0, "maximum": 1}
  },
  "required": ["agent_id"]
}
```

---

## Recommendations

### 1. Auto-Generate Tool Schemas (High Priority)

**Extract from MCP tool definitions:**

```python
# In mcp_server_sse.py
from src.mcp_server_std import list_tools

async def openai_list_tools(request):
    # Get all MCP tools
    mcp_tools = await list_tools()
    
    # Convert to OpenAI format
    openai_tools = []
    for tool in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description.split("\n")[0],  # First line
                "parameters": tool.inputSchema  # Already JSON Schema format!
            }
        })
    
    return JSONResponse({"tools": openai_tools, "count": len(openai_tools)})
```

**Benefits:**
- ✅ All 47 tools automatically exposed
- ✅ Always in sync with MCP definitions
- ✅ Full schema support (enums, nested objects, required fields)
- ✅ Zero maintenance

### 2. Improve Error Handling

**Current:**
```python
except Exception as e:
    return JSONResponse({"error": str(e)})
```

**Better:**
```python
except Exception as e:
    error_response = {
        "name": body.get("name"),
        "result": None,
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "recovery": {"action": "...", "related_tools": [...]}  # From error_response
    }
    return JSONResponse(error_response, status_code=400)
```

### 3. Add Tool Filtering

**Respect tool modes:**
```python
# Filter by GOVERNANCE_TOOL_MODE
if TOOL_MODE != "full":
    tools = [t for t in tools if should_include_tool(t.name, TOOL_MODE)]
```

### 4. Add CORS Headers (for web clients)

```python
from starlette.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specific origins
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

---

## Implementation Plan

### Phase 1: Auto-Generate Schemas (1-2 hours)
- Extract from `list_tools()` MCP definitions
- Convert to OpenAI format
- Test with GPT-4/Gemini

### Phase 2: Enhance Error Handling (30 min)
- Parse error responses
- Include recovery guidance
- Proper HTTP status codes

### Phase 3: Add Features (1 hour)
- Tool mode filtering
- CORS support
- Rate limiting (optional)

### Phase 4: Documentation (30 min)
- Usage examples for GPT/Gemini
- Integration guide
- Testing instructions

---

## Testing Checklist

- [x] GPT-4 can list tools via `/v1/tools` ✅
- [x] GPT-4 can call `process_agent_update` ✅
- [x] GPT-4 receives proper error messages ✅
- [x] Gemini can use same endpoints ✅
- [x] All 46 tools available (auto-generated from MCP) ✅
- [x] Tool modes work (minimal/lite/full) ✅
- [x] Error handling provides recovery guidance ✅
- [x] CORS support added for web clients ✅

---

## Estimated Impact

**Before:** 14 tools, manual maintenance, incomplete schemas  
**After:** 46 tools, auto-generated, full schema support ✅ **IMPLEMENTED**

**Compatibility:** ✅ GPT-4, ✅ GPT-5, ✅ Gemini, ✅ Claude (via MCP), ✅ Ollama (via OpenAI-compatible API)

---

## ✅ Implementation Complete

**Status:** Production Ready

**Changes Made:**
1. ✅ Auto-generated tool schemas from MCP definitions
2. ✅ Enhanced error handling with proper HTTP status codes
3. ✅ CORS middleware added for web clients
4. ✅ Tool mode filtering (minimal/lite/full)
5. ✅ Integration guide created

**See:** [GPT/Gemini Integration Guide](../guides/GPT_GEMINI_INTEGRATION.md)

