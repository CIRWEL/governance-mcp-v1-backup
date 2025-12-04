#!/usr/bin/env python3
"""
Migration tool: Convert file-based knowledge layer to knowledge graph

Reads all existing *_knowledge.json files and converts them to graph format.
Preserves all data, relationships, and metadata.

Usage:
    python3 scripts/migrate_to_knowledge_graph.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import asyncio

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.knowledge_graph import KnowledgeGraph, DiscoveryNode


async def migrate_discovery(old_discovery: dict, agent_id: str) -> DiscoveryNode:
    """Convert old Discovery format to DiscoveryNode"""
    return DiscoveryNode(
        id=old_discovery.get("timestamp", datetime.now().isoformat()),
        agent_id=agent_id,
        type=old_discovery.get("type", "insight"),
        summary=old_discovery.get("summary", ""),
        details=old_discovery.get("details", ""),
        tags=old_discovery.get("tags", []),
        severity=old_discovery.get("severity"),
        timestamp=old_discovery.get("timestamp", datetime.now().isoformat()),
        status=old_discovery.get("status", "open"),
        related_to=old_discovery.get("related_discoveries", []),
        references_files=old_discovery.get("related_files", []),
        resolved_at=old_discovery.get("resolved_at"),
        updated_at=old_discovery.get("updated_at")
    )


async def migrate_file(knowledge_file: Path, graph: KnowledgeGraph) -> int:
    """Migrate a single knowledge file to graph"""
    try:
        with open(knowledge_file, 'r') as f:
            data = json.load(f)
        
        agent_id = data.get("agent_id")
        if not agent_id:
            print(f"  ⚠️  Skipping {knowledge_file.name}: no agent_id", file=sys.stderr)
            return 0
        
        discoveries = data.get("discoveries", [])
        migrated_count = 0
        
        for discovery_data in discoveries:
            try:
                discovery = await migrate_discovery(discovery_data, agent_id)
                await graph.add_discovery(discovery)
                migrated_count += 1
            except Exception as e:
                print(f"  ⚠️  Error migrating discovery: {e}", file=sys.stderr)
                continue
        
        return migrated_count
        
    except Exception as e:
        print(f"  ❌ Error reading {knowledge_file.name}: {e}", file=sys.stderr)
        return 0


async def main():
    """Main migration function"""
    print("🔄 Migrating file-based knowledge layer to knowledge graph...")
    print()
    
    # Find all knowledge files
    knowledge_dir = project_root / "data" / "knowledge"
    if not knowledge_dir.exists():
        print(f"❌ Knowledge directory not found: {knowledge_dir}")
        return
    
    knowledge_files = list(knowledge_dir.glob("*_knowledge.json"))
    
    if not knowledge_files:
        print("ℹ️  No knowledge files found to migrate")
        return
    
    print(f"📁 Found {len(knowledge_files)} knowledge files")
    print()
    
    # Initialize graph
    graph = KnowledgeGraph()
    
    # Migrate each file
    total_migrated = 0
    for knowledge_file in knowledge_files:
        print(f"📄 Migrating {knowledge_file.name}...", end=" ")
        count = await migrate_file(knowledge_file, graph)
        total_migrated += count
        print(f"✅ {count} discoveries")
    
    # Save graph
    print()
    print("💾 Saving knowledge graph...", end=" ")
    await graph._save_to_disk()
    print("✅")
    
    # Print statistics
    stats = await graph.get_stats()
    print()
    print("📊 Migration Statistics:")
    print(f"  Total discoveries: {stats['total_discoveries']}")
    print(f"  Total agents: {stats['total_agents']}")
    print(f"  Total tags: {stats['total_tags']}")
    print()
    print("✅ Migration complete!")
    print()
    print(f"Graph saved to: {graph.persist_file}")
    print()
    print("Next steps:")
    print("  1. Test graph queries: python3 -c 'from src.knowledge_graph import get_knowledge_graph; import asyncio; graph = asyncio.run(get_knowledge_graph()); print(asyncio.run(graph.get_stats()))'")
    print("  2. Update MCP handlers to use graph instead of files")
    print("  3. Archive old knowledge files (optional)")


if __name__ == "__main__":
    asyncio.run(main())

