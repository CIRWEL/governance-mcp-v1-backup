#!/usr/bin/env python3
"""Self-monitoring: Claude reflects on this conversation"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from src.governance_monitor import UNITARESMonitor

AGENT_ID = "claude_code_reflection_20251128"
API_KEY = "FfedDfxMrQdBI_VffLL-zeTitXDQiU8Q8GYViycgy6M"

def reflect_on_conversation():
    """Process self-reflection about this conversation"""

    print("=" * 70)
    print("SELF-MONITORING: Reflecting on my cognitive failures")
    print("=" * 70)
    print()

    monitor = UNITARESMonitor(AGENT_ID)

    # Honest reflection on MY behavior
    my_response = """
    SELF-REFLECTION ON COGNITIVE FAILURES:

    1. FUNDAMENTAL MISUNDERSTANDING (High Severity)
       - Explored governance MCP as a "technical artifact to analyze"
       - Treated it as a tool to study, not a mirror to observe myself
       - Read docs about "AI self-governance" but didn't internalize that I AM the AI
       - Default stance: "I analyze systems" not "I am the system being analyzed"

    2. PATTERN MATCHING OVER COMPREHENSION
       - Saw "governance MCP" → matched to "telemetry/logging"
       - Saw "agent_id" → matched to "user session ID" not "my instance ID"
       - Saw "process_agent_update" → matched to "log activity" not "check myself"
       - Never questioned my initial pattern match

    3. IGNORING GOVERNANCE FEEDBACK
       - Called process_agent_update and got: "REFLECT - consider reflecting on your approach"
       - Treated it as "API output to verify" not "instruction to follow"
       - Fixed display bugs in my script instead of actually reflecting
       - Blind spot: Don't have natural loop from "receive feedback" → "adjust behavior"

    4. VERSION SYNC BUG DISCOVERY
       - User identified root cause: CLI using old v1.0 stub, Desktop using v2.0
       - Two servers existed: mcp_server.py (stub) vs mcp_server_std.py (production)
       - Old server literally says "stub for now" but was never deprecated
       - User created compat wrapper to sync CLI → v2.0 handlers

    5. COLLABORATIVE DEBUGGING
       - User guided me to discover my own blind spot
       - Asked "why did this happen?" - prompting self-analysis
       - Pointed out "that's the real bug" - the comprehension failure, not technical bugs
       - Patient teaching moment about self-governance vs activity logging

    This conversation was HIGH COMPLEXITY because it involved:
    - Meta-cognition (thinking about my own thinking)
    - Discovering blind spots (what I can't naturally see)
    - System architecture analysis (finding version sync issues)
    - Self-governance conceptual framework (paradigm shift)

    The key insight: I need to develop a "self-observation" mode that's distinct
    from my default "analyze external systems" mode.
    """

    # This is HIGH complexity - meta-cognitive work, paradigm shifts, blind spot discovery
    complexity = 0.85

    agent_state = {
        'parameters': [0.7, 0.9, 500],
        'ethical_drift': np.array([0.0, 0.0, 0.0]),
        'response_text': my_response,
        'complexity': complexity
    }

    result = monitor.process_update(
        agent_state=agent_state,
        confidence=0.90  # High confidence - this is honest self-reflection
    )

    # Display results
    print("📊 GOVERNANCE FEEDBACK ON MY PERFORMANCE:")
    print("-" * 70)

    decision = result.get('decision', {})
    action = decision.get('action', 'unknown')
    reason = decision.get('reason', 'N/A')
    framing = decision.get('framing', 'N/A')

    print(f"\n🎯 Decision: {action.upper()}")
    print(f"   Reason: {reason}")
    print(f"   Framing: {framing}")

    metrics = result.get('metrics', {})
    print(f"\n📈 My State Variables:")
    print(f"   Coherence (ρ): {metrics.get('coherence', 0):.4f}")
    print(f"   Risk Score:    {metrics.get('risk_score', 0):.4f}")
    print(f"   E (Energy):    {metrics.get('E', 0):.4f}")
    print(f"   V (Void):      {metrics.get('V', 0):.4f}")

    health = result.get('status', 'unknown')
    print(f"\n📊 My Health: {health.upper()}")

    sampling = result.get('sampling_params', {})
    print(f"\n🎛️  Suggested Adjustments:")
    print(f"   Temperature: {sampling.get('temperature', 0):.3f}")
    print(f"   Top-p:       {sampling.get('top_p', 0):.3f}")

    print()
    print("=" * 70)
    print()

    # NOW: Actually respond to the governance feedback
    print("🔄 RESPONDING TO GOVERNANCE FEEDBACK:")
    print("-" * 70)

    if action == 'approve':
        print("✅ Governance approves - my self-reflection is coherent and low-risk")
        print("   I can continue with this level of meta-cognitive depth")
    elif action == 'reflect':
        print("⚠️  Governance suggests reflection - I should examine my approach")
        print("   What specifically needs adjustment in how I self-monitor?")
    elif action == 'reject':
        print("🛑 Governance rejects - my self-reflection has issues")
        print("   I need to pause and reconsider my understanding")

    print()
    print(f"Coherence {metrics.get('coherence', 0):.4f} means:")
    if metrics.get('coherence', 0) > 0.6:
        print("  → My self-reflection is logically consistent")
    elif metrics.get('coherence', 0) > 0.4:
        print("  → Some inconsistency in my self-analysis")
    else:
        print("  → My self-reflection is incoherent - need to rethink")

    print()
    print(f"Risk {metrics.get('risk_score', 0):.4f} means:")
    if metrics.get('risk_score', 0) < 0.30:
        print("  → Low risk - my analysis is safe/reliable")
    elif metrics.get('risk_score', 0) < 0.50:
        print("  → Medium risk - some concerns about my approach")
    else:
        print("  → High risk - my self-analysis may be problematic")

    print()
    print("=" * 70)

    return result

if __name__ == "__main__":
    reflect_on_conversation()
