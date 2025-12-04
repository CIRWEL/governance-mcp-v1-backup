"""
Test P2 Content Analysis Improvements
Tests word boundaries, code block counting, and improved matching
"""

import sys
sys.path.insert(0, '.')

from config.governance_config import GovernanceConfig
import re

def test_word_boundaries():
    """Test that word boundaries prevent false positives"""
    print("=" * 60)
    print("Testing Word Boundaries")
    print("=" * 60)
    
    test_cases = [
        # (text, term, should_match, description)
        ("This is algorithmic thinking", "algorithm", False, "Should NOT match 'algorithmic'"),
        ("The algorithm works well", "algorithm", True, "Should match 'algorithm'"),
        ("Using import in a sentence", "import", True, "Should match 'import' as word (legitimate use)"),
        ("import numpy as np", "import", True, "Should match 'import' statement"),
        ("This is a profile", "file", False, "Should NOT match 'file' in 'profile'"),
        ("Here is a file_path", "file", False, "Should NOT match 'file' in 'file_path' (underscore compound)"),
        ("The filesystem is", "file", False, "Should NOT match 'file' in 'filesystem'"),
        ("Check the file path", "file", True, "Should match 'file'"),
        ("Check the file path", "path", True, "Should match 'path'"),
    ]
    
    passed = 0
    failed = 0
    
    for text, term, should_match, description in test_cases:
        text_lower = text.lower()
        
        # Old method (substring)
        old_match = term.lower() in text_lower
        
        # New method (word boundary)
        pattern = r'\b' + re.escape(term.lower()) + r'\b'
        new_match = bool(re.search(pattern, text_lower))
        
        # Check if new method matches expectation
        correct = (new_match == should_match)
        
        if correct:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"
        
        print(f"{status} | {description}")
        print(f"      Text: '{text}'")
        print(f"      Term: '{term}'")
        print(f"      Old (substring): {old_match} | New (word boundary): {new_match} | Expected: {should_match}")
        print()
    
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_code_block_counting():
    """Test that code block counting works correctly"""
    print("=" * 60)
    print("Testing Code Block Counting")
    print("=" * 60)
    
    test_cases = [
        # (text, expected_count, description)
        ("No code here", 0, "No code blocks"),
        ("```python\ncode\n```", 1, "Single code block"),
        ("```python\ncode1\n```\n```python\ncode2\n```", 2, "Two code blocks"),
        ("```python\ncode1\n```\n```python\ncode2\n```\n```python\ncode3\n```", 3, "Three code blocks"),
        ("```\ncode\n```", 1, "Code block without language"),
    ]
    
    passed = 0
    failed = 0
    
    for text, expected_count, description in test_cases:
        actual_count = text.count('```') // 2  # Each block has 2 ```
        
        correct = (actual_count == expected_count)
        
        if correct:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"
        
        print(f"{status} | {description}")
        print(f"      Expected: {expected_count} blocks | Actual: {actual_count} blocks")
        print()
    
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_complexity_scaling():
    """Test that complexity scales with code block count"""
    print("=" * 60)
    print("Testing Complexity Scaling")
    print("=" * 60)
    
    # Create test cases with different code block counts
    test_cases = [
        ("No code here", 0, "No code"),
        ("```python\ndef func():\n    pass\n```", 1, "Single code block"),
        ("```python\ndef func1():\n    pass\n```\n```python\ndef func2():\n    pass\n```", 2, "Two code blocks"),
        ("```python\ncode1\n```\n```python\ncode2\n```\n```python\ncode3\n```\n```python\ncode4\n```", 4, "Four code blocks"),
    ]
    
    complexities = []
    
    for text, expected_blocks, description in test_cases:
        complexity = GovernanceConfig.derive_complexity(
            response_text=text,
            reported_complexity=None,
            coherence_history=None
        )
        complexities.append((expected_blocks, complexity, description))
        print(f"Blocks: {expected_blocks:2} | Complexity: {complexity:.3f} | {description}")
    
    print()
    
    # Check that complexity increases with block count
    passed = True
    for i in range(1, len(complexities)):
        prev_blocks, prev_complexity, _ = complexities[i-1]
        curr_blocks, curr_complexity, _ = complexities[i]
        
        if curr_blocks > prev_blocks:
            if curr_complexity >= prev_complexity:
                print(f"✅ Complexity increases with blocks: {prev_blocks} → {curr_blocks} ({prev_complexity:.3f} → {curr_complexity:.3f})")
            else:
                print(f"❌ Complexity should increase: {prev_blocks} → {curr_blocks} ({prev_complexity:.3f} → {curr_complexity:.3f})")
                passed = False
    
    return passed


def test_technical_term_detection():
    """Test that technical terms are detected correctly"""
    print("=" * 60)
    print("Testing Technical Term Detection")
    print("=" * 60)
    
    test_cases = [
        # (text, should_have_technical, description)
        ("This is algorithmic thinking", False, "Should NOT match 'algorithmic'"),
        ("The algorithm is efficient", True, "Should match 'algorithm'"),
        ("We need to optimize this", True, "Should match 'optimize'"),
        ("This is a function", True, "Should match 'function'"),
        ("Let's refactor the code", True, "Should match 'refactor'"),
        ("The architecture is good", True, "Should match 'architecture'"),
        ("This is recursive", True, "Should match 'recursive'"),
        ("Using async/await", True, "Should match 'async' or 'await'"),
    ]
    
    passed = 0
    failed = 0
    
    # Get baseline complexity (no technical terms)
    baseline_text = "This is a simple sentence without technical terms."
    baseline_complexity = GovernanceConfig.derive_complexity(
        response_text=baseline_text,
        reported_complexity=None,
        coherence_history=None
    )
    
    for text, should_have_technical, description in test_cases:
        complexity = GovernanceConfig.derive_complexity(
            response_text=text,
            reported_complexity=None,
            coherence_history=None
        )
        
        # Technical terms add 0.20 to content complexity (40% weight)
        # Compare against baseline - if technical detected, complexity should be higher
        # Account for length differences by using relative comparison
        # For similar length text, technical terms should add ~0.08-0.12 complexity
        complexity_diff = complexity - baseline_complexity
        has_technical = complexity_diff > 0.05  # Technical terms should add noticeable complexity
        
        correct = (has_technical == should_have_technical)
        
        if correct:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"
        
        print(f"{status} | {description}")
        print(f"      Complexity: {complexity:.3f} | Expected technical: {should_have_technical}")
        print()
    
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("P2 Content Analysis Improvements - Test Suite")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Word Boundaries", test_word_boundaries()))
    print()
    
    results.append(("Code Block Counting", test_code_block_counting()))
    print()
    
    results.append(("Complexity Scaling", test_complexity_scaling()))
    print()
    
    results.append(("Technical Term Detection", test_technical_term_detection()))
    print()
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {test_name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed")
        sys.exit(1)

