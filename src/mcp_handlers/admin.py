"""
Admin tool handlers.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
import json
import sys
from datetime import datetime
from pathlib import Path
from .utils import success_response, error_response, require_agent_id, require_registered_agent
from .decorators import mcp_tool
from src.logging_utils import get_logger

logger = get_logger(__name__)

# Import from mcp_server_std module
if 'src.mcp_server_std' in sys.modules:
    mcp_server = sys.modules['src.mcp_server_std']
else:
    import src.mcp_server_std as mcp_server


@mcp_tool("get_server_info", timeout=10.0, rate_limit_exempt=True)
async def handle_get_server_info(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get MCP server version, process information, and health status"""
    import time
    # Import from mcp_server_std module (handles both direct import and module access)
    if 'src.mcp_server_std' in sys.modules:
        mcp_server = sys.modules['src.mcp_server_std']
    else:
        import src.mcp_server_std as mcp_server
    
    if mcp_server.PSUTIL_AVAILABLE:
        import psutil
        
        # Get all MCP server processes
        server_processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'status']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and any('mcp_server_std.py' in str(arg) for arg in cmdline):
                        pid = proc.info['pid']
                        create_time = proc.info.get('create_time', 0)
                        uptime_seconds = time.time() - create_time
                        uptime_minutes = int(uptime_seconds / 60)
                        uptime_hours = int(uptime_minutes / 60)
                        
                        server_processes.append({
                            "pid": pid,
                            "is_current": pid == mcp_server.CURRENT_PID,
                            "uptime_seconds": int(uptime_seconds),
                            "uptime_formatted": f"{uptime_hours}h {uptime_minutes % 60}m",
                            "status": proc.info.get('status', 'unknown')
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            server_processes = [{"error": f"Could not enumerate processes: {e}"}]
        
        # Calculate current process uptime
        try:
            current_proc = psutil.Process(mcp_server.CURRENT_PID)
            current_uptime = time.time() - current_proc.create_time()
        except:
            current_uptime = 0
    else:
        server_processes = [{"error": "psutil not available - cannot enumerate processes"}]
        current_uptime = 0
    
    current_uptime_minutes = int(current_uptime / 60)
    current_uptime_hours = int(current_uptime_minutes / 60)
    
    return success_response({
        "server_version": mcp_server.SERVER_VERSION,
        "build_date": mcp_server.SERVER_BUILD_DATE,
        "current_pid": mcp_server.CURRENT_PID,
        "current_uptime_seconds": int(current_uptime),
        "current_uptime_formatted": f"{current_uptime_hours}h {current_uptime_minutes % 60}m",
        "total_server_processes": len([p for p in server_processes if "error" not in p]),
        "server_processes": server_processes,
        "pid_file_exists": mcp_server.PID_FILE.exists(),
        "max_keep_processes": mcp_server.MAX_KEEP_PROCESSES,
        "health": "healthy"
    })


@mcp_tool("get_tool_usage_stats", timeout=15.0, rate_limit_exempt=True)
async def handle_get_tool_usage_stats(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get tool usage statistics to identify which tools are actually used vs unused"""
    from src.tool_usage_tracker import get_tool_usage_tracker
    
    window_hours = arguments.get("window_hours", 24 * 7)  # Default: 7 days
    tool_name = arguments.get("tool_name")
    agent_id = arguments.get("agent_id")
    
    tracker = get_tool_usage_tracker()
    stats = tracker.get_usage_stats(
        window_hours=window_hours,
        tool_name=tool_name,
        agent_id=agent_id
    )
    
    return success_response(stats)


@mcp_tool("health_check", timeout=10.0, rate_limit_exempt=True)
async def handle_health_check(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle health_check tool - quick health check of system components"""
    import asyncio
    from src.calibration import calibration_checker
    from src.telemetry import telemetry_collector
    from src.audit_log import audit_logger
    # Knowledge layer REMOVED (archived November 28, 2025) - was causing agent unresponsiveness
    
    checks = {}
    loop = asyncio.get_running_loop()
    
    # Check calibration (may trigger lazy initialization - wrap in executor to avoid blocking)
    try:
        # Accessing calibration_checker may trigger lazy initialization which does file I/O
        pending = await loop.run_in_executor(None, lambda: calibration_checker.get_pending_updates())
        checks["calibration"] = {
            "status": "healthy",
            "pending_updates": pending
        }
    except Exception as e:
        checks["calibration"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check telemetry/audit log (filesystem operation - run in executor)
    try:
        log_exists = await loop.run_in_executor(None, lambda: audit_logger.log_file.exists())
        checks["telemetry"] = {
            "status": "healthy" if log_exists else "warning",
            "audit_log_exists": log_exists
        }
    except Exception as e:
        checks["telemetry"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Knowledge layer check REMOVED (archived November 28, 2025)
    # Was causing agent unresponsiveness on Claude Desktop
    
    # Check data directory (filesystem operation - run in executor)
    try:
        data_dir = Path(mcp_server.project_root) / "data"
        data_dir_exists = await loop.run_in_executor(None, lambda: data_dir.exists())
        checks["data_directory"] = {
            "status": "healthy" if data_dir_exists else "warning",
            "exists": data_dir_exists
        }
    except Exception as e:
        checks["data_directory"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Overall health status
    all_healthy = all(c.get("status") == "healthy" for c in checks.values())
    overall_status = "healthy" if all_healthy else "moderate"
    
    return success_response({
        "status": overall_status,
        "version": "2.0.0",
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    })


@mcp_tool("check_calibration", timeout=10.0, rate_limit_exempt=True)
async def handle_check_calibration(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Check calibration of confidence estimates"""
    from src.calibration import calibration_checker
    
    is_calibrated, metrics = calibration_checker.check_calibration()
    
    # Calculate overall accuracy from bins
    bins_data = metrics.get('bins', {})
    total_samples = sum(bin_data.get('count', 0) for bin_data in bins_data.values())
    total_correct = sum(
        int(bin_data.get('count', 0) * bin_data.get('accuracy', 0))
        for bin_data in bins_data.values()
    )
    overall_accuracy = total_correct / total_samples if total_samples > 0 else 0.0
    
    # Calculate confidence distribution from bins
    confidence_values = []
    for bin_key, bin_data in bins_data.items():
        count = bin_data.get('count', 0)
        expected_acc = bin_data.get('expected_accuracy', 0.0)
        # Add confidence value for each sample in this bin
        confidence_values.extend([expected_acc] * count)
    
    if confidence_values:
        import numpy as np
        conf_dist = {
            "mean": float(np.mean(confidence_values)),
            "std": float(np.std(confidence_values)),
            "min": float(np.min(confidence_values)),
            "max": float(np.max(confidence_values))
        }
    else:
        conf_dist = {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    
    return success_response({
        "calibrated": is_calibrated,
        "accuracy": overall_accuracy,
        "confidence_distribution": conf_dist,
        "pending_updates": calibration_checker.get_pending_updates(),
        "total_samples": total_samples,
        "message": "Calibration check complete"
    })


@mcp_tool("update_calibration_ground_truth", timeout=10.0)
async def handle_update_calibration_ground_truth(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Update calibration with ground truth after human review
    
    Supports two modes:
    1. Direct mode: Provide confidence, predicted_correct, actual_correct directly
    2. Timestamp mode: Provide timestamp (and optional agent_id), actual_correct. 
       System looks up confidence and decision from audit log.
    """
    from src.calibration import calibration_checker
    from src.audit_log import AuditLogger
    from datetime import datetime
    
    # Check if using timestamp-based mode
    timestamp = arguments.get("timestamp")
    agent_id = arguments.get("agent_id")
    actual_correct = arguments.get("actual_correct")
    
    if timestamp:
        # TIMESTAMP MODE: Look up confidence and decision from audit log
        if actual_correct is None:
            return [error_response("Missing required parameter: actual_correct (required for timestamp mode)")]
        
        try:
            # Parse timestamp
            if isinstance(timestamp, str):
                decision_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                return [error_response("timestamp must be ISO format string (e.g., '2025-12-08T13:00:00')")]
            
            # Query audit log for decision at that timestamp
            # Use a small window around the timestamp to account for slight timing differences
            from datetime import timedelta
            window_start = (decision_time - timedelta(seconds=5)).isoformat()
            window_end = (decision_time + timedelta(seconds=5)).isoformat()
            
            audit_logger = AuditLogger()
            entries = audit_logger.query_audit_log(
                agent_id=agent_id,
                event_type="auto_attest",
                start_time=window_start,
                end_time=window_end
            )
            
            if not entries:
                return [error_response(
                    f"No decision found at timestamp {timestamp}" + 
                    (f" for agent {agent_id}" if agent_id else ""),
                    details={
                        "suggestion": "Check timestamp format (ISO) and ensure decision was logged",
                        "related_tools": ["get_telemetry_metrics"]
                    }
                )]
            
            # Use most recent entry if multiple found (shouldn't happen with exact timestamp, but be safe)
            entry = entries[-1]
            confidence = entry.get("confidence", 0.0)
            decision = entry.get("details", {}).get("decision", "unknown")
            predicted_correct = decision == "proceed"  # proceed = predicted correct
            
            # Update calibration
            calibration_checker.update_ground_truth(
                confidence=float(confidence),
                predicted_correct=bool(predicted_correct),
                actual_correct=bool(actual_correct)
            )
            
            # Save calibration state
            calibration_checker.save_state()
            
            return success_response({
                "message": "Ground truth updated successfully (timestamp mode)",
                "looked_up": {
                    "confidence": confidence,
                    "decision": decision,
                    "predicted_correct": predicted_correct
                },
                "pending_updates": calibration_checker.get_pending_updates()
            })
            
        except ValueError as e:
            return [error_response(f"Invalid timestamp format: {str(e)}")]
        except Exception as e:
            return [error_response(f"Error looking up decision: {str(e)}")]
    
    else:
        # DIRECT MODE: Require all parameters
        confidence = arguments.get("confidence")
        predicted_correct = arguments.get("predicted_correct")
        
        if confidence is None or predicted_correct is None or actual_correct is None:
            return [error_response(
                "Missing required parameters. Use either:\n"
                "1. Direct mode: confidence, predicted_correct, actual_correct\n"
                "2. Timestamp mode: timestamp, actual_correct (optional: agent_id)",
                details={
                    "direct_mode": {"required": ["confidence", "predicted_correct", "actual_correct"]},
                    "timestamp_mode": {"required": ["timestamp", "actual_correct"], "optional": ["agent_id"]}
                }
            )]
        
        try:
            calibration_checker.update_ground_truth(
                confidence=float(confidence),
                predicted_correct=bool(predicted_correct),
                actual_correct=bool(actual_correct)
            )
            
            # Save calibration state after update
            calibration_checker.save_state()
            
            return success_response({
                "message": "Ground truth updated successfully (direct mode)",
                "pending_updates": calibration_checker.get_pending_updates()
            })
        except Exception as e:
            return [error_response(str(e))]


@mcp_tool("backfill_calibration_from_dialectic", timeout=30.0, rate_limit_exempt=True)
async def handle_backfill_calibration_from_dialectic(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Retroactively update calibration from historical resolved verification-type dialectic sessions.
    
    This processes all existing resolved verification sessions that were created before
    automatic calibration was implemented, ensuring they contribute to calibration.
    
    USE CASES:
    - One-time migration after implementing automatic calibration
    - Backfill historical peer verification data
    - Ensure all resolved verification sessions contribute to calibration
    
    RETURNS:
    {
      "success": true,
      "processed": int,
      "updated": int,
      "errors": int,
      "sessions": [{"session_id": "...", "agent_id": "...", "status": "..."}]
    }
    """
    from src.mcp_handlers.dialectic import backfill_calibration_from_historical_sessions
    
    try:
        results = await backfill_calibration_from_historical_sessions()
        return success_response({
            "success": True,
            "message": f"Backfill complete: {results['updated']}/{results['processed']} sessions updated",
            **results
        })
    except Exception as e:
        return [error_response(f"Error during backfill: {str(e)}")]


@mcp_tool("get_telemetry_metrics", timeout=15.0, rate_limit_exempt=True)
async def handle_get_telemetry_metrics(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get comprehensive telemetry metrics: skip rates, confidence distributions, calibration status"""
    import asyncio
    from src.telemetry import TelemetryCollector
    
    telemetry = TelemetryCollector()
    
    agent_id = arguments.get("agent_id")
    window_hours = arguments.get("window_hours", 24)
    
    # Run blocking I/O operations in executor to prevent hanging
    loop = asyncio.get_running_loop()  # Use get_running_loop() instead of deprecated get_event_loop()
    
    try:
        # Execute blocking operations in thread pool
        skip_metrics, conf_dist, calibration_metrics, suspicious = await asyncio.gather(
            loop.run_in_executor(None, telemetry.get_skip_rate_metrics, agent_id, window_hours),
            loop.run_in_executor(None, telemetry.get_confidence_distribution, agent_id, window_hours),
            loop.run_in_executor(None, telemetry.get_calibration_metrics),
            loop.run_in_executor(None, telemetry.detect_suspicious_patterns, agent_id)
        )
        
        return success_response({
            "agent_id": agent_id or "all_agents",
            "window_hours": window_hours,
            "skip_rate_metrics": skip_metrics,
            "confidence_distribution": conf_dist,
            "calibration": calibration_metrics,
            "suspicious_patterns": suspicious
        })
    except Exception as e:
        logger.error(f"Error in get_telemetry_metrics: {e}")
        return [error_response(f"Error collecting telemetry: {str(e)}")]


@mcp_tool("reset_monitor", timeout=10.0)
async def handle_reset_monitor(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Reset governance state for an agent"""
    # PROACTIVE GATE: Require agent to be registered
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]  # Returns onboarding guidance if not registered
    
    if agent_id in mcp_server.monitors:
        del mcp_server.monitors[agent_id]
        message = f"Monitor reset for agent: {agent_id}"
    else:
        message = f"Monitor not found for agent: {agent_id} (may not be loaded)"
    
    return success_response({
        "message": message,
        "agent_id": agent_id
    })


@mcp_tool("cleanup_stale_locks", timeout=30.0, rate_limit_exempt=True)
async def handle_cleanup_stale_locks(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Clean up stale lock files that are no longer held by active processes"""
    try:
        from src.lock_cleanup import cleanup_stale_state_locks
        
        max_age = arguments.get('max_age_seconds', 300.0)
        dry_run = arguments.get('dry_run', False)
        
        project_root = Path(__file__).parent.parent.parent
        result = cleanup_stale_state_locks(project_root=project_root, max_age_seconds=max_age, dry_run=dry_run)
        
        return success_response({
            "cleaned": result['cleaned'],
            "kept": result['kept'],
            "errors": result['errors'],
            "dry_run": dry_run,
            "max_age_seconds": max_age,
            "cleaned_locks": result.get('cleaned_locks', []),
            "kept_locks": result.get('kept_locks', []),
            "message": f"Cleaned {result['cleaned']} stale lock(s), kept {result['kept']} active lock(s)"
        })
    except Exception as e:
        return [error_response(f"Error cleaning stale locks: {str(e)}")]


@mcp_tool("list_tools", timeout=10.0, rate_limit_exempt=True)
async def handle_list_tools(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """List all available governance tools with descriptions and categories"""
    if 'src.mcp_server_std' in sys.modules:
        mcp_server = sys.modules['src.mcp_server_std']
    else:
        import src.mcp_server_std as mcp_server
    
    # Get actual registered tools from TOOL_HANDLERS registry
    from . import TOOL_HANDLERS
    registered_tool_names = sorted(TOOL_HANDLERS.keys())
    
    # Define tool relationships and workflows
    tool_relationships = {
        "process_agent_update": {
            "depends_on": ["get_agent_api_key"],
            "related_to": ["simulate_update", "get_governance_metrics", "get_system_history"],
            "category": "core"
        },
        "get_governance_metrics": {
            "depends_on": [],
            "related_to": ["process_agent_update", "observe_agent", "get_system_history"],
            "category": "core"
        },
        "simulate_update": {
            "depends_on": [],
            "related_to": ["process_agent_update", "get_governance_metrics"],
            "category": "core"
        },
        "get_thresholds": {
            "depends_on": [],
            "related_to": ["set_thresholds", "process_agent_update"],
            "category": "config"
        },
        "set_thresholds": {
            "depends_on": ["get_thresholds"],
            "related_to": ["get_thresholds", "process_agent_update"],
            "category": "config"
        },
        "observe_agent": {
            "depends_on": ["list_agents"],
            "related_to": ["get_governance_metrics", "compare_agents", "detect_anomalies"],
            "category": "observability"
        },
        "compare_agents": {
            "depends_on": ["list_agents"],
            "related_to": ["observe_agent", "aggregate_metrics", "detect_anomalies"],
            "category": "observability"
        },
        "detect_anomalies": {
            "depends_on": ["list_agents"],
            "related_to": ["observe_agent", "compare_agents", "aggregate_metrics"],
            "category": "observability"
        },
        "aggregate_metrics": {
            "depends_on": [],
            "related_to": ["observe_agent", "compare_agents", "detect_anomalies"],
            "category": "observability"
        },
        "list_agents": {
            "depends_on": [],
            "related_to": ["get_agent_metadata", "get_agent_api_key"],
            "category": "lifecycle"
        },
        "get_agent_metadata": {
            "depends_on": ["list_agents"],
            "related_to": ["list_agents", "update_agent_metadata"],
            "category": "lifecycle"
        },
        "update_agent_metadata": {
            "depends_on": ["list_agents"],
            "related_to": ["get_agent_metadata", "list_agents"],
            "category": "lifecycle"
        },
        "archive_agent": {
            "depends_on": ["list_agents"],
            "related_to": ["list_agents", "delete_agent"],
            "category": "lifecycle"
        },
        "delete_agent": {
            "depends_on": ["list_agents"],
            "related_to": ["archive_agent", "list_agents"],
            "category": "lifecycle"
        },
        "archive_old_test_agents": {
            "depends_on": [],
            "related_to": ["archive_agent", "list_agents"],
            "category": "lifecycle"
        },
        "get_agent_api_key": {
            "depends_on": [],
            "related_to": ["process_agent_update", "list_agents"],
            "category": "lifecycle"
        },
        "mark_response_complete": {
            "depends_on": [],
            "related_to": ["process_agent_update", "get_agent_metadata"],
            "category": "lifecycle"
        },
        "direct_resume_if_safe": {
            "depends_on": ["get_agent_api_key"],
            "related_to": ["request_dialectic_review", "get_governance_metrics"],
            "category": "lifecycle"
        },
        "get_system_history": {
            "depends_on": ["list_agents"],
            "related_to": ["export_to_file", "get_governance_metrics", "observe_agent"],
            "category": "export"
        },
        "export_to_file": {
            "depends_on": ["get_system_history"],
            "related_to": ["get_system_history"],
            "category": "export"
        },
        "reset_monitor": {
            "depends_on": ["list_agents"],
            "related_to": ["process_agent_update"],
            "category": "admin"
        },
        "get_server_info": {
            "depends_on": [],
            "related_to": ["health_check", "cleanup_stale_locks"],
            "category": "admin"
        },
        "health_check": {
            "depends_on": [],
            "related_to": ["get_server_info", "get_telemetry_metrics"],
            "category": "admin"
        },
        "check_calibration": {
            "depends_on": ["update_calibration_ground_truth"],
            "related_to": ["update_calibration_ground_truth"],
            "category": "admin"
        },
        "update_calibration_ground_truth": {
            "depends_on": [],
            "related_to": ["check_calibration"],
            "category": "admin"
        },
        "get_telemetry_metrics": {
            "depends_on": [],
            "related_to": ["health_check", "aggregate_metrics"],
            "category": "admin"
        },
        "get_tool_usage_stats": {
            "depends_on": [],
            "related_to": ["get_telemetry_metrics", "list_tools"],
            "category": "admin"
        },
        "get_workspace_health": {
            "depends_on": [],
            "related_to": ["health_check", "get_server_info"],
            "category": "workspace"
        },
        # Knowledge layer relationships REMOVED (archived November 28, 2025)
        "request_dialectic_review": {
            "depends_on": ["get_agent_api_key"],
            "related_to": ["submit_thesis", "get_dialectic_session"],
            "category": "dialectic"
        },
        "submit_thesis": {
            "depends_on": ["request_dialectic_review"],
            "related_to": ["submit_antithesis", "get_dialectic_session"],
            "category": "dialectic"
        },
        "submit_antithesis": {
            "depends_on": ["submit_thesis"],
            "related_to": ["submit_synthesis", "get_dialectic_session"],
            "category": "dialectic"
        },
        "submit_synthesis": {
            "depends_on": ["submit_antithesis"],
            "related_to": ["get_dialectic_session", "request_dialectic_review"],
            "category": "dialectic"
        },
        "get_dialectic_session": {
            "depends_on": ["request_dialectic_review"],
            "related_to": ["submit_thesis", "submit_antithesis", "submit_synthesis"],
            "category": "dialectic"
        },
        "self_recovery": {
            "depends_on": ["get_agent_api_key"],
            "related_to": ["request_dialectic_review", "smart_dialectic_review"],
            "category": "dialectic"
        },
        "smart_dialectic_review": {
            "depends_on": ["get_agent_api_key"],
            "related_to": ["request_dialectic_review", "self_recovery"],
            "category": "dialectic"
        },
        "cleanup_stale_locks": {
            "depends_on": [],
            "related_to": ["get_server_info"],
            "category": "admin"
        },
        "list_tools": {
            "depends_on": [],
            "related_to": [],
            "category": "admin"
        }
    }
    
    # Define common workflows
    workflows = {
        "onboarding": [
            "list_tools",
            "get_agent_api_key",
            "list_agents",
            "process_agent_update"
        ],
        "monitoring": [
            "list_agents",
            "get_governance_metrics",
            "observe_agent",
            "aggregate_metrics",
            "detect_anomalies"
        ],
        "governance_cycle": [
            "get_agent_api_key",
            "process_agent_update",
            "get_governance_metrics"
        ],
        # Knowledge layer REMOVED (archived November 28, 2025)
        "dialectic_recovery": [
            "request_dialectic_review",
            "submit_thesis",
            "submit_antithesis",
            "submit_synthesis",
            "get_dialectic_session"
        ],
        "export_analysis": [
            "get_system_history",
            "export_to_file"
        ]
    }
    
    # Build tools list dynamically from registered tools
    # Description mapping for tools (fallback to generic if not found)
    tool_descriptions = {
        "process_agent_update": "Run governance cycle, return decision + metrics",
        "get_governance_metrics": "Current state, sampling params, decision stats, stability",
        "simulate_update": "Dry-run governance cycle (no persist)",
        "get_thresholds": "View current threshold config",
        "set_thresholds": "Runtime threshold overrides",
        "observe_agent": "Observe agent state with pattern analysis",
        "compare_agents": "Compare patterns across multiple agents",
        "detect_anomalies": "Scan for unusual patterns across fleet",
        "aggregate_metrics": "Fleet-level health overview",
        "list_agents": "List all agents with lifecycle metadata",
        "get_agent_metadata": "Full metadata for single agent",
        "update_agent_metadata": "Update tags and notes",
        "archive_agent": "Archive for long-term storage",
        "delete_agent": "Delete agent (protected for pioneers)",
        "archive_old_test_agents": "Auto-archive stale test agents",
        "get_agent_api_key": "Get/generate API key for authentication",
        "mark_response_complete": "Mark agent as having completed response, waiting for input",
        "direct_resume_if_safe": "Direct resume without dialectic if agent state is safe",
        "get_system_history": "Export time-series history (inline)",
        "export_to_file": "Export history to JSON/CSV file",
        "reset_monitor": "Reset agent state",
        "get_server_info": "Server version, PID, uptime, health",
        # Knowledge layer descriptions REMOVED (archived November 28, 2025)
        # Knowledge Graph (New - Fast, indexed, transparent)
        "store_knowledge_graph": "Store knowledge discovery in graph (fast, non-blocking)",
        "search_knowledge_graph": "Search knowledge graph by tags, type, agent (indexed queries)",
        "get_knowledge_graph": "Get all knowledge for an agent (fast index lookup)",
        "list_knowledge_graph": "List knowledge graph statistics (full transparency)",
        "update_discovery_status_graph": "Update discovery status (open/resolved/archived)",
        "find_similar_discoveries_graph": "Find similar discoveries by tag overlap (fast tag-based search)",
        "list_tools": "This tool - runtime introspection for onboarding",
        "cleanup_stale_locks": "Clean up stale lock files from crashed/killed processes",
        "request_dialectic_review": "Request peer review for paused/critical agent (circuit breaker recovery)",
        "submit_thesis": "Submit thesis: 'What I did, what I think happened' (dialectic step 1)",
        "submit_antithesis": "Submit antithesis: 'What I observe, my concerns' (dialectic step 2)",
        "submit_synthesis": "Submit synthesis proposal during negotiation (dialectic step 3)",
        "get_dialectic_session": "Get current state of a dialectic session",
        "self_recovery": "Allow agent to recover without reviewer (for when no reviewers available)",
        "smart_dialectic_review": "Smart dialectic that auto-progresses when possible",
        "health_check": "Quick health check - system status and component health",
        "check_calibration": "Check calibration of confidence estimates",
        "update_calibration_ground_truth": "Update calibration with ground truth data",
        "get_telemetry_metrics": "Get comprehensive telemetry metrics",
        "get_workspace_health": "Get comprehensive workspace health status",
        "get_tool_usage_stats": "Get tool usage statistics to identify which tools are actually used vs unused",
    }
    
    # Build tools list from registered tools with metadata from decorators
    from .decorators import get_tool_timeout, get_tool_description
    tools_list = []
    for tool_name in registered_tool_names:
        tool_info = {
            "name": tool_name,
            "description": tool_descriptions.get(tool_name, get_tool_description(tool_name) or f"Tool: {tool_name}")
        }
        # Add timeout metadata if available from decorator
        timeout = get_tool_timeout(tool_name)
        if timeout:
            tool_info["timeout"] = timeout
        # Add category from relationships if available
        if tool_name in tool_relationships:
            tool_info["category"] = tool_relationships[tool_name].get("category", "unknown")
        tools_list.append(tool_info)
    
    tools_info = {
        "success": True,
        "server_version": mcp_server.SERVER_VERSION,
        "tools": tools_list,
        "categories": {
            "core": ["process_agent_update", "get_governance_metrics", "simulate_update"],
            "config": ["get_thresholds", "set_thresholds"],
            "observability": ["observe_agent", "compare_agents", "detect_anomalies", "aggregate_metrics"],
            "lifecycle": ["list_agents", "get_agent_metadata", "update_agent_metadata", "archive_agent", "delete_agent", "archive_old_test_agents", "get_agent_api_key", "mark_response_complete", "direct_resume_if_safe"],
            "export": ["get_system_history", "export_to_file"],
            # Knowledge layer REMOVED (archived November 28, 2025) - was causing agent unresponsiveness
            "dialectic": ["request_dialectic_review", "submit_thesis", "submit_antithesis", "submit_synthesis", "get_dialectic_session", "self_recovery", "smart_dialectic_review"],
            "admin": ["reset_monitor", "get_server_info", "health_check", "check_calibration", "update_calibration_ground_truth", "get_telemetry_metrics", "get_tool_usage_stats", "list_tools", "cleanup_stale_locks"],
            "workspace": ["get_workspace_health"]
        },
        "workflows": workflows,
        "relationships": tool_relationships,
        "note": "Use this tool to discover available capabilities. MCP protocol also provides tool definitions, but this provides categorized overview useful for onboarding."
    }
    
    # Calculate total_tools dynamically to avoid discrepancies
    tools_info["total_tools"] = len(tools_info["tools"])
    
    return success_response(tools_info)


@mcp_tool("get_workspace_health", timeout=30.0, rate_limit_exempt=True)
async def handle_get_workspace_health(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle get_workspace_health tool - comprehensive workspace health status"""
    from src.workspace_health import get_workspace_health
    
    try:
        health_data = get_workspace_health()
        return success_response(health_data)
    except Exception as e:
        import traceback
        import sys
        # SECURITY: Log full traceback internally but sanitize for client
        print(f"[UNITARES MCP] Error checking workspace health: {e}", file=sys.stderr)
        print(f"[UNITARES MCP] Full traceback:\n{traceback.format_exc()}", file=sys.stderr)
        return [error_response(
            f"Error checking workspace health: {str(e)}",
            recovery={
                "action": "Check system configuration and try again",
                "related_tools": ["health_check", "get_server_info"]
            }
        )]
