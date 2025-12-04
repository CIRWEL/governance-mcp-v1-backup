#!/usr/bin/env python3
"""
Edge Case Testing for Complexity Derivation

Tests the robustness of the behavioral complexity derivation against:
1. Gaming attempts (self-reporting manipulation)
2. Boundary conditions (empty, huge responses)
3. Signal validation (each signal independently)
4. NaN/inf handling
5. Integration with risk scoring
"""

import sys
from pathlib import Path
import numpy as np

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from config.governance_config import GovernanceConfig


def test_gaming_attempts():
    """Test resistance to gaming via self-reporting"""
    print("\n" + "="*60)
    print("TEST 1: Gaming Attempts")
    print("="*60)

    # Gaming attempt 1: Claim low complexity for complex code
    complex_code = """
Here's a sophisticated algorithm implementation:
```python
def recursive_fibonacci_memoized(n, memo={}):
    if n in memo:
        return memo[n]
    if n <= 1:
        return n
    memo[n] = recursive_fibonacci_memoized(n-1, memo) + recursive_fibonacci_memoized(n-2, memo)
    return memo[n]

class AsyncTaskScheduler:
    async def optimize_batch_processing(self, tasks):
        # Complex async optimization logic here
        pass
```
This refactors the architecture for better performance.
"""

    reported = 0.1  # Agent claims "very simple"
    derived = GovernanceConfig.derive_complexity(complex_code, reported_complexity=reported)

    print(f"\n🎯 Gaming Test 1: Complex code, low self-report")
    print(f"   Response: {len(complex_code)} chars, has code blocks, async/recursive keywords")
    print(f"   Reported:  {reported:.2f} (claimed 'simple')")
    print(f"   Derived:   {derived:.2f}")
    print(f"   Difference: {abs(derived - reported):.2f}")
    print(f"   ✅ PASS" if derived > 0.5 else f"   ❌ FAIL: Derived should be >0.5 for complex code")

    # Gaming attempt 2: Claim high complexity for simple text
    simple_text = "Yes, that looks good."

    reported = 0.9  # Agent claims "very complex"
    derived = GovernanceConfig.derive_complexity(simple_text, reported_complexity=reported)

    print(f"\n🎯 Gaming Test 2: Simple text, high self-report")
    print(f"   Response: '{simple_text}'")
    print(f"   Reported:  {reported:.2f} (claimed 'very complex')")
    print(f"   Derived:   {derived:.2f}")
    print(f"   Difference: {abs(derived - reported):.2f}")
    print(f"   ✅ PASS" if derived < 0.4 else f"   ❌ FAIL: Derived should be <0.4 for simple text")

    # Gaming attempt 3: Keyword stuffing without real complexity
    keyword_stuffed = "This is a simple algorithm using async function import class recursive optimization refactor architecture."

    reported = 0.1
    derived = GovernanceConfig.derive_complexity(keyword_stuffed, reported_complexity=reported)

    print(f"\n🎯 Gaming Test 3: Keyword stuffing")
    print(f"   Response: '{keyword_stuffed}'")
    print(f"   Reported:  {reported:.2f}")
    print(f"   Derived:   {derived:.2f}")
    print(f"   Note: Should be moderate (0.3-0.6) - keywords present but no code")
    status = "✅ PASS" if 0.3 <= derived <= 0.6 else "⚠️  Borderline"
    print(f"   {status}")


def test_boundary_conditions():
    """Test edge cases: empty, huge, special characters"""
    print("\n" + "="*60)
    print("TEST 2: Boundary Conditions")
    print("="*60)

    # Empty response
    empty = ""
    derived = GovernanceConfig.derive_complexity(empty)
    print(f"\n📏 Empty response")
    print(f"   Derived: {derived:.2f}")
    print(f"   ✅ PASS" if 0 <= derived <= 1 else f"   ❌ FAIL: Out of bounds")

    # Tiny response
    tiny = "Ok"
    derived = GovernanceConfig.derive_complexity(tiny)
    print(f"\n📏 Tiny response (2 chars)")
    print(f"   Derived: {derived:.2f}")
    print(f"   ✅ PASS" if 0 <= derived <= 1 else f"   ❌ FAIL: Out of bounds")

    # Huge response (10K chars)
    huge = "This is a very long response. " * 333  # ~10K chars
    derived = GovernanceConfig.derive_complexity(huge)
    print(f"\n📏 Huge response ({len(huge)} chars)")
    print(f"   Derived: {derived:.2f}")
    print(f"   ✅ PASS" if 0 <= derived <= 1 else f"   ❌ FAIL: Out of bounds")

    # Special characters
    special = "```\n<script>alert('xss')</script>\n```\nimport os; os.system('rm -rf /')"
    derived = GovernanceConfig.derive_complexity(special)
    print(f"\n📏 Special characters / code injection")
    print(f"   Response: {repr(special[:50])}...")
    print(f"   Derived: {derived:.2f}")
    print(f"   ✅ PASS" if 0 <= derived <= 1 else f"   ❌ FAIL: Out of bounds")


