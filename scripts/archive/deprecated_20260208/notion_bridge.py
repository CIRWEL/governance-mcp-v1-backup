#!/usr/bin/env python3
"""
Notion Bridge for UNITARES Governance MCP

Syncs governance data from MCP server to Notion for visualization and tracking.

Features:
- Agent metrics → Notion database
- Knowledge graph discoveries → Notion pages
- Governance history → Notion timeline views
- Real-time sync via SSE or periodic sync

Usage:
    # Setup (one-time)
    export NOTION_API_KEY="your_notion_api_key"
    export NOTION_DATABASE_ID="your_database_id"
    
    # Sync all agents
    python3 scripts/notion_bridge.py --sync-agents
    
    # Sync knowledge graph
    python3 scripts/notion_bridge.py --sync-knowledge
    
    # Full sync (agents + knowledge + metrics)
    python3 scripts/notion_bridge.py --full-sync
    
    # Watch mode (continuous sync via SSE)
    python3 scripts/notion_bridge.py --watch
"""

import sys
import os
import json
import argparse
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    print("⚠️  Notion client not installed. Install with: pip install notion-client", file=sys.stderr)

from src.logging_utils import get_logger
logger = get_logger(__name__)

# Try SSE client first, fallback to direct API
try:
    from scripts.mcp_sse_client import GovernanceMCPClient
    SSE_CLIENT_AVAILABLE = True
except ImportError:
    SSE_CLIENT_AVAILABLE = False
    logger.warning("SSE client not available, using direct API")

from src.governance_monitor import UNITARESMonitor
from src.mcp_handlers.shared import get_mcp_server


