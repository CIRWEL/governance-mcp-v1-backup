"""
SQLite Backend for Calibration State

Goal:
- Provide atomic, concurrent-safe persistence for calibration state under multi-client SSE.
- Keep optional JSON snapshot (`data/calibration_state.json`) for backward compatibility / transparency.

This stores the same state payload as CalibrationChecker.save_state():
{
  "bins": {...},
  "complexity_bins": {...},
  "tactical_bins": {...}
}
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class CalibrationDB:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                  name TEXT PRIMARY KEY,
                  version INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calibration_state (
                  id INTEGER PRIMARY KEY CHECK (id = 1),
                  state_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO schema_version(name, version) VALUES(?, ?);",
                ("calibration_db", self.SCHEMA_VERSION),
            )

    def save_state(self, state: Dict[str, Any], updated_at_iso: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO calibration_state(id, state_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  state_json=excluded.state_json,
                  updated_at=excluded.updated_at;
                """,
                (json.dumps(state, ensure_ascii=False), updated_at_iso),
            )

    def load_state(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT state_json FROM calibration_state WHERE id = 1;").fetchone()
            if not row:
                return None
            try:
                return json.loads(row["state_json"])
            except Exception:
                return None

    def health_check(self) -> Dict[str, Any]:
        with self._connect() as conn:
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            fk_issues = conn.execute("PRAGMA foreign_key_check;").fetchall()
            has_state = conn.execute("SELECT COUNT(*) FROM calibration_state;").fetchone()[0]
            version = conn.execute(
                "SELECT version FROM schema_version WHERE name=?;", ("calibration_db",)
            ).fetchone()
            return {
                "backend": "sqlite",
                "db_path": str(self.db_path),
                "schema_version": int(version[0]) if version else None,
                "integrity_check": integrity,
                "foreign_key_issues": len(fk_issues),
                "has_state_row": bool(has_state),
            }


