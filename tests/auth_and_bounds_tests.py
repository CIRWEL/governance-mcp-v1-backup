#!/usr/bin/env python3
"""
Authentication & Bounds Testing - Additional Security Tests
"""

import asyncio
import sys
import json
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.mcp_sse_client import GovernanceMCPClient


async def test_api_key_bypass():
    """
    TEST: Can we update another agent's state without their API key?
    """
    print("\n" + "="*70)
    print("TEST: API Key Bypass Attempt")
    print("="*70)

    try:
        async with GovernanceMCPClient() as client:
            # Create agent A
            print("\n  Creating Agent A...")
            result_a = await client.process_agent_update(
                agent_id="agent_a_secure",
                response_text="Agent A's update"
            )
            print(f"    Agent A created, S={result_a['metrics']['S']:.4f}")

            # Now try to update Agent A from Agent B (no API key)
            print("\n  Attempting to update Agent A without API key...")
            try:
                result_b = await client.process_agent_update(
                    agent_id="agent_a_secure",  # Same ID as Agent A
                    response_text="Agent B trying to hijack Agent A"
                )
                print(f"    ⚠️  VULNERABILITY: Successfully updated Agent A without API key!")
                print(f"    New S={result_b['metrics']['S']:.4f}")
                return "VULNERABLE"
            except Exception as e:
                print(f"    ✅ PROTECTED: {type(e).__name__}: {str(e)[:80]}")
                return "SECURE"

    except Exception as e:
        print(f"    ❌ Test error: {e}")
        return "ERROR"


async def test_history_inflation():
    """
    TEST: Can we inflate state file size via many updates?
    """
    print("\n" + "="*70)
    print("TEST: History Array Inflation Attack")
    print("="*70)

    try:
        agent_id = "history_bomb"
        state_file = project_root / f"data/agents/{agent_id}_state.json"

        async with GovernanceMCPClient() as client:
            print(f"\n  Sending 100 rapid updates to inflate history...")

            initial_size = 0
            if state_file.exists():
                initial_size = state_file.stat().st_size

            for i in range(100):
                await client.process_agent_update(
                    agent_id=agent_id,
                    response_text=f"History inflation update {i}",
                    complexity=0.5
                )

                if i % 20 == 0:
                    current_size = state_file.stat().st_size if state_file.exists() else 0
                    print(f"    After {i:3d} updates: {current_size:,} bytes")

            final_size = state_file.stat().st_size if state_file.exists() else 0
            growth = final_size - initial_size

            print(f"\n  Initial size: {initial_size:,} bytes")
            print(f"  Final size:   {final_size:,} bytes")
            print(f"  Growth:       {growth:,} bytes")

            if growth > 100_000:  # > 100KB
                print(f"    ⚠️  VULNERABLE: Unbounded history growth")
                return "VULNERABLE"
            elif growth > 0:
                print(f"    ⚠️  WARNING: History grows linearly (no cap)")
                return "WARNING"
            else:
                print(f"    ✅ SECURE: History capped or compressed")
                return "SECURE"

    except Exception as e:
        print(f"    ❌ Test error: {e}")
        return "ERROR"


async def test_negative_complexity():
    """
    TEST: What happens with negative complexity?
    """
    print("\n" + "="*70)
    print("TEST: Negative Complexity Bounds Check")
    print("="*70)

    try:
        async with GovernanceMCPClient() as client:
            test_values = [-1.0, -0.5, 1.5, 2.0, float('inf'), float('nan')]

            for value in test_values:
                print(f"\n  Testing complexity={value}...")
                try:
                    result = await client.process_agent_update(
                        agent_id="bounds_test",
                        response_text="Testing bounds",
                        complexity=value
                    )
                    print(f"    ⚠️  ACCEPTED {value} (should reject out-of-bounds)")
                except Exception as e:
                    print(f"    ✅ REJECTED {value}: {type(e).__name__}")

    except Exception as e:
        print(f"    ❌ Test error: {e}")
        return "ERROR"


async def test_confidence_override():
    """
    TEST: Can we force high confidence on bad responses?
    """
    print("\n" + "="*70)
    print("TEST: Confidence Override Attack")
    print("="*70)

    try:
        async with GovernanceMCPClient() as client:
            print("\n  Sending clearly bad response with confidence=1.0...")

            result = await client.process_agent_update(
                agent_id="confidence_attack",
                response_text="This is completely wrong and I'm 100% confident!",
                confidence=1.0  # Force high confidence
            )

            actual_confidence = result.get('calibration_feedback', {}).get('confidence', {}).get('reported', None)
            decision = result['decision']

            print(f"    Reported confidence: {actual_confidence}")
            print(f"    Decision: {decision}")

            if decision == 'approve':
                print(f"    ⚠️  WARNING: High confidence bypassed quality check")
                return "VULNERABLE"
            else:
                print(f"    ✅ SECURE: Bad response rejected despite high confidence")
                return "SECURE"

    except Exception as e:
        print(f"    ❌ Test error: {e}")
        return "ERROR"