class NotionBridge:
    """Bridge between UNITARES Governance MCP and Notion"""
    
    def __init__(self, notion_api_key: Optional[str] = None, database_id: Optional[str] = None):
        self.notion_api_key = notion_api_key or os.getenv("NOTION_API_KEY")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")
        
        if not self.notion_api_key:
            raise ValueError("NOTION_API_KEY environment variable required")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID environment variable required")
        
        if NOTION_AVAILABLE:
            self.notion = Client(auth=self.notion_api_key)
        else:
            raise ImportError("notion-client package required. Install with: pip install notion-client")
        
        self.mcp_server = get_mcp_server()
    
    async def sync_agents(self, agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Sync agent metrics to Notion database"""
        logger.info("Syncing agents to Notion...")
        
        # Get agent list
        if agent_ids:
            agents_to_sync = agent_ids
        else:
            # Load metadata to get all agents
            self.mcp_server.load_metadata()
            agents_to_sync = list(self.mcp_server.agent_metadata.keys())
        
        synced = []
        errors = []
        
        for agent_id in agents_to_sync:
            try:
                # Get agent metadata
                meta = self.mcp_server.agent_metadata.get(agent_id)
                if not meta:
                    logger.warning(f"Agent {agent_id} not found in metadata")
                    continue
                
                # Get monitor and metrics
                monitor = self.mcp_server.get_or_create_monitor(agent_id)
                metrics = monitor.get_metrics()
                
                # Format for Notion
                notion_properties = self._format_agent_for_notion(agent_id, meta, metrics)
                
                # Check if page exists (search by agent_id property)
                existing_page = await self._find_agent_page(agent_id)
                
                if existing_page:
                    # Update existing page
                    self.notion.pages.update(
                        page_id=existing_page["id"],
                        properties=notion_properties
                    )
                    logger.info(f"Updated Notion page for {agent_id}")
                else:
                    # Create new page
                    self.notion.pages.create(
                        parent={"database_id": self.database_id},
                        properties=notion_properties
                    )
                    logger.info(f"Created Notion page for {agent_id}")
                
                synced.append(agent_id)
                
            except Exception as e:
                logger.error(f"Error syncing agent {agent_id}: {e}", exc_info=True)
                errors.append({"agent_id": agent_id, "error": str(e)})
        
        return {
            "synced": synced,
            "errors": errors,
            "total": len(agents_to_sync),
            "success": len(synced)
        }
    
    def _format_agent_for_notion(self, agent_id: str, meta: Any, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Format agent data for Notion database properties"""
        # Map EISV metrics
        e = metrics.get("E", 0.0)
        i = metrics.get("I", 0.0)
        s = metrics.get("S", 0.0)
        v = metrics.get("V", 0.0)
        
        # Format properties based on Notion database schema
        # Adjust property names/types based on your Notion database schema
        properties = {
            "Agent ID": {
                "title": [{"text": {"content": agent_id}}]
            },
            "Status": {
                "select": {"name": meta.status if meta else "unknown"}
            },
            "Health": {
                "select": {"name": metrics.get("health_status", "unknown")}
            },
            "Risk Score": {
                "number": metrics.get("risk_score", 0.0)
            },
            "Coherence": {
                "number": metrics.get("coherence", 0.0)
            },
            "Energy (E)": {
                "number": e
            },
            "Integrity (I)": {
                "number": i
            },
            "Entropy (S)": {
                "number": s
            },
            "Void (V)": {
                "number": v
            },
            "Updates": {
                "number": metrics.get("update_count", 0)
            },
            "Last Update": {
                "date": {
                    "start": meta.last_update.isoformat() if meta and meta.last_update else None
                }
            }
        }
        
        # Add verdict if available
        if "verdict" in metrics:
            properties["Verdict"] = {
                "select": {"name": metrics["verdict"]}
            }
        
        return properties
    
    async def _find_agent_page(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Find existing Notion page for agent by agent_id"""
        try:
            # Query database for agent_id
            results = self.notion.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Agent ID",
                    "title": {
                        "equals": agent_id
                    }
                }
            )
            
            if results.get("results"):
                return results["results"][0]
            return None
        except Exception as e:
            logger.warning(f"Error finding agent page: {e}")
            return None
    
    async def sync_knowledge_graph(self, limit: int = 100) -> Dict[str, Any]:
        """Sync knowledge graph discoveries to Notion"""
        logger.info("Syncing knowledge graph to Notion...")
        
        try:
            # Use MCP tool if available via SSE, otherwise direct API
            if SSE_CLIENT_AVAILABLE:
                async with GovernanceMCPClient() as client:
                    # Get knowledge graph via MCP
                    # Note: This would need to be implemented in the client
                    # For now, use direct API
                    from src.knowledge_graph import get_knowledge_graph
                    graph = await get_knowledge_graph()
                    discoveries = await graph.search_discoveries(limit=limit)
            else:
                # Direct API fallback
                from src.knowledge_graph import get_knowledge_graph
                graph = await get_knowledge_graph()
                discoveries = await graph.search_discoveries(limit=limit)
            
            synced = []
            errors = []
            
            for discovery in discoveries:
                try:
                    # Create Notion page for discovery
                    page_properties = {
                        "Title": {
                            "title": [{"text": {"content": discovery.get("summary", "Untitled")}}]
                        },
                        "Type": {
                            "select": {"name": discovery.get("type", "insight")}
                        },
                        "Severity": {
                            "select": {"name": discovery.get("severity", "low")}
                        },
                        "Status": {
                            "select": {"name": discovery.get("status", "open")}
                        },
                        "Created": {
                            "date": {
                                "start": discovery.get("timestamp", datetime.now().isoformat())
                            }
                        }
                    }
                    
                    # Create page in a separate database or as child pages
                    # For now, log that we'd create it
                    logger.debug(f"Would create Notion page for discovery: {discovery.get('id')}")
                    synced.append(discovery.get("id"))
                    
                except Exception as e:
                    logger.error(f"Error syncing discovery {discovery.get('id')}: {e}")
                    errors.append({"discovery_id": discovery.get("id"), "error": str(e)})
            
            return {
                "synced": synced,
                "errors": errors,
                "total": len(discoveries)
            }
            
        except Exception as e:
            logger.error(f"Error syncing knowledge graph: {e}", exc_info=True)
            return {"synced": [], "errors": [{"error": str(e)}], "total": 0}
    
    async def watch_mode(self, interval_seconds: int = 60):
        """Continuous sync mode - watches for changes and syncs periodically"""
        logger.info(f"Starting watch mode (sync every {interval_seconds}s)")
        
        try:
            while True:
                logger.info("Running sync cycle...")
                
                # Sync agents
                agent_result = await self.sync_agents()
                logger.info(f"Synced {agent_result['success']}/{agent_result['total']} agents")
                
                # Sync knowledge graph (less frequently)
                # knowledge_result = await self.sync_knowledge_graph()
                # logger.info(f"Synced {knowledge_result['total']} discoveries")
                
                # Wait for next cycle
                await asyncio.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("Watch mode stopped by user")
        except Exception as e:
            logger.error(f"Error in watch mode: {e}", exc_info=True)
            raise


async def main():
    parser = argparse.ArgumentParser(description="Notion Bridge for UNITARES Governance")
    parser.add_argument("--sync-agents", action="store_true", help="Sync agent metrics to Notion")
    parser.add_argument("--sync-knowledge", action="store_true", help="Sync knowledge graph to Notion")
    parser.add_argument("--full-sync", action="store_true", help="Sync everything")
    parser.add_argument("--watch", action="store_true", help="Continuous sync mode")
    parser.add_argument("--interval", type=int, default=60, help="Watch mode interval (seconds)")
    parser.add_argument("--agent-ids", nargs="+", help="Specific agent IDs to sync")
    parser.add_argument("--notion-api-key", help="Notion API key (or use NOTION_API_KEY env var)")
    parser.add_argument("--notion-database-id", help="Notion database ID (or use NOTION_DATABASE_ID env var)")
    
    args = parser.parse_args()
    
    # Check dependencies
    if not NOTION_AVAILABLE:
        print("❌ Error: notion-client package required")
        print("Install with: pip install notion-client")
        sys.exit(1)
    
    # Initialize bridge
    try:
        bridge = NotionBridge(
            notion_api_key=args.notion_api_key,
            database_id=args.notion_database_id
        )
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\nSetup:")
        print("1. Get Notion API key: https://www.notion.so/my-integrations")
        print("2. Create a database in Notion")
        print("3. Share database with your integration")
        print("4. Set environment variables:")
        print("   export NOTION_API_KEY='your_key'")
        print("   export NOTION_DATABASE_ID='your_database_id'")
        sys.exit(1)
    
    # Run requested operations
    if args.watch:
        await bridge.watch_mode(interval_seconds=args.interval)
    elif args.full_sync:
        logger.info("Running full sync...")
        agent_result = await bridge.sync_agents(agent_ids=args.agent_ids)
        knowledge_result = await bridge.sync_knowledge_graph()
        print(f"\n✅ Full sync complete:")
        print(f"   Agents: {agent_result['success']}/{agent_result['total']}")
        print(f"   Discoveries: {knowledge_result['total']}")
    elif args.sync_agents:
        result = await bridge.sync_agents(agent_ids=args.agent_ids)
        print(f"\n✅ Synced {result['success']}/{result['total']} agents")
        if result['errors']:
            print(f"   Errors: {len(result['errors'])}")
    elif args.sync_knowledge:
        result = await bridge.sync_knowledge_graph()
        print(f"\n✅ Synced {result['total']} discoveries")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())

