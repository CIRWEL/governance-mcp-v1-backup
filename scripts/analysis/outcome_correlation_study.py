#!/usr/bin/env python3
"""Run the grounded outcome-correlation study against PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import psycopg2

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.grounded_outcome_study import run_grounded_outcome_study


DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5432/governance"


def load_frame(conn, query: str) -> pd.DataFrame:
    """Run a SQL query and materialize a DataFrame without SQLAlchemy."""
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=columns)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grounded outcome-correlation study")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="PostgreSQL URL")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    try:
        outcomes = load_frame(
            conn,
            """
            SELECT ts, agent_id, outcome_type, outcome_score, is_bad,
                   eisv_e, eisv_i, eisv_s, eisv_v, eisv_phi, eisv_coherence,
                   detail::text AS detail
            FROM audit.outcome_events
            ORDER BY ts
            """,
        )
        identity_agents = load_frame(conn, "SELECT agent_id FROM core.identities")["agent_id"].tolist()
        state_agents = load_frame(
            conn,
            """
            SELECT DISTINCT i.agent_id
            FROM core.agent_state s
            JOIN core.identities i ON i.identity_id = s.identity_id
            """,
        )["agent_id"].tolist()
        audit_agents = load_frame(
            conn,
            "SELECT DISTINCT agent_id FROM audit.events WHERE agent_id IS NOT NULL",
        )["agent_id"].tolist()
        first_behavioral = load_frame(
            conn,
            """
            SELECT MIN(ts)::text AS first_behavioral_timestamp
            FROM audit.events
            WHERE event_type = 'auto_attest' AND payload ? 'beh_obs'
            """,
        )["first_behavioral_timestamp"].iloc[0]

        report = run_grounded_outcome_study(
            outcomes,
            identity_agent_ids=identity_agents,
            state_agent_ids=state_agents,
            audit_agent_ids=audit_agents,
            first_behavioral_timestamp=first_behavioral,
        )
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print("Grounded Outcome Correlation Study")
        print("=" * 34)
        print(report.summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
