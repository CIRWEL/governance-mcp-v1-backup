"""
MCP Handlers for Agent Lifecycle Management

Handles agent creation, metadata, archiving, deletion, and API key management.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
from datetime import datetime, timedelta
import sys

# Import from mcp_server_std module
if 'src.mcp_server_std' in sys.modules:
    mcp_server = sys.modules['src.mcp_server_std']
else:
    import src.mcp_server_std as mcp_server

from .utils import (
    require_agent_id,
    require_registered_agent,
    success_response,
    error_response
)
from .decorators import mcp_tool
from src.governance_monitor import UNITARESMonitor
from src.logging_utils import get_logger

logger = get_logger(__name__)


@mcp_tool("list_agents", timeout=15.0, rate_limit_exempt=True)
async def handle_list_agents(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """List all agents currently being monitored with lifecycle metadata and health status"""
    try:
        # Reload metadata to ensure we have latest state (non-blocking)
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, mcp_server.load_metadata)
        
        grouped = arguments.get("grouped", True)
        include_metrics = arguments.get("include_metrics", True)
        status_filter = arguments.get("status_filter", "all")
        loaded_only = arguments.get("loaded_only", False)
        summary_only = arguments.get("summary_only", False)
        standardized = arguments.get("standardized", True)

        agents_list = []
        
        for agent_id, meta in mcp_server.agent_metadata.items():
            # Filter by status if requested
            if status_filter != "all" and meta.status != status_filter:
                continue
            
            # Filter by loaded status if requested
            if loaded_only:
                if agent_id not in mcp_server.monitors:
                    continue
            
            agent_info = {
                "agent_id": agent_id,
                "lifecycle_status": meta.status,
                "created": meta.created_at,
                "last_update": meta.last_update,
                "total_updates": meta.total_updates,
                "tags": meta.tags.copy() if meta.tags else [],
                "notes": meta.notes if meta.notes else "",
            }
            
            # Add health status and metrics if requested
            if include_metrics and agent_id in mcp_server.monitors:
                try:
                    monitor = mcp_server.monitors[agent_id]
                    metrics = monitor.get_metrics()
                    agent_info["health_status"] = metrics.get("status", "unknown")
                    agent_info["metrics"] = {
                        "E": float(monitor.state.E),
                        "I": float(monitor.state.I),
                        "S": float(monitor.state.S),
                        "V": float(monitor.state.V),
                        "coherence": float(monitor.state.coherence),
                        "current_risk": metrics.get("current_risk"),  # Recent trend (last 10) - USED FOR HEALTH STATUS
                        "attention_score": float(metrics.get("attention_score") or metrics.get("current_risk") or metrics.get("mean_risk", 0.5)),  # Renamed from risk_score - complexity/attention blend
                        "phi": metrics.get("phi"),  # Primary physics signal: Φ objective function
                        "verdict": metrics.get("verdict"),  # Primary governance signal: safe/caution/high-risk
                        "risk_score": float(metrics.get("attention_score") or metrics.get("current_risk") or metrics.get("mean_risk", 0.5)),  # DEPRECATED: Use attention_score instead
                        "mean_risk": float(metrics.get("mean_risk", 0.5)),  # Overall mean (all-time average) - for historical context
                        "lambda1": float(monitor.state.lambda1),
                        "void_active": bool(monitor.state.void_active)
                    }
                except Exception as e:
                    agent_info["health_status"] = "error"
                    agent_info["metrics"] = None
                    logger.warning(f"Error getting metrics for {agent_id}: {e}")
            else:
                # Try to get health status even if monitor not loaded
                if include_metrics:
                    try:
                        monitor = mcp_server.get_or_create_monitor(agent_id)
                        metrics = monitor.get_metrics()
                        agent_info["health_status"] = metrics.get("status", "unknown")
                        # Try to get basic metrics
                        try:
                            agent_info["metrics"] = {
                                "E": float(monitor.state.E),
                                "I": float(monitor.state.I),
                                "S": float(monitor.state.S),
                                "V": float(monitor.state.V),
                                "coherence": float(monitor.state.coherence),
                                "current_risk": metrics.get("current_risk"),  # Recent trend (for health status)
                                "risk_score": float(metrics.get("mean_risk", 0.5)),  # Overall mean (for display)
                                "mean_risk": float(metrics.get("mean_risk", 0.5)),  # Alias for backward compatibility
                                "lambda1": float(monitor.state.lambda1),
                                "void_active": bool(monitor.state.void_active)
                            }
                        except Exception:
                            agent_info["metrics"] = None
                    except Exception as e:
                        agent_info["health_status"] = "unknown"
                        agent_info["metrics"] = None
                        logger.warning(f"Could not load monitor for {agent_id}: {e}")
                else:
                    agent_info["health_status"] = "unknown"
                    agent_info["metrics"] = None
            
            # Add standardized fields if requested
            if standardized:
                agent_info.setdefault("health_status", "unknown")
                agent_info.setdefault("metrics", None)
            
            agents_list.append(agent_info)
        
        # Sort by last_update (most recent first)
        agents_list.sort(key=lambda x: x.get("last_update", ""), reverse=True)
        
        # Group by status if requested
        if grouped and not summary_only:
            grouped_agents = {
                "active": [a for a in agents_list if a.get("lifecycle_status") == "active"],
                "waiting_input": [a for a in agents_list if a.get("lifecycle_status") == "waiting_input"],
                "paused": [a for a in agents_list if a.get("lifecycle_status") == "paused"],
                "archived": [a for a in agents_list if a.get("lifecycle_status") == "archived"],
                "deleted": [a for a in agents_list if a.get("lifecycle_status") == "deleted"]
            }
            
            response_data = {
                "success": True,
                "agents": grouped_agents,
                "summary": {
                    "total": len(agents_list),
                    "by_status": {
                        "active": sum(1 for a in agents_list if a.get("lifecycle_status") == "active"),
                        "waiting_input": sum(1 for a in agents_list if a.get("lifecycle_status") == "waiting_input"),
                        "paused": sum(1 for a in agents_list if a.get("lifecycle_status") == "paused"),
                        "archived": sum(1 for a in agents_list if a.get("lifecycle_status") == "archived"),
                        "deleted": sum(1 for a in agents_list if a.get("lifecycle_status") == "deleted")
                    },
                    "by_health": {
                        "healthy": sum(1 for a in agents_list if a.get("health_status") == "healthy"),
                        "moderate": sum(1 for a in agents_list if a.get("health_status") == "moderate"),
                        "critical": sum(1 for a in agents_list if a.get("health_status") == "critical"),
                        "unknown": sum(1 for a in agents_list if a.get("health_status") == "unknown"),
                        "error": sum(1 for a in agents_list if a.get("health_status") == "error")
                    }
                }
            }
            
            # Add health breakdown if include_metrics
            if include_metrics:
                response_data["summary"]["by_health"] = {
                    "healthy": sum(1 for a in agents_list if a.get("health_status") == "healthy"),
                    "moderate": sum(1 for a in agents_list if a.get("health_status") == "moderate"),
                    "critical": sum(1 for a in agents_list if a.get("health_status") == "critical"),
                    "unknown": sum(1 for a in agents_list if a.get("health_status") == "unknown"),
                    "error": sum(1 for a in agents_list if a.get("health_status") == "error")
                }
        else:
            response_data = {
                "success": True,
                "agents": agents_list,
                "summary": {
                    "total": len(agents_list),
                    "by_status": {
                        "active": sum(1 for a in agents_list if a.get("lifecycle_status") == "active"),
                        "waiting_input": sum(1 for a in agents_list if a.get("lifecycle_status") == "waiting_input"),
                        "paused": sum(1 for a in agents_list if a.get("lifecycle_status") == "paused"),
                        "archived": sum(1 for a in agents_list if a.get("lifecycle_status") == "archived"),
                        "deleted": sum(1 for a in agents_list if a.get("lifecycle_status") == "deleted")
                    }
                }
            }
            
            if include_metrics:
                health_statuses = {"healthy": 0, "moderate": 0, "critical": 0, "unknown": 0, "error": 0}
                for agent in agents_list:
                    status = agent.get("health_status", "unknown")
                    health_statuses[status] = health_statuses.get(status, 0) + 1
                response_data["summary"]["by_health"] = health_statuses
        
        if summary_only:
            return success_response(response_data["summary"])
        
        # Add EISV labels for API documentation (only if metrics are included)
        if include_metrics:
            response_data["eisv_labels"] = UNITARESMonitor.get_eisv_labels()
        
        return success_response(response_data)
        
    except Exception as e:
        return [error_response(f"Error listing agents: {str(e)}")]


@mcp_tool("get_agent_metadata", timeout=10.0)
async def handle_get_agent_metadata(arguments: Sequence[TextContent]) -> list:
    """Get complete metadata for an agent including lifecycle events, current state, and computed fields"""
    # PROACTIVE GATE: Require agent to be registered
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]  # Returns onboarding guidance if not registered
    
    meta = mcp_server.agent_metadata[agent_id]
    monitor = mcp_server.monitors.get(agent_id)
    
    metadata_response = meta.to_dict()
    
    # Add computed fields
    if monitor:
        metadata_response["current_state"] = {
            "lambda1": float(monitor.state.lambda1),
            "coherence": float(monitor.state.coherence),
            "void_active": bool(monitor.state.void_active),
            "E": float(monitor.state.E),
            "I": float(monitor.state.I),
            "S": float(monitor.state.S),
            "V": float(monitor.state.V)
        }
    
    # Days since update
    last_update_dt = datetime.fromisoformat(meta.last_update)
    days_since = (datetime.now() - last_update_dt).days
    metadata_response["days_since_update"] = days_since
    
    # Add EISV labels for API documentation (only if current_state exists)
    if "current_state" in metadata_response:
        metadata_response["eisv_labels"] = UNITARESMonitor.get_eisv_labels()
    
    return success_response(metadata_response)


@mcp_tool("update_agent_metadata", timeout=10.0)
async def handle_update_agent_metadata(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Update agent tags and notes"""
    # PROACTIVE GATE: Require agent to be registered
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    # Reload metadata to ensure we have latest state (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    if agent_id not in mcp_server.agent_metadata:
        return [error_response(f"Agent '{agent_id}' not found")]
    
    meta = mcp_server.agent_metadata[agent_id]
    
    # Update tags if provided
    if "tags" in arguments:
        meta.tags = arguments["tags"]
    
    # Update notes if provided
    if "notes" in arguments:
        append_notes = arguments.get("append_notes", False)
        if append_notes:
            timestamp = datetime.now().isoformat()
            meta.notes = f"{meta.notes}\n[{timestamp}] {arguments['notes']}" if meta.notes else f"[{timestamp}] {arguments['notes']}"
        else:
            meta.notes = arguments["notes"]
    
    # Schedule batched metadata save (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await mcp_server.schedule_metadata_save(force=False)
    
    return success_response({
        "success": True,
        "message": "Agent metadata updated",
        "agent_id": agent_id,
        "tags": meta.tags,
        "notes": meta.notes,
        "updated_at": datetime.now().isoformat()
    })


