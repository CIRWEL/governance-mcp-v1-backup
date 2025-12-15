"""
SQLite Index for Audit Log (Dual-write with JSONL)

Goal:
- Keep `data/audit_log.jsonl` as the append-only raw truth for transparency.
- Add SQLite as a query/index layer so agents can retrieve slices quickly without scanning files.

Design:
- Store each audit entry as a row with JSON columns for `details` and `metadata`.
- Use WAL mode + busy_timeout for multi-client access (SSE + stdio + background tasks).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


def _json_dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _json_loads(v: Optional[str], default: Any) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


class AuditDB:
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
                CREATE TABLE IF NOT EXISTS audit_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  agent_id TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  details_json TEXT NOT NULL,
                  metadata_json TEXT,
                  -- raw_hash is used to make backfill idempotent (avoid duplicates when re-running).
                  raw_hash TEXT UNIQUE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent_time ON audit_events(agent_id, timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_type_time ON audit_events(event_type, timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent_type_time ON audit_events(agent_id, event_type, timestamp);")

            # Optional FTS5: fast lexical search over details_json.
            # We keep this bounded/backfillable to avoid expensive full rebuilds on large logs.
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS audit_events_fts
                    USING fts5(details_text, agent_id UNINDEXED, event_type UNINDEXED, id UNINDEXED);
                    """
                )
                conn.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS audit_events_ai AFTER INSERT ON audit_events BEGIN
                      INSERT INTO audit_events_fts(details_text, agent_id, event_type, id)
                      VALUES (new.details_json, new.agent_id, new.event_type, new.id);
                    END;
                    CREATE TRIGGER IF NOT EXISTS audit_events_ad AFTER DELETE ON audit_events BEGIN
                      DELETE FROM audit_events_fts WHERE id = old.id;
                    END;
                    CREATE TRIGGER IF NOT EXISTS audit_events_au AFTER UPDATE ON audit_events BEGIN
                      DELETE FROM audit_events_fts WHERE id = old.id;
                      INSERT INTO audit_events_fts(details_text, agent_id, event_type, id)
                      VALUES (new.details_json, new.agent_id, new.event_type, new.id);
                    END;
                    """
                )
            except Exception:
                # If SQLite is compiled without FTS5, keep working without it.
                pass

            # Lightweight schema migration: add raw_hash column if missing
            # This handles databases created before raw_hash was added to the schema
            existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(audit_events);").fetchall()}
            if "raw_hash" not in existing_cols:
                try:
                    conn.execute("ALTER TABLE audit_events ADD COLUMN raw_hash TEXT UNIQUE;")
                except Exception:
                    # Best effort: don't crash on migration
                    pass

            conn.execute(
                "INSERT OR REPLACE INTO schema_version(name, version) VALUES(?, ?);",
                ("audit_db", self.SCHEMA_VERSION),
            )

    def append_event(self, entry: Dict[str, Any], raw_hash: Optional[str] = None) -> None:
        """
        Insert a single audit entry.

        Expected keys: timestamp, agent_id, event_type, confidence, details, metadata(optional)
        """
        ts = str(entry.get("timestamp") or "")
        agent_id = str(entry.get("agent_id") or "")
        event_type = str(entry.get("event_type") or "")
        confidence = float(entry.get("confidence") or 0.0)
        details = entry.get("details") or {}
        metadata = entry.get("metadata")

        if not ts or not agent_id or not event_type:
            # Don't crash; skip malformed entries
            return

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO audit_events(
                  timestamp, agent_id, event_type, confidence, details_json, metadata_json, raw_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ts,
                    agent_id,
                    event_type,
                    confidence,
                    _json_dumps(details),
                    _json_dumps(metadata) if metadata is not None else None,
                    raw_hash,
                ),
            )
            # If row inserted, lastrowid will be set and triggers handle FTS insert.
            _ = cur.lastrowid

    def query(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000,
        order: str = "asc",
    ) -> List[Dict[str, Any]]:
        """
        Query audit entries.

        Note: default order is ASC to match legacy JSONL scan semantics (oldest-first).
        """
        where = []
        params: List[Any] = []
        if agent_id:
            where.append("agent_id = ?")
            params.append(agent_id)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if start_time:
            where.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            where.append("timestamp <= ?")
            params.append(end_time)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        order_sql = "ASC" if (order or "").lower() != "desc" else "DESC"
        limit = int(limit or 1000)

        with self._connect() as conn:
            cur = conn.execute(
                f"""
                SELECT timestamp, agent_id, event_type, confidence, details_json, metadata_json
                FROM audit_events
                {where_sql}
                ORDER BY timestamp {order_sql}
                LIMIT ?;
                """,
                (*params, limit),
            )
            out: List[Dict[str, Any]] = []
            for row in cur.fetchall():
                out.append(
                    {
                        "timestamp": row["timestamp"],
                        "agent_id": row["agent_id"],
                        "event_type": row["event_type"],
                        "confidence": float(row["confidence"]),
                        "details": _json_loads(row["details_json"], {}),
                        "metadata": _json_loads(row["metadata_json"], None),
                    }
                )
            return out

    def fts_search(
        self,
        query: str,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Full-text search over details_json via FTS5.

        This is for agent retrieval (fast lexical recall) and is intentionally separate
        from query() to keep backward-compat semantics stable.
        """
        query = (query or "").strip()
        if not query:
            return []

        where = ["f.audit_events_fts MATCH ?"]
        params: List[Any] = [query]

        if agent_id:
            where.append("e.agent_id = ?")
            params.append(agent_id)
        if event_type:
            where.append("e.event_type = ?")
            params.append(event_type)
        if start_time:
            where.append("e.timestamp >= ?")
            params.append(start_time)
        if end_time:
            where.append("e.timestamp <= ?")
            params.append(end_time)

        where_sql = " AND ".join(where)
        limit = int(limit or 200)

        with self._connect() as conn:
            try:
                cur = conn.execute(
                    f"""
                    SELECT e.timestamp, e.agent_id, e.event_type, e.confidence, e.details_json, e.metadata_json
                    FROM audit_events_fts f
                    JOIN audit_events e ON e.id = f.id
                    WHERE {where_sql}
                    ORDER BY e.timestamp ASC
                    LIMIT ?;
                    """,
                    (*params, limit),
                )
            except Exception:
                # FTS not available / not created
                return []

            out: List[Dict[str, Any]] = []
            for row in cur.fetchall():
                out.append(
                    {
                        "timestamp": row["timestamp"],
                        "agent_id": row["agent_id"],
                        "event_type": row["event_type"],
                        "confidence": float(row["confidence"]),
                        "details": _json_loads(row["details_json"], {}),
                        "metadata": _json_loads(row["metadata_json"], None),
                    }
                )
            return out

    def backfill_fts(self, limit: int = 50000) -> Dict[str, Any]:
        """
        Bounded backfill for FTS index.

        Indexes up to `limit` rows that exist in audit_events but not audit_events_fts.
        Safe to re-run.
        """
        limit = int(limit or 50000)
        with self._connect() as conn:
            # Ensure FTS table exists
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS audit_events_fts USING fts5(details_text, agent_id UNINDEXED, event_type UNINDEXED, id UNINDEXED);"
                )
            except Exception as e:
                return {"success": False, "error": f"FTS not available: {e}"}

            # Identify missing ids (bounded)
            rows = conn.execute(
                """
                SELECT id, agent_id, event_type, details_json
                FROM audit_events
                WHERE id NOT IN (SELECT id FROM audit_events_fts)
                ORDER BY id ASC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()

            inserted = 0
            for r in rows:
                try:
                    conn.execute(
                        "INSERT INTO audit_events_fts(details_text, agent_id, event_type, id) VALUES (?, ?, ?, ?);",
                        (r["details_json"], r["agent_id"], r["event_type"], r["id"]),
                    )
                    inserted += 1
                except Exception:
                    continue

            return {"success": True, "attempted": len(rows), "inserted": inserted, "limit": limit}

    def skip_rate_metrics(self, agent_id: Optional[str], cutoff_iso: str) -> Dict[str, Any]:
        """
        Compute skip rate stats since cutoff time using SQL aggregation.
        """
        with self._connect() as conn:
            params: List[Any] = [cutoff_iso]
            agent_filter = ""
            if agent_id:
                agent_filter = "AND agent_id = ?"
                params.append(agent_id)

            # total updates (auto_attest)
            total_updates = conn.execute(
                f"""
                SELECT COUNT(*) FROM audit_events
                WHERE timestamp >= ? AND event_type = 'auto_attest' {agent_filter};
                """,
                params,
            ).fetchone()[0]

            # total skips + avg confidence for skips
            total_skips, avg_conf = conn.execute(
                f"""
                SELECT COUNT(*), AVG(confidence) FROM audit_events
                WHERE timestamp >= ? AND event_type = 'lambda1_skip' {agent_filter};
                """,
                params,
            ).fetchone()

            total_skips = int(total_skips or 0)
            total_updates = int(total_updates or 0)
            avg_confidence = float(avg_conf or 0.0)
            denom = total_skips + total_updates
            skip_rate = (total_skips / denom) if denom > 0 else 0.0
            return {
                "total_skips": total_skips,
                "total_updates": total_updates,
                "skip_rate": skip_rate,
                "avg_confidence": avg_confidence,
            }

    def health_check(self) -> Dict[str, Any]:
        with self._connect() as conn:
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            fk_issues = conn.execute("PRAGMA foreign_key_check;").fetchall()
            count = conn.execute("SELECT COUNT(*) FROM audit_events;").fetchone()[0]
            version = conn.execute("SELECT version FROM schema_version WHERE name=?;", ("audit_db",)).fetchone()
            fts_enabled = False
            try:
                conn.execute("SELECT 1 FROM audit_events_fts LIMIT 1;")
                fts_enabled = True
            except Exception:
                fts_enabled = False
            return {
                "backend": "sqlite",
                "db_path": str(self.db_path),
                "schema_version": int(version[0]) if version else None,
                "integrity_check": integrity,
                "foreign_key_issues": len(fk_issues),
                "event_count": int(count),
                "fts_enabled": fts_enabled,
            }

    def backfill_from_jsonl(
        self,
        jsonl_path: Path,
        max_lines: int = 50000,
        batch_size: int = 2000,
    ) -> Dict[str, Any]:
        """
        One-time bounded backfill: read audit_log.jsonl and insert into SQLite index.

        This is safe to run multiple times due to raw_hash UNIQUE + INSERT OR IGNORE.
        """
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            return {"success": False, "error": f"JSONL not found: {jsonl_path}"}

        inserted = 0
        skipped = 0
        errors = 0
        processed = 0

        # Insert in a single connection/transaction for speed.
        with self._connect() as conn:
            conn.execute("BEGIN;")
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if processed >= max_lines:
                            break
                        processed += 1
                        raw = line.strip()
                        if not raw:
                            continue
                        try:
                            entry = json.loads(raw)
                            h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                            # Inline insert (avoid opening new connections)
                            ts = str(entry.get("timestamp") or "")
                            agent_id = str(entry.get("agent_id") or "")
                            event_type = str(entry.get("event_type") or "")
                            confidence = float(entry.get("confidence") or 0.0)
                            details = entry.get("details") or {}
                            metadata = entry.get("metadata")

                            if not ts or not agent_id or not event_type:
                                skipped += 1
                                continue

                            cur = conn.execute(
                                """
                                INSERT OR IGNORE INTO audit_events(
                                  timestamp, agent_id, event_type, confidence, details_json, metadata_json, raw_hash
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?);
                                """,
                                (
                                    ts,
                                    agent_id,
                                    event_type,
                                    confidence,
                                    _json_dumps(details),
                                    _json_dumps(metadata) if metadata is not None else None,
                                    h,
                                ),
                            )
                            # SQLite: rowcount is 1 if inserted, 0 if ignored
                            if cur.rowcount == 1:
                                inserted += 1
                            else:
                                skipped += 1

                            if (processed % batch_size) == 0:
                                conn.execute("COMMIT;")
                                conn.execute("BEGIN;")
                        except Exception:
                            errors += 1
                            continue
                conn.execute("COMMIT;")
            except Exception as e:
                conn.execute("ROLLBACK;")
                return {"success": False, "error": str(e), "processed": processed, "inserted": inserted, "skipped": skipped, "errors": errors}

        return {
            "success": True,
            "jsonl_path": str(jsonl_path),
            "processed": processed,
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors,
            "max_lines": max_lines,
        }


