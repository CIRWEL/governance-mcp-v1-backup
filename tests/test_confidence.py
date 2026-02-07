"""
Tests for src/confidence.py — Confidence derivation from EISV state.

Tests derive_confidence with mock GovernanceState and tool_usage_tracker.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.confidence import derive_confidence


# ============================================================================
# Helper: mock state
# ============================================================================

def _mock_state(coherence=0.5, I=0.5, S=0.5, V=0.0):
    """Create a mock GovernanceState with EISV attributes."""
    state = MagicMock()
    state.coherence = coherence
    state.I = I
    state.S = S
    state.V = V
    return state


def _mock_tracker(total_calls=0, success_count=0):
    """Create a mock tool_usage_tracker."""
    tracker = MagicMock()
    if total_calls > 0:
        tracker.get_usage_stats.return_value = {
            "total_calls": total_calls,
            "tools": {
                "some_tool": {
                    "total_calls": total_calls,
                    "success_count": success_count,
                }
            }
        }
    else:
        tracker.get_usage_stats.return_value = {"total_calls": 0, "tools": {}}
    return tracker


# ============================================================================
# derive_confidence — basic behavior
# ============================================================================

class TestDeriveConfidenceBasic:

    def test_returns_tuple(self):
        state = _mock_state()
        confidence, metadata = derive_confidence(state)
        assert isinstance(confidence, float)
        assert isinstance(metadata, dict)

    def test_bounded_above(self):
        state = _mock_state(coherence=1.0, I=1.0, S=0.0, V=0.0)
        confidence, _ = derive_confidence(state)
        assert confidence <= 0.95

    def test_bounded_below(self):
        state = _mock_state(coherence=0.0, I=0.0, S=1.0, V=1.0)
        confidence, _ = derive_confidence(state)
        assert confidence >= 0.05

    def test_none_state(self):
        confidence, metadata = derive_confidence(None)
        assert confidence == max(0.05, min(0.95, 0.5))  # default eisv_confidence
        assert metadata["source"] == "eisv_only"

    def test_source_is_eisv_only(self):
        state = _mock_state()
        _, metadata = derive_confidence(state)
        assert metadata["source"] == "eisv_only"


# ============================================================================
# derive_confidence — EISV effects
# ============================================================================

class TestDeriveConfidenceEISV:

    def test_high_coherence_increases_confidence(self):
        low = derive_confidence(_mock_state(coherence=0.2, I=0.5, S=0.3, V=0.0))[0]
        high = derive_confidence(_mock_state(coherence=0.9, I=0.5, S=0.3, V=0.0))[0]
        assert high > low

    def test_high_integrity_increases_confidence(self):
        low = derive_confidence(_mock_state(coherence=0.5, I=0.2, S=0.3, V=0.0))[0]
        high = derive_confidence(_mock_state(coherence=0.5, I=0.9, S=0.3, V=0.0))[0]
        assert high > low

    def test_high_entropy_decreases_confidence(self):
        low_s = derive_confidence(_mock_state(coherence=0.7, I=0.7, S=0.1, V=0.0))[0]
        high_s = derive_confidence(_mock_state(coherence=0.7, I=0.7, S=0.9, V=0.0))[0]
        assert low_s > high_s

    def test_high_void_decreases_confidence(self):
        low_v = derive_confidence(_mock_state(coherence=0.7, I=0.7, S=0.3, V=0.0))[0]
        high_v = derive_confidence(_mock_state(coherence=0.7, I=0.7, S=0.3, V=0.5))[0]
        assert low_v > high_v

    def test_negative_void_also_penalizes(self):
        zero_v = derive_confidence(_mock_state(coherence=0.7, I=0.7, S=0.3, V=0.0))[0]
        neg_v = derive_confidence(_mock_state(coherence=0.7, I=0.7, S=0.3, V=-0.5))[0]
        assert zero_v > neg_v

    def test_metadata_contains_eisv_details(self):
        state = _mock_state(coherence=0.8, I=0.7, S=0.2, V=0.1)
        _, metadata = derive_confidence(state)
        assert "eisv" in metadata
        assert metadata["eisv"]["coherence"] == 0.8
        assert metadata["eisv"]["integrity"] == 0.7
        assert metadata["eisv"]["entropy"] == 0.2
        assert metadata["eisv"]["void"] == 0.1
        assert "void_penalty" in metadata["eisv"]
        assert "entropy_penalty" in metadata["eisv"]


# ============================================================================
# derive_confidence — tool tracker integration
# ============================================================================

class TestDeriveConfidenceToolTracker:

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_tool_stats_in_metadata(self, mock_get_tracker):
        mock_get_tracker.return_value = _mock_tracker(total_calls=10, success_count=8)
        state = _mock_state()
        _, metadata = derive_confidence(state, agent_id="agent-123")
        assert "tool_stats" in metadata
        assert metadata["tool_stats"]["total_calls"] == 10
        assert metadata["tool_stats"]["success_rate"] == 0.8

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_tool_confidence_excluded_from_final(self, mock_get_tracker):
        mock_get_tracker.return_value = _mock_tracker(total_calls=10, success_count=10)
        state = _mock_state()
        _, metadata = derive_confidence(state, agent_id="agent-123")
        assert "tool_confidence_excluded" in metadata
        assert metadata["exclusion_reason"]  # reason documented

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_no_agent_id_skips_tracker(self, mock_get_tracker):
        state = _mock_state()
        _, metadata = derive_confidence(state)
        mock_get_tracker.assert_not_called()

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_tracker_error_handled(self, mock_get_tracker):
        mock_get_tracker.side_effect = Exception("DB down")
        state = _mock_state()
        confidence, metadata = derive_confidence(state, agent_id="agent-123")
        assert confidence >= 0.05  # still returns valid confidence
        assert "tracker_error" in metadata

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_zero_calls_default_confidence(self, mock_get_tracker):
        mock_get_tracker.return_value = _mock_tracker(total_calls=0)
        state = _mock_state()
        _, metadata = derive_confidence(state, agent_id="agent-123")
        assert "tool_stats" not in metadata

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_high_call_count_high_reliability(self, mock_get_tracker):
        mock_get_tracker.return_value = _mock_tracker(total_calls=5, success_count=5)
        state = _mock_state()
        _, metadata = derive_confidence(state, agent_id="agent-123")
        assert metadata["reliability"] == "high"

    @patch("src.tool_usage_tracker.get_tool_usage_tracker")
    def test_low_call_count_medium_reliability(self, mock_get_tracker):
        mock_get_tracker.return_value = _mock_tracker(total_calls=2, success_count=2)
        state = _mock_state()
        _, metadata = derive_confidence(state, agent_id="agent-123")
        assert metadata["reliability"] == "medium"
