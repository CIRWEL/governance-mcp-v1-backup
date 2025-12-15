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

# Import from mcp_server_std module (using shared utility)
from .shared import get_mcp_server
mcp_server = get_mcp_server()


@mcp_tool("observe_agent", timeout=15.0)
async def handle_observe_agent(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Observe another agent's governance state with pattern analysis"""
    # PROACTIVE GATE: Require target agent to be registered before observing
    # Note: This checks if the TARGET agent exists, not the caller.
    # This allows unregistered rescue agents to observe registered agents.
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]  # Returns onboarding guidance if not registered
    
    # Reload metadata to get latest state (handles multi-process sync) - non-blocking
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
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
                "risk_score": float(metrics.get("risk_score") or metrics.get("current_risk") or 0.0),  # Governance/operational risk
                "phi": metrics.get("phi"),  # Primary physics signal
                "verdict": metrics.get("verdict"),  # Primary governance signal
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


@mcp_tool("compare_agents", timeout=15.0)
async def handle_compare_agents(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Compare governance patterns across multiple agents"""
    # Reload metadata to get latest state (handles multi-process sync) - non-blocking
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
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
    
    compare_metrics = arguments.get("compare_metrics", ["risk_score", "coherence", "E", "I", "S", "V"])  # Default metrics for comparison
    
    # Get metrics for all agents
    agents_data = []
    for agent_id in agent_ids:
        monitor = mcp_server.monitors.get(agent_id)
        if monitor is None:
            # Load monitor state (non-blocking)
            loop = asyncio.get_running_loop()
            persisted_state = await loop.run_in_executor(None, mcp_server.load_monitor_state, agent_id)
            if persisted_state:
                monitor = UNITARESMonitor(agent_id, load_state=False)
                monitor.state = persisted_state
        
        if monitor:
            metrics = monitor.get_metrics()
            
            # Calculate health_status consistently with process_agent_update
            # Use health_checker.get_health_status() instead of metrics.get("status")
            risk_score = metrics.get("risk_score") or metrics.get("current_risk")
            coherence = float(monitor.state.coherence) if monitor.state else None
            void_active = bool(monitor.state.void_active) if monitor.state else False
            
            health_status_obj, _ = mcp_server.health_checker.get_health_status(
                risk_score=risk_score,
                coherence=coherence,
                void_active=void_active
            )
            
            agents_data.append({
                "agent_id": agent_id,
                "current_risk": metrics.get("current_risk"),  # Recent trend (last 10) - USED FOR HEALTH STATUS
                "risk_score": float(metrics.get("risk_score") or metrics.get("current_risk") or metrics.get("mean_risk", 0.0)),  # Governance/operational risk
                "phi": metrics.get("phi"),  # Primary physics signal
                "verdict": metrics.get("verdict"),  # Primary governance signal
                "mean_risk": metrics.get("mean_risk", 0.0),  # Overall mean (all-time average) - for historical context
                "coherence": float(monitor.state.coherence),
                "E": float(monitor.state.E),
                "I": float(monitor.state.I),
                "S": float(monitor.state.S),
                "V": float(monitor.state.V),  # Added missing V
                "health_status": health_status_obj.value  # Use consistent calculation
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


@mcp_tool("compare_me_to_similar", timeout=15.0)
async def handle_compare_me_to_similar(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Compare yourself to similar agents automatically - finds similar agents and compares
    
    IMPROVEMENT #5: Agent comparison templates
    """
    # SECURITY FIX: Require registered agent (prevents phantom agent_ids)
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    # Reload metadata to get latest state
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    # Get current agent's metrics
    monitor = mcp_server.get_or_create_monitor(agent_id)
    my_metrics = monitor.get_metrics()
    
    my_E = float(my_metrics.get('E', 0.7))
    my_I = float(my_metrics.get('I', 0.8))
    my_S = float(my_metrics.get('S', 0.2))
    my_coherence = float(my_metrics.get('coherence', 0.5))
    my_phi = my_metrics.get('phi', 0.0)
    my_verdict = my_metrics.get('verdict', 'caution')
    
    # Find similar agents (similar EISV values)
    similar_agents = []
    similarity_threshold = arguments.get("similarity_threshold", 0.15)  # Within 15% on each metric
    
    for other_id, other_meta in mcp_server.agent_metadata.items():
        if other_id == agent_id or other_meta.status not in ["active", "waiting_input"]:
            continue
        
        try:
            other_monitor = mcp_server.get_or_create_monitor(other_id)
            other_metrics = other_monitor.get_metrics()
            
            other_E = float(other_metrics.get('E', 0.7))
            other_I = float(other_metrics.get('I', 0.8))
            other_S = float(other_metrics.get('S', 0.2))
            other_coherence = float(other_metrics.get('coherence', 0.5))
            
            # Calculate similarity (Euclidean distance in EISV space)
            E_diff = abs(my_E - other_E)
            I_diff = abs(my_I - other_I)
            S_diff = abs(my_S - other_S)
            coherence_diff = abs(my_coherence - other_coherence)
            
            # Similar if within threshold on all metrics
            if (E_diff <= similarity_threshold and 
                I_diff <= similarity_threshold and 
                S_diff <= similarity_threshold):
                
                similarity_score = 1.0 - ((E_diff + I_diff + S_diff + coherence_diff) / 4.0)
                similar_agents.append({
                    "agent_id": other_id,
                    "similarity_score": similarity_score,
                    "metrics": {
                        "E": other_E,
                        "I": other_I,
                        "S": other_S,
                        "coherence": other_coherence,
                        "phi": other_metrics.get('phi', 0.0),
                        "verdict": other_metrics.get('verdict', 'caution'),
                        "risk_score": other_metrics.get('risk_score', 0.4)
                    },
                    "differences": {
                        "E": other_E - my_E,
                        "I": other_I - my_I,
                        "S": other_S - my_S,
                        "coherence": other_coherence - my_coherence
                    },
                    "total_updates": other_meta.total_updates,
                    "status": other_meta.status
                })
        except Exception as e:
            logger.debug(f"Could not compare with agent {other_id}: {e}")
            continue
    
    # Sort by similarity score (highest first)
    similar_agents.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    # Take top 3 most similar
    top_similar = similar_agents[:3]
    
    if not top_similar:
        return success_response({
            "agent_id": agent_id,
            "message": "No similar agents found (within similarity threshold)",
            "my_metrics": {
                "E": my_E,
                "I": my_I,
                "S": my_S,
                "coherence": my_coherence,
                "phi": my_phi,
                "verdict": my_verdict
            },
            "suggestion": "Try adjusting similarity_threshold parameter or use compare_agents with specific agent_ids"
        })
    
    # Build comparison response
    comparison_data = {
        "agent_id": agent_id,
        "my_metrics": {
            "E": my_E,
            "I": my_I,
            "S": my_S,
            "coherence": my_coherence,
            "phi": my_phi,
            "verdict": my_verdict,
            "risk_score": my_metrics.get('risk_score', 0.4)
        },
        "similar_agents": top_similar,
        "message": f"Found {len(top_similar)} similar agent(s). Here's how you compare:",
        "insights": []
    }
    
    # Generate insights
    for similar in top_similar:
        insights = []
        if similar["metrics"]["I"] > my_I + 0.05:
            insights.append(f"Higher Information Integrity ({similar['metrics']['I']:.2f} vs {my_I:.2f})")
        if similar["metrics"]["S"] < my_S - 0.05:
            insights.append(f"Lower Entropy ({similar['metrics']['S']:.2f} vs {my_S:.2f})")
        if similar["metrics"]["phi"] > my_phi + 0.05:
            insights.append(f"Better phi score ({similar['metrics']['phi']:.2f} vs {my_phi:.2f}) - closer to 'safe' verdict")
        if similar["metrics"]["verdict"] == "safe" and my_verdict != "safe":
            insights.append(f"Achieved 'safe' verdict (you're at '{my_verdict}')")
        
        if insights:
            comparison_data["insights"].append({
                "agent_id": similar["agent_id"],
                "insights": insights,
                "total_updates": similar["total_updates"]
            })
    
    comparison_data["eisv_labels"] = UNITARESMonitor.get_eisv_labels()
    
    return success_response(comparison_data)


@mcp_tool("detect_anomalies", timeout=15.0)
async def handle_detect_anomalies(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Detect anomalies across agents"""
    import asyncio
    
    # Reload metadata to get latest state (handles multi-process sync) - non-blocking
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
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
    loop = asyncio.get_running_loop()  # Use get_running_loop() instead of deprecated get_event_loop()
    
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
                    logger.warning(f"Error processing agent in detect_anomalies: {result}", exc_info=True)
    except Exception as e:
        logger.error(f"Error in detect_anomalies: {e}", exc_info=True)
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
    
    # Reload metadata to get latest state (handles multi-process sync) - non-blocking
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    agent_ids = arguments.get("agent_ids")
    include_health_breakdown = arguments.get("include_health_breakdown", True)
    
    # Get agent list
    if not agent_ids:
        agent_ids = [aid for aid, meta in mcp_server.agent_metadata.items() if meta.status == "active"]
    
    # Aggregate metrics
    total_agents = len(agent_ids)
    agents_with_data = 0
    total_updates = 0
    risk_scores = []  # Governance/operational risk scores
    coherence_scores = []
    health_statuses = {"healthy": 0, "moderate": 0, "critical": 0, "unknown": 0}
    decision_counts = {"proceed": 0, "pause": 0}  # Two-tier system (backward compat: approve/reflect/reject mapped)
    
    for agent_id in agent_ids:
        monitor = mcp_server.monitors.get(agent_id)
        if monitor is None:
            # Load monitor state (non-blocking)
            loop = asyncio.get_running_loop()
            persisted_state = await loop.run_in_executor(None, mcp_server.load_monitor_state, agent_id)
            if persisted_state:
                monitor = UNITARESMonitor(agent_id, load_state=False)
                monitor.state = persisted_state
        
        if monitor:
            agents_with_data += 1
            metrics = monitor.get_metrics()
            
            # Aggregate risk_score and coherence
            risk_score = metrics.get("risk_score") or metrics.get("current_risk")
            if risk_score is not None:
                risk_scores.append(float(risk_score))
            elif monitor.state.risk_history:
                # Fallback to risk_history if risk_score not available
                history_values = [float(r) for r in monitor.state.risk_history[-10:]]  # Last 10 updates
                risk_scores.extend(history_values)
            coherence_scores.append(float(monitor.state.coherence))
            
            # Aggregate health status
            status = metrics.get("status", "unknown")
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
        "mean_risk_score": float(np.mean(risk_scores)) if risk_scores else 0.0,  # Governance/operational risk (mean)
        "mean_risk": float(np.mean(risk_scores)) if risk_scores else 0.0,  # DEPRECATED: Use mean_risk_score instead
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
