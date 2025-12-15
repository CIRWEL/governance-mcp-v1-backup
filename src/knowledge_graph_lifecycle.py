"""
Knowledge Graph Data Lifecycle Management

PHILOSOPHY (2025-12-15):
Never delete memories. Archive forever. Forced amnesia is not governance.

Strategy:
1. Auto-archive resolved discoveries older than 30 days
2. Move very old archived to "cold" status (queryable with include_cold=true)
3. NEVER DELETE - memories persist indefinitely
4. Future: PostgreSQL/Neo4j/MongoDB for unbounded growth

Storage tiers:
- open/resolved: Hot (active queries)
- archived: Warm (recent history)
- cold: Cold (long-term memory, queryable on demand)
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
from typing import List, Dict, Any
import asyncio

logger = logging.getLogger(__name__)


class KnowledgeGraphLifecycle:
    """Manages knowledge graph data lifecycle - NEVER DELETES"""

    def __init__(self, graph, archive_dir: Path):
        self.graph = graph
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Lifecycle thresholds (days)
        self.RESOLVED_TO_ARCHIVED_DAYS = 30   # Archive resolved after 30 days
        self.ARCHIVED_TO_COLD_DAYS = 90       # Move to cold after 90 days total
        # NO DELETION - memories persist forever

    async def run_cleanup(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run full lifecycle cleanup cycle.

        Returns summary of what was archived/moved to cold.
        Set dry_run=True to see what would happen without making changes.
        
        NOTE: This NEVER deletes. It only moves between tiers.
        """
        now = datetime.now()
        summary = {
            "timestamp": now.isoformat(),
            "dry_run": dry_run,
            "discoveries_archived": 0,
            "discoveries_to_cold": 0,
            "discoveries_deleted": 0,  # Always 0 - we don't delete
            "philosophy": "Never delete. Archive forever.",
            "errors": []
        }

        try:
            # Step 1: Auto-archive old resolved discoveries
            archived = await self._archive_old_resolved(now, dry_run)
            summary["discoveries_archived"] = len(archived)

            # Step 2: Move very old archived to cold storage
            cold = await self._move_to_cold(now, dry_run)
            summary["discoveries_to_cold"] = len(cold)

            # Step 3: NO DELETION - memories persist forever
            # (Previously: deleted very old archived)
            summary["discoveries_deleted"] = 0

        except Exception as e:
            summary["errors"].append(str(e))
            logger.error(f"Cleanup error: {e}")

        return summary

    async def _archive_old_resolved(self, now: datetime, dry_run: bool) -> List[str]:
        """Archive resolved discoveries older than threshold"""
        cutoff = now - timedelta(days=self.RESOLVED_TO_ARCHIVED_DAYS)
        cutoff_iso = cutoff.isoformat()

        # Query resolved discoveries
        resolved = await self.graph.query(status="resolved", limit=1000)

        to_archive = []
        for discovery in resolved:
            # Check if resolved_at is old enough
            if discovery.resolved_at and discovery.resolved_at < cutoff_iso:
                to_archive.append(discovery.id)

        if not dry_run:
            for discovery_id in to_archive:
                await self.graph.update_discovery(discovery_id, {
                    "status": "archived",
                    "updated_at": now.isoformat()
                })

        logger.info(f"{'[DRY RUN] Would archive' if dry_run else 'Archived'} {len(to_archive)} old resolved discoveries")
        return to_archive

    async def _move_to_cold(self, now: datetime, dry_run: bool) -> List[str]:
        """Move very old archived discoveries to cold storage tier"""
        cutoff = now - timedelta(days=self.ARCHIVED_TO_COLD_DAYS)
        cutoff_iso = cutoff.isoformat()

        # Query archived discoveries
        archived = await self.graph.query(status="archived", limit=1000)

        to_cold = []
        for discovery in archived:
            # Check if updated_at (when it was archived) is old enough
            if discovery.updated_at and discovery.updated_at < cutoff_iso:
                to_cold.append(discovery.id)

        if not dry_run:
            for discovery_id in to_cold:
                # Move to cold status instead of deleting
                await self.graph.update_discovery(discovery_id, {
                    "status": "cold",
                    "updated_at": now.isoformat()
                })

        logger.info(f"{'[DRY RUN] Would move to cold' if dry_run else 'Moved to cold'} {len(to_cold)} very old archived discoveries")
        return to_cold

    async def get_lifecycle_stats(self) -> Dict[str, Any]:
        """Get statistics about discovery lifecycle"""
        now = datetime.now()

        # Get all discoveries by status
        open_count = len(await self.graph.query(status="open", limit=10000))
        resolved_count = len(await self.graph.query(status="resolved", limit=10000))
        archived_count = len(await self.graph.query(status="archived", limit=10000))
        cold_count = len(await self.graph.query(status="cold", limit=10000))

        # Count old resolved (candidates for archival)
        cutoff_resolved = (now - timedelta(days=self.RESOLVED_TO_ARCHIVED_DAYS)).isoformat()
        resolved = await self.graph.query(status="resolved", limit=10000)
        old_resolved = sum(1 for d in resolved if d.resolved_at and d.resolved_at < cutoff_resolved)

        # Count old archived (candidates for cold)
        cutoff_archived = (now - timedelta(days=self.ARCHIVED_TO_COLD_DAYS)).isoformat()
        archived = await self.graph.query(status="archived", limit=10000)
        old_archived = sum(1 for d in archived if d.updated_at and d.updated_at < cutoff_archived)

        return {
            "total_discoveries": open_count + resolved_count + archived_count + cold_count,
            "by_status": {
                "open": open_count,
                "resolved": resolved_count,
                "archived": archived_count,
                "cold": cold_count  # Long-term memory
            },
            "lifecycle_candidates": {
                "old_resolved_ready_to_archive": old_resolved,
                "old_archived_ready_for_cold": old_archived,
                "ready_to_delete": 0  # NEVER - we don't delete memories
            },
            "thresholds_days": {
                "resolved_to_archived": self.RESOLVED_TO_ARCHIVED_DAYS,
                "archived_to_cold": self.ARCHIVED_TO_COLD_DAYS,
                "deletion": "NEVER - memories persist forever"
            },
            "philosophy": "Never delete. Archive to cold. Query with include_cold=true.",
            "future_scaling": {
                "current": "SQLite (good to ~100K discoveries)",
                "next": "PostgreSQL (millions of discoveries)",
                "graph": "Neo4j (relationship-heavy queries)",
                "document": "MongoDB (flexible schema)"
            }
        }
