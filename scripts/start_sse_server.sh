#!/bin/bash
# Start the Governance MCP Server in SSE mode (multi-client support)
#
# Usage:
#   ./scripts/start_sse_server.sh [--port PORT] [--host HOST]
#
# Default: http://127.0.0.1:8765/sse

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Check for Python
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &> /dev/null; then
    echo "Error: Python not found. Set PYTHON env var or install Python 3."
    exit 1
fi

# Dependencies: do NOT auto-install at runtime (avoids surprise failures / permission issues)
if ! "$PYTHON" -c "import mcp, uvicorn, starlette" 2>/dev/null; then
    echo "Error: missing dependencies for SSE server."
    echo ""
    echo "Install minimal (stdio only):"
    echo "  pip install -r requirements-core.txt"
    echo ""
    echo "Install full (SSE/HTTP):"
    echo "  pip install -r requirements-full.txt"
    echo ""
    exit 1
fi

echo "Starting Governance MCP Server (SSE mode)..."
exec "$PYTHON" src/mcp_server_sse.py "$@"