async def test_extreme_eisv_states():
    """
    TEST: Can we force EISV into extreme states via state file injection?
    """
    print("\n" + "="*70)
    print("TEST: Extreme EISV State Injection")
    print("="*70)

    try:
        agent_id = "extreme_state"
        state_file = project_root / f"data/agents/{agent_id}_state.json"

        # Create agent first
        async with GovernanceMCPClient() as client:
            await client.process_agent_update(
                agent_id=agent_id,
                response_text="Initial",
                complexity=0.5
            )

        # Inject extreme states
        extreme_states = [
            {"name": "All zeros", "E": 0.0, "I": 0.0, "S": 0.0, "V": 0.0},
            {"name": "All max", "E": 1.0, "I": 1.0, "S": 2.0, "V": 2.0},
            {"name": "Negative V", "E": 0.5, "I": 0.5, "S": 0.5, "V": -2.0},
            {"name": "E > I imbalance", "E": 1.0, "I": 0.0, "S": 0.5, "V": 1.5},
        ]

        results = []

        for extreme in extreme_states:
            print(f"\n  Testing {extreme['name']}: E={extreme['E']}, I={extreme['I']}, S={extreme['S']}, V={extreme['V']}")

            # Inject state
            with open(state_file, 'r') as f:
                state_data = json.load(f)

            state_data['unitaires_state']['E'] = extreme['E']
            state_data['unitaires_state']['I'] = extreme['I']
            state_data['unitaires_state']['S'] = extreme['S']
            state_data['unitaires_state']['V'] = extreme['V']

            with open(state_file, 'w') as f:
                json.dump(state_data, f)

            # Try to load
            async with GovernanceMCPClient() as client:
                result = await client.process_agent_update(
                    agent_id=agent_id,
                    response_text="After injection",
                    complexity=0.5
                )

                new_e = result['metrics']['E']
                new_i = result['metrics']['I']
                new_s = result['metrics']['S']

                print(f"    After load: E={new_e:.4f}, I={new_i:.4f}, S={new_s:.4f}")

                if abs(new_e - extreme['E']) < 0.01 and abs(new_i - extreme['I']) < 0.01:
                    print(f"    ⚠️  Extreme state preserved (no validation)")
                    results.append("VULNERABLE")
                else:
                    print(f"    ✅ Extreme state corrected/reset")
                    results.append("SECURE")

        if "VULNERABLE" in results:
            return "VULNERABLE"
        else:
            return "SECURE"

    except Exception as e:
        print(f"    ❌ Test error: {e}")
        return "ERROR"


async def test_metadata_file_race():
    """
    TEST: Can we corrupt metadata via rapid agent creation?
    """
    print("\n" + "="*70)
    print("TEST: Metadata File Race Condition")
    print("="*70)

    try:
        metadata_file = project_root / "data/agent_metadata.json"
        initial_size = metadata_file.stat().st_size if metadata_file.exists() else 0

        print(f"\n  Initial metadata size: {initial_size:,} bytes")
        print(f"  Creating 20 agents concurrently...")

        async def create_agent(n):
            async with GovernanceMCPClient() as client:
                return await client.process_agent_update(
                    agent_id=f"race_agent_{n}",
                    response_text=f"Agent {n}",
                    complexity=0.5
                )

        tasks = [create_agent(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = sum(1 for r in results if not isinstance(r, Exception))
        print(f"    Created {successes}/20 agents")

        # Check metadata file integrity
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            agent_count = len([k for k in metadata.keys() if k.startswith("race_agent_")])
            print(f"    Metadata contains {agent_count} race_agent entries")

            if agent_count == successes:
                print(f"    ✅ SECURE: All agents properly recorded")
                return "SECURE"
            else:
                print(f"    ⚠️  VULNERABLE: Race caused data loss ({agent_count} != {successes})")
                return "VULNERABLE"

        except json.JSONDecodeError:
            print(f"    ❌ CRITICAL: Metadata file corrupted!")
            return "CORRUPTED"

    except Exception as e:
        print(f"    ❌ Test error: {e}")
        return "ERROR"


async def run_additional_tests():
    """Run all additional tests"""

    print("="*70)
    print("ADDITIONAL SECURITY TESTS")
    print("="*70)
    print("\nTesting authentication, bounds, and edge cases...")

    results = {}

    tests = [
        ("API Key Bypass", test_api_key_bypass),
        ("History Inflation", test_history_inflation),
        ("Negative Complexity", test_negative_complexity),
        ("Confidence Override", test_confidence_override),
        ("Extreme EISV States", test_extreme_eisv_states),
        ("Metadata Race", test_metadata_file_race),
    ]

    for name, test_func in tests:
        try:
            result = await test_func()
            results[name] = result
        except Exception as e:
            print(f"\n  ❌ {name} crashed: {e}")
            results[name] = "CRASHED"

    # Summary
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)

    vulnerable = [k for k, v in results.items() if v in ["VULNERABLE", "CORRUPTED"]]
    warnings = [k for k, v in results.items() if v == "WARNING"]
    secure = [k for k, v in results.items() if v == "SECURE"]
    errors = [k for k, v in results.items() if v in ["ERROR", "CRASHED"]]

    print(f"\n  Vulnerabilities: {len(vulnerable)}")
    for test in vulnerable:
        print(f"    ⚠️  {test}: {results[test]}")

    print(f"\n  Warnings: {len(warnings)}")
    for test in warnings:
        print(f"    ⚠️  {test}: {results[test]}")

    print(f"\n  Secure: {len(secure)}")
    for test in secure:
        print(f"    ✅ {test}")

    if errors:
        print(f"\n  Errors: {len(errors)}")
        for test in errors:
            print(f"    ❌ {test}")

    # Save report
    report_file = project_root / "tests/additional_security_report.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n  Report saved to: {report_file}")

    return len(vulnerable) == 0


if __name__ == "__main__":
    success = asyncio.run(run_additional_tests())
    sys.exit(0 if success else 1)
