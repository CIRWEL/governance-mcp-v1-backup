#!/bin/bash
# ⚠️ DEPRECATED: Use governance_mcp_cli.sh (or governance_cli.sh symlink) instead
#
# This script uses direct Python API with CUSTOM interpretations.
# The new governance_mcp_cli.sh uses MCP SSE with CANONICAL interpretations.
#
# Why deprecated:
# - Adds custom warning thresholds not in core governance
# - Can contradict actual governance decisions (e.g., "low coherence" warning)
# - Not consistent with other MCP clients (Cursor, Desktop)
#
# Migration: Use ./governance_mcp_cli.sh or ./governance_cli.sh (symlink) instead
#
# OLD Usage: ./governance_cli_deprecated.sh [agent_id] [response_text] [complexity]

echo "⚠️  WARNING: This script is DEPRECATED"
echo "    Use governance_mcp_cli.sh for canonical MCP feedback"
echo "    Or use governance_cli.sh (symlink to MCP version)"
echo ""

PROJECT_DIR="/Users/cirwel/projects/governance-mcp-v1"
cd "$PROJECT_DIR" || exit 1

# Default values
AGENT_ID="${1:-claude_code_cli_$(date +%Y%m%d_%H%M%S)}"
RESPONSE_TEXT="${2:-Logging activity from Claude Code CLI}"
COMPLEXITY="${3:-0.5}"

echo "╔════════════════════════════════════════════════════════╗"
echo "║         UNITARES Governance Monitor (CLI)             ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Agent ID:   $AGENT_ID"
echo "Response:   $RESPONSE_TEXT"
echo "Complexity: $COMPLEXITY"
echo ""

python3 << PYTHON
from src.governance_monitor import UNITARESMonitor
import json

try:
    m = UNITARESMonitor(agent_id='$AGENT_ID')
    result = m.process_update({
        'response_text': '$RESPONSE_TEXT',
        'complexity': float($COMPLEXITY)
    })

    print("┌─────────────────────────────────────────────────────┐")
    print("│               GOVERNANCE DECISION                   │")
    print("└─────────────────────────────────────────────────────┘")
    print(f"  Action:   {result['decision']['action'].upper()}")
    print(f"  Reason:   {result['decision']['reason']}")
    if result['decision'].get('guidance'):
        print(f"  Guidance: {result['decision']['guidance']}")
    print("")

    print("┌─────────────────────────────────────────────────────┐")
    print("│                    METRICS                          │")
    print("└─────────────────────────────────────────────────────┘")
    metrics = result['metrics']
    print(f"  Energy (E):        {metrics['E']:.3f}")
    print(f"  Integrity (I):     {metrics['I']:.3f}")
    print(f"  Entropy (S):       {metrics['S']:.3f}")
    print(f"  Void (V):          {metrics['V']:.3f}")
    print(f"  Coherence:         {metrics['coherence']:.3f}")
    print(f"  Attention Score:   {metrics['attention_score']:.3f}")
    print(f"  Regime:            {metrics.get('regime', 'N/A')}")
    print("")

    if 'api_key' in result:
        print("┌─────────────────────────────────────────────────────┐")
        print("│                  NEW AGENT                          │")
        print("└─────────────────────────────────────────────────────┘")
        print(f"  API Key: {result['api_key']}")
        print("  ⚠️  Save this key for future calls!")
        print("")

    # Show interpretation
    print("┌─────────────────────────────────────────────────────┐")
    print("│                 INTERPRETATION                      │")
    print("└─────────────────────────────────────────────────────┘")

    if metrics['coherence'] < 0.5:
        print("  ⚠️  Low coherence - consider simplifying approach")
    else:
        print("  ✅ Good coherence - work is well-organized")

    if metrics['attention_score'] > 0.5:
        print("  💭 High cognitive load - take breaks as needed")
    else:
        print("  ✅ Manageable cognitive load")

    if result['decision']['action'] == 'pause':
        print("  ⏸️  System suggests a break")
    else:
        print("  ✅ Clear to proceed")

    print("")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
PYTHON

echo "════════════════════════════════════════════════════════"
echo ""
echo "To use in scripts:"
echo "  ./governance_cli.sh 'my_agent_id' 'what I did' 0.7"
echo ""
echo "To use directly in Python:"
echo "  cd $PROJECT_DIR"
echo '  python3 -c "from src.governance_monitor import UNITARESMonitor; ...'
echo ""