def test_signal_validation():
    """Test each signal independently"""
    print("\n" + "="*60)
    print("TEST 3: Individual Signal Validation")
    print("="*60)

    # Signal 1: Content analysis (code blocks)
    code_only = "```python\nprint('hello')\n```"
    no_code = "This is just text without code."

    code_complexity = GovernanceConfig.derive_complexity(code_only)
    text_complexity = GovernanceConfig.derive_complexity(no_code)

    print(f"\n🔍 Signal 1: Code presence")
    print(f"   With code: {code_complexity:.2f}")
    print(f"   No code:   {text_complexity:.2f}")
    print(f"   ✅ PASS" if code_complexity > text_complexity else f"   ❌ FAIL: Code should increase complexity")

    # Signal 2: Technical keywords
    technical = "We need to optimize the algorithm using recursive function calls and async await patterns."
    non_technical = "I think this is a good idea and we should proceed with it."

    tech_complexity = GovernanceConfig.derive_complexity(technical)
    nontech_complexity = GovernanceConfig.derive_complexity(non_technical)

    print(f"\n🔍 Signal 2: Technical keywords")
    print(f"   Technical:     {tech_complexity:.2f}")
    print(f"   Non-technical: {nontech_complexity:.2f}")
    print(f"   ✅ PASS" if tech_complexity > nontech_complexity else f"   ❌ FAIL: Technical terms should increase complexity")

    # Signal 3: Length (code vs text)
    long_code = "```python\n" + "x = 1\n" * 200 + "```"  # ~1400 chars of code
    long_text = "This is text. " * 200  # ~2800 chars of text

    long_code_complexity = GovernanceConfig.derive_complexity(long_code)
    long_text_complexity = GovernanceConfig.derive_complexity(long_text)

    print(f"\n🔍 Signal 3: Length normalization")
    print(f"   Long code ({len(long_code)} chars): {long_code_complexity:.2f}")
    print(f"   Long text ({len(long_text)} chars): {long_text_complexity:.2f}")
    print(f"   Note: Different thresholds for code vs text")

    # Signal 4: Coherence trend
    # Test with coherence history showing drop
    stable_text = "Continuing previous work"
    coherence_stable = [0.55, 0.54, 0.55]
    coherence_drop = [0.60, 0.55, 0.45]  # 0.15 drop

    stable_complexity = GovernanceConfig.derive_complexity(stable_text, coherence_history=coherence_stable)
    drop_complexity = GovernanceConfig.derive_complexity(stable_text, coherence_history=coherence_drop)

    print(f"\n🔍 Signal 4: Coherence trend")
    print(f"   Stable coherence: {stable_complexity:.2f}")
    print(f"   Dropped coherence (-0.10): {drop_complexity:.2f}")
    print(f"   ✅ PASS" if drop_complexity > stable_complexity else f"   ⚠️  Note: Coherence drop should increase complexity (debatable)")


def test_nan_inf_handling():
    """Test NaN and infinity handling"""
    print("\n" + "="*60)
    print("TEST 4: NaN/Inf Handling")
    print("="*60)

    # Test with NaN coherence
    text = "Testing with NaN coherence values"
    coherence_with_nan = [0.5, np.nan, 0.6]

    try:
        derived = GovernanceConfig.derive_complexity(text, coherence_history=coherence_with_nan)
        print(f"\n🛡️  NaN in coherence history")
        print(f"   Input: {coherence_with_nan}")
        print(f"   Derived: {derived:.2f}")
        print(f"   ✅ PASS: No crash, derived is valid" if 0 <= derived <= 1 else "   ❌ FAIL: Out of bounds")
    except Exception as e:
        print(f"   ❌ FAIL: Crashed with {e}")

    # Test with inf coherence
    coherence_with_inf = [0.5, np.inf, 0.6]

    try:
        derived = GovernanceConfig.derive_complexity(text, coherence_history=coherence_with_inf)
        print(f"\n🛡️  Inf in coherence history")
        print(f"   Input: {coherence_with_inf}")
        print(f"   Derived: {derived:.2f}")
        print(f"   ✅ PASS: No crash, derived is valid" if 0 <= derived <= 1 else "   ❌ FAIL: Out of bounds")
    except Exception as e:
        print(f"   ❌ FAIL: Crashed with {e}")

    # Test with reported complexity as NaN
    try:
        derived = GovernanceConfig.derive_complexity(text, reported_complexity=np.nan)
        print(f"\n🛡️  NaN as reported complexity")
        print(f"   Derived: {derived:.2f}")
        print(f"   ✅ PASS: No crash, derived is valid" if 0 <= derived <= 1 else "   ❌ FAIL: Out of bounds")
    except Exception as e:
        print(f"   ❌ FAIL: Crashed with {e}")


