#!/usr/bin/env python3
"""
Test script to verify state inconsistency bug between 
process_agent_update and get_governance_metrics.

Run: python3 tests/test_state_inconsistency.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.governance_monitor import UNITARESMonitor
import numpy as np


def test_state_inconsistency():
    """Test that demonstrates the inconsistency bug."""
    
    # Create fresh monitor
    monitor = UNITARESMonitor(agent_id="test_inconsistency", load_state=False)
    
    # Run several updates to build up history
    for i in range(15):
        agent_state = {
            'parameters': np.array([]),
            'ethical_drift': np.array([0.01, 0.01, 0.01]),
            'response_text': 'Test update',
            'complexity': 0.3  # Low complexity
        }
        result = monitor.process_update(agent_state)
    
    # Get the values from process_update (latest)
    process_attention = result['metrics']['attention_score']
    process_status = result['status']
    
    # Get the values from get_metrics (smoothed)
    metrics = monitor.get_metrics()
    get_attention = metrics['attention_score']
    get_status = metrics['status']
    latest_attention = metrics.get('latest_attention_score')
    
    print("=== State Inconsistency Bug Verification ===\n")
    print(f"After 15 updates with complexity=0.3:\n")
    
    print("process_update() returns:")
    print(f"  attention_score: {process_attention:.4f}")
    print(f"  status: {process_status}")
    
    print("\nget_metrics() returns:")
    print(f"  attention_score: {get_attention:.4f} (smoothed)")
    print(f"  latest_attention_score: {latest_attention:.4f} (point value)")
    print(f"  status: {get_status}")
    
    print("\n--- Analysis ---")
    if abs(process_attention - get_attention) > 0.001:
        print(f"❌ BUG CONFIRMED: attention_score differs by {abs(process_attention - get_attention):.4f}")
        print(f"   process_update uses point value, get_metrics uses smoothed mean")
    else:
        print("✓ attention_score matches (may not reproduce with this history)")
    
    if process_status != get_status:
        print(f"❌ BUG CONFIRMED: status differs ({process_status} vs {get_status})")
    else:
        print("✓ status matches")
    
    if latest_attention is not None and abs(process_attention - latest_attention) < 0.001:
        print(f"✓ latest_attention_score matches process_update (partial fix exists)")
    
    print("\n--- Risk History ---")
    print(f"Last 10 risk values: {[round(r, 4) for r in monitor.state.risk_history[-10:]]}")
    print(f"Mean of last 10: {np.mean(monitor.state.risk_history[-10:]):.4f}")
    print(f"Latest value: {monitor.state.risk_history[-1]:.4f}")


if __name__ == "__main__":
    test_state_inconsistency()
