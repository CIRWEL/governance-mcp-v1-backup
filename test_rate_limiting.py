#!/usr/bin/env python3
"""
Test Knowledge Graph Rate Limiting

Tests the 10 stores/hour per agent rate limit to prevent poisoning flood attacks.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge_graph import KnowledgeGraph, DiscoveryNode


async def test_rate_limiting():
    """Test that rate limiting prevents flood attacks"""

    print("\n" + "="*60)
    print("KNOWLEDGE GRAPH RATE LIMITING TESTS")
    print("="*60)

    # Create temp graph (don't persist to avoid conflicts)
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    graph = KnowledgeGraph(persist_file=Path(temp_file.name))

    test_agent = "test_flood_agent"
    results = {
        "passed": 0,
        "failed": 0
    }

    # Test 1: Allow up to 10 stores
    print("\n" + "-"*60)
    print("Test 1: Allow 10 stores within limit")
    print("-"*60)

    try:
        for i in range(10):
            discovery = DiscoveryNode(
                id=f"test_discovery_{i}",
                agent_id=test_agent,
                type="test",
                summary=f"Test discovery {i}",
                details="Testing rate limiting"
            )
            await graph.add_discovery(discovery)

        print(f"✅ PASS: Successfully stored 10 discoveries")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ FAIL: Should allow 10 stores, got error: {e}")
        results["failed"] += 1

    # Test 2: Block 11th store
    print("\n" + "-"*60)
    print("Test 2: Block 11th store (exceeds limit)")
    print("-"*60)

    try:
        discovery = DiscoveryNode(
            id="test_discovery_11",
            agent_id=test_agent,
            type="test",
            summary="Test discovery 11 (should fail)",
            details="This should be blocked"
        )
        await graph.add_discovery(discovery)

        print(f"❌ FAIL: Should have blocked 11th store")
        results["failed"] += 1
    except ValueError as e:
        if "Rate limit exceeded" in str(e):
            print(f"✅ PASS: Correctly blocked 11th store")
            print(f"   Error message: {str(e)[:100]}...")
            results["passed"] += 1
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            results["failed"] += 1
    except Exception as e:
        print(f"❌ FAIL: Unexpected error: {e}")
        results["failed"] += 1

    # Test 3: Different agent can still store
    print("\n" + "-"*60)
    print("Test 3: Different agent unaffected by rate limit")
    print("-"*60)

    try:
        discovery = DiscoveryNode(
            id="test_discovery_different_agent",
            agent_id="different_test_agent",
            type="test",
            summary="Different agent test",
            details="Should work fine"
        )
        await graph.add_discovery(discovery)

        print(f"✅ PASS: Different agent can store (rate limits are per-agent)")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ FAIL: Different agent should not be affected: {e}")
        results["failed"] += 1

    # Test 4: Old stores don't count (simulate 1 hour passing)
    print("\n" + "-"*60)
    print("Test 4: Old stores expire after 1 hour")
    print("-"*60)

    # Manually manipulate timestamps to simulate 1 hour passing
    old_time = (datetime.now() - timedelta(hours=1, minutes=5)).isoformat()

    # Replace all timestamps with old timestamp
    if test_agent in graph.agent_store_timestamps:
        graph.agent_store_timestamps[test_agent] = [old_time] * 10

    try:
        discovery = DiscoveryNode(
            id="test_discovery_after_expiry",
            agent_id=test_agent,
            type="test",
            summary="Test after expiry",
            details="Should work because old stores expired"
        )
        await graph.add_discovery(discovery)

        print(f"✅ PASS: Old stores expired, new store allowed")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ FAIL: Should allow store after expiry: {e}")
        results["failed"] += 1

    # Test 5: Verify error message contains helpful info
    print("\n" + "-"*60)
    print("Test 5: Error message contains helpful information")
    print("-"*60)

    # Add 9 more stores (we already have 1 from Test 4, so 9+1=10 total)
    for i in range(9):
        discovery = DiscoveryNode(
            id=f"test_discovery_batch2_{i}",
            agent_id=test_agent,
            type="test",
            summary=f"Batch 2 discovery {i}"
        )
        await graph.add_discovery(discovery)

    # Now try to add the 11th store (should fail)
    try:
        discovery = DiscoveryNode(
            id="test_discovery_error_message",
            agent_id=test_agent,
            type="test",
            summary="Test error message"
        )
        await graph.add_discovery(discovery)

        print(f"❌ FAIL: Should have blocked")
        results["failed"] += 1
    except ValueError as e:
        error_msg = str(e)
        required_info = [
            "Rate limit exceeded",
            test_agent,
            "10",  # Limit
            "hour",
            "poisoning"  # Mentions why
        ]

        missing = [info for info in required_info if info not in error_msg]

        if not missing:
            print(f"✅ PASS: Error message contains all required information")
            print(f"   Message: {error_msg[:150]}...")
            results["passed"] += 1
        else:
            print(f"❌ FAIL: Error message missing: {missing}")
            print(f"   Message: {error_msg}")
            results["failed"] += 1

    # Test 6: Rate limiting is persistent (state is maintained)
    print("\n" + "-"*60)
    print("Test 6: Rate limit state persists across calls")
    print("-"*60)

    # The 10 stores from Test 5 should still block new stores
    try:
        discovery = DiscoveryNode(
            id="test_discovery_persistence",
            agent_id=test_agent,
            type="test",
            summary="Test persistence"
        )
        await graph.add_discovery(discovery)

        print(f"❌ FAIL: Should still be rate limited")
        results["failed"] += 1
    except ValueError as e:
        if "Rate limit exceeded" in str(e):
            print(f"✅ PASS: Rate limit state persisted")
            results["passed"] += 1
        else:
            print(f"❌ FAIL: Wrong error: {e}")
            results["failed"] += 1

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Passed: {results['passed']}/6")
    print(f"Failed: {results['failed']}/6")

    if results["failed"] == 0:
        print("\n✅ ALL TESTS PASSED")
        print("\nRate limiting implementation is working correctly:")
        print("  • Allows up to 10 stores/hour per agent")
        print("  • Blocks additional stores with clear error message")
        print("  • Rate limits are per-agent (don't affect others)")
        print("  • Old stores expire after 1 hour")
        print("  • State persists across calls")
        print("  • Error messages are informative")
        return 0
    else:
        print(f"\n❌ {results['failed']} TEST(S) FAILED")
        return 1

    # Cleanup
    try:
        import os
        os.unlink(temp_file.name)
    except:
        pass


if __name__ == "__main__":
    exit_code = asyncio.run(test_rate_limiting())
    sys.exit(exit_code)
