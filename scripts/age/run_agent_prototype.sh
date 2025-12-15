#!/usr/bin/env bash
set -euo pipefail

# Agent helper: spin up Apache AGE, export from SQLite, import into AGE, run sample queries.
#
# This is intended for AI agents / maintainers doing graph-query prototyping.
# It does NOT change production runtime wiring (SQLite remains canonical).
#
# Usage:
#   ./scripts/age/run_agent_prototype.sh
#
# Optional env overrides:
#   SQLITE_DB_PATH=data/governance.db
#   AGE_GRAPH=governance
#   EXPORT_LIMIT=5000
#   OUT_SQL=/tmp/age_import.sql
#   NO_AGENTS=1
#   NO_DIALECTIC=1

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

SQLITE_DB_PATH="${SQLITE_DB_PATH:-data/governance.db}"
AGE_GRAPH="${AGE_GRAPH:-governance}"
EXPORT_LIMIT="${EXPORT_LIMIT:-5000}"
OUT_SQL="${OUT_SQL:-/tmp/age_import.sql}"

NO_AGENTS="${NO_AGENTS:-0}"
NO_DIALECTIC="${NO_DIALECTIC:-0}"

if [[ ! -f "$SQLITE_DB_PATH" ]]; then
  echo "ERROR: SQLite DB not found at '$SQLITE_DB_PATH'."
  echo "Hint: start the governance server once to generate data, or point SQLITE_DB_PATH at an existing DB."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. Install Docker Desktop (or equivalent) to run the AGE prototype."
  exit 1
fi

compose_cmd=()
if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "ERROR: docker compose not available (neither 'docker compose' nor 'docker-compose')."
  exit 1
fi

echo "==> Starting postgres+AGE container..."
"${compose_cmd[@]}" -f scripts/age/docker-compose.age.yml up -d

echo "==> Bootstrapping AGE (extension + graph)..."
docker exec -i postgres-age psql -U postgres -d postgres < scripts/age/bootstrap.sql >/dev/null

echo "==> Exporting from SQLite → AGE import SQL..."
export_args=(
  --sqlite "$SQLITE_DB_PATH"
  --out "$OUT_SQL"
  --graph "$AGE_GRAPH"
  --limit "$EXPORT_LIMIT"
  --mode merge
  --recreate-graph
)
if [[ "$NO_AGENTS" == "1" ]]; then
  export_args+=(--no-agents)
fi
if [[ "$NO_DIALECTIC" == "1" ]]; then
  export_args+=(--no-dialectic)
fi

python3 scripts/age/export_knowledge_sqlite_to_age.py "${export_args[@]}"

echo "==> Importing into AGE..."
docker exec -i postgres-age psql -U postgres -d postgres < "$OUT_SQL" >/dev/null

echo "==> Running sample queries (edit placeholders in scripts/age/sample_queries.sql for deeper checks)..."
docker exec -i postgres-age psql -U postgres -d postgres < scripts/age/sample_queries.sql || true

echo "==> Done."
echo "Container: postgres-age (port 5432)"
echo "Import SQL: $OUT_SQL"

