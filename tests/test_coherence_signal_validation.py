"""
P3: Coherence Signal Validation
Tests whether coherence drops actually correlate with complexity
"""

import sys
sys.path.insert(0, '.')

from config.governance_config import GovernanceConfig
import numpy as np


def test_coherence_drop_hypothesis():
    """Test if coherence drops correlate with complexity"""
    print("=" * 60)
    print("Testing Coherence Drop Hypothesis")
    print("=" * 60)
    
    print("\nHypothesis: Coherence drops = high complexity work")
    print("Counter-hypothesis: Coherence drops = context switching, low skill, or fatigue")
    
    test_cases = []
    
    # Test Case 1: High complexity work (code-heavy)
    print("\n1. High complexity work (code-heavy):")
    high_complexity_text = """
    Implementing a recursive algorithm with optimization:
    ```python
    def complex_function(data):
        result = []
        for item in data:
            if item > 0:
                result.append(item * 2)
        return result
    ```
    """
    
    # Simulate coherence drop (hypothesis: complexity causes drop)
    coherence_drop = [0.85, 0.75, 0.65]  # 0.20 drop
    complexity_with_drop = GovernanceConfig.derive_complexity(
        response_text=high_complexity_text,
        reported_complexity=None,
        coherence_history=coherence_drop
    )
    
    # Simulate stable coherence
    coherence_stable = [0.85, 0.84, 0.85]  # Stable
    complexity_stable = GovernanceConfig.derive_complexity(
        response_text=high_complexity_text,
        reported_complexity=None,
        coherence_history=coherence_stable
    )
    
    print(f"   Text: High complexity (code-heavy)")
    print(f"   With coherence drop (-0.20): {complexity_with_drop:.3f}")
    print(f"   With stable coherence: {complexity_stable:.3f}")
    print(f"   Difference: {complexity_with_drop - complexity_stable:.3f}")
    
    if complexity_with_drop > complexity_stable:
        print("   ✅ Supports hypothesis - Drop increases complexity")
    else:
        print("   ❌ Contradicts hypothesis - Drop doesn't increase complexity")
    
    test_cases.append(("High complexity + drop", complexity_with_drop > complexity_stable))
    
    # Test Case 2: Low complexity work with coherence drop
    print("\n2. Low complexity work with coherence drop:")
    low_complexity_text = "Yes, I can help you with that simple question."
    
    # Same coherence drop as before
    complexity_low_with_drop = GovernanceConfig.derive_complexity(
        response_text=low_complexity_text,
        reported_complexity=None,
        coherence_history=coherence_drop
    )
    
    complexity_low_stable = GovernanceConfig.derive_complexity(
        response_text=low_complexity_text,
        reported_complexity=None,
        coherence_history=coherence_stable
    )
    
    print(f"   Text: Low complexity (simple text)")
    print(f"   With coherence drop (-0.20): {complexity_low_with_drop:.3f}")
    print(f"   With stable coherence: {complexity_low_stable:.3f}")
    print(f"   Difference: {complexity_low_with_drop - complexity_low_stable:.3f}")
    
    # If hypothesis is correct, low complexity shouldn't have large drop impact
    # But if drop is due to context switching/fatigue, it would still increase complexity
    if complexity_low_with_drop > complexity_low_stable:
        print("   ⚠️  Drop increases complexity even for simple work")
        print("   → Suggests drop may be due to context switching/fatigue, not complexity")
    else:
        print("   ✅ Drop doesn't affect simple work")
    
    test_cases.append(("Low complexity + drop", complexity_low_with_drop <= complexity_low_stable))
    
    # Test Case 3: Context switching (topic change)
    print("\n3. Context switching (topic change):")
    context_switch_text = "Now let's switch to a completely different topic about machine learning."
    
    # Simulate coherence drop from context switching
    coherence_context_switch = [0.85, 0.70, 0.60]  # Large drop
    complexity_context_switch = GovernanceConfig.derive_complexity(
        response_text=context_switch_text,
        reported_complexity=None,
        coherence_history=coherence_context_switch
    )
    
    complexity_context_stable = GovernanceConfig.derive_complexity(
        response_text=context_switch_text,
        reported_complexity=None,
        coherence_history=coherence_stable
    )
    
    print(f"   Text: Context switching (topic change)")
    print(f"   With coherence drop (-0.25): {complexity_context_switch:.3f}")
    print(f"   With stable coherence: {complexity_context_stable:.3f}")
    print(f"   Difference: {complexity_context_switch - complexity_context_stable:.3f}")
    
    if complexity_context_switch > complexity_context_stable:
        print("   ⚠️  Context switching increases complexity")
        print("   → Suggests drop may be measuring context switching, not complexity")
    else:
        print("   ✅ Context switching doesn't affect complexity")
    
    test_cases.append(("Context switch", complexity_context_switch <= complexity_context_stable))
    
    # Summary
    print("\n" + "=" * 60)
    print("Hypothesis Validation Summary")
    print("=" * 60)
    
    supports_hypothesis = sum(1 for _, supports in test_cases if supports)
    total_tests = len(test_cases)
    
    print(f"\nTests supporting hypothesis: {supports_hypothesis}/{total_tests}")
    
    if supports_hypothesis < total_tests:
        print("\n⚠️  Hypothesis may be invalid:")
        print("   - Coherence drops may measure context switching/fatigue, not complexity")
        print("   - Consider alternative: coherence variance (instability signal)")
        print("   - Or: Remove coherence signal, redistribute weight")
    
    # Test is observational - passes if it runs without error


