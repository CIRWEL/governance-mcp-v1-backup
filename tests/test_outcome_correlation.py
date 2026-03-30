"""Tests for outcome correlation study: verdict distribution, metric correlations, risk bins."""

import pytest
from src.outcome_correlation import (
    _pearson_r,
    compute_verdict_distribution,
    compute_metric_correlations,
    compute_risk_bins,
    CorrelationReport,
    _build_summary,
)


def _make_outcome(
    eisv_verdict="safe",
    is_bad=False,
    outcome_score=1.0,
    eisv_e=0.7,
    eisv_i=0.8,
    eisv_s=0.2,
    eisv_v=0.0,
    eisv_phi=0.3,
    eisv_coherence=0.8,
    **kwargs,
):
    return {
        "eisv_verdict": eisv_verdict,
        "is_bad": is_bad,
        "outcome_score": outcome_score,
        "eisv_e": eisv_e,
        "eisv_i": eisv_i,
        "eisv_s": eisv_s,
        "eisv_v": eisv_v,
        "eisv_phi": eisv_phi,
        "eisv_coherence": eisv_coherence,
        "detail": kwargs.get("detail"),
    }


class TestPearsonR:
    def test_perfect_positive(self):
        r = _pearson_r([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert r is not None
        assert abs(r - 1.0) < 1e-6

    def test_perfect_negative(self):
        r = _pearson_r([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
        assert r is not None
        assert abs(r + 1.0) < 1e-6

    def test_no_correlation(self):
        r = _pearson_r([1, 2, 3, 4, 5], [5, 1, 4, 2, 3])
        assert r is not None
        assert abs(r) < 0.5

    def test_insufficient_data(self):
        assert _pearson_r([1, 2], [3, 4]) is None
        assert _pearson_r([], []) is None

    def test_zero_variance(self):
        assert _pearson_r([5, 5, 5], [1, 2, 3]) is None


class TestVerdictDistribution:
    def test_groups_by_verdict(self):
        outcomes = [
            _make_outcome(eisv_verdict="safe", is_bad=False),
            _make_outcome(eisv_verdict="safe", is_bad=False),
            _make_outcome(eisv_verdict="safe", is_bad=True),
            _make_outcome(eisv_verdict="caution", is_bad=True),
            _make_outcome(eisv_verdict="high-risk", is_bad=True),
        ]
        dist = compute_verdict_distribution(outcomes)
        assert dist["safe"]["count"] == 3
        assert dist["safe"]["bad_count"] == 1
        assert abs(dist["safe"]["bad_rate"] - 1 / 3) < 0.01
        assert dist["caution"]["count"] == 1
        assert dist["high-risk"]["bad_rate"] == 1.0

    def test_empty_outcomes(self):
        dist = compute_verdict_distribution([])
        assert dist == {}

    def test_unknown_verdict(self):
        outcomes = [_make_outcome(eisv_verdict=None)]
        dist = compute_verdict_distribution(outcomes)
        assert "unknown" in dist

    def test_avg_score(self):
        outcomes = [
            _make_outcome(eisv_verdict="safe", outcome_score=0.8),
            _make_outcome(eisv_verdict="safe", outcome_score=0.6),
        ]
        dist = compute_verdict_distribution(outcomes)
        assert abs(dist["safe"]["avg_score"] - 0.7) < 0.01


class TestMetricCorrelations:
    def test_positive_energy_correlation(self):
        outcomes = [
            _make_outcome(eisv_e=0.3, outcome_score=0.2),
            _make_outcome(eisv_e=0.5, outcome_score=0.5),
            _make_outcome(eisv_e=0.7, outcome_score=0.7),
            _make_outcome(eisv_e=0.9, outcome_score=0.9),
        ]
        corr = compute_metric_correlations(outcomes)
        assert corr["E"] is not None
        assert corr["E"] > 0.9

    def test_negative_entropy_correlation(self):
        outcomes = [
            _make_outcome(eisv_s=0.1, outcome_score=0.9),
            _make_outcome(eisv_s=0.3, outcome_score=0.7),
            _make_outcome(eisv_s=0.6, outcome_score=0.4),
            _make_outcome(eisv_s=0.9, outcome_score=0.1),
        ]
        corr = compute_metric_correlations(outcomes)
        assert corr["S"] is not None
        assert corr["S"] < -0.9

    def test_insufficient_data_returns_none(self):
        outcomes = [_make_outcome(), _make_outcome()]
        corr = compute_metric_correlations(outcomes)
        assert corr["E"] is None

    def test_all_metrics_present(self):
        outcomes = [
            _make_outcome(eisv_e=0.5 + i * 0.1, outcome_score=0.5 + i * 0.1)
            for i in range(5)
        ]
        corr = compute_metric_correlations(outcomes)
        assert set(corr.keys()) == {"E", "I", "S", "V", "PHI", "COHERENCE"}


class TestRiskBins:
    def test_bins_by_risk_proxy(self):
        outcomes = [
            _make_outcome(eisv_e=0.9, eisv_i=0.8, eisv_s=0.1, is_bad=False),
            _make_outcome(eisv_e=0.5, eisv_i=0.5, eisv_s=0.5, is_bad=True),
            _make_outcome(eisv_e=0.2, eisv_i=0.3, eisv_s=0.8, is_bad=True),
        ]
        bins = compute_risk_bins(outcomes)
        assert len(bins) == 3
        assert bins[0]["label"] == "healthy"
        assert bins[0]["count"] == 1
        assert bins[0]["bad_rate"] == 0.0
        assert bins[1]["label"] == "moderate"
        assert bins[1]["count"] == 1
        assert bins[2]["label"] == "critical"
        assert bins[2]["count"] == 1

    def test_empty_outcomes(self):
        bins = compute_risk_bins([])
        assert len(bins) == 3
        assert all(b["count"] == 0 for b in bins)

    def test_missing_eisv_skipped(self):
        outcomes = [_make_outcome(eisv_e=None, eisv_i=None, eisv_s=None)]
        bins = compute_risk_bins(outcomes)
        assert sum(b["count"] for b in bins) == 0

    def test_behavioral_risk_preferred(self):
        outcomes = [
            _make_outcome(
                eisv_e=0.9, eisv_i=0.9, eisv_s=0.1,
                detail={"behavioral_eisv": {"risk": 0.7}},
                is_bad=True,
            ),
        ]
        bins = compute_risk_bins(outcomes)
        assert bins[2]["count"] == 1


class TestBuildSummary:
    def test_summary_includes_counts(self):
        report = CorrelationReport(
            total_outcomes=10,
            good_outcomes=8,
            bad_outcomes=2,
            verdict_distribution={"safe": {"count": 8, "bad_rate": 0.1, "bad_count": 1, "avg_score": 0.9}},
            metric_correlations={"E": 0.85, "I": 0.7, "S": -0.6, "V": None, "PHI": 0.5, "COHERENCE": 0.4},
            risk_bins=[
                {"range": "0.00-0.35", "label": "healthy", "count": 7, "bad_count": 0, "bad_rate": 0.0},
                {"range": "0.35-0.60", "label": "moderate", "count": 2, "bad_count": 1, "bad_rate": 0.5},
                {"range": "0.60-1.01", "label": "critical", "count": 1, "bad_count": 1, "bad_rate": 1.0},
            ],
            summary="",
        )
        summary = _build_summary(report)
        assert "10" in summary
        assert "8 good" in summary
        assert "2 bad" in summary
        assert "E" in summary
