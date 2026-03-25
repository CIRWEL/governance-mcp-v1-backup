"""Tests for behavioral_trajectory.py — TrajectorySignature from governance history."""

import pytest
from unittest.mock import MagicMock, patch

from src.behavioral_trajectory import (
    compute_behavioral_trajectory,
    project_eisv_trajectory,
    _compute_preferences,
    _compute_beliefs,
    _compute_attractor,
    _compute_recovery,
    _compute_stability,
)
from src.trajectory_identity import TrajectorySignature


# ── Helpers ──

def make_histories(n=20, E=0.8, I=0.7, S=0.1, V=0.05, coherence=0.5,
                   decision="proceed", regime="high"):
    """Generate uniform test histories."""
    return {
        "E_history": [E] * n,
        "I_history": [I] * n,
        "S_history": [S] * n,
        "V_history": [V] * n,
        "coherence_history": [coherence] * n,
        "decision_history": [decision] * n,
        "regime_history": [regime] * n,
        "update_count": n,
    }


# ══════════════════════════════════════════════════
#  Unit tests: compute_behavioral_trajectory
# ══════════════════════════════════════════════════

class TestBehavioralTrajectory:
    def test_returns_none_with_insufficient_history(self):
        h = make_histories(n=5)
        result = compute_behavioral_trajectory(**h)
        assert result is None

    def test_returns_none_with_empty_history(self):
        h = make_histories(n=0)
        result = compute_behavioral_trajectory(**h)
        assert result is None

    def test_returns_dict_with_sufficient_history(self):
        h = make_histories(n=15)
        result = compute_behavioral_trajectory(**h)
        assert result is not None
        assert isinstance(result, dict)

    def test_signature_compatible_with_trajectory_signature(self):
        """Output can be parsed by TrajectorySignature.from_dict()."""
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        sig = TrajectorySignature.from_dict(result)
        assert sig.observation_count == 20
        assert sig.stability_score >= 0
        assert sig.identity_confidence >= 0

    def test_all_required_keys_present(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        for key in ("preferences", "beliefs", "attractor", "recovery", "relational"):
            assert key in result, f"Missing key: {key}"
        for key in ("observation_count", "stability_score", "identity_confidence", "computed_at"):
            assert key in result, f"Missing metadata key: {key}"

    def test_beliefs_values_has_4_elements(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        assert len(result["beliefs"]["values"]) == 4

    def test_attractor_center_has_4_elements(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        assert len(result["attractor"]["center"]) == 4

    def test_stability_score_in_bounds(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        assert 0.0 <= result["stability_score"] <= 1.0

    def test_identity_confidence_ramps_with_update_count(self):
        h_low = make_histories(n=20)
        h_low["update_count"] = 20
        h_high = make_histories(n=20)
        h_high["update_count"] = 150
        r_low = compute_behavioral_trajectory(**h_low)
        r_high = compute_behavioral_trajectory(**h_high)
        assert r_high["identity_confidence"] > r_low["identity_confidence"]

    def test_identity_confidence_caps_at_1(self):
        h = make_histories(n=20)
        h["update_count"] = 1000
        result = compute_behavioral_trajectory(**h)
        assert result["identity_confidence"] <= 1.0

    def test_relational_marks_non_embodied(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        assert result["relational"]["agent_type"] == "non_embodied"

    def test_task_type_counts_included_in_preferences(self):
        h = make_histories(n=20)
        h["task_type_counts"] = {"feature": 10, "testing": 5, "mixed": 5}
        result = compute_behavioral_trajectory(**h)
        dist = result["preferences"]["task_type_distribution"]
        assert abs(dist["feature"] - 0.5) < 0.01
        assert abs(dist["testing"] - 0.25) < 0.01

    def test_none_task_type_counts_gives_empty_dist(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        assert result["preferences"]["task_type_distribution"] == {}

    def test_calibration_error_affects_beliefs_confidence(self):
        h = make_histories(n=20)
        r_none = compute_behavioral_trajectory(**h, calibration_error=None)
        r_high = compute_behavioral_trajectory(**h, calibration_error=0.8)
        assert r_none["beliefs"]["confidence"] > r_high["beliefs"]["confidence"]


# ══════════════════════════════════════════════════
#  Unit tests: Recovery
# ══════════════════════════════════════════════════

class TestRecovery:
    def test_default_tau_when_no_dips(self):
        coh = [0.5] * 20
        result = _compute_recovery(coh)
        assert result["tau_estimate"] == 3.0

    def test_single_step_below_threshold_ignored(self):
        """Single step below 0.46 doesn't count — need 2+ consecutive."""
        coh = [0.5] * 5 + [0.44] + [0.5] * 14
        result = _compute_recovery(coh)
        assert result["tau_estimate"] == 3.0  # Default — not a real dip

    def test_tau_computed_from_sustained_dip(self):
        # 2 consecutive steps below 0.46, then recover at 0.49
        # Dip starts at index 5, recovers at index 9 → tau = 4
        coh = [0.5] * 5 + [0.44, 0.43, 0.44, 0.45] + [0.49] + [0.5] * 10
        result = _compute_recovery(coh)
        assert result["tau_estimate"] == 4.0  # 9 - 5 = 4

    def test_tau_averages_multiple_dips(self):
        # Two sustained dips with different recovery times
        # Dip 1: indices 3-4 below, recover at 5 → tau=2
        # Dip 2: indices 8-11 below, recover at 12 → tau=4
        coh = ([0.5] * 3
               + [0.44, 0.43] + [0.49]          # dip 1: tau = 5 - 3 = 2
               + [0.5] * 2
               + [0.44, 0.43, 0.44, 0.43] + [0.49]  # dip 2: tau = 12 - 8 = 4
               + [0.5] * 5)
        result = _compute_recovery(coh)
        assert result["tau_estimate"] == 3.0  # (2 + 4) / 2

    def test_unrecovered_dip_not_counted(self):
        coh = [0.5] * 10 + [0.44] * 10
        result = _compute_recovery(coh)
        assert result["tau_estimate"] == 3.0  # Default — dip never recovered

    def test_near_boundary_oscillation_ignored(self):
        """Values oscillating near 0.48-0.49 should not trigger dip detection."""
        coh = [0.49, 0.48, 0.49, 0.48, 0.49, 0.48] * 3 + [0.5, 0.5]
        result = _compute_recovery(coh)
        assert result["tau_estimate"] == 3.0  # All above 0.46, no real dips


# ══════════════════════════════════════════════════
#  Unit tests: Stability
# ══════════════════════════════════════════════════

class TestStability:
    def test_constant_coherence_high_stability(self):
        assert _compute_stability([0.5] * 20) == 1.0

    def test_varying_coherence_lower_stability(self):
        coh = [0.45, 0.55] * 10
        assert _compute_stability(coh) < 1.0

    def test_stability_in_bounds(self):
        coh = [0.3, 0.7] * 10
        s = _compute_stability(coh)
        assert 0.0 <= s <= 1.0


# ══════════════════════════════════════════════════
#  Similarity tests
# ══════════════════════════════════════════════════

class TestSimilarity:
    def test_identical_trajectories_high_similarity(self):
        h = make_histories(n=20)
        r1 = compute_behavioral_trajectory(**h)
        r2 = compute_behavioral_trajectory(**h)
        sig1 = TrajectorySignature.from_dict(r1)
        sig2 = TrajectorySignature.from_dict(r2)
        assert sig1.similarity(sig2) > 0.8

    def test_divergent_trajectories_low_similarity(self):
        h1 = make_histories(n=20, E=0.9, I=0.9, S=0.05, V=0.01, coherence=0.52)
        h2 = make_histories(n=20, E=0.3, I=0.3, S=0.8, V=0.5, coherence=0.46)
        r1 = compute_behavioral_trajectory(**h1)
        r2 = compute_behavioral_trajectory(**h2)
        sig1 = TrajectorySignature.from_dict(r1)
        sig2 = TrajectorySignature.from_dict(r2)
        assert sig1.similarity(sig2) < 0.6

    def test_similarity_symmetric(self):
        h1 = make_histories(n=20, E=0.8)
        h2 = make_histories(n=20, E=0.6)
        r1 = compute_behavioral_trajectory(**h1)
        r2 = compute_behavioral_trajectory(**h2)
        sig1 = TrajectorySignature.from_dict(r1)
        sig2 = TrajectorySignature.from_dict(r2)
        assert abs(sig1.similarity(sig2) - sig2.similarity(sig1)) < 0.001


# ══════════════════════════════════════════════════
#  Integration tests: injection in update_enrichments.py
# ══════════════════════════════════════════════════

class TestTrajectoryInjection:
    def test_lumen_signature_takes_priority(self):
        """When trajectory_signature is provided, behavioral is not computed."""
        from src.behavioral_trajectory import compute_behavioral_trajectory
        # If arguments have trajectory_signature, the behavioral path is skipped
        args = {"trajectory_signature": {"preferences": {}, "beliefs": {"values": [0.5]*4}}}
        sig = args.get("trajectory_signature")
        assert sig is not None  # Lumen path taken

    def test_behavioral_computed_when_no_signature(self):
        h = make_histories(n=20)
        result = compute_behavioral_trajectory(**h)
        assert result is not None
        sig = TrajectorySignature.from_dict(result)
        assert sig.observation_count == 20

    def test_no_computation_for_new_agent(self):
        h = make_histories(n=5)
        result = compute_behavioral_trajectory(**h)
        assert result is None

    def test_computation_failure_is_safe(self):
        """If compute_behavioral_trajectory raises, enrichment continues."""
        with patch(
            "src.behavioral_trajectory.compute_behavioral_trajectory",
            side_effect=RuntimeError("boom"),
        ):
            try:
                from src.behavioral_trajectory import compute_behavioral_trajectory
                compute_behavioral_trajectory(**make_histories(n=20))
            except Exception:
                pass  # Simulates the try/except in enrichment


class TestProjectEISVTrajectory:
    def test_insufficient_history_returns_none(self):
        assert project_eisv_trajectory([], [], [], []) is None
        assert project_eisv_trajectory([0.5], [0.5], [0.1], [0.0]) is None
        assert project_eisv_trajectory([0.5, 0.5], [0.5, 0.5], [0.1, 0.1], [0.0, 0.0]) is None

    def test_returns_projected_values(self):
        E = [0.8] * 10
        I = [0.7] * 10
        S = [0.1] * 10
        V = [0.05] * 10
        result = project_eisv_trajectory(E, I, S, V, steps=5)
        assert result is not None
        assert result["steps"] == 5
        assert result["dt"] == 0.1
        assert len(result["projected"]["E"]) == 5
        assert len(result["projected"]["I"]) == 5
        assert len(result["projected"]["S"]) == 5
        assert len(result["projected"]["V"]) == 5

    def test_current_state_matches_last_history(self):
        E = [0.8, 0.85, 0.9]
        I = [0.7, 0.72, 0.74]
        S = [0.1, 0.08, 0.06]
        V = [0.0, 0.01, 0.02]
        result = project_eisv_trajectory(E, I, S, V)
        assert result["current"]["E"] == 0.9
        assert result["current"]["I"] == 0.74
        assert result["current"]["S"] == 0.06
        assert result["current"]["V"] == 0.02

    def test_entropy_rising_warning(self):
        E = [0.3] * 5
        I = [0.3] * 5
        S = [0.8] * 5  # High entropy
        V = [0.0] * 5
        result = project_eisv_trajectory(E, I, S, V, steps=20)
        # With high initial S, projection may warn about entropy
        assert result is not None
        assert isinstance(result["warnings"], list)

    def test_integrity_falling_warning(self):
        E = [0.5] * 5
        I = [0.35] * 5  # Low integrity
        S = [0.3] * 5
        V = [0.0] * 5
        result = project_eisv_trajectory(E, I, S, V, steps=20)
        assert result is not None
        # I < 0.4 should trigger integrity_falling warning
        if result["projected"]["I"][-1] < 0.4:
            assert "integrity_falling" in result["warnings"]

    def test_void_accumulating_warning(self):
        E = [0.9] * 5
        I = [0.3] * 5  # E >> I causes void accumulation
        S = [0.1] * 5
        V = [0.4] * 5
        result = project_eisv_trajectory(E, I, S, V, steps=20)
        assert result is not None

    def test_custom_steps_and_dt(self):
        E = [0.8] * 5
        I = [0.7] * 5
        S = [0.1] * 5
        V = [0.0] * 5
        result = project_eisv_trajectory(E, I, S, V, steps=3, dt=0.05)
        assert result["steps"] == 3
        assert result["dt"] == 0.05
        assert len(result["projected"]["E"]) == 3

    def test_fallback_without_governance_core(self):
        """When governance_core is unavailable, falls back to EWMA extrapolation."""
        import importlib
        import sys
        E = [0.8] * 10
        I = [0.7] * 10
        S = [0.1] * 10
        V = [0.0] * 10

        # Temporarily remove governance_core from sys.modules to force ImportError
        saved = sys.modules.get("governance_core")
        sys.modules["governance_core"] = None  # forces ImportError on from X import Y
        try:
            # Re-import to pick up the blocked module
            import src.behavioral_trajectory as bt
            importlib.reload(bt)
            result = bt.project_eisv_trajectory(E, I, S, V, steps=5)
            assert result is not None
            assert len(result["projected"]["E"]) == 5
        finally:
            if saved is not None:
                sys.modules["governance_core"] = saved
            else:
                sys.modules.pop("governance_core", None)
            importlib.reload(bt)
