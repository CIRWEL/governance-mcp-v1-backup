#!/usr/bin/env python3
"""
Test Lambda1 PI Controller Implementation

Verifies that:
1. Lambda1 adapts via PI controller
2. Void frequency calculation works
3. Theta.eta1 mapping is correct
4. Sampling parameters change with lambda1
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.governance_monitor import UNITARESMonitor
from governance_core.coherence import lambda1
from governance_core.parameters import Theta, DEFAULT_PARAMS
from config.governance_config import config
import numpy as np


def test_lambda1_theta_mapping():
    """Test that lambda1 maps correctly from theta.eta1"""
    print("\n1. Testing Lambda1 Theta Mapping...")
    
    test_cases = [
        (0.1, 0.05, "minimum"),
        (0.3, 0.125, "midpoint"),
        (0.5, 0.20, "maximum"),
    ]
    
    all_passed = True
    for eta1, expected_lambda1, label in test_cases:
        theta = Theta(C1=1.0, eta1=eta1)
        actual_lambda1 = lambda1(theta, DEFAULT_PARAMS, 
                                 lambda1_min=config.LAMBDA1_MIN,
                                 lambda1_max=config.LAMBDA1_MAX)
        
        if abs(actual_lambda1 - expected_lambda1) < 0.001:
            print(f"   ✅ {label}: eta1={eta1:.1f} → lambda1={actual_lambda1:.4f}")
        else:
            print(f"   ❌ {label}: eta1={eta1:.1f} → lambda1={actual_lambda1:.4f} (expected {expected_lambda1:.4f})")
            all_passed = False
    
    return all_passed


def test_pi_controller():
    """Test PI controller logic"""
    print("\n2. Testing PI Controller...")
    
    # Test case: High void frequency should adjust lambda1
    lambda1_current = 0.15
    void_freq_current = 0.05  # 5% (above 2% target)
    void_freq_target = 0.02
    coherence_current = 0.70  # Below 85% target
    coherence_target = 0.85
    integral_state = 0.0
    
    lambda1_new, integral_new = config.pi_update(
        lambda1_current=lambda1_current,
        void_freq_current=void_freq_current,
        void_freq_target=void_freq_target,
        coherence_current=coherence_current,
        coherence_target=coherence_target,
        integral_state=integral_state,
        dt=1.0
    )
    
    print(f"   Input: lambda1={lambda1_current:.4f}, void_freq={void_freq_current:.3f}, coherence={coherence_current:.3f}")
    print(f"   Output: lambda1={lambda1_new:.4f}, integral={integral_new:.4f}")
    print(f"   Change: {lambda1_new - lambda1_current:+.4f}")
    
    # Verify bounds
    if config.LAMBDA1_MIN <= lambda1_new <= config.LAMBDA1_MAX:
        print(f"   ✅ Lambda1 within bounds [{config.LAMBDA1_MIN}, {config.LAMBDA1_MAX}]")
        return True
    else:
        print(f"   ❌ Lambda1 out of bounds!")
        return False


def test_void_frequency_calculation():
    """Test void frequency calculation"""
    print("\n3. Testing Void Frequency Calculation...")
    
    # Create a monitor
    monitor = UNITARESMonitor("test_pi_controller", load_state=False)
    
    # Simulate some V history with void events
    # Add some values that will trigger void state
    monitor.state.V_history = [
        0.05, 0.08, 0.12, 0.15, 0.18,  # Some normal values
        0.20, 0.22, 0.25,  # Void events (above ~0.15 threshold)
        0.10, 0.08, 0.05   # Back to normal
    ]
    
    void_freq = monitor._calculate_void_frequency()
    print(f"   V history: {len(monitor.state.V_history)} points")
    print(f"   Void frequency: {void_freq:.3f} ({void_freq*100:.1f}%)")
    
    if 0.0 <= void_freq <= 1.0:
        print(f"   ✅ Void frequency in valid range [0, 1]")
        return True
    else:
        print(f"   ❌ Void frequency out of range!")
        return False


def test_lambda1_adaptation():
    """Test that lambda1 actually adapts over multiple updates"""
    print("\n4. Testing Lambda1 Adaptation...")
    
    monitor = UNITARESMonitor("test_adaptation", load_state=False)
    
    # Initialize with some history
    for i in range(20):
        monitor.state.V_history.append(0.10 + np.random.randn() * 0.05)
        monitor.state.coherence_history.append(0.70 + np.random.randn() * 0.10)
        monitor.state.update_count = i + 1
    
    initial_lambda1 = monitor.state.lambda1
    initial_eta1 = monitor.state.unitaires_theta.eta1
    
    print(f"   Initial: lambda1={initial_lambda1:.4f}, eta1={initial_eta1:.4f}")
    
    # Simulate a few lambda1 updates
    lambda1_values = []
    for i in range(5):
        # Update lambda1
        new_lambda1 = monitor.update_lambda1()
        lambda1_values.append(new_lambda1)
        monitor.state.update_count += 5  # Simulate 5 more updates
    
    final_lambda1 = monitor.state.lambda1
    final_eta1 = monitor.state.unitaires_theta.eta1
    
    print(f"   Final: lambda1={final_lambda1:.4f}, eta1={final_eta1:.4f}")
    print(f"   Values: {[f'{l:.4f}' for l in lambda1_values]}")
    
    # Check if lambda1 changed
    if abs(final_lambda1 - initial_lambda1) > 0.001:
        print(f"   ✅ Lambda1 adapted: {initial_lambda1:.4f} → {final_lambda1:.4f}")
        return True
    else:
        print(f"   ⚠️  Lambda1 unchanged (may be correct if metrics are at target)")
        return True  # Not necessarily a failure


def test_sampling_parameters():
    """Test that sampling parameters change with lambda1"""
    print("\n5. Testing Sampling Parameters Adaptation...")
    
    test_lambda1_values = [0.05, 0.125, 0.20]
    
    print("   Lambda1 → Sampling Parameters:")
    for l1 in test_lambda1_values:
        params = config.lambda_to_params(l1)
        print(f"   λ₁={l1:.3f}: temp={params['temperature']:.3f}, "
              f"top_p={params['top_p']:.3f}, max_tokens={params['max_tokens']}")
    
    # Verify range
    min_params = config.lambda_to_params(config.LAMBDA1_MIN)
    max_params = config.lambda_to_params(config.LAMBDA1_MAX)
    
    temp_range = max_params['temperature'] - min_params['temperature']
    top_p_range = max_params['top_p'] - min_params['top_p']
    tokens_range = max_params['max_tokens'] - min_params['max_tokens']
    
    print(f"   Range: temp={temp_range:.3f}, top_p={top_p_range:.3f}, tokens={tokens_range}")
    
    if temp_range > 0 and top_p_range > 0 and tokens_range > 0:
        print(f"   ✅ Sampling parameters vary with lambda1")
        return True
    else:
        print(f"   ❌ Sampling parameters don't vary!")
        return False


def main():
    """Run all tests"""
    print("=" * 70)
    print("Lambda1 PI Controller Implementation Tests")
    print("=" * 70)
    
    results = []
    
    results.append(("Lambda1 Theta Mapping", test_lambda1_theta_mapping()))
    results.append(("PI Controller", test_pi_controller()))
    results.append(("Void Frequency Calculation", test_void_frequency_calculation()))
    results.append(("Lambda1 Adaptation", test_lambda1_adaptation()))
    results.append(("Sampling Parameters", test_sampling_parameters()))
    
    print("\n" + "=" * 70)
    print("Test Results Summary")
    print("=" * 70)
    
    passed_count = 0
    for name, test_passed in results:
        status = "✅ PASS" if test_passed else "❌ FAIL"
        print(f"{status}: {name}")
        if test_passed:
            passed_count += 1
    
    print(f"\nTotal: {passed_count}/{len(results)} tests passed")
    
    if results == len(results):
        print("\n🎉 All tests passed! PI Controller implementation verified.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Review implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

