# date-context MCP Connection Issues

**Note:** `date-context` is a separate MCP server/repo. This guide lives here only as a convenience note for integration troubleshooting.

## Problem

The `date-context` MCP server keeps losing connection, requiring frequent reconnections.

## Root Cause

**SSE (Server-Sent Events) connections require periodic keepalive messages** to prevent timeouts. Without these, proxies, load balancers, and clients will close idle connections after 30-60 seconds.

### Why This Happens

1. **Missing Keepalive Messages**: SSE connections need periodic comment lines (`:\n\n`) sent by the server to keep the connection alive
2. **Network/Proxy Timeouts**: Intermediate proxies often timeout idle connections after 30-60 seconds
3. **Client Timeouts**: Cursor/Claude Desktop may have their own timeout settings
4. **No Activity**: If the server doesn't send data or keepalive messages, the connection appears idle

## Solutions

### Solution 1: Switch to stdio Transport (Recommended)

If `date-context` supports stdio transport, it's more stable for long-lived connections:

**Before (SSE - unstable):**
```json
{
  "mcpServers": {
    "date-context": {
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

**After (stdio - stable):**
```json
{
  "mcpServers": {
    "date-context": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-date-context"]
    }
  }
}
```

### Solution 2: Check date-context Server Configuration

Verify that the `date-context` server is configured to send keepalive messages:

1. Check the server logs for connection timeouts
2. Verify the server version (update if outdated)
3. Check if there's a keepalive/ping interval setting

### Solution 3: Update date-context Server

Ensure you're using the latest version:

```bash
# Update via npm
npm update -g @modelcontextprotocol/server-date-context

# Or use latest via npx
npx -y @modelcontextprotocol/server-date-context@latest
```

### Solution 4: Check Network/Proxy Settings

1. **No Proxies**: Ensure no intermediate proxies are timing out connections
2. **Firewall**: Check firewall settings that might close idle connections
3. **Load Balancer**: If behind a load balancer, check its idle timeout settings

### Solution 5: Monitor Connection Patterns

Use the governance server's diagnostics:

```python
# Via governance MCP tool
get_connection_diagnostics()

# Or check connection health
get_connected_clients()
```

Look for:
- High reconnection rates
- Idle connection timeouts
- Connection health status

## Diagnostic Tools

Run the diagnostic script:

```bash
python scripts/diagnose_date_context_connection.py
```

This will:
- Test SSE connectivity
- Check Cursor configuration
- Test date-context via stdio
- Provide recommendations

## Technical Details

### SSE Keepalive Requirements

SSE connections must send periodic comment lines to prevent timeouts:

```
: keepalive comment\n\n
```

Without these, the connection appears idle and gets closed.

### Keepalive Intervals

- **Recommended**: Send keepalive every 15-30 seconds
- **Minimum**: At least every 60 seconds to prevent most proxy timeouts
- **Maximum**: Don't exceed 5 minutes (some proxies timeout at 5 minutes)

### Connection Timeout Settings

Common timeout values:
- **Nginx**: 60 seconds (default)
- **Apache**: 60 seconds (default)
- **Cloudflare**: 100 seconds
- **AWS ALB**: 60 seconds (default)
- **Client browsers**: 30-60 seconds

## Prevention

1. **Use stdio transport** when possible (more stable)
2. **Ensure servers send keepalive** messages for SSE connections
3. **Monitor connection health** using governance server diagnostics
4. **Update servers regularly** to get latest fixes
5. **Check logs** for connection timeout patterns

## Related Issues

- Similar issues can affect any SSE-based MCP server
- The governance MCP server has connection tracking to help diagnose these issues
- See `docs/reference/SSE_SERVER.md` for more on SSE transport

## References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [SSE Keepalive Best Practices](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [date-context Server](https://github.com/modelcontextprotocol/servers/tree/main/src/date-context)
