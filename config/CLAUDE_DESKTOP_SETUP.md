# Claude Desktop MCP Configuration

**Last Updated:** February 4, 2026  
**Status:** ✅ Configured

## Current Configuration

Claude Desktop is configured to use both MCP servers via Streamable HTTP:

### 1. Anima MCP (Pi - Lumen)
- **URL:** `http://192.168.1.165:8766/mcp/`
- **Port:** 8766
- **Host:** Raspberry Pi (lumen)
- **Purpose:** Lumen's embodied mind - sensors, anima state, display, messaging

### 2. Unitares Governance (Mac)
- **URL:** `http://localhost:8767/mcp/`
- **Port:** 8767
- **Host:** Mac (local)
- **Purpose:** Multi-agent governance, knowledge graph, dialectic sessions

## Configuration File

**Location:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Backup:** `~/Library/Application Support/Claude/claude_desktop_config.json.backup`

## Using Tailscale (Remote Access)

If you need to access the Pi from outside your local network, update the anima URL to use Tailscale:

```json
{
  "mcpServers": {
    "anima": {
      "type": "http",
      "url": "http://100.89.201.36:8766/mcp/"
    },
    "unitares-governance": {
      "type": "http",
      "url": "http://localhost:8767/mcp/"
    }
  }
}
```

**Tailscale IP:** `100.89.201.36` (from `pi_orchestration.py`)

## Restart Required

After updating the configuration:
1. **Quit Claude Desktop completely** (Cmd+Q)
2. **Restart Claude Desktop**
3. The MCP servers should connect automatically

## Verification

To verify the servers are accessible:

```bash
# Test anima (Pi)
curl http://192.168.1.165:8766/mcp/

# Test unitares-governance (Mac)
curl http://localhost:8767/mcp/
```

Both should return MCP protocol responses.

## Troubleshooting

### Anima won't connect

1. **Check Pi is online:**
   ```bash
   ping 192.168.1.165
   ```

2. **Check anima service on Pi:**
   ```bash
   ssh unitares-anima@192.168.1.165 "systemctl status anima"
   ```

3. **Try Tailscale URL:**
   - Update config to use `http://100.89.201.36:8766/mcp/`
   - Requires Tailscale app running on Mac

### Unitares won't connect

1. **Check server is running:**
   ```bash
   curl http://localhost:8767/health
   ```

2. **Check launchd service:**
   ```bash
   launchctl list | grep governance
   ```

3. **Start server manually:**
   ```bash
   cd ~/projects/governance-mcp-v1
   python3 src/mcp_server.py --port 8767
   ```

## Port Reference

| Port | Service | Host | Purpose |
|------|---------|------|---------|
| 8766 | Anima MCP | Pi | Lumen's MCP server |
| 8767 | Unitares Governance | Mac | Governance MCP server |

**Note:** Both use Streamable HTTP at `/mcp/` endpoint (SSE deprecated).
