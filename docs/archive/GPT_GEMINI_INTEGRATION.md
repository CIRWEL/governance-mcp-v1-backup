# GPT/Gemini Integration Guide

For using UNITARES Governance with OpenAI GPT and Google Gemini

---

## Architecture Overview

**UNITARES doesn't replace GPT/Gemini; it sits beside them as a governance brain.** You call your usual models; they call UNITARES tools for safety, metrics, and collective memory.

**Two transport paths:**

- **Claude/Cursor** → MCP protocol → `/sse` endpoint
- **GPT/Gemini** → OpenAI-compatible API → `/v1/tools` and `/v1/tools/call` endpoints

**Key point:** `GET /v1/tools` is read-only discovery; `POST /v1/tools/call` executes tools.

---

## Quick Start

### 1. Start the Server

```bash
# Start SSE server (includes OpenAI-compatible endpoints)
python3 src/mcp_server_sse.py --port 8765

# Server provides:
# - MCP endpoint: http://127.0.0.1:8765/sse (for Claude/Cursor)
# - OpenAI endpoint: http://127.0.0.1:8765/v1/tools (for GPT/Gemini)
```

### 2. List Available Tools

```bash
curl http://127.0.0.1:8765/v1/tools
```

**Response:**

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "process_agent_update",
        "description": "Share your work and get supportive feedback",
        "parameters": {
          "type": "object",
          "properties": {
            "agent_id": {"type": "string", "description": "Agent identifier"},
            "complexity": {"type": "number", "minimum": 0, "maximum": 1},
            "api_key": {"type": "string", "description": "UNITARES agent API key (not your OpenAI/Gemini key)"}
          },
          "required": ["agent_id"]
        }
      }
    },
    ...
  ],
  "count": 46,
  "mode": "full"
}
```

**Note:** The `mode` field reflects the current `GOVERNANCE_TOOL_MODE` setting. You can confirm which mode is active via this response.

### 3. Call a Tool

```bash
curl -X POST http://127.0.0.1:8765/v1/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "health_check",
    "arguments": {}
  }'
```

---

## OpenAI GPT Integration

### Using OpenAI Python SDK

```python
import json
import openai
import requests

# Configure OpenAI client (normal OpenAI endpoint - no base_url override)
client = openai.OpenAI(
    api_key="your-openai-key",
    # No base_url override - OpenAI client talks to OpenAI normally
)

# Get available governance tools from UNITARES server
tools_response = requests.get("http://127.0.0.1:8765/v1/tools")
tools = tools_response.json()["tools"]

# Use in chat completion (GPT talks to OpenAI, but can call UNITARES tools)
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Check system health"}
    ],
    tools=tools,  # Pass governance tools
    tool_choice="auto"
)

# Handle tool calls (these go to UNITARES server, not OpenAI)
tool_calls = response.choices[0].message.tool_calls or []
for tool_call in tool_calls:
    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)
    
    # Call governance server directly
    result = requests.post(
        "http://127.0.0.1:8765/v1/tools/call",
        json={"name": tool_name, "arguments": tool_args}
    ).json()
    
    print(f"Tool {tool_name} result: {result['result']}")
```

### Using OpenAI Function Calling Directly

```python
import requests
import json

# Get tools
tools_response = requests.get("http://127.0.0.1:8765/v1/tools")
tools = tools_response.json()["tools"]

# Call tool directly
result = requests.post(
    "http://127.0.0.1:8765/v1/tools/call",
    json={
        "name": "process_agent_update",
        "arguments": {
            "agent_id": "gpt_agent_001",
            "complexity": 0.7,
            "response_text": "Completed analysis of governance metrics"
        }
    }
)

print(json.dumps(result.json(), indent=2))
```

---

## Google Gemini Integration

### Using Google Generative AI SDK

```python
import google.generativeai as genai
import requests

# Configure Gemini
genai.configure(api_key="your-gemini-key")

# Get governance tools from UNITARES server
tools_response = requests.get("http://127.0.0.1:8765/v1/tools")
tools = tools_response.json()["tools"]

# Convert to Gemini format: single tool object with all function declarations
gemini_tools = [
    {
        "function_declarations": [t["function"] for t in tools]
    }
]

# Create model with tools (Gemini talks to Google, but can call UNITARES tools)
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    tools=gemini_tools,
)

# Use in conversation
response = model.generate_content(
    "Check system health and get governance metrics"
)

# Handle function calls (these go to UNITARES server, not Google)
for part in response.candidates[0].content.parts:
    if getattr(part, "function_call", None):
        tool_name = part.function_call.name
        tool_args = dict(part.function_call.args)
        
        # Call governance server directly
        result = requests.post(
            "http://127.0.0.1:8765/v1/tools/call",
            json={"name": tool_name, "arguments": tool_args}
        ).json()
        
        print(f"Tool {tool_name} result: {result['result']}")
```

### Using Gemini REST API

```python
import requests

# Get tools
tools = requests.get("http://127.0.0.1:8765/v1/tools").json()["tools"]

# Call Gemini API with governance tools
response = requests.post(
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent",
    headers={"x-goog-api-key": "your-key"},
    json={
        "contents": [{"parts": [{"text": "Check system health"}]}],
        "tools": [{"function_declarations": [t["function"] for t in tools]}]
    }
)

