#!/usr/bin/env python3
"""
Diagnostic test for complexity bug.

Tests if complexity actually affects dynamics in real MCP flow.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp_handlers import dispatch_tool
import json

async def test_complexity_effect():
    """Test if complexity affects S in actual MCP flow"""
    print("=" * 70)
    print("COMPLEXITY BUG DIAGNOSTIC")
    print("=" * 70)
    
    # Test 1: Low complexity agent
    agent_id_low = "test_complexity_low"
    print(f"\n1. Creating agent with complexity=0.1")
    
    result = await dispatch_tool("process_agent_update", {
        "agent_id": agent_id_low,
        "complexity": 0.1,
        "response_text": "Test"
    })
    
    if result:
        data = json.loads(result[0].text)
        if data.get('success'):
            api_key_low = data.get('api_key')
            s_initial_low = data.get('metrics', {}).get('S', 0)
            print(f"   Initial S: {s_initial_low:.6f}")
    
    # Do 20 updates with complexity=0.1
    for i in range(20):
        result = await dispatch_tool("process_agent_update", {
            "agent_id": agent_id_low,
            "api_key": api_key_low,
            "complexity": 0.1,
            "response_text": f"Update {i+1}"
        })
        if result:
            data = json.loads(result[0].text)
            if data.get('success'):
                s = data.get('metrics', {}).get('S', 0)
                if i == 0 or i == 9 or i == 19:
                    print(f"   Update {i+1}: S={s:.6f}")
    
    # Get final state
    result = await dispatch_tool("get_governance_metrics", {
        "agent_id": agent_id_low
    })
    if result:
        data = json.loads(result[0].text)
        if data.get('success'):
            s_final_low = data.get('S', 0)
            print(f"   Final S: {s_final_low:.6f}")
    
    # Test 2: High complexity agent
    agent_id_high = "test_complexity_high"
    print(f"\n2. Creating agent with complexity=0.9")
    
    result = await dispatch_tool("process_agent_update", {
        "agent_id": agent_id_high,
        "complexity": 0.9,
        "response_text": "Test"
    })
    
    if result:
        data = json.loads(result[0].text)
        if data.get('success'):
            api_key_high = data.get('api_key')
            s_initial_high = data.get('metrics', {}).get('S', 0)
            print(f"   Initial S: {s_initial_high:.6f}")
    
    # Do 20 updates with complexity=0.9
    for i in range(20):
        result = await dispatch_tool("process_agent_update", {
            "agent_id": agent_id_high,
            "api_key": api_key_high,
            "complexity": 0.9,
            "response_text": f"Update {i+1}"
        })
        if result:
            data = json.loads(result[0].text)
            if data.get('success'):
                s = data.get('metrics', {}).get('S', 0)
                if i == 0 or i == 9 or i == 19:
                    print(f"   Update {i+1}: S={s:.6f}")
    
    # Get final state
    result = await dispatch_tool("get_governance_metrics", {
        "agent_id": agent_id_high
    })
    if result:
        data = json.loads(result[0].text)
        if data.get('success'):
            s_final_high = data.get('S', 0)
            print(f"   Final S: {s_final_high:.6f}")
    
    print(f"\n3. Comparison:")
    print(f"   Low complexity:  {s_initial_low:.6f} → {s_final_low:.6f}")
    print(f"   High complexity: {s_initial_high:.6f} → {s_final_high:.6f}")
    print(f"   Final difference: {s_final_high - s_final_low:.6f}")
    
    if abs(s_final_high - s_final_low) < 0.01:
        print("\n   ❌ BUG CONFIRMED: Complexity has no effect!")
    else:
        print(f"\n   ✅ Complexity IS affecting S (difference: {s_final_high - s_final_low:.6f})")

if __name__ == "__main__":
    asyncio.run(test_complexity_effect())

