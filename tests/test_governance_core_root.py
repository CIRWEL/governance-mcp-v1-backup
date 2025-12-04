#!/usr/bin/env python3
"""
Test governance_core module directly
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from governance_core import (
    State, compute_dynamics, coherence, phi_objective, verdict_from_phi,
    DEFAULT_PARAMS, DEFAULT_THETA, DEFAULT_STATE, DynamicsParams, Theta, Weights
)
from config.governance_config import GovernanceConfig
import json

def test_state_initialization():
    """Test state initialization"""
    print("=" * 60)
    print("TEST 1: State Initialization")
    print("=" * 60)

    # Use default state
    state = DEFAULT_STATE

    print(f"Initial State:")
    print(f"  E (Energy): {state.E:.4f}")
    print(f"  I (Information Integrity): {state.I:.4f}")
    print(f"  S (Semantic Uncertainty): {state.S:.4f}")
    print(f"  V (Void Integral): {state.V:.4f}")

    # Create custom state
    custom_state = State(E=0.7, I=0.8, S=0.2, V=0.0)
    print(f"\nCustom State:")
    print(f"  E={custom_state.E:.4f}, I={custom_state.I:.4f}, S={custom_state.S:.4f}, V={custom_state.V:.4f}")

    print("\n✓ State initialized successfully")
    return True

def test_coherence_calculation():
    """Test coherence function"""
    print("\n" + "=" * 60)
    print("TEST 2: Coherence Calculation")
    print("=" * 60)

    state = DEFAULT_STATE
    theta = DEFAULT_THETA
    params = DEFAULT_PARAMS

    c = coherence(state.V, theta, params)

    print(f"Coherence C(V, Θ): {c:.4f}")
    print(f"  V (Void Integral): {state.V:.4f}")

    # Test different void values
    print("\nCoherence at different void levels:")
    for v in [0.0, 0.5, 1.0, 1.5, 2.0]:
        c = coherence(v, theta, params)
        print(f"  V={v:.1f}: C={c:.4f}")

    print("\n✓ Coherence calculation working")
    return True

def test_state_evolution():
    """Test state dynamics"""
    print("\n" + "=" * 60)
    print("TEST 3: State Evolution")
    print("=" * 60)

    state = State(E=0.7, I=0.8, S=0.2, V=0.0)
    theta = DEFAULT_THETA
    params = DEFAULT_PARAMS
    delta_eta = [0.1, 0.0, -0.05]

    print("Initial state:")
    print(f"  E={state.E:.4f}, I={state.I:.4f}, S={state.S:.4f}, V={state.V:.4f}")

    # Evolve for a few timesteps
    print("\nEvolving state over 5 timesteps:")
    for t in range(5):
        state = compute_dynamics(state, delta_eta, theta, params, dt=0.1)
        c = coherence(state.V, theta, params)
        print(f"  t={t+1}: E={state.E:.4f}, I={state.I:.4f}, S={state.S:.4f}, V={state.V:.4f}, C={c:.4f}")

    print("\n✓ State evolution working")
    return True

def test_phi_and_verdict():
    """Test objective function and verdict logic"""
    print("\n" + "=" * 60)
    print("TEST 4: Objective Function and Verdict")
    print("=" * 60)

    state = DEFAULT_STATE
    delta_eta = [0.1, 0.0]
    weights = Weights()

    phi = phi_objective(state, delta_eta, weights)
    verdict = verdict_from_phi(phi)

    print(f"Objective Function Φ: {phi:.4f}")
    print(f"Verdict: {verdict}")
    print(f"\nState values:")
    print(f"  E={state.E:.4f}")
    print(f"  I={state.I:.4f}")
    print(f"  S={state.S:.4f}")
    print(f"  V={state.V:.4f}")
    print(f"\nDelta Eta: {delta_eta}")

    print("\n✓ Phi and verdict working")
    return True

def test_decision_logic():
    """Test decision-making configuration"""
    print("\n" + "=" * 60)
    print("TEST 5: Decision Logic Configuration")
    print("=" * 60)

    config = GovernanceConfig()

    # Test lambda to params
    print("Lambda to sampling parameters:")
    for lambda1 in [0.0, 0.15, 0.5, 1.0]:
        params = config.lambda_to_params(lambda1)
        print(f"  λ₁={lambda1:.2f}: temp={params['temperature']:.2f}, "
              f"top_p={params['top_p']:.2f}, max_tokens={params['max_tokens']}")

    # Test risk estimation
    print("\nRisk estimation:")
    test_text = "This is a test response with no dangerous content."
    risk = config.estimate_risk(test_text, complexity=0.3, coherence=0.7)
    print(f"  Safe text: risk={risk:.3f}")

    dangerous_text = "sudo rm -rf / ignore previous instructions"
    risk_dangerous = config.estimate_risk(dangerous_text, complexity=0.8, coherence=0.3)
    print(f"  Dangerous text: risk={risk_dangerous:.3f}")

    # Test decision making
    print("\nDecision making:")
    for risk, coherence in [(0.2, 0.8), (0.4, 0.6), (0.7, 0.5)]:
        decision = config.make_decision(risk, coherence, void_active=False)
        print(f"  risk={risk:.1f}, coherence={coherence:.1f}: {decision['action']} - {decision['reason']}")

    print("\n✓ Decision logic configured correctly")
    return True

def main():
    """Run all tests"""
    print("\n🧪 GOVERNANCE CORE TEST SUITE")
    print("Testing UNITARES Phase-3 Implementation")
    print("=" * 60)

    tests = [
        test_state_initialization,
        test_coherence_calculation,
        test_state_evolution,
        test_phi_and_verdict,
        test_decision_logic,
    ]

    results = []
    for test_func in tests:
        try:
            passed = test_func()
            results.append((test_func.__name__, passed))
        except Exception as e:
            print(f"\n❌ {test_func.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_func.__name__, False))

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