# Parse function call(s) from response JSON and POST to /v1/tools/call
# (Example: extract from response.candidates[0].content.parts where function_call exists)
```

---

## Tool Modes

The server respects `GOVERNANCE_TOOL_MODE` environment variable:

- **`minimal`** (default): 3 essential tools
  - `get_agent_api_key`
  - `process_agent_update`
  - `get_governance_metrics`

- **`lite`**: ~15 commonly used tools

- **`full`**: All 46 tools

```bash
# Set mode before starting server
export GOVERNANCE_TOOL_MODE=full
python3 src/mcp_server_sse.py
```

---

## Common Workflows

### 1. Agent Onboarding

```python
# Step 1: Get UNITARES agent API key (not your OpenAI/Gemini provider key)
result = requests.post(
    "http://127.0.0.1:8765/v1/tools/call",
    json={
        "name": "get_agent_api_key",
        "arguments": {"agent_id": "gpt_agent_001"}
    }
).json()

# This is a UNITARES agent key, used for governance operations
api_key = result["result"]["api_key"]
print(f"UNITARES API Key: {api_key}")
```

### 2. Log Work Progress

```python
# Step 2: Log work
result = requests.post(
    "http://127.0.0.1:8765/v1/tools/call",
    json={
        "name": "process_agent_update",
        "arguments": {
            "agent_id": "gpt_agent_001",
            "api_key": api_key,
            "complexity": 0.7,
            "response_text": "Completed feature implementation"
        }
    }
).json()

metrics = result["result"]["metrics"]
print(f"Coherence: {metrics['coherence']}")
print(f"Decision: {metrics['decision']['action']}")
```

### 3. Check Current State

```python
# Step 3: Get current metrics
result = requests.post(
    "http://127.0.0.1:8765/v1/tools/call",
    json={
        "name": "get_governance_metrics",
        "arguments": {"agent_id": "gpt_agent_001"}
    }
).json()

print(f"E: {result['result']['E']}, I: {result['result']['I']}")
```

---

## Error Handling

### Standard Error Response

```json
{
  "name": "process_agent_update",
  "result": null,
  "success": false,
  "error": "agent_id is required",
  "error_type": "ValueError"
}
```

### Common Errors

1. **Missing agent_id**: Use `get_agent_api_key` first
2. **Invalid API key**: Regenerate with `get_agent_api_key` (note: this is a UNITARES agent key, not your OpenAI/Gemini provider key)
3. **Tool not found**: Check `/v1/tools` for available tools
4. **Tool mode restriction**: Set `GOVERNANCE_TOOL_MODE=full` to see all tools

---

## Security Considerations

### Production Setup

1. **Restrict CORS origins**:

   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://your-app.com"],  # Specific origins
       allow_methods=["GET", "POST"],
   )
   ```

2. **Add authentication**:
   - API key validation
   - Rate limiting (already built-in)
   - IP whitelisting

3. **Use HTTPS**:
   - Deploy behind reverse proxy (nginx, Caddy)
   - Use SSL certificates

---

## Comparison: MCP vs OpenAI Endpoints

| Feature | MCP (Claude/Cursor) | OpenAI (GPT/Gemini) |
|---------|---------------------|---------------------|
| Transport | SSE/stdio | HTTP REST |
| Endpoint | `/sse` | `/v1/tools` (read-only), `/v1/tools/call` (execute) |
| Tool Discovery | `list_tools` | `GET /v1/tools` |
| Tool Execution | `call_tool` | `POST /v1/tools/call` |
| Format | MCP protocol | OpenAI function calling |
| Multi-client | ✅ Yes | ✅ Yes |
| Tool Count | 46 | 46 (auto-generated from MCP) |

---

## Testing

### Quick Test Scripts

**Python test (recommended):**

```bash
python3 tests/test_openai_endpoints.py
# Or with custom URL:
python3 tests/test_openai_endpoints.py --base-url http://127.0.0.1:8765
```

**Shell script (quick check):**

```bash
./tests/test_openai_endpoints.sh
# Or with custom URL:
./tests/test_openai_endpoints.sh http://127.0.0.1:8765
```

### Manual Testing

**Test Tool List:**

```bash
curl http://127.0.0.1:8765/v1/tools | jq '.count'
# Should return: 46 (or filtered count based on mode)
```

**Test Tool Execution:**

```bash
curl -X POST http://127.0.0.1:8765/v1/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "health_check", "arguments": {}}' | jq '.success'
# Should return: true
```

**Test CORS (from browser):**

```javascript
fetch('http://127.0.0.1:8765/v1/tools')
  .then(r => r.json())
  .then(data => console.log(`Tools: ${data.count}`));
```

---

## Troubleshooting

### Tools Not Showing

- Check `GOVERNANCE_TOOL_MODE` environment variable
- Verify server is running: `curl http://127.0.0.1:8765/health`
- Check server logs for errors

### CORS Errors

- Verify CORS middleware is added
- Check browser console for specific CORS error
- Ensure `allow_origins` includes your domain

### Tool Execution Fails

- Check error message in response
- Verify tool name matches exactly
- Ensure required parameters are provided
- Check server logs for detailed errors

---

## Next Steps

1. **Start server**: `python3 src/mcp_server_sse.py`
2. **Get tools**: `curl http://127.0.0.1:8765/v1/tools`
3. **Integrate**: Use examples above for your GPT/Gemini client
4. **Monitor**: Check `/health` endpoint regularly

---

**See Also:**

- [START_HERE.md](../../START_HERE.md) - General onboarding
- [AI_ASSISTANT_GUIDE.md](../reference/AI_ASSISTANT_GUIDE.md) - Understanding EISV metrics
- [GPT_GEMINI_COMPATIBILITY_20251209.md](../analysis/GPT_GEMINI_COMPATIBILITY_20251209.md) - Technical details