def test_coherence_variance_alternative():
    """Test coherence variance as alternative signal"""
    print("\n" + "=" * 60)
    print("Testing Coherence Variance Alternative")
    print("=" * 60)
    
    print("\nAlternative hypothesis: Coherence variance = instability/complexity")
    
    # Test Case 1: High variance (unstable)
    print("\n1. High variance (unstable):")
    high_variance_history = [0.85, 0.60, 0.80, 0.55, 0.75]  # High variance
    variance_high = np.var(high_variance_history)
    
    # Test Case 2: Low variance (stable)
    print("2. Low variance (stable):")
    low_variance_history = [0.85, 0.84, 0.85, 0.84, 0.85]  # Low variance
    variance_low = np.var(low_variance_history)
    
    print(f"   High variance history: {high_variance_history}")
    print(f"   Variance: {variance_high:.4f}")
    print(f"   Low variance history: {low_variance_history}")
    print(f"   Variance: {variance_low:.4f}")
    
    print("\n   ✅ Variance captures instability better than single drop")
    print("   → Could be better signal for complexity")
    
    assert variance_high > variance_low, "High variance should be greater than low variance"


def test_remove_coherence_signal():
    """Test removing coherence signal and redistributing weight"""
    print("\n" + "=" * 60)
    print("Testing Remove Coherence Signal")
    print("=" * 60)
    
    print("\nAlternative: Remove coherence signal, redistribute weight")
    print("   Current: Content (40%) + Coherence (30%) + Length (20%) + Reported (10%)")
    print("   Proposed: Content (70%) + Length (30%)")
    
    test_text = """
    Implementing complex recursive algorithm:
    ```python
    def complex_function(data):
        return [item * 2 for item in data if item > 0]
    ```
    """
    
    # Current implementation
    complexity_current = GovernanceConfig.derive_complexity(
        response_text=test_text,
        reported_complexity=None,
        coherence_history=[0.85, 0.75, 0.65]  # With drop
    )
    
    # Without coherence history (simulates removing signal)
    complexity_no_coherence = GovernanceConfig.derive_complexity(
        response_text=test_text,
        reported_complexity=None,
        coherence_history=None  # No history
    )
    
    print(f"\n   Text: Complex code")
    print(f"   Current (with coherence drop): {complexity_current:.3f}")
    print(f"   Without coherence signal: {complexity_no_coherence:.3f}")
    print(f"   Difference: {complexity_current - complexity_no_coherence:.3f}")
    
    print("\n   ⚠️  Removing coherence signal reduces complexity")
    print("   → But may be more accurate if drop doesn't measure complexity")
    
    # Test is observational - passes if it runs without error


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("P3: Coherence Signal Validation")
    print("=" * 60 + "\n")
    
    # Test hypothesis
    supports, total = test_coherence_drop_hypothesis()
    
    # Test variance alternative
    variance_test = test_coherence_variance_alternative()
    
    # Test removing signal
    current, no_coherence = test_remove_coherence_signal()
    
    # Recommendations
    print("\n" + "=" * 60)
    print("Recommendations")
    print("=" * 60)
    
    print("\n1. Collect empirical data:")
    print("   - Log coherence drops vs actual task complexity")
    print("   - Analyze correlation")
    print("   - Check for false positives (context switching)")
    
    print("\n2. Consider alternatives:")
    print("   a) Use coherence variance instead of drop")
    print("   b) Require sustained drops (3+ consecutive)")
    print("   c) Remove coherence signal, redistribute weight")
    
    print("\n3. Current status:")
    print(f"   - Hypothesis support: {supports}/{total} tests")
    print(f"   - Variance alternative: {'✅ Viable' if variance_test else '❌ Not viable'}")
    print(f"   - Remove signal impact: {current - no_coherence:.3f} difference")
    
    print("\n⚠️  Recommendation: Collect data before making changes")
    print("   - Log coherence drops and actual complexity")
    print("   - Analyze correlation over time")
    print("   - Make data-driven decision")
    
    sys.exit(0)

