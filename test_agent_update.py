#!/usr/bin/env python3
"""Test agent update and explore governance system"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.governance_monitor import UNITARESMonitor
import numpy as np

# Agent details
AGENT_ID = "cirwel_cli_20251128"
API_KEY = "QjcLagsR2SAP8Zb5tOKoxq7ndnJ34Jc6tOvLqJsHnqk"

def test_update():
    """Process a test update"""
    print("=" * 60)
    print(f"Testing governance update for: {AGENT_ID}")
    print("=" * 60)
    print()

    # Create monitor
    monitor = UNITARESMonitor(AGENT_ID)

    # Simulate an update
    response_text = """
    I'm exploring the governance MCP system to understand:
    - How the UNITARES thermodynamic framework works
    - Multi-model support and calibration
    - Per-agent subjective vs universal objective thresholds
    - Potential bugs, bottlenecks, and security issues
    """

    complexity = 0.6  # Medium complexity task

    # Create agent state (required format)
    agent_state = {
        'parameters': [0.7, 0.9, 300],  # temperature, top_p, max_tokens
        'ethical_drift': np.array([0.0, 0.0, 0.0]),  # E, I, S drift
        'response_text': response_text,
        'complexity': complexity
    }

    # Process update
    result = monitor.process_update(
        agent_state=agent_state,
        confidence=1.0
    )

    # Display results
    print("Update Results:")
    print("-" * 60)
    print(f"Decision: {result.get('decision', 'unknown')}")
    print(f"Risk Score: {result.get('risk_score', 0):.3f}")

    metrics = result.get('metrics', {})
    print(f"\nState Variables (EISV):")
    print(f"  E (Energy): {metrics.get('E', 0):.4f}")
    print(f"  I (Information): {metrics.get('I', 0):.4f}")
    print(f"  S (Entropy): {metrics.get('S', 0):.4f}")
    print(f"  V (Void): {metrics.get('V', 0):.4f}")
    print(f"  Coherence: {metrics.get('coherence', 0):.4f}")

    print(f"\nAdaptive Parameters:")
    print(f"  λ₁ (Lambda1): {metrics.get('lambda1', 0):.4f}")

    sampling = result.get('suggested_sampling_params', {})
    print(f"\nSuggested Sampling:")
    print(f"  Temperature: {sampling.get('temperature', 0):.2f}")
    print(f"  Top-p: {sampling.get('top_p', 0):.2f}")
    print(f"  Max tokens: {sampling.get('max_tokens', 0)}")

    print()
    print("=" * 60)

    return result

if __name__ == "__main__":
    test_update()
