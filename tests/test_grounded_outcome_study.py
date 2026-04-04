import pandas as pd

from src.grounded_outcome_study import (
    classify_outcome_provenance,
    compute_data_quality_report,
    fit_grouped_linear_r2,
    prepare_outcome_frame,
)


def test_classify_outcome_provenance_marks_endogenous_and_exogenous():
    assert classify_outcome_provenance("trajectory_validated", {"source": "trajectory_self_validation"}) == "endogenous"
    assert classify_outcome_provenance("cirs_resonance", {"source": "cirs_resonance"}) == "endogenous"
    assert classify_outcome_provenance("test_passed", {"passed": 12}) == "exogenous"
    assert classify_outcome_provenance("task_completed", {"action": "git_commit"}) == "exogenous"
    assert classify_outcome_provenance("task_completed", {"source": "auto_checkin"}) == "endogenous"


def test_prepare_outcome_frame_adds_snapshot_flags():
    frame = pd.DataFrame(
        [
            {
                "agent_id": "a",
                "outcome_type": "test_passed",
                "outcome_score": 1.0,
                "is_bad": False,
                "eisv_e": 0.7,
                "eisv_i": 0.8,
                "eisv_s": 0.2,
                "eisv_v": -0.1,
                "eisv_phi": 0.2,
                "eisv_coherence": 0.5,
                "detail": '{"passed": 1}',
            },
            {
                "agent_id": "b",
                "outcome_type": "test_passed",
                "outcome_score": 1.0,
                "is_bad": False,
                "eisv_e": None,
                "eisv_i": None,
                "eisv_s": None,
                "eisv_v": None,
                "eisv_phi": None,
                "eisv_coherence": None,
                "detail": '{"passed": 1}',
            },
        ]
    )
    prepared = prepare_outcome_frame(frame)
    assert prepared["has_full_snapshot"].tolist() == [True, False]
    assert prepared["has_any_snapshot"].tolist() == [True, False]


def test_compute_data_quality_report_flags_zero_variance_and_missing_joins():
    frame = pd.DataFrame(
        [
            {
                "agent_id": "x",
                "outcome_type": "test_passed",
                "outcome_score": 1.0,
                "is_bad": False,
                "eisv_e": None,
                "eisv_i": None,
                "eisv_s": None,
                "eisv_v": None,
                "eisv_phi": None,
                "eisv_coherence": None,
                "detail": '{"passed": 1}',
            },
            {
                "agent_id": "y",
                "outcome_type": "task_completed",
                "outcome_score": 1.0,
                "is_bad": False,
                "eisv_e": None,
                "eisv_i": None,
                "eisv_s": None,
                "eisv_v": None,
                "eisv_phi": None,
                "eisv_coherence": None,
                "detail": '{"action": "git_commit"}',
            },
        ]
    )
    report = compute_data_quality_report(
        frame,
        identity_agent_ids=[],
        state_agent_ids=[],
        audit_agent_ids=[],
        first_behavioral_timestamp=None,
    )
    assert report.exogenous_outcomes == 2
    assert report.exogenous_negative_outcomes == 0
    assert report.exogenous_score_std == 0.0
    assert report.exogenous_any_snapshot == 0
    assert report.state_join_agents == 0
    assert any("zero variance" in note for note in report.notes)
    assert any("not paired with any EISV snapshot" in note for note in report.notes)


def test_fit_grouped_linear_r2_returns_signal_on_synthetic_data():
    rows = []
    for agent in ("a", "b", "c", "d", "e"):
        offset = ord(agent) - ord("a")
        for idx in range(10):
            score = idx / 10 + offset * 0.01
            rows.append(
                {
                    "agent_id": agent,
                    "outcome_score": score,
                    "eisv_e": score,
                    "eisv_i": score * 0.9,
                    "eisv_s": 1.0 - score,
                    "eisv_v": -score * 0.1,
                    "eisv_phi": score * 0.8,
                    "eisv_coherence": score * 0.7,
                }
            )
    frame = pd.DataFrame(rows)
    report = fit_grouped_linear_r2(frame, min_samples=20, min_agents=5)
    assert report.status == "ok"
    assert report.r2_mean is not None
    assert report.r2_mean > 0.7


def test_fit_grouped_linear_r2_rejects_constant_target():
    frame = pd.DataFrame(
        [
            {
                "agent_id": f"a{i // 4}",
                "outcome_score": 1.0,
                "eisv_e": 0.7,
                "eisv_i": 0.8,
                "eisv_s": 0.2,
                "eisv_v": -0.1,
                "eisv_phi": 0.2,
                "eisv_coherence": 0.5,
            }
            for i in range(20)
        ]
    )
    report = fit_grouped_linear_r2(frame, min_samples=10, min_agents=5)
    assert report.status == "insufficient_data"
    assert report.reason == "target has zero variance"