@mcp_tool("archive_agent", timeout=15.0)
async def handle_archive_agent(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Archive an agent for long-term storage"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    # Reload metadata to ensure we have latest state (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    if agent_id not in mcp_server.agent_metadata:
        return [error_response(f"Agent '{agent_id}' not found")]
    
    meta = mcp_server.agent_metadata[agent_id]
    
    if meta.status == "archived":
        return [error_response(f"Agent '{agent_id}' is already archived")]
    
    reason = arguments.get("reason", "Manual archive")
    keep_in_memory = arguments.get("keep_in_memory", False)
    
    meta.status = "archived"
    meta.archived_at = datetime.now().isoformat()
    meta.add_lifecycle_event("archived", reason)
    
    # Optionally unload from memory
    if not keep_in_memory and agent_id in mcp_server.monitors:
        del mcp_server.monitors[agent_id]
    
    # Schedule batched metadata save (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await mcp_server.schedule_metadata_save(force=False)
    
    return success_response({
        "success": True,
        "message": f"Agent '{agent_id}' archived successfully",
        "agent_id": agent_id,
        "lifecycle_status": "archived",
        "archived_at": meta.archived_at,
        "reason": reason,
        "kept_in_memory": keep_in_memory
    })


@mcp_tool("delete_agent", timeout=15.0)
async def handle_delete_agent(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle delete_agent tool - delete agent and archive data (protected: cannot delete pioneer agents)"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    confirm = arguments.get("confirm", False)
    if not confirm:
        return [error_response("Deletion requires explicit confirmation (confirm=true)")]
    
    # Reload metadata to ensure we have latest state (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    if agent_id not in mcp_server.agent_metadata:
        return [error_response(f"Agent '{agent_id}' not found")]
    
    meta = mcp_server.agent_metadata[agent_id]
    
    # Check if agent is a pioneer (protected)
    if "pioneer" in meta.tags:
        return [error_response(
            f"Cannot delete pioneer agent '{agent_id}'",
            recovery={
                "action": "Pioneer agents are protected from deletion. Use archive_agent instead.",
                "related_tools": ["archive_agent"],
                "workflow": ["1. Call archive_agent to archive instead of delete", "2. Pioneer agents preserve system history"]
            }
        )]
    
    backup_first = arguments.get("backup_first", True)
    
    # Backup if requested
    backup_path = None
    if backup_first:
        try:
            import json
            import asyncio
            from pathlib import Path
            backup_dir = Path(mcp_server.project_root) / "data" / "archives"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_file = backup_dir / f"{agent_id}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_data = {
                "agent_id": agent_id,
                "metadata": meta.to_dict(),
                "backed_up_at": datetime.now().isoformat()
            }
            
            # Write backup file in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            def _write_backup_sync():
                """Synchronous backup write - runs in executor"""
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2)
            
            await loop.run_in_executor(None, _write_backup_sync)
            backup_path = str(backup_file)
        except Exception as e:
            logger.warning(f"Could not backup agent before deletion: {e}")
    
    # Delete agent
    meta.status = "deleted"
    meta.add_lifecycle_event("deleted", "Manual deletion")
    
    # Remove from monitors
    if agent_id in mcp_server.monitors:
        del mcp_server.monitors[agent_id]
    
    # Schedule batched metadata save (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await mcp_server.schedule_metadata_save(force=False)
    
    return success_response({
        "success": True,
        "message": f"Agent '{agent_id}' deleted successfully",
        "agent_id": agent_id,
        "archived": backup_path is not None,
        "backup_path": backup_path
    })


