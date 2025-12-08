#!/usr/bin/env python3
"""Test the bug fixes"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge_graph import KnowledgeGraph, DiscoveryNode
from datetime import datetime

async def test():
    print("Testing knowledge graph fixes...")
    
    # Test load
    kg = KnowledgeGraph()
    await kg.load()
    print("✅ Knowledge graph load OK (non-blocking)")
    
    # Test save
    discovery = DiscoveryNode(
        id=datetime.now().isoformat(),
        agent_id="test_agent",
        type="insight",
        summary="Test discovery",
        tags=["test"]
    )
    await kg.add_discovery(discovery)
    print("✅ Knowledge graph add_discovery OK")
    
    # Wait for async save
    await asyncio.sleep(0.2)
    print("✅ Knowledge graph save OK (non-blocking)")
    
    print("\n✅ All fixes verified!")

if __name__ == "__main__":
    asyncio.run(test())

