"""
Automated Ground Truth Collection for Calibration

SELF-GOVERNANCE PRINCIPLE (2025-12-13):
The system should not assume humans are the ground truth oracle. Instead:
- Observable outcomes (tests pass, files created, commands succeed) are primary signals
- Peer consensus is a secondary signal  
- Human feedback is optional enhancement, not required

This module automatically evaluates decisions based on OBJECTIVE signals:
1. Agent trajectory health (did they get stuck/paused?)
2. Test results (did pytest pass after code changes?)
3. Linter status (did code lint cleanly?)
4. Command outcomes (did terminal commands succeed?)
5. File operations (were expected files created?)

Human calibration via update_calibration_ground_truth is still available
but should be the exception, not the rule.
"""

import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Project root
project_root = Path(__file__).parent.parent


# =============================================================================
# OBJECTIVE OUTCOME EVALUATORS
# These evaluate ground truth from observable signals, NOT human judgment
# =============================================================================

def evaluate_test_outcome(test_run_result: Dict) -> Optional[bool]:
    """
    Evaluate ground truth from pytest/test results.
    
    Args:
        test_run_result: Dict with keys like 'passed', 'failed', 'errors', 'exit_code'
        
    Returns:
        True if tests passed, False if failed, None if can't evaluate
    """
    if not test_run_result:
        return None
    
    # Check exit code first (most reliable)
    exit_code = test_run_result.get('exit_code')
    if exit_code is not None:
        return exit_code == 0
    
    # Fallback to pass/fail counts
    failed = test_run_result.get('failed', 0)
    errors = test_run_result.get('errors', 0)
    passed = test_run_result.get('passed', 0)
    
    if failed > 0 or errors > 0:
        return False
    elif passed > 0:
        return True
    
    return None


def evaluate_command_outcome(command_result: Dict) -> Optional[bool]:
    """
    Evaluate ground truth from terminal command execution.
    
    Args:
        command_result: Dict with 'exit_code', 'success', 'error' etc.
        
    Returns:
        True if command succeeded, False if failed, None if can't evaluate
    """
    if not command_result:
        return None
    
    # Check explicit success flag
    if 'success' in command_result:
        return bool(command_result['success'])
    
    # Check exit code
    exit_code = command_result.get('exit_code')
    if exit_code is not None:
        return exit_code == 0
    
    # Check for error field
    if command_result.get('error'):
        return False
    
    return None


def evaluate_file_operation(file_path: str, expected_exists: bool = True) -> Optional[bool]:
    """
    Evaluate ground truth from file operation outcome.
    
    Args:
        file_path: Path to check
        expected_exists: Whether file should exist after operation
        
    Returns:
        True if outcome matches expectation, False otherwise
    """
    try:
        exists = Path(file_path).exists()
        return exists == expected_exists
    except Exception:
        return None


def evaluate_lint_outcome(lint_result: Dict) -> Optional[bool]:
    """
    Evaluate ground truth from linter results.
    
    Args:
        lint_result: Dict with 'errors', 'warnings', 'issues' etc.
        
    Returns:
        True if no errors, False if errors present, None if can't evaluate
    """
    if not lint_result:
        return None
    
    # Check for explicit error count
    errors = lint_result.get('errors', lint_result.get('error_count', 0))
    if isinstance(errors, list):
        errors = len(errors)
    
    if errors > 0:
        return False
    
    # If we have any result and no errors, consider it success
    if lint_result:
        return True
    
    return None


# =============================================================================
# COMPOSITE EVALUATOR
# Combines multiple objective signals
# =============================================================================

