"""Step 8: Pattern tracking and cognitive loop detection."""

from typing import Any, Dict

from src.logging_utils import get_logger

logger = get_logger(__name__)


async def track_patterns(name: str, arguments: Dict[str, Any], ctx) -> Any:
    """Cognitive loop detection and hypothesis tracking."""
    try:
        from src.pattern_tracker import get_pattern_tracker
        from ..utils import get_bound_agent_id
        from ..support.pattern_helpers import record_hypothesis_if_needed, check_untested_hypotheses, mark_hypothesis_tested

        tracker = get_pattern_tracker()
        agent_id = get_bound_agent_id(arguments)
        if agent_id:
            loop_result = tracker.record_tool_call(agent_id, name, arguments)
            if loop_result and loop_result.get("detected"):
                logger.warning(f"[PATTERN_DETECTION] Agent {agent_id[:8]}...: {loop_result['message']}")

            record_hypothesis_if_needed(agent_id, name, arguments)

            hypothesis_warning = check_untested_hypotheses(agent_id)
            if hypothesis_warning:
                logger.warning(f"[PATTERN_DETECTION] Agent {agent_id[:8]}...: {hypothesis_warning}")

            mark_hypothesis_tested(agent_id, name, arguments)
            tracker.record_progress(agent_id)
    except Exception as e:
        logger.debug(f"Pattern tracking failed: {e}")

    return name, arguments, ctx