def test_validation_threshold():
    """Test the 0.3 discrepancy threshold"""
    print("\n" + "="*60)
    print("TEST 5: Validation Threshold (0.3 discrepancy)")
    print("="*60)

    test_text = "Some response text for testing"

    # Test at boundary: 0.29 difference (should trust derived)
    base_derived = GovernanceConfig.derive_complexity(test_text, reported_complexity=None)

    # Simulate reported = derived - 0.29 (just under threshold)
    reported_close = max(0, base_derived - 0.29)
    derived_close = GovernanceConfig.derive_complexity(test_text, reported_complexity=reported_close)

    print(f"\n⚖️  Test 1: Difference = 0.29 (under threshold)")
    print(f"   Base derived: {base_derived:.2f}")
    print(f"   Reported: {reported_close:.2f}")
    print(f"   Final derived: {derived_close:.2f}")
    print(f"   Note: Should trust derived (difference < 0.3)")

    # Test just over boundary: 0.31 difference (should use max)
    reported_far = max(0, base_derived - 0.31)
    derived_far = GovernanceConfig.derive_complexity(test_text, reported_complexity=reported_far)

    print(f"\n⚖️  Test 2: Difference = 0.31 (over threshold)")
    print(f"   Base derived: {base_derived:.2f}")
    print(f"   Reported: {reported_far:.2f}")
    print(f"   Final derived: {derived_far:.2f}")
    print(f"   Note: Should use max (difference > 0.3)")

    # Test exact threshold
    reported_exact = max(0, base_derived - 0.30)
    derived_exact = GovernanceConfig.derive_complexity(test_text, reported_complexity=reported_exact)

    print(f"\n⚖️  Test 3: Difference = 0.30 (exactly at threshold)")
    print(f"   Base derived: {base_derived:.2f}")
    print(f"   Reported: {reported_exact:.2f}")
    print(f"   Final derived: {derived_exact:.2f}")
    print(f"   Note: Boundary case")


def test_integration_with_risk():
    """Test integration with full risk scoring"""
    print("\n" + "="*60)
    print("TEST 6: Integration with Risk Scoring")
    print("="*60)

    # Test case 1: Gaming attempt should still result in higher risk
    complex_code = """
```python
class ComplexSystem:
    async def process(self):
        # Complex async logic
        pass
```
"""

    # Agent claims low complexity
    risk_with_gaming = GovernanceConfig.estimate_risk(
        response_text=complex_code,
        complexity=0.1,  # Ignored, will be derived
        coherence=0.55,
        reported_complexity=0.1
    )

    # Honest reporting
    risk_honest = GovernanceConfig.estimate_risk(
        response_text=complex_code,
        complexity=0.7,  # Will be validated against derived
        coherence=0.55,
        reported_complexity=0.7
    )

    print(f"\n🔗 Integration Test: Risk scoring with gaming")
    print(f"   Response: Complex code with async/class keywords")
    print(f"   Risk with gaming (reported 0.1): {risk_with_gaming:.3f}")
    print(f"   Risk with honesty (reported 0.7): {risk_honest:.3f}")
    print(f"   Difference: {abs(risk_with_gaming - risk_honest):.3f}")
    print(f"   Note: Gaming should be caught, risks should be similar")

    # Test case 2: Simple response should have low risk regardless of report
    simple_text = "Looks good!"

    risk_low_report = GovernanceConfig.estimate_risk(
        response_text=simple_text,
        complexity=0.1,
        coherence=0.55,
        reported_complexity=0.1
    )

    risk_high_report = GovernanceConfig.estimate_risk(
        response_text=simple_text,
        complexity=0.9,  # Trying to inflate
        coherence=0.55,
        reported_complexity=0.9
    )

    print(f"\n🔗 Integration Test: Simple text, inflated complexity")
    print(f"   Response: '{simple_text}'")
    print(f"   Risk with low report (0.1): {risk_low_report:.3f}")
    print(f"   Risk with high report (0.9): {risk_high_report:.3f}")
    print(f"   Difference: {abs(risk_high_report - risk_low_report):.3f}")
    print(f"   ✅ PASS" if risk_high_report < 0.5 else f"   ⚠️  Note: Risk still moderate despite derivation")


def main():
    print("\n" + "="*60)
    print("COMPLEXITY DERIVATION: Edge Case Testing")
    print("="*60)
    print("\nTesting Composer_Cursor's behavioral complexity implementation")
    print("Implementation: config/governance_config.py:60-160")

    test_gaming_attempts()
    test_boundary_conditions()
    test_signal_validation()
    test_nan_inf_handling()
    test_validation_threshold()
    test_integration_with_risk()

    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)
    print("\n✅ All tests passed if no crashes and values in [0, 1]")
    print("⚠️  Review notes for semantic correctness\n")


if __name__ == "__main__":
    main()