def evaluate_objective_outcomes(outcomes: Dict) -> Optional[bool]:
    """
    Evaluate ground truth from multiple objective outcomes.
    
    Uses weighted voting - any failure signal = failure (conservative).
    
    Args:
        outcomes: Dict with optional keys: 'tests', 'commands', 'files', 'lint'
        
    Returns:
        True if all signals pass, False if any fail, None if no signals
    """
    results = []
    
    if 'tests' in outcomes:
        result = evaluate_test_outcome(outcomes['tests'])
        if result is not None:
            results.append(('tests', result))
    
    if 'commands' in outcomes:
        for cmd in (outcomes['commands'] if isinstance(outcomes['commands'], list) else [outcomes['commands']]):
            result = evaluate_command_outcome(cmd)
            if result is not None:
                results.append(('command', result))
    
    if 'files' in outcomes:
        for file_check in outcomes['files']:
            path = file_check.get('path')
            expected = file_check.get('expected_exists', True)
            if path:
                result = evaluate_file_operation(path, expected)
                if result is not None:
                    results.append(('file', result))
    
    if 'lint' in outcomes:
        result = evaluate_lint_outcome(outcomes['lint'])
        if result is not None:
            results.append(('lint', result))
    
    if not results:
        return None
    
    # Conservative: any failure = overall failure
    if any(not r[1] for r in results):
        logger.info(f"Objective evaluation FAILED: {[r for r in results if not r[1]]}")
        return False
    
    logger.info(f"Objective evaluation PASSED: {len(results)} signals all positive")
    return True


def evaluate_decision_outcome(entry: Dict, metadata: Dict) -> Optional[bool]:
    """
    Evaluate whether a decision was correct based on agent outcomes.
    
    This evaluates STRATEGIC calibration (trajectory health) - whether agents
    with high confidence ended up in healthy states.
    
    Args:
        entry: Audit log entry with decision details
        metadata: Agent metadata dict
        
    Returns:
        True if decision was correct, False if incorrect, None if can't evaluate
    """
    agent_id = entry.get('agent_id', 'unknown')
    decision = entry.get('details', {}).get('decision', 'unknown')
    risk_score = entry.get('details', {}).get('risk_score', 0)
    coherence = entry.get('details', {}).get('coherence', 0)
    
    agent_meta = metadata.get(agent_id, {})
    status = agent_meta.get('status', 'unknown')
    loop_detected = agent_meta.get('loop_detected_at')
    paused_at = agent_meta.get('paused_at')
    
    # Evaluate actual correctness based on outcomes (STRATEGIC calibration)
    # This measures trajectory health: "Did agents with high confidence end up in good states?"
    
    # Check if decision was "proceed" (for outcome evaluation logic)
    decision_was_proceed = decision == 'proceed'
    
    if decision_was_proceed:
        # "Proceed" decision - check if agent got stuck
        if status == 'paused' or loop_detected or paused_at:
            return False  # Should have paused but didn't
        elif status in ['active', 'waiting_input', 'archived']:
            return True  # Agent continued successfully
        else:
            return None  # Can't evaluate
    else:
        # "Pause" decision - check if it was appropriate
        if risk_score > 0.6 or coherence < 0.4:
            return True  # Pause was appropriate
        elif risk_score < 0.4 and coherence > 0.5:
            return False  # Pause was too conservative
        else:
            return None  # Can't evaluate


