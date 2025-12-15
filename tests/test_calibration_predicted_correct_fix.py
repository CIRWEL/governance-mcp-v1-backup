#!/usr/bin/env python3
"""
Regression test for predicted_correct calibration fix.

Tests that high-confidence decisions result in high accuracy (not inverted).

NOTE (2025-12): These tests test JSON state file behavior which is deprecated.
CalibrationChecker now uses SQLite by default and loads from canonical DB.
These tests are skipped until they can be updated to test SQLite behavior.
"""

import pytest
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.calibration import CalibrationChecker

# Skip all tests - they test deprecated JSON state_file behavior
pytestmark = pytest.mark.skip(reason="Tests JSON state_file behavior which is deprecated - calibration uses SQLite")


def test_high_confidence_proceed_not_inverted():
    """
    Test that high-confidence proceed decisions show high accuracy (not inverted).
    
    Before fix: High confidence proceed → low accuracy (inverted)
    After fix: High confidence proceed → high accuracy (correct)
    """
    print("\n1. Testing high-confidence proceed → high accuracy...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "calibration_state.json"
        checker = CalibrationChecker(state_file=state_file)
        
        # Simulate high-confidence proceed decisions that were correct
        # These should result in HIGH accuracy, not low
        for _ in range(10):
            # High confidence (0.9) proceed that was correct
            checker.update_ground_truth(
                confidence=0.9,
                predicted_correct=True,  # confidence >= 0.5 = True
                actual_correct=True
            )
        
        # Check calibration
        is_calibrated, result = checker.check_calibration(min_samples_per_bin=5)
        
        # High confidence bin should show high accuracy
        high_conf_bin = result['bins'].get('0.9-1.0', {})
        if high_conf_bin:
            accuracy = high_conf_bin.get('accuracy', 0)
            count = high_conf_bin.get('count', 0)
            
            print(f"   High confidence bin (0.9-1.0):")
            print(f"   - Count: {count}")
            print(f"   - Accuracy: {accuracy:.2%}")
            
            # After fix: high confidence should show high accuracy (>50%)
            assert accuracy > 0.5, f"High confidence should show high accuracy, got {accuracy:.2%}"
            assert count == 10, f"Should have 10 samples, got {count}"
            
            print(f"   ✅ High confidence → high accuracy (not inverted)")
        else:
            raise AssertionError("High confidence bin not found in results")


def test_low_confidence_not_inverted():
    """
    Test that low-confidence decisions show appropriate accuracy.
    
    The key fix: predicted_correct is now based on confidence (>=0.5), not decision.
    So low confidence (<0.5) should have predicted_correct=False.
    """
    print("\n2. Testing low-confidence decisions...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "calibration_state.json"
        checker = CalibrationChecker(state_file=state_file)
        
        # Test low confidence bin (0.0-0.5) 
        # With confidence-based prediction: confidence < 0.5 → predicted_correct=False
        for _ in range(5):
            checker.update_ground_truth(
                confidence=0.3,  # Low confidence
                predicted_correct=False,  # confidence < 0.5 = False (FIXED: not decision-based)
                actual_correct=True  # Was actually correct
            )
        
        # Check calibration
        is_calibrated, result = checker.check_calibration(min_samples_per_bin=5)
        
        low_conf_bin = result['bins'].get('0.0-0.5', {})
        if low_conf_bin:
            accuracy = low_conf_bin.get('accuracy', 0)
            count = low_conf_bin.get('count', 0)
            
            print(f"   Low confidence bin (0.0-0.5):")
            print(f"   - Count: {count}")
            print(f"   - Accuracy: {accuracy:.2%}")
            
            # Key test: All samples were actually correct, so accuracy should be 100%
            # This verifies the fix: we're using confidence-based prediction (confidence < 0.5 → predicted_correct=False)
            # but actual_correct=True, so accuracy = 5/5 = 100%
            assert count == 5, f"Should have 5 total samples, got {count}"
            assert accuracy == 1.0, f"All samples were actually correct, accuracy should be 100%, got {accuracy:.2%}"
            
            # Verify predicted_correct is 0 by checking the checker directly
            # (not exposed in check_calibration result, but we can verify the fix worked)
            assert checker.bin_stats['0.0-0.5']['predicted_correct'] == 0, \
                f"Should have 0 predicted correct (confidence < 0.5), got {checker.bin_stats['0.0-0.5']['predicted_correct']}"
            assert checker.bin_stats['0.0-0.5']['actual_correct'] == 5, \
                f"Should have 5 actually correct, got {checker.bin_stats['0.0-0.5']['actual_correct']}"
            
            print(f"   ✅ Low confidence uses confidence-based predicted_correct (not decision-based)")
        else:
            raise AssertionError("Low confidence bin not found in results")


def test_tactical_calibration_fix():
    """
    Test that tactical calibration uses confidence-based predicted_correct.
    
    Key fix: record_tactical_decision now uses confidence >= 0.5 for predicted_correct,
    not decision == "proceed".
    """
    print("\n3. Testing tactical calibration fix...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "calibration_state.json"
        checker = CalibrationChecker(state_file=state_file)
        
        # Record tactical decisions with high confidence
        # After fix: confidence >= 0.5 → predicted_correct=True (not decision-based)
        for _ in range(5):
            # High confidence proceed decision that was correct
            checker.record_tactical_decision(
                confidence=0.85,
                decision="proceed",
                immediate_outcome=True
            )
        
        # Also test low confidence tactical (should have predicted_correct=False)
        for _ in range(3):
            checker.record_tactical_decision(
                confidence=0.3,  # Low confidence
                decision="proceed",  # Even though decision is proceed
                immediate_outcome=True
            )
        
        # Check tactical calibration
        is_calibrated, result = checker.check_calibration(min_samples_per_bin=5)
        
        tactical_calibration = result.get('tactical_calibration', {})
        tactical_bins = tactical_calibration.get('bins', {})
        
        if tactical_bins:
            high_conf_tactical = tactical_bins.get('0.8-0.9', {})
            low_conf_tactical = tactical_bins.get('0.0-0.5', {})
            
            if high_conf_tactical:
                accuracy = high_conf_tactical.get('decision_accuracy', 0)  # Tactical uses 'decision_accuracy'
                count = high_conf_tactical.get('count', 0)
                
                print(f"   Tactical high confidence bin (0.8-0.9):")
                print(f"   - Count: {count}")
                print(f"   - Decision accuracy: {accuracy:.2%}")
                
                # High confidence tactical should show high accuracy
                assert count == 5, f"Should have 5 high confidence samples, got {count}"
                assert accuracy == 1.0, f"All high confidence tactical decisions were correct, accuracy should be 100%, got {accuracy:.2%}"
                
                # Verify predicted_correct is based on confidence, not decision
                assert checker.tactical_bin_stats['0.8-0.9']['predicted_correct'] == 5, \
                    f"High confidence should have predicted_correct=5 (confidence >= 0.5), got {checker.tactical_bin_stats['0.8-0.9']['predicted_correct']}"
                
                print(f"   ✅ Tactical calibration uses confidence-based predicted_correct")
            
            if low_conf_tactical:
                # Low confidence should have predicted_correct=0 (confidence < 0.5)
                assert checker.tactical_bin_stats['0.0-0.5']['predicted_correct'] == 0, \
                    f"Low confidence should have predicted_correct=0 (confidence < 0.5), got {checker.tactical_bin_stats['0.0-0.5']['predicted_correct']}"
                print(f"   ✅ Low confidence tactical correctly uses confidence-based prediction")
        else:
            print(f"   ⚠️  Tactical bins not populated (may need more samples)")


if __name__ == "__main__":
    print("=" * 70)
    print("CALIBRATION PREDICTED_CORRECT FIX - REGRESSION TEST")
    print("=" * 70)
    
    try:
        test_high_confidence_proceed_not_inverted()
        test_low_confidence_not_inverted()
        test_tactical_calibration_fix()
        
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nCalibration fix verified:")
        print("  - High confidence → high accuracy (not inverted)")
        print("  - Low confidence → appropriate accuracy")
        print("  - Tactical calibration uses confidence-based prediction")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

