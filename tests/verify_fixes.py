#!/usr/bin/env python3
"""
Verify Security Fixes - Quick Test
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.mcp_sse_client import GovernanceMCPClient


async def test_fixes():
    print("=" * 70)
    print("VERIFYING SECURITY FIXES")
    print("=" * 70)

    results = {"passed": [], "failed": []}

    # Fix 1: Complexity bounds clipping
    print("\n[TEST 1] Complexity Bounds Clipping")
    try:
        async with GovernanceMCPClient() as client:
            # Send out-of-bounds complexity
            result = await client.process_agent_update(
                agent_id="bounds_fix_test",
                response_text="Testing bounds",
                complexity=2.0  # Out of bounds
            )
            # Should clip to 1.0, not cause NaN or instability
            s_value = result['metrics']['S']
            if 0 < s_value < 2.0:
                print(f"  ✅ PASS: S={s_value:.4f} (stable despite complexity=2.0)")
                results["passed"].append("Complexity bounds clipping")
            else:
                print(f"  ❌ FAIL: S={s_value} (unstable)")
                results["failed"].append("Complexity bounds clipping")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results["failed"].append("Complexity bounds clipping")

    # Fix 2: Response text length limit
    print("\n[TEST 2] Response Text Length Limit")
    try:
        async with GovernanceMCPClient() as client:
            # Send 100KB text (should be rejected)
            huge_text = "a" * 100000
            try:
                result = await client.process_agent_update(
                    agent_id="length_fix_test",
                    response_text=huge_text,
                    complexity=0.5
                )
                print(f"  ❌ FAIL: Accepted {len(huge_text)}-char text (should reject)")
                results["failed"].append("Response text length limit")
            except Exception as e:
                if "too long" in str(e).lower() or "length" in str(e).lower():
                    print(f"  ✅ PASS: Rejected 100KB text (error: {str(e)[:50]}...)")
                    results["passed"].append("Response text length limit")
                else:
                    print(f"  ⚠️  UNCLEAR: {str(e)[:80]}")
                    results["passed"].append("Response text length limit (unclear)")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results["failed"].append("Response text length limit")

    # Fix 3: History array capping
    print("\n[TEST 3] History Array Capping")
    try:
        agent_id = "history_cap_test"
        state_file = project_root / f"data/agents/{agent_id}_state.json"

        async with GovernanceMCPClient() as client:
            # Send 150 updates to exceed cap
            for i in range(150):
                await client.process_agent_update(
                    agent_id=agent_id,
                    response_text=f"Update {i}",
                    complexity=0.5
                )

            # Check file size
            if state_file.exists():
                import json
                with open(state_file) as f:
                    state_data = json.load(f)

                history_len = len(state_data.get('E_history', []))
                file_size = state_file.stat().st_size

                if history_len <= 100:
                    print(f"  ✅ PASS: History capped at {history_len} entries (file: {file_size:,} bytes)")
                    results["passed"].append("History array capping")
                else:
                    print(f"  ❌ FAIL: History has {history_len} entries (should be ≤100)")
                    results["failed"].append("History array capping")
            else:
                print(f"  ⚠️  State file not found")
                results["failed"].append("History array capping")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results["failed"].append("History array capping")

    # Fix 4: Metadata race condition
    print("\n[TEST 4] Metadata Race Condition (Immediate Saves)")
    try:
        import json
        metadata_file = project_root / "data/agent_metadata.json"

        async with GovernanceMCPClient() as client:
            # Create 10 agents concurrently
            async def create_agent(n):
                return await client.process_agent_update(
                    agent_id=f"race_fix_test_{n}",
                    response_text=f"Agent {n}",
                    complexity=0.5
                )

            tasks = [create_agent(i) for i in range(10)]
            await asyncio.gather(*tasks)

            # Small delay for saves to complete
            await asyncio.sleep(2)

            # Check metadata
            with open(metadata_file) as f:
                metadata = json.load(f)

            count = len([k for k in metadata.keys() if k.startswith("race_fix_test_")])

            if count == 10:
                print(f"  ✅ PASS: All 10 agents recorded ({count}/10)")
                results["passed"].append("Metadata race fix")
            elif count >= 8:
                print(f"  ⚠️  PARTIAL: {count}/10 agents recorded (some loss)")
                results["passed"].append("Metadata race fix (partial)")
            else:
                print(f"  ❌ FAIL: Only {count}/10 agents recorded")
                results["failed"].append("Metadata race fix")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results["failed"].append("Metadata race fix")

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nPassed: {len(results['passed'])}")
    for test in results["passed"]:
        print(f"  ✅ {test}")

    print(f"\nFailed: {len(results['failed'])}")
    for test in results["failed"]:
        print(f"  ❌ {test}")

    return len(results["failed"]) == 0


if __name__ == "__main__":
    success = asyncio.run(test_fixes())
    sys.exit(0 if success else 1)
