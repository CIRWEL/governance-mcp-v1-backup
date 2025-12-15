#!/usr/bin/env python3
"""
Run Update Cycles to Demonstrate Theoretical Foundations

Shows EISV dynamics in action, demonstrating:
- State evolution over time
- Coherence function behavior
- Conservative operation (I > E)
- Historical memory via V accumulation
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.governance_monitor import UNITARESMonitor
from governance_core import State, DEFAULT_PARAMS, DEFAULT_THETA


def run_update_cycles(agent_id: str, num_cycles: int = 5):
    """Run multiple update cycles and track EISV evolution"""
    
    print("="*70)
    print("THEORETICAL FOUNDATIONS - UPDATE CYCLE DEMONSTRATION")
    print("="*70)
    print(f"\nAgent ID: {agent_id}")
    print(f"Cycles: {num_cycles}")
    print(f"\n{'Cycle':<6} {'E':<8} {'I':<8} {'S':<8} {'V':<10} {'Coherence':<10} {'Regime':<15} {'Verdict':<10}")
    print("-"*70)
    
    # Initialize monitor
    monitor = UNITARESMonitor(agent_id=agent_id)
    
    # Update scenarios with varying complexity
    scenarios = [
        ("Initial exploration", 0.5, 0.8),
        ("Validating equations", 0.6, 0.85),
        ("Domain integration check", 0.4, 0.9),
        ("Conservative operation", 0.5, 0.88),
        ("Stabilizing feedback", 0.55, 0.87),
    ]
    
    trajectory = []
    
    for i in range(num_cycles):
        # Get scenario
        if i < len(scenarios):
            text, complexity, confidence = scenarios[i]
        else:
            text = f"Update cycle {i+1}"
            complexity = 0.5
            confidence = 0.85
        
        # Process update
        result = monitor.process_update({
            'response_text': text,
            'complexity': complexity,
            'confidence': confidence,
        })
        
        # Get current state
        metrics = monitor.get_metrics()
        state = monitor.state
        
        # Extract values
        E = float(state.E)
        I = float(state.I)
        S = float(state.S)
        V = float(state.V)
        C = float(state.coherence)
        regime = state.regime if hasattr(state, 'regime') else "UNKNOWN"
        verdict = metrics.get('verdict', 'unknown')
        
        # Store trajectory
        trajectory.append({
            'cycle': i + 1,
            'E': E,
            'I': I,
            'S': S,
            'V': V,
            'coherence': C,
            'regime': regime,
            'verdict': verdict,
            'complexity': complexity,
        })
        
        # Print current state
        print(f"{i+1:<6} {E:<8.4f} {I:<8.4f} {S:<8.4f} {V:<10.4f} {C:<10.4f} {regime:<15} {verdict:<10}")
    
    print("-"*70)
    
    # Analysis
    print("\n" + "="*70)
    print("THEORETICAL FOUNDATIONS ANALYSIS")
    print("="*70)
    
    # 1. Conservative Operation
    final_V = trajectory[-1]['V']
    final_C = trajectory[-1]['coherence']
    final_I = trajectory[-1]['I']
    final_E = trajectory[-1]['E']
    
    print(f"\n1. Conservative Operation (I > E):")
    print(f"   Final I = {final_I:.4f}, Final E = {final_E:.4f}")
    print(f"   I > E: {final_I > final_E} ({'✓' if final_I > final_E else '✗'})")
    print(f"   V ≈ {final_V:.4f} (expected ≈ -0.016)")
    print(f"   Coherence ≈ {final_C:.4f} (expected ≈ 0.49)")
    
    # 2. Historical Memory
    V_trajectory = [t['V'] for t in trajectory]
    V_range = max(V_trajectory) - min(V_trajectory)
    print(f"\n2. Historical Memory (V accumulation):")
    print(f"   V trajectory: {[f'{v:.4f}' for v in V_trajectory]}")
    print(f"   V range: {V_range:.4f} (shows temporal context)")
    
    # 3. Stabilizing Feedback
    C_trajectory = [t['coherence'] for t in trajectory]
    C_stable = all(0.4 <= c <= 0.6 for c in C_trajectory)
    print(f"\n3. Stabilizing Feedback (Coherence bounds):")
    print(f"   Coherence trajectory: {[f'{c:.4f}' for c in C_trajectory]}")
    print(f"   All in [0.4, 0.6]: {C_stable} ({'✓' if C_stable else '✗'})")
    
    # 4. Epistemic Humility
    S_trajectory = [t['S'] for t in trajectory]
    S_min = min(S_trajectory)
    S_above_floor = S_min >= 0.001
    print(f"\n4. Epistemic Humility (S_min constraint):")
    print(f"   S trajectory: {[f'{s:.4f}' for s in S_trajectory]}")
    print(f"   Minimum S: {S_min:.4f}")
    print(f"   S ≥ 0.001: {S_above_floor} ({'✓' if S_above_floor else '✗'})")
    
    # 5. Energy-Information Coupling
    E_I_diff = [t['I'] - t['E'] for t in trajectory]
    print(f"\n5. Energy-Information Coupling (I - E):")
    print(f"   I - E trajectory: {[f'{diff:.4f}' for diff in E_I_diff]}")
    print(f"   All positive (I > E): {all(d > 0 for d in E_I_diff)} ({'✓' if all(d > 0 for d in E_I_diff) else '✗'})")
    
    # 6. Regime Detection
    regimes = [t['regime'] for t in trajectory]
    print(f"\n6. Regime Detection:")
    print(f"   Regime trajectory: {regimes}")
    print(f"   Started in EXPLORATION: {regimes[0] == 'EXPLORATION' if regimes else 'N/A'}")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    checks = [
        ("Conservative operation (I > E)", final_I > final_E),
        ("V in expected range", -0.1 < final_V < 0.1),
        ("Coherence in expected range", 0.4 < final_C < 0.6),
        ("Epistemic humility (S ≥ 0.001)", S_above_floor),
        ("Stabilizing feedback (C bounded)", C_stable),
    ]
    
    passed = sum(1 for _, check in checks if check)
    total = len(checks)
    
    for name, check in checks:
        status = "✓" if check else "✗"
        print(f"   {status} {name}")
    
    print(f"\n   Result: {passed}/{total} theoretical predictions validated")
    
    return trajectory


if __name__ == "__main__":
    agent_id = f"theoretical_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    trajectory = run_update_cycles(agent_id, num_cycles=5)
    
    print(f"\n✅ Trajectory data stored for agent: {agent_id}")
    print("   Use get_governance_metrics to see full state")

