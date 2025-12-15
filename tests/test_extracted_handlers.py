import pytest
"""
Test extracted handlers individually.

Tests the more complex handlers to ensure they work correctly.
"""

import sys
import asyncio
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.mark.asyncio
async def test_get_governance_metrics():
    """Test get_governance_metrics handler"""
    print("\nTesting get_governance_metrics...")
    
    from src.mcp_handlers import dispatch_tool
    
    # Test with non-existent agent (should error gracefully)
    result = await dispatch_tool("get_governance_metrics", {"agent_id": "test_nonexistent_agent"})
    assert result is not None, "Should return error response"
    
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == False, "Should fail for non-existent agent"
    print("✅ Handles non-existent agent correctly")
    
    # Test with missing agent_id (should error)
    result = await dispatch_tool("get_governance_metrics", {})
    assert result is not None, "Should return error response"
    
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == False, "Should fail without agent_id"
    error_msg = response_data.get("error", "").lower()
    assert "agent_id" in error_msg or "required" in error_msg, f"Should mention agent_id or required (got: {error_msg})"
    print("✅ Validates required arguments")
    
    print("✅ get_governance_metrics handler tests passed")


@pytest.mark.asyncio
async def test_simulate_update():
    """Test simulate_update handler
    
    Note: simulate_update requires a registered agent (security fix 2025-12).
    We first register via process_agent_update, then test simulation.
    """
    print("\nTesting simulate_update...")
    
    from src.mcp_handlers import dispatch_tool
    
    # Test with missing agent_id
    result = await dispatch_tool("simulate_update", {})
    assert result is not None, "Should return error response"
    
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == False, "Should fail without agent_id"
    print("✅ Validates required arguments")
    
    # First register the agent (required after security fix)
    agent_id = "test_simulate_agent_registered"
    result = await dispatch_tool("process_agent_update", {
        "agent_id": agent_id,
        "complexity": 0.3,
        "confidence": 0.8
    })
    response_data = json.loads(result[0].text)
    api_key = response_data.get("api_key")
    assert api_key is not None, "Should get API key on registration"
    print("✅ Agent registered")
    
    # Now test simulation with registered agent
    result = await dispatch_tool("simulate_update", {
        "agent_id": agent_id,
        "parameters": [0.7, 0.8, 0.15, 0.0],
        "ethical_drift": [0.0, 0.0, 0.0],
        "complexity": 0.3,
        "confidence": 0.9
    })
    
    assert result is not None, "Should return result"
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == True, "Should succeed with registered agent"
    assert response_data.get("simulation") == True, "Should mark as simulation"
    assert "metrics" in response_data, "Should have metrics"
    print("✅ Simulates update correctly")
    
    # Test that unregistered agent fails
    result = await dispatch_tool("simulate_update", {
        "agent_id": "unregistered_agent_xyz123",
        "complexity": 0.3
    })
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == False, "Should fail for unregistered agent"
    print("✅ Rejects unregistered agents")
    
    print("✅ simulate_update handler tests passed")


@pytest.mark.asyncio
async def test_set_thresholds():
    """Test set_thresholds handler
    
    Note: set_thresholds requires admin privileges (security fix 2025-12).
    Admin status requires 'admin' tag or 100+ updates.
    For testing, we verify the auth rejection and get_thresholds (read-only).
    """
    print("\nTesting set_thresholds...")
    
    from src.mcp_handlers import dispatch_tool
    
    # Test that unauthenticated request fails
    result = await dispatch_tool("set_thresholds", {
        "thresholds": {"risk_approve_threshold": 0.32},
        "validate": True
    })
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == False, "Should fail without auth"
    print("✅ Rejects unauthenticated requests")
    
    # Test that non-admin agent fails
    agent_id = "test_threshold_nonadmin"
    result = await dispatch_tool("process_agent_update", {
        "agent_id": agent_id,
        "complexity": 0.3
    })
    response_data = json.loads(result[0].text)
    api_key = response_data.get("api_key")
    
    result = await dispatch_tool("set_thresholds", {
        "agent_id": agent_id,
        "api_key": api_key,
        "thresholds": {"risk_approve_threshold": 0.32},
        "validate": True
    })
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == False, "Should fail for non-admin agent"
    assert "admin" in response_data.get("error", "").lower(), "Should mention admin requirement"
    print("✅ Rejects non-admin agents")
    
    # Verify get_thresholds works (read-only, no auth needed)
    result = await dispatch_tool("get_thresholds", {})
    response_data = json.loads(result[0].text)
    assert response_data.get("success") == True, "Should succeed for read-only"
    assert "thresholds" in response_data, "Should have thresholds"
    print("✅ get_thresholds works (read-only)")
    
    print("✅ set_thresholds handler tests passed")


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in handlers"""
    print("\nTesting error handling...")
    
    from src.mcp_handlers import dispatch_tool
    
    # Test with invalid arguments
    result = await dispatch_tool("set_thresholds", {
        "thresholds": {"invalid_threshold": 999},
        "validate": True
    })
    
    assert result is not None, "Should return result"
    response_data = json.loads(result[0].text)
    # Should either succeed (if invalid threshold ignored) or fail gracefully
    assert "success" in response_data, "Should have success field"
    print("✅ Handles invalid arguments gracefully")
    
    print("✅ Error handling tests passed")


async def main():
    """Run all handler tests"""
    try:
        await test_get_governance_metrics()
        await test_simulate_update()
        await test_set_thresholds()
        await test_error_handling()
        print("\n🎉 All handler tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

