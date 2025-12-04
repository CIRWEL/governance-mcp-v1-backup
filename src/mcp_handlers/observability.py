"""
Observability tool handlers.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
import sys
from .utils import success_response, error_response, require_argument, require_registered_agent
from .decorators import mcp_tool
from src.governance_monitor import UNITARESMonitor
from src.logging_utils import get_logger

logger = get_logger(__name__)

# Import from mcp_server_std module
if 'src.mcp_server_std' in sys.modules:
    mcp_server = sys.modules['src.mcp_server_std']
else:
    import src.mcp_server_std as mcp_server


@mcp_tool("observe_agent", timeout=15.0)
async def handle_observe_agent(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Observe another agent's governance state with pattern analysis"""
    # PROACTIVE GATE: Require target agent to be registered before observing
    # Note: This checks if the TARGET agent exists, not the caller.
    # This allows unregistered rescue agents to observe registered agents.
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]  # Returns onboarding guidance if not registered
    
    # Reload metadata to get latest state (handles multi-process sync)
    mcp_server.load_metadata()
    
    include_history = arguments.get("include_history", True)
    analyze_patterns_flag = arguments.get("analyze_patterns", True)
    
    # Load monitor state from disk if not in memory (consistent with get_governance_metrics)
    monitor = mcp_server.get_or_create_monitor(agent_id)
    
    # Perform pattern analysis
    if analyze_patterns_flag:
        observation = mcp_server.analyze_agent_patterns(monitor, include_history=include_history)
    else:
        # Just return current state without analysis
        metrics = monitor.get_metrics()
        observation = {
            "current_state": {
                "E": float(monitor.state.E),
                "I": float(monitor.state.I),
                "S": float(monitor.state.S),
                "V": float(monitor.state.V),
                "coherence": float(monitor.state.coherence),
                "attention_score": float(metrics.get("attention_score") or metrics.get("current_risk") or 0.0),  # Renamed from risk_score
                "phi": metrics.get("phi"),  # Primary physics signal
                "verdict": metrics.get("verdict"),  # Primary governance signal
                "risk_score": float(metrics.get("attention_score") or metrics.get("current_risk") or 0.0),  # DEPRECATED
                "lambda1": float(monitor.state.lambda1),
                "update_count": monitor.state.update_count
            }
        }
    
    # Add EISV labels for API documentation
    response_data = {
        "agent_id": agent_id,
        "observation": observation,
        "eisv_labels": UNITARESMonitor.get_eisv_labels()
    }
    
    return success_response(response_data)


