"""Dialectic operations mixin for PostgresBackend."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..dialectic_constants import ACTIVE_DIALECTIC_STATUSES
from src.logging_utils import get_logger

logger = get_logger(__name__)


class DialecticMixin:
    """Dialectic session and message operations."""

    async def create_dialectic_session(
        self,
        session_id: str,
        paused_agent_id: str,
        reviewer_agent_id: Optional[str] = None,
        reason: Optional[str] = None,
        discovery_id: Optional[str] = None,
        dispute_type: Optional[str] = None,
        session_type: Optional[str] = None,
        topic: Optional[str] = None,
        max_synthesis_rounds: Optional[int] = None,
        synthesis_round: Optional[int] = None,
        paused_agent_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        async with self.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO core.agents (id, api_key)
                    VALUES ($1, '')
                    ON CONFLICT (id) DO NOTHING
                    """,
                    paused_agent_id,
                )
                if reviewer_agent_id:
                    await conn.execute(
                        """
                        INSERT INTO core.agents (id, api_key)
                        VALUES ($1, '')
                        ON CONFLICT (id) DO NOTHING
                        """,
                        reviewer_agent_id,
                    )

                resolution_data = {}
                if reason:
                    resolution_data["reason"] = reason
                if discovery_id:
                    resolution_data["discovery_id"] = discovery_id
                if dispute_type:
                    resolution_data["dispute_type"] = dispute_type
                if topic:
                    resolution_data["topic"] = topic
                if max_synthesis_rounds is not None:
                    resolution_data["max_synthesis_rounds"] = max_synthesis_rounds
                if synthesis_round is not None:
                    resolution_data["synthesis_round"] = synthesis_round
                if paused_agent_state:
                    resolution_data["paused_agent_state"] = paused_agent_state

                final_session_type = session_type or "review"
                initial_status = "thesis"

                await conn.execute("""
                    INSERT INTO core.dialectic_sessions (
                        session_id, session_type, status, paused_agent_id, reviewer_agent_id,
                        created_at, updated_at, resolution
                    ) VALUES ($1, $2, $3, $4, $5, now(), now(), $6)
                """,
                    session_id,
                    final_session_type,
                    initial_status,
                    paused_agent_id,
                    reviewer_agent_id,
                    json.dumps(resolution_data) if resolution_data else None,
                )
                return {"session_id": session_id, "created": True}
            except Exception as e:
                if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                    return {"session_id": session_id, "created": False, "error": "already_exists"}
                raise

    async def get_dialectic_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM core.dialectic_sessions WHERE session_id = $1
            """, session_id)
            if not row:
                return None

            session = dict(row)

            if "session_id" not in session:
                session["session_id"] = session_id

            if "status" in session:
                session["phase"] = session["status"]

            if session.get("resolution"):
                resolution = session["resolution"]
                if isinstance(resolution, str):
                    resolution = json.loads(resolution)
                session["resolution"] = resolution

                if isinstance(resolution, dict):
                    if "reason" in resolution:
                        session["reason"] = resolution["reason"]
                    if "discovery_id" in resolution:
                        session["discovery_id"] = resolution["discovery_id"]
                    if "dispute_type" in resolution:
                        session["dispute_type"] = resolution["dispute_type"]
                    if "topic" in resolution:
                        session["topic"] = resolution["topic"]
                    if "max_synthesis_rounds" in resolution:
                        session["max_synthesis_rounds"] = resolution["max_synthesis_rounds"]
                    if "synthesis_round" in resolution:
                        session["synthesis_round"] = resolution["synthesis_round"]
                    if "paused_agent_state" in resolution:
                        session["paused_agent_state"] = resolution["paused_agent_state"]

            rows = await conn.fetch("""
                SELECT * FROM core.dialectic_messages
                WHERE session_id = $1
                ORDER BY message_id ASC
            """, session_id)

            messages = []
            for msg_row in rows:
                msg = dict(msg_row)
                if msg.get("proposed_conditions"):
                    msg["proposed_conditions"] = json.loads(msg["proposed_conditions"]) if isinstance(msg["proposed_conditions"], str) else msg["proposed_conditions"]
                if msg.get("observed_metrics"):
                    msg["observed_metrics"] = json.loads(msg["observed_metrics"]) if isinstance(msg["observed_metrics"], str) else msg["observed_metrics"]
                if msg.get("concerns"):
                    msg["concerns"] = json.loads(msg["concerns"]) if isinstance(msg["concerns"], str) else msg["concerns"]
                messages.append(msg)

            session["messages"] = messages
            return session

    async def get_dialectic_session_by_agent(
        self,
        agent_id: str,
        active_only: bool = True,
    ) -> Optional[Dict[str, Any]]:
        async with self.acquire() as conn:
            if active_only:
                pg_active_statuses = tuple(s for s in ACTIVE_DIALECTIC_STATUSES if s != "active")
                status_filter = "AND status = ANY($2::text[])"
                row = await conn.fetchrow(f"""
                    SELECT session_id FROM core.dialectic_sessions
                    WHERE (paused_agent_id = $1 OR reviewer_agent_id = $1)
                    {status_filter}
                    ORDER BY created_at DESC
                    LIMIT 1
                """, agent_id, list(pg_active_statuses))
            else:
                status_filter = ""
                row = await conn.fetchrow(f"""
                    SELECT session_id FROM core.dialectic_sessions
                    WHERE (paused_agent_id = $1 OR reviewer_agent_id = $1)
                    {status_filter}
                    ORDER BY created_at DESC
                    LIMIT 1
                """, agent_id)
            if row:
                return await self.get_dialectic_session(row["session_id"])
            return None

    async def get_all_active_dialectic_sessions_for_agent(
        self,
        agent_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all active sessions where agent is paused agent or reviewer."""
        async with self.acquire() as conn:
            pg_active_statuses = tuple(s for s in ACTIVE_DIALECTIC_STATUSES if s != "active")
            rows = await conn.fetch("""
                SELECT session_id FROM core.dialectic_sessions
                WHERE (paused_agent_id = $1 OR reviewer_agent_id = $1)
                AND status = ANY($2::text[])
                ORDER BY created_at DESC
            """, agent_id, list(pg_active_statuses))

            sessions = []
            for row in rows:
                session = await self.get_dialectic_session(row["session_id"])
                if session:
                    sessions.append(session)
            return sessions

    async def update_dialectic_session_phase(
        self,
        session_id: str,
        phase: str,
    ) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute("""
                UPDATE core.dialectic_sessions
                SET status = $1, updated_at = now()
                WHERE session_id = $2
            """, phase, session_id)
            return "UPDATE 1" in result

    async def update_dialectic_session_reviewer(
        self,
        session_id: str,
        reviewer_agent_id: str,
    ) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute("""
                UPDATE core.dialectic_sessions
                SET reviewer_agent_id = $1, updated_at = now()
                WHERE session_id = $2
            """, reviewer_agent_id, session_id)
            return "UPDATE 1" in result

    async def add_dialectic_message(
        self,
        session_id: str,
        agent_id: str,
        message_type: str,
        root_cause: Optional[str] = None,
        proposed_conditions: Optional[List[str]] = None,
        reasoning: Optional[str] = None,
        observed_metrics: Optional[Dict[str, Any]] = None,
        concerns: Optional[List[str]] = None,
        agrees: Optional[bool] = None,
        signature: Optional[str] = None,
    ) -> int:
        async with self.acquire() as conn:
            message_id = await conn.fetchval("""
                INSERT INTO core.dialectic_messages (
                    session_id, agent_id, message_type, timestamp,
                    root_cause, proposed_conditions, reasoning,
                    observed_metrics, concerns, agrees, signature
                ) VALUES ($1, $2, $3, now(), $4, $5, $6, $7, $8, $9, $10)
                RETURNING message_id
            """,
                session_id,
                agent_id,
                message_type,
                root_cause,
                json.dumps(proposed_conditions) if proposed_conditions else None,
                reasoning,
                json.dumps(observed_metrics) if observed_metrics else None,
                json.dumps(concerns) if concerns else None,
                agrees,
                signature,
            )

            await conn.execute("""
                UPDATE core.dialectic_sessions SET updated_at = now() WHERE session_id = $1
            """, session_id)

            return message_id

    async def resolve_dialectic_session(
        self,
        session_id: str,
        resolution: Dict[str, Any],
        status: str = "resolved",
    ) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute("""
                UPDATE core.dialectic_sessions
                SET status = $1, resolution = $2, resolved_at = now(), updated_at = now()
                WHERE session_id = $3
            """,
                status,
                json.dumps(resolution),
                session_id,
            )
            return "UPDATE 1" in result

    async def is_agent_in_active_dialectic_session(self, agent_id: str) -> bool:
        async with self.acquire() as conn:
            pg_active_statuses = tuple(s for s in ACTIVE_DIALECTIC_STATUSES if s != "active")
            result = await conn.fetchval("""
                SELECT 1 FROM core.dialectic_sessions
                WHERE (paused_agent_id = $1 OR reviewer_agent_id = $1)
                AND status = ANY($2::text[])
                LIMIT 1
            """, agent_id, list(pg_active_statuses))
            return result is not None

    async def get_pending_dialectic_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get dialectic sessions awaiting a reviewer (reviewer_agent_id IS NULL).

        Used for pull-based discovery: agents check for pending reviews on status().
        """
        async with self.acquire() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT session_id, paused_agent_id, session_type, status,
                           created_at, resolution
                    FROM core.dialectic_sessions
                    WHERE reviewer_agent_id IS NULL
                    AND status IN ('pending', 'thesis')
                    ORDER BY created_at ASC
                    LIMIT $1
                """, limit)
                id_key = "session_id"
            except Exception as e:
                try:
                    rows = await conn.fetch("""
                        SELECT session_id, paused_agent_id, status, created_at
                        FROM core.dialectic_sessions
                        WHERE reviewer_agent_id IS NULL
                        AND status IN ('pending', 'thesis')
                        ORDER BY created_at ASC
                        LIMIT $1
                    """, limit)
                    id_key = "session_id"
                except Exception:
                    try:
                        rows = await conn.fetch("""
                            SELECT session_id, paused_agent_id, session_type, status,
                                   created_at
                            FROM core.dialectic_sessions
                            WHERE reviewer_agent_id IS NULL
                            AND status IN ('pending', 'thesis')
                            ORDER BY created_at ASC
                            LIMIT $1
                        """, limit)
                        id_key = "session_id"
                    except Exception:
                        rows = await conn.fetch("""
                            SELECT session_id, paused_agent_id, status, created_at
                            FROM core.dialectic_sessions
                            WHERE reviewer_agent_id IS NULL
                            AND status IN ('pending', 'thesis')
                            ORDER BY created_at ASC
                            LIMIT $1
                        """, limit)
                        id_key = "session_id"

            sessions = []
            for row in rows:
                session = {
                    "session_id": row[id_key],
                    "paused_agent_id": row["paused_agent_id"],
                    "session_type": row.get("session_type"),
                    "phase": row["status"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                resolution_val = row.get("resolution") if hasattr(row, "get") else None
                if resolution_val:
                    resolution = resolution_val
                    if isinstance(resolution, str):
                        resolution = json.loads(resolution)
                    if isinstance(resolution, dict):
                        if "reason" in resolution:
                            session["reason"] = resolution["reason"]
                        if "discovery_id" in resolution:
                            session["discovery_id"] = resolution["discovery_id"]
                        if "dispute_type" in resolution:
                            session["dispute_type"] = resolution["dispute_type"]
                        if "topic" in resolution:
                            session["topic"] = resolution["topic"]
                sessions.append(session)

            return sessions
