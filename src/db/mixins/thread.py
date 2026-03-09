"""Thread identity operations mixin for PostgresBackend."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.logging_utils import get_logger

logger = get_logger(__name__)


class ThreadMixin:
    """Thread identity operations (migration 006)."""

    async def create_or_get_thread(
        self, thread_id: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Idempotent: create a thread if it doesn't exist, return current state.

        Returns {"thread_id": str, "created": bool, "next_node_seq": int}
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO core.threads (thread_id, metadata)
                VALUES ($1, $2)
                ON CONFLICT (thread_id) DO UPDATE
                    SET metadata = core.threads.metadata
                RETURNING thread_id, next_node_seq,
                          (xmax = 0) AS created
                """,
                thread_id,
                json.dumps(metadata or {}),
            )
            return dict(row)

    async def claim_thread_position(self, thread_id: str) -> int:
        """
        Atomically claim the next node position in a thread.

        Position 1 = thread root, 2 = first fork, etc.
        Raises ValueError if thread not found.
        """
        async with self.acquire() as conn:
            try:
                pos = await conn.fetchval(
                    "SELECT core.claim_thread_position($1)",
                    thread_id,
                )
                return pos
            except Exception as e:
                if "Thread not found" in str(e):
                    raise ValueError(f"Thread not found: {thread_id}") from e
                raise

    async def get_thread_nodes(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Return all nodes in a thread ordered by position.

        Each dict: {agent_id, thread_position, parent_agent_id, spawn_reason,
                    created_at, label, status}
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id AS agent_id, thread_position, parent_agent_id,
                       spawn_reason, created_at, label, status
                FROM core.agents
                WHERE thread_id = $1
                ORDER BY thread_position
                """,
                thread_id,
            )
            result = []
            for r in rows:
                d = dict(r)
                if d.get("created_at"):
                    d["created_at"] = d["created_at"].isoformat()
                result.append(d)
            return result

    async def get_agent_thread_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Return thread membership for a single agent, or None if not threaded.

        Dict: {thread_id, thread_position, parent_agent_id, spawn_reason}
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT thread_id, thread_position, parent_agent_id, spawn_reason
                FROM core.agents
                WHERE id = $1
                """,
                agent_id,
            )
            if not row or not row["thread_id"]:
                return None
            return dict(row)