@mcp_tool("archive_old_test_agents", timeout=30.0, rate_limit_exempt=True)
async def handle_archive_old_test_agents(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Manually archive old test/demo agents that haven't been updated recently"""
    max_age_hours = arguments.get("max_age_hours", 6)  # Default: 6 hours (test/ping agents don't need to stick around)
    max_age_days = arguments.get("max_age_days")  # Backward compatibility: convert days to hours
    
    # Convert days to hours if provided (backward compatibility)
    if max_age_days is not None:
        max_age_hours = max_age_days * 24
    
    if max_age_hours < 0.1:
        return [error_response("max_age_hours must be at least 0.1 (6 minutes)")]
    
    # Reload metadata to ensure we have latest state (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    archived_agents = []
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    for agent_id, meta in list(mcp_server.agent_metadata.items()):
        # Only archive test/demo agents
        if not (agent_id.startswith("test_") or agent_id.startswith("demo_") or "test" in agent_id.lower()):
            continue
        
        # Skip if already archived/deleted
        if meta.status in ["archived", "deleted"]:
            continue
        
        # Archive immediately if very low update count (1-2 updates = just a ping/test)
        if meta.total_updates <= 2:
            meta.status = "archived"
            meta.archived_at = datetime.now().isoformat()
            meta.add_lifecycle_event("archived", f"Auto-archived: test/ping agent with {meta.total_updates} update(s)")
            archived_agents.append(agent_id)
            
            # Unload from memory
            if agent_id in mcp_server.monitors:
                del mcp_server.monitors[agent_id]
            continue
        
        # Check age for agents with more updates
        last_update_dt = datetime.fromisoformat(meta.last_update)
        if last_update_dt < cutoff_time:
            age_hours = (datetime.now() - last_update_dt).total_seconds() / 3600
            meta.status = "archived"
            meta.archived_at = datetime.now().isoformat()
            meta.add_lifecycle_event("archived", f"Inactive for {age_hours:.1f} hours (threshold: {max_age_hours} hours)")
            archived_agents.append(agent_id)
            
            # Unload from memory
            if agent_id in mcp_server.monitors:
                del mcp_server.monitors[agent_id]
    
    if archived_agents:
        # Schedule batched metadata save (non-blocking)
        import asyncio
        loop = asyncio.get_running_loop()
        await mcp_server.schedule_metadata_save(force=False)
    
    return success_response({
        "success": True,
        "archived_count": len(archived_agents),
        "archived_agents": archived_agents,
        "max_age_hours": max_age_hours,
        "threshold_used": max_age_hours,
        "note": "Test agents with ≤2 updates archived immediately. Others archived after inactivity threshold."
    })


@mcp_tool("get_agent_api_key", timeout=10.0)
async def handle_get_agent_api_key(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get or generate API key for an agent"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    regenerate = arguments.get("regenerate", False)
    
    # Check if agent exists
    is_new_agent = agent_id not in mcp_server.agent_metadata
    
    # SECURITY: For existing agents, require authentication to get/regenerate key
    if not is_new_agent:
        api_key = arguments.get("api_key")
        if not api_key:
            return [error_response(
                "Authentication required to retrieve API key for existing agent. Provide your api_key parameter.",
                recovery={
                    "action": "Include your api_key in the request to prove ownership",
                    "related_tools": ["list_agents"],
                    "workflow": "If you've lost your key, contact system administrator for recovery"
                }
            )]
        
        # Verify authentication
        meta = mcp_server.agent_metadata[agent_id]
        if meta.api_key != api_key:
            return [error_response(
                "Invalid API key. Cannot retrieve key for another agent.",
                recovery={
                    "action": "Use your own API key to retrieve your own key",
                    "related_tools": ["list_agents"]
                }
            )]
    
    # Get or create metadata (creates agent if new)
    meta = mcp_server.get_or_create_metadata(agent_id)
    
    # CRITICAL: Force immediate save for new agent creation to prevent key rotation bug
    # If metadata isn't saved, process_agent_update's load_metadata() will wipe it out
    if is_new_agent:
        import asyncio
        loop = asyncio.get_running_loop()
        await mcp_server.schedule_metadata_save(force=True)
    
    # Regenerate API key if requested (requires auth for existing agents)
    if regenerate:
        if not is_new_agent and not api_key:
            return [error_response("Authentication required to regenerate API key for existing agent")]
        
        new_key = mcp_server.generate_api_key()
        meta.api_key = new_key
        # Force immediate save for API key regeneration (critical operation)
        import asyncio
        loop = asyncio.get_running_loop()
        await mcp_server.schedule_metadata_save(force=True)
        
        # Log regeneration for audit
        from src.audit_log import audit_logger
        audit_logger.log("api_key_regenerated", {
            "agent_id": agent_id,
            "regenerated_by": "self" if not is_new_agent else "new_agent"
        })
        
        return success_response({
            "success": True,
            "agent_id": agent_id,
            "api_key": new_key,
            "is_new": False,
            "regenerated": True,
            "message": "API key regenerated - old key is now invalid"
        })
    
    return success_response({
        "success": True,
        "agent_id": agent_id,
        "api_key": meta.api_key,
        "is_new": agent_id not in mcp_server.agent_metadata or meta.total_updates == 0,
        "regenerated": False,
        "message": "API key retrieved" if meta.api_key else "API key generated"
    })


@mcp_tool("mark_response_complete", timeout=5.0)
async def handle_mark_response_complete(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Mark agent as having completed response, waiting for input"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    # Verify API key if provided
    api_key = arguments.get("api_key")
    if api_key:
        meta = mcp_server.agent_metadata.get(agent_id)
        if meta and hasattr(meta, 'api_key') and meta.api_key != api_key:
            return [error_response("Authentication failed: Invalid API key")]
    
    # Get or create metadata
    meta = mcp_server.get_or_create_metadata(agent_id)
    
    # Update status to waiting_input
    meta.status = "waiting_input"
    meta.last_response_at = datetime.now().isoformat()
    meta.response_completed = True
    
    # Add lifecycle event
    summary = arguments.get("summary", "")
    meta.add_lifecycle_event("response_completed", summary if summary else "Response completed, waiting for input")
    
    # Schedule batched metadata save (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await mcp_server.schedule_metadata_save(force=False)
    
    # MAINTENANCE PROMPT: Surface open discoveries from this session
    # Behavioral nudge: Remind agent to resolve discoveries before ending session
    open_discoveries = []
    try:
        from src.knowledge_graph import get_knowledge_graph
        # Note: datetime and timedelta already imported at module level (line 9)
        
        graph = await get_knowledge_graph()
        
        # Get open discoveries from this agent (recent - last 24 hours)
        now = datetime.now()
        one_day_ago = (now - timedelta(hours=24)).isoformat()
        
        all_agent_discoveries = await graph.query(
            agent_id=agent_id,
            status="open",
            limit=20  # Get recent discoveries
        )
        
        # Filter to recent discoveries (last 24 hours)
        recent_open = [
            d for d in all_agent_discoveries
            if d.timestamp >= one_day_ago
        ]
        
        # Prioritize bug_found and high severity
        recent_open.sort(key=lambda d: (
            0 if d.type == "bug_found" else 1,  # Bugs first
            0 if d.severity == "high" else 1 if d.severity == "medium" else 2,  # High severity first
            d.timestamp  # Then by recency
        ))
        
        open_discoveries = recent_open[:5]  # Top 5 for prompt
        
    except Exception as e:
        # Don't fail if knowledge graph check fails - this is a nice-to-have prompt
        logger.warning(f"Could not check open discoveries: {e}")
    
    response_data = {
        "success": True,
        "message": "Response completion marked",
        "agent_id": agent_id,
        "status": "waiting_input",
        "last_response_at": meta.last_response_at,
        "response_completed": True
    }
    
    # Add maintenance prompt if there are open discoveries
    if open_discoveries:
        response_data["maintenance_prompt"] = {
            "message": f"You have {len(open_discoveries)} open discovery/discoveries from this session. Consider resolving them:",
            "open_discoveries": [
                {
                    "id": d.id,
                    "summary": d.summary,
                    "type": d.type,
                    "severity": d.severity,
                    "timestamp": d.timestamp
                }
                for d in open_discoveries
            ],
            "suggested_actions": [
                "Mark as resolved: update_discovery_status_graph(discovery_id='...', status='resolved')",
                "If discovery is incorrect or needs correction, use dialectic: request_dialectic_review(discovery_id='...', dispute_type='dispute')",
                "Archive if obsolete: update_discovery_status_graph(discovery_id='...', status='archived')"
            ],
            "related_tools": [
                "update_discovery_status_graph",
                "request_dialectic_review",
                "search_knowledge_graph"
            ],
            "tip": "Resolving discoveries helps maintain knowledge graph quality. Use dialectic for collaborative corrections."
        }
    
    return success_response(response_data)


@mcp_tool("direct_resume_if_safe", timeout=10.0)
async def handle_direct_resume_if_safe(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Direct resume without dialectic if agent state is safe. Tier 1 recovery for simple stuck scenarios."""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    # Verify API key
    api_key = arguments.get("api_key")
    if not api_key:
        return [error_response("API key required for direct resume")]
    
    meta = mcp_server.agent_metadata.get(agent_id)
    if not meta:
        return [error_response(f"Agent '{agent_id}' not found")]
    
    if meta.api_key != api_key:
        return [error_response("Authentication failed: Invalid API key")]
    
    # Get current governance metrics
    try:
        monitor = mcp_server.get_or_create_monitor(agent_id)
        metrics = monitor.get_metrics()
        
        coherence = float(monitor.state.coherence)
        risk_score = float(metrics.get("mean_risk", 0.5))
        void_active = bool(monitor.state.void_active)
        status = meta.status
        
    except Exception as e:
        return [error_response(f"Error getting governance metrics: {str(e)}")]
    
    # Safety checks
    safety_checks = {
        "coherence_ok": coherence > 0.40,
        "risk_ok": risk_score < 0.60,
        "no_void": not void_active,
        "status_ok": status in ["paused", "waiting_input", "moderate"]
    }
    
    if not all(safety_checks.values()):
        failed_checks = [k for k, v in safety_checks.items() if not v]
        return [error_response(
            f"Not safe to resume. Failed checks: {failed_checks}. "
            f"Metrics: coherence={coherence:.3f}, risk={risk_score:.3f}, "
            f"void_active={void_active}, status={status}. "
            f"Use request_dialectic_review for complex recovery."
        )]
    
    # Get conditions if provided
    conditions = arguments.get("conditions", [])
    reason = arguments.get("reason", "Direct resume - state is safe")
    
    # Resume agent
    meta.status = "active"
    meta.paused_at = None
    meta.add_lifecycle_event("resumed", f"Direct resume: {reason}. Conditions: {conditions}")
    
    # Schedule batched metadata save (non-blocking)
    import asyncio
    loop = asyncio.get_running_loop()
    await mcp_server.schedule_metadata_save(force=False)
    
    return success_response({
        "success": True,
        "message": "Agent resumed successfully",
        "agent_id": agent_id,
        "action": "resumed",
        "conditions": conditions,
        "reason": reason,
        "metrics": {
            "coherence": coherence,
            "risk_score": risk_score,
            "void_active": void_active,
            "previous_status": status
        },
        "note": "Agent resumed via Tier 1 recovery (direct resume). Use request_dialectic_review for complex cases."
    })
