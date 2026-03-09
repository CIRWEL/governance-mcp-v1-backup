"""Step 2: Verify Trajectory Identity."""

from typing import Any, Dict

from src.logging_utils import get_logger

logger = get_logger(__name__)


async def verify_trajectory(name: str, arguments: Dict[str, Any], ctx) -> Any:
    """Non-blocking trajectory signature verification."""
    try:
        traj_sig = arguments.get("trajectory_signature") if arguments else None
        if traj_sig and isinstance(traj_sig, dict) and ctx.bound_agent_id:
            from src.trajectory_identity import TrajectorySignature, verify_trajectory_identity
            from ..context import set_trajectory_confidence

            sig = TrajectorySignature.from_dict(traj_sig)
            verification = await verify_trajectory_identity(ctx.bound_agent_id, sig)

            if verification and not verification.get("error"):
                coherence_sim = verification.get("tiers", {}).get("coherence", {}).get("similarity")
                lineage_sim = verification.get("tiers", {}).get("lineage", {}).get("similarity")
                sims = [s for s in [coherence_sim, lineage_sim] if s is not None]
                if sims:
                    traj_conf = min(sims)
                    ctx.trajectory_confidence_token = set_trajectory_confidence(traj_conf)

                if not verification.get("verified"):
                    logger.warning(
                        f"[TRAJECTORY] Verification FAILED for {ctx.bound_agent_id[:8]}...: "
                        f"failed_tiers={verification.get('failed_tiers', [])}"
                    )
    except Exception as e:
        logger.debug(f"[TRAJECTORY] Verification skipped: {e}")

    return name, arguments, ctx
