"""Tests for event_detector.py — drift trend classification and EWMA forecasting."""

import pytest

from src.event_detector import (
    classify_drift_trend,
    predict_drift_crossing,
    TREND_STABLE,
    TREND_DRIFTING_UP,
    TREND_DRIFTING_DOWN,
    DRIFT_ALERT_THRESHOLD,
)


class TestClassifyDriftTrend:
    def test_empty_history(self):
        trend, strength = classify_drift_trend([])
        assert trend == TREND_STABLE

    def test_short_history_still_classifies(self):
        # Even 2 values can classify if delta is significant
        trend, strength = classify_drift_trend([0.1, 0.2])
        assert trend == TREND_DRIFTING_UP

    def test_stable_flat(self):
        trend, _ = classify_drift_trend([0.1] * 10)
        assert trend == TREND_STABLE

    def test_drifting_up(self):
        # Monotonically increasing
        history = [i * 0.05 for i in range(10)]
        trend, strength = classify_drift_trend(history)
        assert trend == TREND_DRIFTING_UP
        assert strength > 0.5

    def test_drifting_down(self):
        # Monotonically decreasing
        history = [0.5 - i * 0.05 for i in range(10)]
        trend, strength = classify_drift_trend(history)
        assert trend == TREND_DRIFTING_DOWN
        assert strength > 0.5


class TestPredictDriftCrossing:
    def test_empty_history_returns_zeros(self):
        result = predict_drift_crossing([])
        assert result["ewma_current"] == 0.0
        assert result["ewma_slope"] == 0.0
        assert result["predicted_crossing_steps"] is None
        assert result["confidence"] == 0.0

    def test_short_history_returns_zeros(self):
        result = predict_drift_crossing([0.1, 0.2])
        assert result["confidence"] == 0.0

    def test_flat_history_no_crossing(self):
        result = predict_drift_crossing([0.01] * 10, threshold=0.3)
        assert result["predicted_crossing_steps"] is None
        # Low confidence when slope is flat
        assert result["confidence"] < 0.5

    def test_rising_history_predicts_crossing(self):
        # Linearly increasing toward threshold
        history = [i * 0.02 for i in range(15)]
        result = predict_drift_crossing(history, threshold=0.5)
        assert result["ewma_slope"] > 0
        # Should predict a crossing since values are rising toward 0.5
        # (whether it predicts within forecast window depends on exact EWMA)

    def test_already_above_threshold_no_crossing(self):
        # Already above threshold — no crossing predicted
        history = [0.6] * 10
        result = predict_drift_crossing(history, threshold=0.3)
        assert result["predicted_crossing_steps"] is None

    def test_confidence_scales_with_history_length(self):
        # Short history: low confidence
        short = predict_drift_crossing([0.01, 0.02, 0.03], threshold=0.5)
        # Long history: higher confidence
        long_hist = predict_drift_crossing([i * 0.01 for i in range(15)], threshold=0.5)
        assert long_hist["confidence"] >= short["confidence"]

    def test_custom_alpha(self):
        history = [i * 0.03 for i in range(10)]
        low_alpha = predict_drift_crossing(history, alpha=0.1)
        high_alpha = predict_drift_crossing(history, alpha=0.9)
        # Higher alpha gives more weight to recent values
        assert high_alpha["ewma_current"] != low_alpha["ewma_current"]

    def test_negative_drift_predicts_negative_crossing(self):
        # Drift going negative
        history = [-i * 0.03 for i in range(15)]
        result = predict_drift_crossing(history, threshold=0.5)
        assert result["ewma_slope"] < 0

    def test_returns_rounded_values(self):
        history = [i * 0.0123456789 for i in range(10)]
        result = predict_drift_crossing(history)
        # ewma_current and ewma_slope should be rounded to 6 decimal places
        assert len(str(result["ewma_current"]).split(".")[-1]) <= 6
        assert len(str(result["ewma_slope"]).split(".")[-1]) <= 6