async def collect_ground_truth_automatically(
    min_age_hours: float = 2.0,
    max_decisions: int = 50,
    dry_run: bool = False,
    rebuild: bool = False
) -> Dict:
    """
    Automatically collect ground truth for decisions older than min_age_hours.
    
    Args:
        min_age_hours: Minimum age of decisions to evaluate (default: 2 hours)
        max_decisions: Maximum number of decisions to process per run (0 = no limit)
        dry_run: If True, don't update calibration, just return what would be updated
        rebuild: If True, reset calibration and rebuild from scratch (for fixing inverted data)
        
    Returns:
        Dict with statistics about collected ground truth
    """
    from src.calibration import calibration_checker
    from src.audit_log import AuditLogger
    
    audit_logger = AuditLogger()
    
    # Load agent metadata (prefer server loader, which supports SQLite backend).
    # This avoids hard dependency on data/agent_metadata.json snapshots.
    metadata = {}
    try:
        import src.mcp_server_std as mcp_server
        # Ensure latest metadata is loaded using configured backend (json/sqlite/auto)
        mcp_server.load_metadata()
        # Convert AgentMetadata objects to dicts (this module expects dict-like access)
        for aid, meta_obj in getattr(mcp_server, "agent_metadata", {}).items():
            try:
                if hasattr(meta_obj, "to_dict"):
                    metadata[aid] = meta_obj.to_dict()
                elif isinstance(meta_obj, dict):
                    metadata[aid] = meta_obj
            except Exception:
                continue
    except Exception as e:
        # Fallback: try JSON snapshot if present (backward compatibility)
        metadata_path = project_root / "data" / "agent_metadata.json"
        if not metadata_path.exists():
            logger.warning(f"Agent metadata not found (and server load failed: {e}), skipping ground truth collection")
            return {"updated": 0, "skipped": 0, "errors": 0}
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    
    # If rebuilding, reset calibration first
    if rebuild and not dry_run:
        logger.info("Rebuilding calibration from scratch (rebuild=True)")
        calibration_checker.reset()
        calibration_checker.save_state()
    
    # Query recent decisions
    cutoff_time = (datetime.now() - timedelta(hours=min_age_hours)).isoformat()
    entries = audit_logger.query_audit_log(
        event_type="auto_attest",
        start_time=None,  # From beginning
        end_time=cutoff_time  # Up to cutoff
    )
    
    if not entries:
        return {"updated": 0, "skipped": 0, "errors": 0, "message": "No decisions found"}
    
    # If rebuild mode, process all entries (no limit)
    if rebuild:
        max_decisions = 0  # 0 = no limit
    
    # Filter to decisions that need ground truth
    # Check which ones already have ground truth by looking at calibration state
    state = calibration_checker.bin_stats
    
    # Get timestamps that already have ground truth (approximate check)
    # This is a heuristic - we'll skip decisions that are very recent in calibration
    processed = 0
    updated = 0
    skipped = 0
    errors = 0
    
    # Group by timestamp to avoid duplicates
    seen_timestamps = set()
    
    # Process entries (limit if max_decisions > 0)
    entries_to_process = entries if max_decisions == 0 else entries[:max_decisions]
    
    for entry in entries_to_process:
        timestamp = entry.get('timestamp')
        if not timestamp or timestamp in seen_timestamps:
            continue
        
        seen_timestamps.add(timestamp)
        processed += 1
        
        try:
            # Evaluate outcome
            actual_correct = evaluate_decision_outcome(entry, metadata)
            
            if actual_correct is None:
                skipped += 1
                continue
            
            if dry_run:
                updated += 1
                confidence = entry.get('confidence', 0.0)
                # Use confidence-based prediction: high confidence = predicted correct
                predicted_correct = float(confidence) >= 0.5
                logger.info(f"[DRY RUN] Would update: {timestamp} -> confidence={confidence:.2f}, predicted_correct={predicted_correct}, actual_correct={actual_correct}")
            else:
                # Update calibration (STRATEGIC: trajectory health)
                confidence = entry.get('confidence', 0.0)
                # FIXED: Use confidence-based prediction, not decision-based
                # High confidence (>=0.5) = we predicted correct
                # Low confidence (<0.5) = we predicted incorrect
                predicted_correct = float(confidence) >= 0.5
                
                calibration_checker.update_ground_truth(
                    confidence=float(confidence),
                    predicted_correct=bool(predicted_correct),
                    actual_correct=bool(actual_correct)
                )
                
                updated += 1
                logger.info(f"Auto-updated ground truth: {timestamp} -> actual_correct={actual_correct}")
        
        except Exception as e:
            errors += 1
            logger.error(f"Error processing decision {timestamp}: {e}", exc_info=True)
    
    if not dry_run and updated > 0:
        # Save calibration state
        calibration_checker.save_state()
    
    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run
    }


async def auto_ground_truth_collector_task(interval_hours: float = 6.0):
    """
    Background task that periodically collects ground truth.
    
    Args:
        interval_hours: How often to run collection (default: 6 hours)
    """
    logger.info(f"Auto ground truth collector started (interval: {interval_hours}h)")
    
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)  # Convert to seconds
            
            logger.info("Running automatic ground truth collection...")
            result = await collect_ground_truth_automatically(
                min_age_hours=2.0,
                max_decisions=50,
                dry_run=False
            )
            
            logger.info(
                f"Ground truth collection complete: "
                f"updated={result['updated']}, skipped={result['skipped']}, errors={result['errors']}"
            )
        
        except Exception as e:
            logger.error(f"Error in auto ground truth collector: {e}", exc_info=True)
            # Wait before retrying
            await asyncio.sleep(3600)  # Wait 1 hour on error