@mcp_tool("compare_agents", timeout=20.0)
async def handle_compare_agents(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Compare governance patterns across multiple agents"""
    # Reload metadata to get latest state (handles multi-process sync)
    mcp_server.load_metadata()
    
    agent_ids = arguments.get("agent_ids", [])
    if not agent_ids or len(agent_ids) < 2:
        return [error_response(
            "At least 2 agent_ids required for comparison",
            recovery={
                "action": "Provide at least 2 agent_ids in the agent_ids array",
                "related_tools": ["list_agents"],
                "workflow": "1. Call list_agents to see available agents 2. Select 2+ agent_ids to compare"
            }
        )]
    
    compare_metrics = arguments.get("compare_metrics", ["attention_score", "coherence", "E", "I", "S", "V"])  # Updated default: attention_score instead of risk_score, added V
    
    # Get metrics for all agents
    agents_data = []
    for agent_id in agent_ids:
        monitor = mcp_server.monitors.get(agent_id)
        if monitor is None:
            persisted_state = mcp_server.load_monitor_state(agent_id)
            if persisted_state:
                monitor = UNITARESMonitor(agent_id, load_state=False)
                monitor.state = persisted_state
        
        if monitor:
            metrics = monitor.get_metrics()
            agents_data.append({
                "agent_id": agent_id,
                "current_risk": metrics.get("current_risk"),  # Recent trend (last 10) - USED FOR HEALTH STATUS
                "attention_score": float(metrics.get("attention_score") or metrics.get("current_risk") or metrics.get("mean_risk", 0.0)),  # Renamed from risk_score
                "phi": metrics.get("phi"),  # Primary physics signal
                "verdict": metrics.get("verdict"),  # Primary governance signal
                "risk_score": float(metrics.get("attention_score") or metrics.get("current_risk") or metrics.get("mean_risk", 0.0)),  # DEPRECATED
                "mean_risk": metrics.get("mean_risk", 0.0),  # Overall mean (all-time average) - for historical context
                "coherence": float(monitor.state.coherence),
                "E": float(monitor.state.E),
                "I": float(monitor.state.I),
                "S": float(monitor.state.S),
                "V": float(monitor.state.V),  # Added missing V
                "health_status": metrics.get("status", "unknown")
            })
    
    if len(agents_data) < 2:
        return [error_response(
            f"Could not load data for at least 2 agents. Loaded: {len(agents_data)}",
            recovery={
                "action": "Ensure agents exist and have state. Some agents may need initial process_agent_update call.",
                "related_tools": ["list_agents", "get_governance_metrics", "process_agent_update"],
                "workflow": "1. Call list_agents to verify agents exist 2. Call get_governance_metrics to check if agents have state 3. Call process_agent_update if agents need initialization"
            }
        )]
    
    # Import numpy for statistical operations
    import numpy as np
    
    # Compute similarities and differences
    similarities = []
    differences = []
    outliers = []
    
    # Compare each metric
    for metric in compare_metrics:
        values = [(a["agent_id"], a.get(metric, 0)) for a in agents_data if metric in a]
        if len(values) < 2:
            continue
        
        metric_values = [v[1] for v in values]
        mean_val = np.mean(metric_values)
        std_val = np.std(metric_values) if len(metric_values) > 1 else 0.0
        
        # Find similar pairs (within 1 std dev)
        for i, (id1, val1) in enumerate(values):
            for j, (id2, val2) in enumerate(values[i+1:], i+1):
                if abs(val1 - val2) < std_val * 0.5:  # Similar if within 0.5 std dev
                    similarities.append({
                        "agents": [id1, id2],
                        "metric": metric,
                        "similarity": 1.0 - abs(val1 - val2) / (mean_val + 0.001),
                        "description": f"Both show similar {metric} patterns"
                    })
        
        # Find outliers (beyond 2 std dev)
        for agent_id, val in values:
            if std_val > 0 and abs(val - mean_val) > 2 * std_val:
                outliers.append({
                    "agent_id": agent_id,
                    "metric": metric,
                    "value": float(val),
                    "mean": float(mean_val),
                    "reason": f"{metric} is {'above' if val > mean_val else 'below'} average"
                })
    
    # Add EISV labels for API documentation
    response_data = {
        "comparison": {
            "agents": agents_data,
            "similarities": similarities[:10],  # Limit to top 10
            "differences": differences,
            "outliers": outliers
        },
        "eisv_labels": UNITARESMonitor.get_eisv_labels()
    }
    
    return success_response(response_data)


@mcp_tool("detect_anomalies", timeout=20.0)
async def handle_detect_anomalies(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Detect anomalies across agents"""
    import asyncio
    
    # Reload metadata to get latest state (handles multi-process sync)
    mcp_server.load_metadata()
    
    agent_ids = arguments.get("agent_ids")
    anomaly_types = arguments.get("anomaly_types", ["risk_spike", "coherence_drop"])
    min_severity = arguments.get("min_severity", "medium")
    
    severity_levels = {"low": 0, "medium": 1, "high": 2}
    min_severity_level = severity_levels.get(min_severity, 1)
    
    # Get agent list
    if not agent_ids:
        # Scan all agents (limit to active ones for performance)
        agent_ids = [aid for aid, meta in mcp_server.agent_metadata.items() 
                     if meta.status == "active"][:50]  # Limit to 50 agents max
    
    all_anomalies = []
    loop = asyncio.get_event_loop()
    
    # Process agents in batches to prevent blocking
    async def process_agent(agent_id: str):
        """Process a single agent's anomalies"""
        monitor = mcp_server.monitors.get(agent_id)
        if monitor is None:
            # Load state in executor to avoid blocking
            persisted_state = await loop.run_in_executor(
                None, mcp_server.load_monitor_state, agent_id
            )
            if persisted_state:
                monitor = UNITARESMonitor(agent_id, load_state=False)
                monitor.state = persisted_state
        
        if monitor:
            # Analyze patterns in executor (may do file I/O)
            from src.pattern_analysis import analyze_agent_patterns
            analysis = await loop.run_in_executor(
                None, analyze_agent_patterns, monitor, False
            )
            
            # Filter anomalies by type and severity
            agent_anomalies = []
            for anomaly in analysis.get("anomalies", []):
                if anomaly["type"] in anomaly_types:
                    anomaly_severity_level = severity_levels.get(anomaly.get("severity", "low"), 0)
                    if anomaly_severity_level >= min_severity_level:
                        anomaly["agent_id"] = agent_id
                        agent_anomalies.append(anomaly)
            return agent_anomalies
        return []
    
    # Process agents concurrently (but limit concurrency)
    try:
        # Process in batches of 10 to avoid overwhelming system
        batch_size = 10
        for i in range(0, len(agent_ids), batch_size):
            batch = agent_ids[i:i+batch_size]
            batch_results = await asyncio.gather(*[process_agent(aid) for aid in batch], return_exceptions=True)
            for result in batch_results:
                if isinstance(result, list):
                    all_anomalies.extend(result)
                elif isinstance(result, Exception):
                    # Log but continue
                    import sys
                    print(f"[UNITARES MCP] Error processing agent in detect_anomalies: {result}", file=sys.stderr)
    except Exception as e:
        import sys
        print(f"[UNITARES MCP] Error in detect_anomalies: {e}", file=sys.stderr)
        return [error_response(f"Error detecting anomalies: {str(e)}")]
    
    # Sort by severity (high first)
    all_anomalies.sort(key=lambda x: severity_levels.get(x.get("severity", "low"), 0), reverse=True)
    
    # Count by severity and type
    by_severity = {"high": 0, "medium": 0, "low": 0}
    by_type = {}
    for anomaly in all_anomalies:
        severity = anomaly.get("severity", "low")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        anomaly_type = anomaly.get("type", "unknown")
        by_type[anomaly_type] = by_type.get(anomaly_type, 0) + 1
    
    # Add EISV labels for API documentation
    return success_response({
        "anomalies": all_anomalies,
        "summary": {
            "total_anomalies": len(all_anomalies),
            "by_severity": by_severity,
            "by_type": by_type
        },
        "eisv_labels": UNITARESMonitor.get_eisv_labels()
    })


@mcp_tool("aggregate_metrics", timeout=15.0)
async def handle_aggregate_metrics(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get fleet-level health overview"""
    import numpy as np
    
    # Reload metadata to get latest state (handles multi-process sync)
    mcp_server.load_metadata()
    
    agent_ids = arguments.get("agent_ids")
    include_health_breakdown = arguments.get("include_health_breakdown", True)
    
    # Get agent list
    if not agent_ids:
        agent_ids = [aid for aid, meta in mcp_server.agent_metadata.items() if meta.status == "active"]
    
    # Aggregate metrics
    total_agents = len(agent_ids)
    agents_with_data = 0
    total_updates = 0
    attention_scores = []  # Renamed from risk_scores
    coherence_scores = []
    health_statuses = {"healthy": 0, "moderate": 0, "critical": 0, "unknown": 0}  # "moderate" renamed from "degraded"
    decision_counts = {"proceed": 0, "pause": 0}  # Two-tier system (backward compat: approve/reflect/reject mapped)
    
    for agent_id in agent_ids:
        monitor = mcp_server.monitors.get(agent_id)
        if monitor is None:
            persisted_state = mcp_server.load_monitor_state(agent_id)
            if persisted_state:
                monitor = UNITARESMonitor(agent_id, load_state=False)
                monitor.state = persisted_state
        
        if monitor:
            agents_with_data += 1
            metrics = monitor.get_metrics()
            
            # Aggregate attention_score (renamed from risk_score) and coherence
            attention_score = metrics.get("attention_score") or metrics.get("current_risk")
            if attention_score is not None:
                attention_scores.append(float(attention_score))
            elif monitor.state.risk_history:
                # Fallback to risk_history if attention_score not available
                attention_scores.extend([float(r) for r in monitor.state.risk_history[-10:]])  # Last 10 updates
            coherence_scores.append(float(monitor.state.coherence))
            
            # Aggregate health status (map "degraded" → "moderate" for backward compat)
            status = metrics.get("status", "unknown")
            if status == "degraded":
                status = "moderate"  # Backward compatibility
            health_statuses[status] = health_statuses.get(status, 0) + 1
            
            # Aggregate decisions
            decision_stats = metrics.get("decision_statistics", {})
            # Map old decisions to new system
            proceed_count = decision_stats.get("proceed", 0) + decision_stats.get("approve", 0) + decision_stats.get("reflect", 0) + decision_stats.get("revise", 0)
            pause_count = decision_stats.get("pause", 0) + decision_stats.get("reject", 0)
            decision_counts["proceed"] += proceed_count
            decision_counts["pause"] += pause_count
            # Backward compatibility (keep old keys for compatibility)
            decision_counts["approve"] = decision_stats.get("approve", 0)
            decision_counts["reflect"] = decision_stats.get("reflect", 0) + decision_stats.get("revise", 0)
            decision_counts["reject"] = decision_stats.get("reject", 0)
            
            # Count total updates
            total_updates += monitor.state.update_count
    
    # Compute aggregate statistics
    aggregate_data = {
        "total_agents": total_agents,
        "agents_with_data": agents_with_data,
        "total_updates": total_updates,
        "mean_attention_score": float(np.mean(attention_scores)) if attention_scores else 0.0,  # Renamed from mean_risk
        "mean_risk": float(np.mean(attention_scores)) if attention_scores else 0.0,  # DEPRECATED: Use mean_attention_score
        "mean_coherence": float(np.mean(coherence_scores)) if coherence_scores else 0.0,
        "decision_distribution": {
            **decision_counts,
            "total": sum(decision_counts.values())
        }
    }
    
    if include_health_breakdown:
        aggregate_data["health_breakdown"] = health_statuses
    
    # Add EISV labels for API documentation
    return success_response({
        "aggregate": aggregate_data,
        "eisv_labels": UNITARESMonitor.get_eisv_labels()
    })
