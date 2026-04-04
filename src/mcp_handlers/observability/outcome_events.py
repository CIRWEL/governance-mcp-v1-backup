"""
Outcome Events Tool - Record measurable outcomes paired with EISV snapshots.

Enables validation of the EISV model by collecting real outcome data
(drawing completions, test results, task completions) alongside the
EISV state at outcome time.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
from ..utils import success_response, error_response
from ..decorators import mcp_tool
from src.logging_utils import get_logger
from src.mcp_handlers.shared import lazy_mcp_server as mcp_server
logger = get_logger(__name__)

# Outcome types that are considered "bad" by default
BAD_OUTCOME_TYPES = {"test_failed", "tool_rejected", "drawing_abandoned", "task_failed"}
GOOD_OUTCOME_TYPES = {"test_passed", "drawing_completed", "task_completed"}
NEUTRAL_OUTCOME_TYPES = {"trajectory_validated"}  # is_bad determined by score
VALID_OUTCOME_TYPES = BAD_OUTCOME_TYPES | GOOD_OUTCOME_TYPES | NEUTRAL_OUTCOME_TYPES

@mcp_tool("outcome_event", timeout=15.0)
async def handle_outcome_event(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Record an outcome event paired with the agent's current EISV snapshot."""
    from src.db import get_db
    from ..context import get_context_agent_id

    outcome_type = arguments.get("outcome_type")
    if not outcome_type:
        return [error_response(
            "outcome_type is required",
            error_code="MISSING_PARAM",
            error_category="validation_error",
        )]

    if outcome_type not in VALID_OUTCOME_TYPES:
        return [error_response(
            f"Unknown outcome_type '{outcome_type}'. Valid: {sorted(VALID_OUTCOME_TYPES)}",
            error_code="INVALID_PARAM",
            error_category="validation_error",
        )]

    # Get agent_id from context
    agent_id = get_context_agent_id()
    if not agent_id:
        # Fall back to explicit argument
        agent_id = arguments.get("agent_id")
    if not agent_id:
        return [error_response(
            "Could not determine agent_id from session context. Provide agent_id explicitly.",
            error_code="NO_AGENT_ID",
            error_category="identity_error",
        )]

    # Infer is_bad if not provided
    is_bad = arguments.get("is_bad")
    if is_bad is None:
        is_bad = outcome_type in BAD_OUTCOME_TYPES

    # Infer outcome_score if not provided
    outcome_score = arguments.get("outcome_score")
    if outcome_score is None:
        outcome_score = 0.0 if is_bad else 1.0

    detail = dict(arguments.get("detail") or {})

    # Fetch EISV snapshot for this outcome. Explicit snapshots are allowed so
    # exogenous callers can preserve the pairing even when they are outside a
    # stateful governance session.
    db = get_db()
    explicit_eisv = arguments.get("eisv_snapshot")
    snapshot_source = "missing"
    eisv = None
    if isinstance(explicit_eisv, dict):
        eisv = explicit_eisv
        snapshot_source = "explicit"
    else:
        eisv = await db.get_latest_eisv_by_agent_id(agent_id)
        if eisv:
            snapshot_source = "db_latest_eisv"

    eisv_e = eisv.get("E") if eisv else None
    eisv_i = eisv.get("I") if eisv else None
    eisv_s = eisv.get("S") if eisv else None
    eisv_v = eisv.get("V") if eisv else None
    eisv_phi = eisv.get("phi") if eisv else None
    eisv_verdict = eisv.get("verdict") if eisv else None
    eisv_coherence = eisv.get("coherence") if eisv else None
    eisv_regime = eisv.get("regime") if eisv else None
    detail["snapshot_source"] = snapshot_source
    if eisv is None:
        detail["snapshot_missing"] = True
    elif eisv.get("primary_eisv_source") and "primary_eisv_source" not in detail:
        detail["primary_eisv_source"] = eisv.get("primary_eisv_source")
    if eisv and eisv.get("behavioral_eisv") and "behavioral_eisv" not in detail:
        detail["behavioral_eisv"] = eisv.get("behavioral_eisv")

    # Embed behavioral EISV (observation-first, per-agent) alongside ODE snapshot
    try:
        monitor = mcp_server.monitors.get(agent_id) if hasattr(mcp_server, 'monitors') else None
        if monitor:
            bstate = getattr(monitor, '_behavioral_state', None)
            if bstate and bstate.confidence > 0 and 'behavioral_eisv' not in detail:
                detail['behavioral_eisv'] = {
                    'E': round(bstate.E, 4),
                    'I': round(bstate.I, 4),
                    'S': round(bstate.S, 4),
                    'V': round(bstate.V, 4),
                    'confidence': round(bstate.confidence, 4),
                }
    except Exception:
        pass  # Fail-safe: ODE snapshot still recorded

    # Insert
    outcome_id = await db.record_outcome_event(
        agent_id=agent_id,
        outcome_type=outcome_type,
        is_bad=is_bad,
        outcome_score=outcome_score,
        session_id=arguments.get("session_id"),
        eisv_e=eisv_e,
        eisv_i=eisv_i,
        eisv_s=eisv_s,
        eisv_v=eisv_v,
        eisv_phi=eisv_phi,
        eisv_verdict=eisv_verdict,
        eisv_coherence=eisv_coherence,
        eisv_regime=eisv_regime,
        detail=detail,
    )

    if not outcome_id:
        return [error_response(
            "Failed to record outcome event (database error)",
            error_code="DB_ERROR",
            error_category="system_error",
        )]

    logger.info(
        "Recorded outcome: type=%s is_bad=%s score=%.2f agent=%s verdict=%s",
        outcome_type, is_bad, outcome_score, agent_id, eisv_verdict,
    )

    # Record calibration from outcome event
    _confidence = arguments.get('confidence')
    if _confidence is not None:
        _confidence = float(_confidence)
    else:
        try:
            monitor = mcp_server.monitors.get(agent_id)
            if monitor and monitor._prev_confidence is not None:
                _confidence = float(monitor._prev_confidence)
        except Exception:
            pass

    if _confidence is not None:
        try:
            from src.calibration import calibration_checker
            calibration_checker.record_prediction(
                confidence=_confidence,
                predicted_correct=(_confidence >= 0.5),
                actual_correct=float(outcome_score),
            )
            # Test outcomes are strong exogenous signals — record tactical too
            if outcome_type in ('test_passed', 'test_failed'):
                calibration_checker.record_tactical_decision(
                    confidence=_confidence,
                    decision='proceed',
                    immediate_outcome=not is_bad,
                )
        except Exception as e_cal:
            logger.debug(f"Calibration from outcome_event skipped: {e_cal}")

    return success_response({
        "outcome_id": outcome_id,
        "outcome_type": outcome_type,
        "is_bad": is_bad,
        "outcome_score": outcome_score,
        "eisv_snapshot": {
            "E": eisv_e,
            "I": eisv_i,
            "S": eisv_s,
            "V": eisv_v,
            "phi": eisv_phi,
            "verdict": eisv_verdict,
            "coherence": eisv_coherence,
            "regime": eisv_regime,
            "primary_eisv": eisv.get("primary_eisv") if eisv else None,
            "primary_eisv_source": eisv.get("primary_eisv_source") if eisv else None,
            "behavioral_eisv": eisv.get("behavioral_eisv") if eisv else None,
            "ode_eisv": eisv.get("ode_eisv") if eisv else None,
            "ode_diagnostics": eisv.get("ode_diagnostics") if eisv else None,
        } if eisv else None,
    })


@mcp_tool("outcome_correlation", timeout=30.0)
async def handle_outcome_correlation(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Run outcome correlation study: does EISV instability predict bad outcomes?"""
    from src.outcome_correlation import OutcomeCorrelation
    from ..context import get_context_agent_id
    import dataclasses

    agent_id = arguments.get("agent_id") or get_context_agent_id()
    since_hours = float(arguments.get("since_hours", 168))

    try:
        study = OutcomeCorrelation()
        report = await study.run(agent_id=agent_id, since_hours=since_hours)

        if report.total_outcomes == 0:
            return [error_response(
                f"No outcome events found in the last {since_hours:.0f} hours"
                + (f" for agent {agent_id}" if agent_id else ""),
                error_code="NO_DATA",
                error_category="validation_error",
            )]

        return success_response(dataclasses.asdict(report))
    except Exception as e:
        logger.error(f"Outcome correlation failed: {e}")
        return [error_response(
            f"Correlation study failed: {e}",
            error_code="STUDY_ERROR",
            error_category="system_error",
        )]
