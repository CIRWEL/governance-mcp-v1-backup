# PostgreSQL + Apache AGE Setup

This directory contains the schema and setup files for migrating to PostgreSQL with Apache AGE extension.

## Files

- `schema.sql` - PostgreSQL relational schema (agents, sessions, dialectic, etc.)
- `graph_schema.cypher` - AGE graph schema documentation and setup
- `partitions.sql` - (Optional) Partition management for audit tables

## Setup Instructions

### 1. Install PostgreSQL

```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS
brew install postgresql

# Or use Docker
docker run -d --name postgres-governance \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=governance \
  -p 5432:5432 \
  postgres:15
```

### 2. Install Apache AGE Extension

```bash
# Clone AGE repository
git clone https://github.com/apache/age.git
cd age

# Follow AGE installation instructions
# See the Apache AGE setup guide (docs site).
```

Or use the AGE Docker image:

```bash
docker run -d --name postgres-age \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=governance \
  -p 5432:5432 \
  apache/age:latest
```

### 3. Create Database and Schema

```bash
# Connect to PostgreSQL
psql -U postgres -d governance

# Run schema
\i db/postgres/schema.sql

# Verify AGE extension / graph
SELECT * FROM ag_catalog.create_graph('governance_graph');
```

### 4. Configure Environment

```bash
export DB_BACKEND=postgres
export DB_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/governance
export DB_AGE_GRAPH=governance_graph
```

### 4.1 Graph name convention (important)

This repo standardizes on the AGE graph name **`governance_graph`**.

- **Why**: the Postgres backend uses `DB_AGE_GRAPH` (defaulting to `governance_graph`) when calling `cypher(...)`.
- **Rule**: if you create a different graph name locally, set `DB_AGE_GRAPH` accordingly or graph queries will fail.

### 4.2 Optional: choose the Knowledge Graph backend

The main runtime DB backend is controlled by `DB_BACKEND`, but the **knowledge graph** also supports a backend override:

```bash
# Force AGE knowledge graph backend (PostgreSQL + Apache AGE)
export UNITARES_KNOWLEDGE_BACKEND=age
```

### 5. Run Migration

```bash
# Dry run first
python scripts/migrate_to_postgres_age.py --dry-run

# Actual migration
python scripts/migrate_to_postgres_age.py
```

## Schema Overview

### Relational Tables (core schema)

- `core.agents` - Agent identity and metadata
- `core.agent_sessions` - Session bindings (fast lookup)
- `core.dialectic_sessions` - Dialectic recovery sessions
- `core.identities` - (Legacy) Identity records for backward compatibility

### Graph (AGE)

- **Nodes:**
  - `:Discovery` - Knowledge discoveries (insights, questions, self_observations)
  - `:Agent` - Agent nodes (mirror of relational table)
  - `:Tag` - Tag nodes for efficient traversal

- **Edges:**
  - `:AUTHORED` - (Agent)-[:AUTHORED]->(Discovery)
  - `:RESPONDS_TO` - (Discovery)-[:RESPONDS_TO]->(Discovery)
  - `:RELATED_TO` - (Discovery)-[:RELATED_TO]->(Discovery)
  - `:TAGGED` - (Discovery)-[:TAGGED]->(Tag)
  - `:TEMPORALLY_NEAR` - (Discovery)-[:TEMPORALLY_NEAR]->(Discovery)

## Example Queries

See `db/postgres/graph_schema.cypher` for example Cypher queries.

## Sanity checks (quick validation)

After running the schema, these checks catch 90% of setup mistakes:

```bash
# 1) Confirm Postgres connectivity
psql $DB_POSTGRES_URL -c "SELECT 1"

# 2) Confirm AGE extension exists
psql $DB_POSTGRES_URL -c "SELECT name, installed_version FROM pg_available_extensions WHERE name='age'"

# 3) Confirm the graph exists
psql $DB_POSTGRES_URL -c "SELECT graphid, name FROM ag_catalog.ag_graph WHERE name='governance_graph'"
```

## Migration Phases

1. **Phase 1**: PostgreSQL tables for agents, sessions (keep JSON/SQLite for discoveries)
2. **Phase 2**: Install AGE, create graph, dual-write discoveries
3. **Phase 3**: Backfill historical discoveries to graph
4. **Phase 4**: Cut over reads to AGE
5. **Phase 5**: Deprecate JSON/SQLite

## Troubleshooting

### AGE query errors / “cypher function not found”

- Ensure the extension is installed and loaded:
  - `CREATE EXTENSION IF NOT EXISTS age;`
- In some setups you may need to load AGE per-session:
  - `LOAD 'age';`
  - `SET search_path = ag_catalog, "$user", public;`

### AGE Extension Not Found

```sql
-- Check if AGE is installed
SELECT * FROM pg_available_extensions WHERE name = 'age';

-- If not installed, follow AGE installation guide
```

### Graph Already Exists

```sql
-- Drop and recreate (WARNING: deletes all graph data)
SELECT * FROM ag_catalog.drop_graph('governance_graph', true);
SELECT * FROM ag_catalog.create_graph('governance_graph');
```

### Connection Issues

```bash
# Test connection
psql $DB_POSTGRES_URL -c "SELECT 1"

# Check pool settings
export DB_POSTGRES_MIN_CONN=2
export DB_POSTGRES_MAX_CONN=10
```

### Common pitfalls

- **Graph name mismatch**: your graph is not `governance_graph` but `DB_AGE_GRAPH` wasn’t updated.
- **Extension not enabled in the DB**: you installed AGE on the host but didn’t run `CREATE EXTENSION age;` inside the target database.
- **Running migration before schema**: `scripts/migrate_to_postgres_age.py` assumes `db/postgres/schema.sql` has been applied.

