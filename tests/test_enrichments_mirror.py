"""
Tests for mirror signal enrichments in src/mcp_handlers/updates/enrichments.py.

Tests _detect_gaming, _search_kg_by_checkin_text, _generate_reflection_prompt,
and the async enrich_mirror_signals orchestrator.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.mcp_handlers.updates.enrichments import (
    _detect_gaming,
    _generate_reflection_prompt,
)


# ============================================================================
# Helper: minimal UpdateContext mock
# ============================================================================

def _make_ctx(
    *,
    response_text="",
    task_type="mixed",
    complexity=0.5,
    confidence=None,
    arguments=None,
    complexity_history=None,
    confidence_history=None,
):
    """Create a minimal UpdateContext-like object for testing."""
    ctx = MagicMock()
    ctx.response_text = response_text
    ctx.task_type = task_type
    ctx.complexity = complexity
    ctx.confidence = confidence
    ctx.arguments = arguments or {}
    ctx.response_data = {}
    ctx.agent_uuid = "test-uuid-1234"
    ctx.mcp_server = MagicMock()

    # Mock monitor with state histories
    monitor = MagicMock()
    state = MagicMock()

    if complexity_history is not None:
        state.complexity_history = complexity_history
    else:
        state.complexity_history = []

    if confidence_history is not None:
        state.confidence_history = confidence_history
    else:
        state.confidence_history = []

    monitor.state = state
    ctx.monitor = monitor

    return ctx


# ============================================================================
# _detect_gaming
# ============================================================================

class TestDetectGaming:

    def test_low_variance_complexity_detected(self):
        ctx = _make_ctx(complexity_history=[0.5, 0.5, 0.5, 0.5, 0.5])
        signals = _detect_gaming(ctx)
        assert len(signals) >= 1
        assert any("autopilot" in s.lower() for s in signals)

    def test_normal_variance_not_flagged(self):
        ctx = _make_ctx(complexity_history=[0.3, 0.5, 0.7, 0.4, 0.6])
        signals = _detect_gaming(ctx)
        # High variance should not trigger
        assert not any("autopilot" in s.lower() for s in signals)

    def test_too_few_reports_not_flagged(self):
        ctx = _make_ctx(complexity_history=[0.5, 0.5, 0.5])
        signals = _detect_gaming(ctx)
        assert len(signals) == 0

    def test_low_variance_confidence_detected(self):
        ctx = _make_ctx(
            complexity_history=[0.3, 0.5, 0.7, 0.4, 0.6],  # normal variance
            confidence_history=[0.8, 0.8, 0.8, 0.8, 0.8],  # low variance
        )
        signals = _detect_gaming(ctx)
        assert any("confidence" in s.lower() for s in signals)

    def test_no_monitor_returns_empty(self):
        ctx = _make_ctx()
        ctx.monitor = None
        signals = _detect_gaming(ctx)
        assert signals == []

    def test_near_identical_values_detected(self):
        ctx = _make_ctx(complexity_history=[0.501, 0.502, 0.500, 0.501, 0.500])
        signals = _detect_gaming(ctx)
        assert len(signals) >= 1
        assert any("variance" in s.lower() or "autopilot" in s.lower() for s in signals)


# ============================================================================
# _generate_reflection_prompt
# ============================================================================

class TestGenerateReflectionPrompt:

    def test_introspection_task_type(self):
        ctx = _make_ctx(task_type="introspection")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is not None
        assert "understanding" in prompt.lower()

    def test_debugging_task_type(self):
        ctx = _make_ctx(task_type="debugging")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is not None
        assert "assumption" in prompt.lower()

    def test_mixed_task_type_no_text(self):
        ctx = _make_ctx(task_type="mixed", response_text="")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is None

    def test_stuck_keyword_in_text(self):
        ctx = _make_ctx(task_type="mixed", response_text="I'm stuck on this problem")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is not None
        assert "unblock" in prompt.lower()

    def test_refactor_keyword_in_text(self):
        ctx = _make_ctx(task_type="mixed", response_text="Continuing the refactor of auth module")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is not None
        assert "structural" in prompt.lower()

    def test_testing_task_type(self):
        ctx = _make_ctx(task_type="testing")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is not None
        assert "covered" in prompt.lower()

    def test_feature_task_type(self):
        ctx = _make_ctx(task_type="feature")
        prompt = _generate_reflection_prompt(ctx)
        assert prompt is not None
        assert "simplest" in prompt.lower()
