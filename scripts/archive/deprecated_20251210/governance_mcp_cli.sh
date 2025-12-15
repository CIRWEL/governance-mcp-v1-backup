#!/bin/bash
# Governance Monitor CLI using MCP SSE (Unified Source of Truth)
# Usage: ./governance_mcp_cli.sh [agent_id] [response_text] [complexity]

PROJECT_DIR="/Users/cirwel/projects/governance-mcp-v1"
cd "$PROJECT_DIR" || exit 1

# Default values
AGENT_ID="${1:-claude_code_mcp_$(date +%Y%m%d_%H%M%S)}"
RESPONSE_TEXT="${2:-Logging activity from Claude Code via MCP SSE}"
COMPLEXITY="${3:-0.5}"

echo "╔════════════════════════════════════════════════════════╗"
echo "║    UNITARES Governance Monitor (MCP SSE - Unified)     ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Agent ID:   $AGENT_ID"
echo "Response:   $RESPONSE_TEXT"
echo "Complexity: $COMPLEXITY"
echo ""

python3 << PYTHON
import asyncio
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path('$PROJECT_DIR')))

from scripts.mcp_sse_client import GovernanceMCPClient

async def main():
    try:
        async with GovernanceMCPClient() as client:
            # Call the canonical MCP handler
            result = await client.process_agent_update(
                agent_id='$AGENT_ID',
                response_text='$RESPONSE_TEXT',
                complexity=float($COMPLEXITY)
            )

            # Use standardized metric reporting
            from src.mcp_handlers.utils import print_metrics
            
            agent_id = result.get('agent_id', '$AGENT_ID')
            metrics = result.get('metrics', {})
            
            print("┌─────────────────────────────────────────────────────┐")
            print("│         GOVERNANCE DECISION (Canonical MCP)         │")
            print("└─────────────────────────────────────────────────────┘")
            decision = result.get('decision', {})
            print(f"  Action:   {decision.get('action', 'unknown').upper()}")
            print(f"  Reason:   {decision.get('reason', 'N/A')}")
            if decision.get('guidance'):
                print(f"  Guidance: {decision['guidance']}")
            print("")

            # Use standardized metric printing (includes agent_id, timestamp, EISV)
            print_metrics(agent_id, metrics, title="Core Metrics")
            
            print("")
            print("┌─────────────────────────────────────────────────────┐")
            print("│                OPERATIONAL STATE                    │")
            print("└─────────────────────────────────────────────────────┘")
            print(f"  Regime:            {metrics.get('regime', 'N/A')}")
            print(f"  Confidence:        {metrics.get('confidence', 'N/A'):.3f}")
            print(f"  Health Status:     {metrics.get('health_status', 'N/A')}")
            if metrics.get('health_message'):
                print(f"  Health Message:    {metrics['health_message']}")
            print("")

            if 'api_key' in result:
                print("┌─────────────────────────────────────────────────────┐")
                print("│                  NEW AGENT                          │")
                print("└─────────────────────────────────────────────────────┘")
                print(f"  API Key: {result['api_key']}")
                print("  ⚠️  Save this key for future calls!")
                print("")

            # Show shared state info
            print("┌─────────────────────────────────────────────────────┐")
            print("│              SHARED STATE (via SSE)                 │")
            print("└─────────────────────────────────────────────────────┘")
            print("  ✅ Using canonical MCP handler interpretation")
            print("  ✅ State shared with Cursor and all MCP clients")
            print("  ✅ Real-time multi-agent awareness enabled")
            print("")

    except Exception as e:
        print(f"❌ Error connecting to MCP server: {e}")
        print("")
        print("Troubleshooting:")
        print("  1. Check if SSE server is running: lsof -i :8765")
        print("  2. Start server: ./scripts/start_sse_server.sh")
        print("  3. Check server logs: cat data/logs/sse_server.log")
        import traceback
        traceback.print_exc()
        sys.exit(1)

asyncio.run(main())
PYTHON

echo "════════════════════════════════════════════════════════"
echo ""
echo "💡 This uses the MCP SSE server for unified governance"
echo "   All feedback comes from canonical MCP handlers"
echo "   No custom interpretations added!"
echo ""
