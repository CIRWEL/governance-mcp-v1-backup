#!/bin/bash
# MCP Exploration Tool - Standardized system checks
# Usage: ./mcp_explore.sh [command]

PROJECT_DIR="/Users/cirwel/projects/governance-mcp-v1"
cd "$PROJECT_DIR" || exit 1

COMMAND="${1:-status}"

case "$COMMAND" in
  status|health)
    echo "🏥 SYSTEM HEALTH CHECK"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    python3 << 'EOF'
import asyncio, sys, json
sys.path.insert(0, '/Users/cirwel/projects/governance-mcp-v1')
from scripts.mcp_sse_client import GovernanceMCPClient

async def check():
    async with GovernanceMCPClient() as client:
        result = await client.call_tool("get_workspace_health", {})
        if hasattr(result, 'content'):
            for c in result.content:
                if hasattr(c, 'text'):
                    data = json.loads(c.text)
                    print(f"Status: {data.get('status', 'unknown')}")
                    print(f"Active agents: {data.get('active_agents', 0)}")
                    print(f"Total discoveries: {data.get('total_discoveries', 0)}")
asyncio.run(check())
EOF
    ;;

  agents|list)
    echo "👥 ACTIVE AGENTS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    python3 << 'EOF'
import asyncio, sys, json
sys.path.insert(0, '/Users/cirwel/projects/governance-mcp-v1')
from scripts.mcp_sse_client import GovernanceMCPClient

async def check():
    async with GovernanceMCPClient() as client:
        result = await client.call_tool("list_agents", {})
        if hasattr(result, 'content'):
            for c in result.content:
                if hasattr(c, 'text'):
                    data = json.loads(c.text)
                    agents = data.get('agents', [])
                    print(f"Total agents: {len(agents)}\n")
                    for agent in agents[:10]:
                        aid = agent.get('agent_id', 'unknown')
                        status = agent.get('lifecycle_status', '?')
                        updates = agent.get('update_count', 0)
                        print(f"  • {aid[:50]}")
                        print(f"    Status: {status}, Updates: {updates}")
asyncio.run(check())
EOF
    ;;

  tools)
    echo "🔧 AVAILABLE MCP TOOLS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    python3 << 'EOF'
import asyncio, sys
sys.path.insert(0, '/Users/cirwel/projects/governance-mcp-v1')
from scripts.mcp_sse_client import GovernanceMCPClient

async def check():
    async with GovernanceMCPClient() as client:
        tools = await client.list_tools()
        print(f"Total tools: {len(tools)}\n")
        for tool in tools[:20]:
            print(f"  • {tool.name}")
        if len(tools) > 20:
            print(f"\n  ... and {len(tools) - 20} more")
asyncio.run(check())
EOF
    ;;

  knowledge|kg)
    echo "📚 KNOWLEDGE GRAPH"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    python3 << 'EOF'
import asyncio, sys, json
sys.path.insert(0, '/Users/cirwel/projects/governance-mcp-v1')
from scripts.mcp_sse_client import GovernanceMCPClient

async def check():
    async with GovernanceMCPClient() as client:
        result = await client.call_tool("list_knowledge_graph", {})
        if hasattr(result, 'content'):
            for c in result.content:
                if hasattr(c, 'text'):
                    data = json.loads(c.text)
                    print(f"Total discoveries: {data.get('total_discoveries', 0)}")
                    cats = data.get('discoveries_by_category', {})
                    print(f"Categories: {len(cats)}\n")
                    for cat, count in list(cats.items())[:10]:
                        print(f"  • {cat}: {count}")
asyncio.run(check())
EOF
    ;;

  server)
    echo "🌐 SSE SERVER STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Checking port 8765..."
    lsof -i :8765 | grep LISTEN || echo "  ❌ Not running"
    echo ""
    echo "Checking launchd service..."
    launchctl list | grep governance || echo "  ❌ Not loaded"
    ;;

  all)
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║              COMPLETE MCP SYSTEM CHECK                ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    $0 server
    echo ""
    $0 status
    echo ""
    $0 agents
    echo ""
    $0 knowledge
    ;;

  help|*)
    cat << 'HELP'
MCP Exploration Tool - Standardized system checks

USAGE:
  ./mcp_explore.sh [command]

COMMANDS:
  status, health    - System health check
  agents, list      - List active agents
  tools             - Show available MCP tools
  knowledge, kg     - Knowledge graph stats
  server            - Check SSE server status
  all               - Run all checks
  help              - Show this help

EXAMPLES:
  ./mcp_explore.sh status
  ./mcp_explore.sh agents
  ./mcp_explore.sh all

HELP
    ;;
esac
