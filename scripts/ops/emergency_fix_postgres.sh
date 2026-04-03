#!/bin/bash
# Emergency fix for PostgreSQL "too many clients" error

set -e

PG_BIN="/opt/homebrew/opt/postgresql@17/bin"
PG_USER="${PG_USER:-postgres}"

echo "Emergency PostgreSQL Connection Fix"
echo "======================================"
echo ""

# Kill idle-in-transaction connections older than 1 minute
echo "Attempting to kill stale connections..."
"$PG_BIN/psql" -U "$PG_USER" -d postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = 'governance'
      AND pid != pg_backend_pid()
      AND state = 'idle in transaction'
      AND state_change < now() - interval '1 minute';
" || echo "Could not kill stale connections"

# Check current max_connections
echo ""
echo "Current max_connections setting:"
"$PG_BIN/psql" -U "$PG_USER" -d postgres -c "SHOW max_connections;" || echo "Could not check max_connections"

# Increase max_connections
echo ""
echo "Increasing max_connections to 200..."
"$PG_BIN/psql" -U "$PG_USER" -d postgres -c "
    ALTER SYSTEM SET max_connections = 200;
    SELECT pg_reload_conf();
" || echo "Could not increase max_connections (may need service restart)"

echo ""
echo "Fix applied. You may need to restart PostgreSQL:"
echo "   brew services restart postgresql@17"
