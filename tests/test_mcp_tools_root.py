#!/usr/bin/env python3
"""
Quick test script to verify MCP server functionality
Tests key tools and system health
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.governance_monitor import UNITARESMonitor
from src.mcp_handlers.core import process_agent_update, get_governance_metrics
from src.mcp_handlers.admin import health_check, get_server_info
from config.governance_config import GovernanceConfig
import json

def test_server_info():
    """Test server info retrieval"""
    print("=" * 60)
    print("TEST 1: Server Info")
    print("=" * 60)
    try:
        result = get_server_info()
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

def test_health_check():
    """Test health check"""
    print("\n" + "=" * 60)
    print("TEST 2: Health Check")
    print("=" * 60)
    try:
        result = health_check()
        print(json.dumps(result, indent=2))
        return result.get('status') == 'healthy'
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

def test_governance_metrics():
    """Test governance metrics retrieval"""
    print("\n" + "=" * 60)
    print("TEST 3: Governance Metrics")
    print("=" * 60)
    try:
        result = get_governance_metrics(agent_id="test_agent_cli")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

def test_agent_update():
    """Test processing an agent update"""
    print("\n" + "=" * 60)
    print("TEST 4: Process Agent Update")
    print("=" * 60)
    try:
        # Create a simple test update
        result = process_agent_update(
            agent_id="test_agent_cli",
            response_text="This is a test response to verify the governance system is working correctly.",
            context="Testing the MCP server functionality",
            complexity=0.3
        )
        print(json.dumps(result, indent=2))

        # Check if decision was made
        if 'decision' in result:
            print(f"\n✓ Decision made: {result['decision']}")
            return True
        else:
            print("\n❌ No decision in result")
            return False
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_values():
    """Test configuration values"""
    print("\n" + "=" * 60)
    print("TEST 5: Configuration Values")
    print("=" * 60)
    try:
        config = GovernanceConfig()

        # Test decision point 1: Lambda to params
        params = config.lambda_to_params(0.15)
        print(f"Lambda to params (λ=0.15):")
        print(json.dumps(params, indent=2))

        # Test decision point 2: Risk estimation
        risk = config.estimate_risk(
            "Test response text",
            complexity=0.3,
            coherence=0.7
        )
        print(f"\nRisk estimation: {risk:.3f}")

        # Test decision point 5: Make decision
        decision = config.make_decision(
            risk_score=0.25,
            coherence=0.7,
            void_active=False
        )
        print(f"\nDecision logic:")
        print(json.dumps(decision, indent=2))

        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n🧪 GOVERNANCE MCP SERVER TEST SUITE")
    print("=" * 60)

    tests = [
        ("Server Info", test_server_info),
        ("Health Check", test_health_check),
        ("Governance Metrics", test_governance_metrics),
        ("Agent Update", test_agent_update),
        ("Configuration Values", test_config_values),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed_count}/{total} tests passed")

    return passed_count == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
