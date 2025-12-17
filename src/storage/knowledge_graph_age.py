"""
AGE-backed Knowledge Graph Implementation

Apache AGE implementation of the knowledge graph interface.
Uses PostgreSQL + AGE for native graph queries.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from src.logging_utils import get_logger
from src.knowledge_graph import DiscoveryNode, ResponseTo
from src.db import get_db
from src.db.age_queries import (
    create_discovery_node,
    create_agent_node,
    create_authored_edge,
    create_responds_to_edge,
    create_related_to_edge,
    create_temporally_near_edge,
    create_tagged_edge,
    query_agent_discoveries,
    query_response_chain,
    create_indexes,
)

logger = get_logger(__name__)


class KnowledgeGraphAGE:
    """
    AGE-backed knowledge graph implementation.
    
    Uses Apache AGE for native graph queries while maintaining compatibility
    with the existing KnowledgeGraph interface.
    """

    def __init__(self, graph_name: str = "governance_graph"):
        # Note: the actual AGE graph name used at query time is owned by the DB backend
        # (see PostgresBackend._age_graph). We keep a local copy for SQL operations
        # that reference the graph schema (e.g., CREATE INDEX ON <graph>.Label(...)).
        self.graph_name = graph_name
        self._db = None
        self._indexes_created = False
        self.rate_limit_stores_per_hour = 20  # Max stores per agent per hour

    async def _get_db(self):
        """Get database backend (lazy initialization)."""
        if self._db is None:
            self._db = get_db()
            await self._db.init()

            # Best-effort: align our graph_name with backend config
            try:
                if hasattr(self._db, "_age_graph"):
                    self.graph_name = getattr(self._db, "_age_graph") or self.graph_name
                elif hasattr(self._db, "_postgres") and getattr(self._db, "_postgres_available", False):
                    pg = getattr(self._db, "_postgres")
                    if hasattr(pg, "_age_graph"):
                        self.graph_name = getattr(pg, "_age_graph") or self.graph_name
            except Exception:
                pass
            
            # Create indexes on first use
            if not self._indexes_created:
                await self._create_indexes()
                self._indexes_created = True
        
        return self._db

    async def _create_indexes(self):
        """Create AGE indexes for efficient queries."""
        db = await self._get_db()
        if not await db.graph_available():
            logger.warning("AGE not available, skipping index creation")
            return
        
        # AGE indexes are created via SQL on the graph schema, not via cypher()
        indexes = create_indexes(self.graph_name)
        for sql, _params in indexes:
            try:
                await self._execute_age_sql(sql)
                logger.debug(f"Created index: {sql[:60]}...")
            except Exception as e:
                logger.warning(f"Failed to create index: {e}")

    async def _execute_age_sql(self, sql: str) -> None:
        """
        Execute a SQL statement against Postgres (used for AGE DDL like CREATE INDEX).

        Supports DB_BACKEND=postgres and DB_BACKEND=dual (uses the Postgres secondary).
        """
        db = await self._get_db()
        pool = None
        if hasattr(db, "_pool"):
            pool = getattr(db, "_pool")
        elif hasattr(db, "_postgres") and getattr(db, "_postgres_available", False):
            pg = getattr(db, "_postgres")
            pool = getattr(pg, "_pool", None)
        if pool is None:
            raise RuntimeError("PostgreSQL pool unavailable (AGE SQL execution requires Postgres backend)")

        async with pool.acquire() as conn:
            await conn.execute("LOAD 'age'")
            await conn.execute("SET search_path = ag_catalog, core, audit, public")
            await conn.execute(sql)

    async def add_discovery(
        self,
        discovery: DiscoveryNode,
        auto_link_temporal: bool = True,
    ) -> None:
        """
        Add a discovery to the graph.
        
        Args:
            discovery: DiscoveryNode to add
            auto_link_temporal: If True, automatically create TEMPORALLY_NEAR edges
                              to recent discoveries by the same agent
        """
        # Rate limiting check (security measure)
        await self._check_rate_limit(discovery.agent_id)
        
        db = await self._get_db()
        
        if not await db.graph_available():
            raise RuntimeError("AGE graph not available. Check PostgreSQL AGE extension.")
        
        # Extract EISV fields if this is a self_observation
        eisv_e = None
        eisv_i = None
        eisv_s = None
        eisv_v = None
        regime = None
        coherence = None
        
        if discovery.type == "self_observation" and discovery.provenance:
            prov = discovery.provenance
            eisv_e = prov.get("E") or prov.get("eisv_e")
            eisv_i = prov.get("I") or prov.get("eisv_i")
            eisv_s = prov.get("S") or prov.get("eisv_s")
            eisv_v = prov.get("V") or prov.get("eisv_v")
            regime = prov.get("regime")
            coherence = prov.get("coherence")
        
        # Parse timestamp
        timestamp = None
        if discovery.timestamp:
            try:
                timestamp = datetime.fromisoformat(discovery.timestamp.replace('Z', '+00:00'))
            except Exception:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        
        resolved_at = None
        if discovery.resolved_at:
            try:
                resolved_at = datetime.fromisoformat(discovery.resolved_at.replace('Z', '+00:00'))
            except Exception:
                pass
        
        # Create discovery node
        cypher, params = create_discovery_node(
            discovery_id=discovery.id,
            agent_id=discovery.agent_id,
            discovery_type=discovery.type,
            summary=discovery.summary,
            details=discovery.details,
            severity=discovery.severity,
            status=discovery.status,
            timestamp=timestamp,
            resolved_at=resolved_at,
            eisv_e=eisv_e,
            eisv_i=eisv_i,
            eisv_s=eisv_s,
            eisv_v=eisv_v,
            regime=regime,
            coherence=coherence,
            tags=discovery.tags,
            metadata={
                "related_to": discovery.related_to,
                "references_files": discovery.references_files,
                "confidence": discovery.confidence,
                "provenance": discovery.provenance,
                "provenance_chain": discovery.provenance_chain,
            } if any([discovery.related_to, discovery.references_files, 
                     discovery.confidence, discovery.provenance, discovery.provenance_chain]) else None,
        )
        
        # Execute via graph_query
        await db.graph_query(cypher, params)
        
        # Create/update agent node
        agent_cypher, agent_params = create_agent_node(
            agent_id=discovery.agent_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        await db.graph_query(agent_cypher, agent_params)
        
        # Create AUTHORED edge
        authored_cypher, authored_params = create_authored_edge(
            agent_id=discovery.agent_id,
            discovery_id=discovery.id,
            at=timestamp,
        )
        await db.graph_query(authored_cypher, authored_params)
        
        # Create RESPONDS_TO edge if response_to exists
        if discovery.response_to:
            responds_cypher, responds_params = create_responds_to_edge(
                from_discovery_id=discovery.id,
                to_discovery_id=discovery.response_to.discovery_id,
            )
            await db.graph_query(responds_cypher, responds_params)
        
        # Create RELATED_TO edges
        for related_id in discovery.related_to:
            related_cypher, related_params = create_related_to_edge(
                from_discovery_id=discovery.id,
                to_discovery_id=related_id,
            )
            await db.graph_query(related_cypher, related_params)
        
        # Create TAGGED edges
        for tag in discovery.tags:
            tagged_cypher, tagged_params = create_tagged_edge(
                discovery_id=discovery.id,
                tag_name=tag,
            )
            await db.graph_query(tagged_cypher, tagged_params)
        
        # Auto-link temporal edges if enabled
        if auto_link_temporal:
            await self._link_temporal_edges(discovery, timestamp)
        
        logger.debug(f"Added discovery {discovery.id} to AGE graph")

    async def _link_temporal_edges(
        self,
        discovery: DiscoveryNode,
        timestamp: datetime,
        window_seconds: int = 300,  # 5 minutes
    ):
        """Create TEMPORALLY_NEAR edges to recent discoveries by the same agent."""
        db = await self._get_db()
        
        # Find recent discoveries by the same agent
        cypher = f"""
            MATCH (d:Discovery {{agent_id: $agent_id}})
            WHERE d.id <> $discovery_id
              AND d.timestamp IS NOT NULL
              AND datetime(d.timestamp) >= datetime($timestamp) - duration({{seconds: $window}})
              AND datetime(d.timestamp) <= datetime($timestamp) + duration({{seconds: $window}})
            RETURN d.id AS id, d.timestamp AS ts
        """
        
        params = {
            "agent_id": discovery.agent_id,
            "discovery_id": discovery.id,
            "timestamp": timestamp.isoformat(),
            "window": window_seconds,
        }
        
        results = await db.graph_query(cypher, params)
        
        # Create temporal edges
        for result in results:
            other_id = result.get("id")
            other_ts_str = result.get("ts")
            if not other_id or not other_ts_str:
                continue
            
            try:
                other_ts = datetime.fromisoformat(other_ts_str.replace('Z', '+00:00'))
                delta_seconds = abs(int((timestamp - other_ts).total_seconds()))
                
                if delta_seconds <= window_seconds:
                    temp_cypher, temp_params = create_temporally_near_edge(
                        from_discovery_id=discovery.id,
                        to_discovery_id=other_id,
                        delta_seconds=delta_seconds,
                    )
                    await db.graph_query(temp_cypher, temp_params)
            except Exception as e:
                logger.debug(f"Failed to create temporal edge: {e}")

    async def get_discovery(self, discovery_id: str) -> Optional[DiscoveryNode]:
        """Get a discovery by ID."""
        db = await self._get_db()
        
        cypher = """
            MATCH (d:Discovery {id: ${discovery_id}})
            RETURN d
        """
        
        results = await db.graph_query(cypher, {"discovery_id": discovery_id})
        
        if not results:
            return None
        
        # Parse result (AGE returns agtype, need to convert)
        node_data = self._parse_agtype_node(results[0].get("d"))
        return self._node_to_discovery(node_data)

    async def query(
        self,
        agent_id: Optional[str] = None,
        type: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[DiscoveryNode]:
        """
        Query discoveries with filters.
        
        Args:
            agent_id: Filter by agent
            type: Filter by discovery type
            status: Filter by status
            tags: Filter by tags (any match)
            limit: Maximum results
        """
        db = await self._get_db()
        
        # Build query
        conditions = []
        params = {}
        
        if agent_id:
            conditions.append("d.agent_id = ${agent_id}")
            params["agent_id"] = agent_id
        
        if type:
            conditions.append("d.type = ${type}")
            params["type"] = type
        
        if status:
            conditions.append("d.status = ${status}")
            params["status"] = status
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Handle tags (need to match any tag)
        tag_match = ""
        if tags:
            params["tags"] = tags
            tag_match = """
                MATCH (d)-[:TAGGED]->(t:Tag)
                WHERE t.name IN ${tags}
            """
            if conditions:
                where_clause += " AND EXISTS {"
            else:
                where_clause = "EXISTS {"
            where_clause += tag_match + "}"
        
        cypher = f"""
            MATCH (d:Discovery)
            {tag_match if tags and not conditions else ""}
            WHERE {where_clause}
            RETURN d
            ORDER BY d.timestamp DESC
            LIMIT ${{limit}}
        """
        
        params["limit"] = limit
        
        results = await db.graph_query(cypher, params)
        
        discoveries = []
        for result in results:
            node_data = self._parse_agtype_node(result.get("d"))
            discovery = self._node_to_discovery(node_data)
            if discovery:
                discoveries.append(discovery)
        
        return discoveries

    async def get_agent_discoveries(
        self,
        agent_id: str,
        limit: Optional[int] = None,
    ) -> List[DiscoveryNode]:
        """Get all discoveries for an agent."""
        return await self.query(
            agent_id=agent_id,
            limit=limit or 100,
        )

    def _parse_agtype_node(self, agtype_value: Any) -> Dict[str, Any]:
        """
        Parse AGE agtype node to dictionary.
        
        AGE returns agtype which needs to be converted to Python types.
        """
        if agtype_value is None:
            return {}
        
        # If it's already a dict, return it
        if isinstance(agtype_value, dict):
            return agtype_value
        
        # If it's a string (JSON), parse it
        if isinstance(agtype_value, str):
            try:
                return json.loads(agtype_value)
            except Exception:
                return {}
        
        # Try to extract properties
        if hasattr(agtype_value, "properties"):
            return dict(agtype_value.properties)
        
        # Fallback: convert to dict
        try:
            return dict(agtype_value)
        except Exception:
            return {}

    def _node_to_discovery(self, node_data: Dict[str, Any]) -> Optional[DiscoveryNode]:
        """Convert AGE node data to DiscoveryNode."""
        if not node_data or "id" not in node_data:
            return None
        
        # Extract metadata if present
        metadata = node_data.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        
        # Parse response_to if present
        response_to = None
        if "response_to" in metadata:
            resp_data = metadata["response_to"]
            if isinstance(resp_data, dict):
                response_to = ResponseTo(
                    discovery_id=resp_data.get("discovery_id", ""),
                    response_type=resp_data.get("response_type", "extend"),
                )
        
        return DiscoveryNode(
            id=node_data.get("id", ""),
            agent_id=node_data.get("agent_id", ""),
            type=node_data.get("type", "insight"),
            summary=node_data.get("summary", ""),
            details=node_data.get("details", ""),
            tags=node_data.get("tags", []),
            severity=node_data.get("severity"),
            timestamp=node_data.get("timestamp", datetime.now().isoformat()),
            status=node_data.get("status", "open"),
            related_to=metadata.get("related_to", []),
            response_to=response_to,
            references_files=metadata.get("references_files", []),
            resolved_at=node_data.get("resolved_at"),
            updated_at=node_data.get("updated_at"),
            confidence=metadata.get("confidence"),
            provenance=metadata.get("provenance"),
            provenance_chain=metadata.get("provenance_chain"),
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        db = await self._get_db()
        
        cypher = """
            MATCH (d:Discovery)
            RETURN count(d) AS total_discoveries
        """
        
        total = await db.graph_query(cypher, {})
        total_count = total[0].get("total_discoveries", 0) if total else 0
        
        # Count by agent
        cypher = """
            MATCH (d:Discovery)
            RETURN d.agent_id AS agent_id, count(*) AS cnt
        """
        by_agent_raw = await db.graph_query(cypher, {})
        by_agent = {}
        for row in by_agent_raw:
            agent_id = row.get("agent_id") or row.get("agent_id")
            cnt = row.get("cnt") or row.get("cnt") or 0
            if agent_id:
                by_agent[str(agent_id)] = int(cnt) if isinstance(cnt, (int, float)) else 0
        
        # Count by type
        cypher = """
            MATCH (d:Discovery)
            RETURN d.type AS type, count(*) AS cnt
        """
        by_type_raw = await db.graph_query(cypher, {})
        by_type = {}
        for row in by_type_raw:
            type_name = row.get("type") or row.get("type")
            cnt = row.get("cnt") or row.get("cnt") or 0
            if type_name:
                by_type[str(type_name)] = int(cnt) if isinstance(cnt, (int, float)) else 0
        
        # Count by status
        cypher = """
            MATCH (d:Discovery)
            RETURN d.status AS status, count(*) AS cnt
        """
        by_status_raw = await db.graph_query(cypher, {})
        by_status = {}
        for row in by_status_raw:
            status_name = row.get("status") or row.get("status")
            cnt = row.get("cnt") or row.get("cnt") or 0
            if status_name:
                by_status[str(status_name)] = int(cnt) if isinstance(cnt, (int, float)) else 0
        
        # Count edges
        cypher = """
            MATCH ()-[r]->()
            RETURN count(r) AS total_edges
        """
        edges_result = await db.graph_query(cypher, {})
        total_edges = edges_result[0].get("total_edges", 0) if edges_result else 0
        
        return {
            "total_discoveries": total_count,
            "by_agent": by_agent,
            "by_type": by_type,
            "by_status": by_status,
            "total_edges": total_edges,
            "total_agents": len(by_agent),
        }

    async def _check_rate_limit(self, agent_id: str) -> None:
        """
        Check if agent has exceeded rate limit (20 stores/hour).
        Raises ValueError if limit exceeded.
        Uses PostgreSQL for persistent rate limit tracking.
        """
        db = await self._get_db()
        
        # Use PostgreSQL to check rate limits
        async with db._pool.acquire() as conn:
            from datetime import datetime, timedelta
            one_hour_ago = datetime.now() - timedelta(hours=1)
            
            # Count recent stores
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM audit.rate_limits
                WHERE agent_id = $1 AND timestamp > $2
                """,
                agent_id,
                one_hour_ago,
            )
            
            count = count or 0
            if count >= self.rate_limit_stores_per_hour:
                raise ValueError(
                    f"Rate limit exceeded: Agent '{agent_id}' has stored {count} "
                    f"discoveries in the last hour (limit: {self.rate_limit_stores_per_hour}/hour). "
                    f"This prevents knowledge graph poisoning flood attacks. "
                    f"Please wait before storing more discoveries."
                )
            
            # Record this store for rate limiting
            await conn.execute(
                """
                INSERT INTO audit.rate_limits (agent_id, timestamp)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                agent_id,
                datetime.now(),
            )
            
            # Cleanup old rate limit entries (older than 1 hour)
            await conn.execute(
                """
                DELETE FROM audit.rate_limits
                WHERE timestamp < $1
                """,
                one_hour_ago,
            )

    async def load(self) -> None:
        """
        Load graph (no-op for AGE backend - data is always in PostgreSQL).
        Exists for compatibility with other backends.
        """
        # AGE backend is always persistent, no loading needed
        pass

    async def find_similar(
        self,
        discovery: DiscoveryNode,
        limit: int = 5,
    ) -> List[DiscoveryNode]:
        """
        Find similar discoveries by tag overlap.
        
        Args:
            discovery: Discovery to find similar ones for
            limit: Maximum number of results
            
        Returns:
            List of similar DiscoveryNodes
        """
        if not discovery.tags:
            return []
        
        # Find discoveries with overlapping tags
        db = await self._get_db()
        
        cypher = f"""
            MATCH (d:Discovery)-[:TAGGED]->(t:Tag)
            WHERE t.name IN ${{tags}}
              AND d.id <> ${{exclude_id}}
            WITH d, count(DISTINCT t) AS shared_tags
            ORDER BY shared_tags DESC
            LIMIT ${{limit}}
            RETURN d
        """
        
        params = {
            "tags": discovery.tags,
            "exclude_id": discovery.id,
            "limit": limit,
        }
        
        results = await db.graph_query(cypher, params)
        
        similar = []
        for result in results:
            node_data = self._parse_agtype_node(result.get("d"))
            disc = self._node_to_discovery(node_data)
            if disc:
                similar.append(disc)
        
        return similar

    async def find_similar_by_tags(
        self,
        tags: List[str],
        exclude_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[DiscoveryNode]:
        """
        Find discoveries with overlapping tags.
        
        Args:
            tags: List of tags to match
            exclude_id: Discovery ID to exclude from results
            limit: Maximum number of results
            
        Returns:
            List of similar DiscoveryNodes
        """
        if not tags:
            return []
        
        db = await self._get_db()
        
        exclude_clause = " AND d.id <> ${exclude_id}" if exclude_id else ""
        
        cypher = f"""
            MATCH (d:Discovery)-[:TAGGED]->(t:Tag)
            WHERE t.name IN ${{tags}}{exclude_clause}
            WITH d, count(DISTINCT t) AS shared_tags
            ORDER BY shared_tags DESC
            LIMIT ${{limit}}
            RETURN d
        """
        
        params = {
            "tags": tags,
            "limit": limit,
        }
        if exclude_id:
            params["exclude_id"] = exclude_id
        
        results = await db.graph_query(cypher, params)
        
        similar = []
        for result in results:
            node_data = self._parse_agtype_node(result.get("d"))
            disc = self._node_to_discovery(node_data)
            if disc:
                similar.append(disc)
        
        return similar

