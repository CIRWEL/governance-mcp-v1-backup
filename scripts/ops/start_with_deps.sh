#!/bin/bash
# Start Governance MCP Server with dependencies (PostgreSQL via Homebrew)
# Used by LaunchAgent for auto-start at login

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

PG_BIN="/opt/homebrew/opt/postgresql@17/bin"

# Start PostgreSQL if not running
if ! "$PG_BIN/pg_isready" -h localhost -p 5432 -q 2>/dev/null; then
    echo "Starting PostgreSQL@17..."
    brew services start postgresql@17 2>/dev/null || true

    echo "Waiting for PostgreSQL..."
    for i in {1..15}; do
        if "$PG_BIN/pg_isready" -h localhost -p 5432 -q 2>/dev/null; then
            echo "PostgreSQL is ready"
            break
        fi
        sleep 1
    done

    if ! "$PG_BIN/pg_isready" -h localhost -p 5432 -q 2>/dev/null; then
        echo "Failed to start PostgreSQL"
        exit 1
    fi
else
    echo "PostgreSQL is ready"
fi

# Start the MCP server
exec "$SCRIPT_DIR/start_server.sh" "$@"
