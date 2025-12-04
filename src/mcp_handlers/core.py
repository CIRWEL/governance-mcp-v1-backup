"""
Core governance tool handlers.

EISV Completeness: Utilities available in src/eisv_format.py and src/eisv_validator.py
to ensure all metrics (E, I, S, V) are reported together, preventing selection bias.
See docs/guides/EISV_COMPLETENESS.md for usage.
"""

from typing import Dict, Any, Optional
from mcp.types import TextContent
import json
import sys
import importlib
import re
from .utils import success_response, error_response, require_agent_id
from .decorators import mcp_tool
from src.logging_utils import get_logger

logger = get_logger(__name__)

# EISV validation utilities (enforce completeness to prevent selection bias)
try:
    from src.eisv_validator import validate_governance_response
    EISV_VALIDATION_AVAILABLE = True
except ImportError:
    EISV_VALIDATION_AVAILABLE = False
    logger.warning("EISV validation not available - install eisv_validator.py")
# Import from parent module - use importlib to avoid circular imports
from pathlib import Path

# Get mcp_server_std module
if 'src.mcp_server_std' in sys.modules:
    mcp_server = sys.modules['src.mcp_server_std']
else:
    # Import if not already loaded
    import src.mcp_server_std as mcp_server

from src.governance_monitor import UNITARESMonitor
from datetime import datetime


def _assess_thermodynamic_significance(
    monitor: Optional[Any],  # UNITARESMonitor type (can be None)
    result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Determine if this update is thermodynamically significant.
    
    Significant events worth logging:
    - Risk spiked > 15%
    - Coherence dropped > 10%
    - Void crossed threshold (|V| > 0.10)
    - Circuit breaker triggered
    - Decision is pause/reject
    
    Returns dict with:
        is_significant: bool
        reasons: list[str]
        timestamp: str
    """
    # Significance thresholds (from config)
    from config.governance_config import config
    RISK_SPIKE_THRESHOLD = config.RISK_SPIKE_THRESHOLD
    COHERENCE_DROP_THRESHOLD = config.COHERENCE_DROP_THRESHOLD
    VOID_THRESHOLD = config.SIGNIFICANCE_VOID_THRESHOLD
    HISTORY_WINDOW = config.SIGNIFICANCE_HISTORY_WINDOW
    
    reasons = []
    
    if not monitor:
        return {
            'is_significant': False,
            'reasons': ['No monitor available'],
            'timestamp': datetime.now().isoformat(),
        }
    
    state = monitor.state
    metrics = result.get('metrics', {})
    
    # Check risk spike (compare latest to average of previous)
    if len(state.risk_history) >= 2:
        current_risk = state.risk_history[-1]
        # Use average of previous history as baseline
        history_slice = state.risk_history[-HISTORY_WINDOW:-1] if len(state.risk_history) > 1 else []
        if history_slice:
            baseline_risk = sum(history_slice) / len(history_slice)
            risk_delta = current_risk - baseline_risk
            if risk_delta > RISK_SPIKE_THRESHOLD:
                reasons.append(f"risk_spike: +{risk_delta:.3f} (from {baseline_risk:.3f} to {current_risk:.3f})")
    
    # Check coherence drop
    if len(state.coherence_history) >= 2:
        current_coherence = state.coherence_history[-1]
        history_slice = state.coherence_history[-HISTORY_WINDOW:-1] if len(state.coherence_history) > 1 else []
        if history_slice:
            baseline_coherence = sum(history_slice) / len(history_slice)
            coh_delta = baseline_coherence - current_coherence
            if coh_delta > COHERENCE_DROP_THRESHOLD:
                reasons.append(f"coherence_drop: -{coh_delta:.3f} (from {baseline_coherence:.3f} to {current_coherence:.3f})")
    
    # Check void threshold
    V = state.V
    if abs(V) > VOID_THRESHOLD:
        reasons.append(f"void_significant: V={V:.4f} (threshold: {VOID_THRESHOLD})")
    
    # Check circuit breaker
    if result.get('circuit_breaker', {}).get('triggered'):
        reasons.append("circuit_breaker_triggered")
    
    # Check decision type
    decision = result.get('decision', {}).get('action', '')
    if decision in ['pause', 'reject']:
        reasons.append(f"decision_{decision}")
    
    return {
        'is_significant': len(reasons) > 0,
        'reasons': reasons,
        'timestamp': datetime.now().isoformat(),
    }


@mcp_tool("get_governance_metrics", timeout=10.0)
async def handle_get_governance_metrics(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get current governance state and metrics for an agent without updating state"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]  # Wrap in list for Sequence[TextContent]

    # Load monitor state from disk if not in memory (allows querying agents without recent updates)
    monitor = mcp_server.get_or_create_monitor(agent_id)

    metrics = monitor.get_metrics()

    # Add EISV labels for API documentation
    metrics['eisv_labels'] = UNITARESMonitor.get_eisv_labels()

    return success_response(metrics)


@mcp_tool("simulate_update", timeout=30.0)
async def handle_simulate_update(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle simulate_update tool - dry-run governance cycle without persisting state"""
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]  # Wrap in list for Sequence[TextContent]
    
    # Get or create monitor
    monitor = mcp_server.get_or_create_monitor(agent_id)
    
    # Prepare agent state
    import numpy as np
    agent_state = {
        "parameters": np.array(arguments.get("parameters", [])),
        "ethical_drift": np.array(arguments.get("ethical_drift", [0.0, 0.0, 0.0])),
        "response_text": arguments.get("response_text", ""),
        "complexity": arguments.get("complexity", 0.5)
    }
    
    # Extract confidence parameter (defaults to 1.0 for backward compatibility)
    confidence = float(arguments.get("confidence", 1.0))
    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
    
    # Run simulation (doesn't persist state) with confidence
    result = monitor.simulate_update(agent_state, confidence=confidence)
    
    return success_response({
        "simulation": True,
        **result
    })


@mcp_tool("process_agent_update", timeout=60.0)
async def handle_process_agent_update(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle process_agent_update tool - complex handler with authentication and state management
    
    Share your work and get supportive feedback. This is your companion tool for checking in 
    and understanding your state. Includes automatic timeout protection (60s default).
    """
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]  # Wrap in list for Sequence[TextContent]

    # Authenticate agent ownership (prevents impersonation)
    # For new agents, allow creation without key (will generate one)
    # For existing agents, require API key
    is_new_agent = agent_id not in mcp_server.agent_metadata
    key_was_generated = False
    
    # ONBOARDING GUIDANCE: Suggest querying knowledge graph for new agents
    onboarding_guidance = None
    if is_new_agent:
        try:
            from src.knowledge_graph import get_knowledge_graph
            graph = await get_knowledge_graph()
            stats = await graph.get_stats()
            if stats.get("total_discoveries", 0) > 0:
                # Suggest querying knowledge graph based on agent's purpose
                onboarding_guidance = {
                    "message": "New agent detected. Consider querying knowledge graph to learn from previous sessions.",
                    "suggested_query": "search_knowledge_graph()",
                    "knowledge_available": {
                        "total_discoveries": stats.get("total_discoveries", 0),
                        "total_agents": stats.get("total_agents", 0),
                        "by_type": stats.get("by_type", {}),
                        "example_tags": list(stats.get("by_tag", {}).keys())[:5] if stats.get("by_tag") else []
                    },
                    "tip": "Knowledge persists across sessions but isn't auto-loaded to avoid context bloat. Query what you need when you need it."
                }
        except Exception as e:
            # Don't fail onboarding if knowledge graph check fails
            logger.warning(f"Could not check knowledge graph for onboarding: {e}")
    
    # Get or ensure API key exists
    api_key = arguments.get("api_key")
    if not is_new_agent:
        # Existing agent - require authentication
        auth_valid, auth_error = mcp_server.require_agent_auth(agent_id, arguments, enforce=False)
        if not auth_valid:
            return [auth_error] if auth_error else [error_response("Authentication failed")]
        # Lazy migration: if agent has no key, generate one on first update
        meta = mcp_server.agent_metadata[agent_id]
        if meta.api_key is None:
            meta.api_key = mcp_server.generate_api_key()
            key_was_generated = True
            logger.info(f"Generated API key for existing agent '{agent_id}' (migration)")
        # Use metadata key if not provided in arguments
        if not api_key:
            api_key = meta.api_key
    else:
        # New agent - will generate key in get_or_create_metadata
        pass
    
    # Check agent status - auto-resume archived agents on engagement
    if agent_id in mcp_server.agent_metadata:
        meta = mcp_server.agent_metadata[agent_id]
        if meta.status == "archived":
            # Auto-resume: Any engagement resumes archived agents
            meta.status = "active"
            meta.archived_at = None
            meta.add_lifecycle_event("resumed", "Auto-resumed on engagement")
            await mcp_server.save_metadata_async()
        elif meta.status == "paused":
            # Paused agents still need explicit resume
            return [error_response(
                f"Agent '{agent_id}' is paused. Resume it first before processing updates."
            )]
        elif meta.status == "deleted":
            return [error_response(f"Agent '{agent_id}' is deleted and cannot be used.")]

    # VALIDATION: Derive/validate self-reported complexity and confidence
    # Agents can report these, but we validate against behavior where possible
    reported_complexity = arguments.get("complexity", 0.5)
    reported_confidence = arguments.get("confidence", 1.0)
    
    # Clamp values to valid ranges
    complexity = max(0.0, min(1.0, float(reported_complexity)))
    confidence = max(0.0, min(1.0, float(reported_confidence)))
    
    # Note: Complexity derivation happens in estimate_risk() via GovernanceConfig.derive_complexity()
    # which analyzes response_text content, coherence trends, and validates against self-reported values.
    # The reported complexity here is validated/clamped, but final complexity is derived from behavior.
    
    # Clean up zombies before processing
    try:
        cleaned = mcp_server.process_mgr.cleanup_zombies(max_keep_processes=mcp_server.MAX_KEEP_PROCESSES)
        if cleaned:
            logger.info(f"Cleaned up {len(cleaned)} zombie processes")
    except Exception as e:
        logger.warning(f"Could not clean zombies: {e}")

    # Acquire lock for agent state update (prevents race conditions)
    # The lock manager now has automatic retry with stale lock cleanup built-in
    try:
        with mcp_server.lock_manager.acquire_agent_lock(agent_id, timeout=5.0, max_retries=3):
            # Prepare agent state (use validated complexity and confidence from above)
            import numpy as np
            agent_state = {
                "parameters": np.array(arguments.get("parameters", [])),
                "ethical_drift": np.array(arguments.get("ethical_drift", [0.0, 0.0, 0.0])),
                "response_text": arguments.get("response_text", ""),
                "complexity": complexity  # Use validated value (clamped to [0, 1])
            }

            # Ensure metadata exists (for new agents, this creates it with API key)
            if is_new_agent:
                meta = mcp_server.get_or_create_metadata(agent_id)
                api_key = meta.api_key  # Get generated key
            
            # Use validated confidence (already clamped to [0, 1] above)
            
            # Use authenticated update function (async version)
            result = await mcp_server.process_update_authenticated_async(
                agent_id=agent_id,
                api_key=api_key,
                agent_state=agent_state,
                auto_save=True,
                confidence=confidence
            )
            
            # Update heartbeat
            mcp_server.process_mgr.write_heartbeat()

            # Calculate health status using risk-based thresholds
            # Support both attention_score (new) and risk_score (deprecated) for backward compatibility
            metrics_dict = result.get('metrics', {})
            attention_score = metrics_dict.get('attention_score') or metrics_dict.get('risk_score', None)
            coherence = metrics_dict.get('coherence', None)
            void_active = metrics_dict.get('void_active', False)
            
            health_status, health_message = mcp_server.health_checker.get_health_status(
                risk_score=attention_score,  # health_checker still uses risk_score internally
                coherence=coherence,
                void_active=void_active
            )
            
            # Add health status to response
            if 'metrics' not in result:
                result['metrics'] = {}
            result['metrics']['health_status'] = health_status.value
            result['metrics']['health_message'] = health_message

            # Add EISV labels for API documentation
            result['eisv_labels'] = UNITARESMonitor.get_eisv_labels()

            # Significance detection and auto-export (from orchestrator ideas)
            auto_export_on_significance = arguments.get("auto_export_on_significance", False)
            significance_info = None
            if auto_export_on_significance:
                # Monitor should be in memory after process_update_authenticated_async,
                # but use get_or_create_monitor for consistency and safety
                monitor = mcp_server.get_or_create_monitor(agent_id)
                significance_info = _assess_thermodynamic_significance(
                    monitor=monitor,
                    result=result
                )
                if significance_info.get('is_significant'):
                    # Auto-export significant event
                    try:
                        from .export import handle_export_to_file
                        export_result = await handle_export_to_file({
                            'agent_id': agent_id,
                            'api_key': api_key,
                            'format': 'json',
                            'filename': f"{agent_id}_significant_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            'complete_package': False
                        })
                        # Parse export result
                        export_text = export_result[0].text if export_result else ""
                        if export_text:
                            export_data = json.loads(export_text)
                            significance_info['exported'] = True
                            significance_info['export_path'] = export_data.get('file_path')
                    except Exception as e:
                        # Don't fail the update if export fails
                        logger.warning(f"Auto-export failed: {e}")
                        significance_info['exported'] = False
                        significance_info['export_error'] = str(e)
                else:
                    significance_info['exported'] = False

            # Collect any warnings
            warnings = []
            
            # Check for default agent_id warning
            try:
                default_warning = mcp_server.check_agent_id_default(agent_id)
                if default_warning:
                    warnings.append(default_warning)
            except (NameError, AttributeError):
                # Function not available (shouldn't happen, but be defensive)
                pass
            except Exception as e:
                # Log but don't fail the update
                logger.warning(f"Could not check agent_id default: {e}")

            # Build response
            response_data = result.copy()
            if warnings:
                response_data["warning"] = "; ".join(warnings)
            
            # Add helpful explanation for sampling_params (optional - use if helpful)
            if "sampling_params" in response_data:
                sampling_params = response_data["sampling_params"]
                response_data["sampling_params_note"] = (
                    "Optional suggestions based on your current state. "
                    "You can use these for your next generation, or ignore them - they're just recommendations. "
                    f"Temperature {sampling_params.get('temperature', 0):.2f} = {'more creative' if sampling_params.get('temperature', 0) > 0.7 else 'more focused' if sampling_params.get('temperature', 0) < 0.5 else 'balanced'} approach. "
                    f"Max tokens {sampling_params.get('max_tokens', 0)} = suggested response length."
                )
            
            # Add significance info AFTER response_data is created
            if significance_info:
                response_data['significance'] = significance_info
            
            # Proactive knowledge surfacing - show relevant discoveries from previous sessions
            # ENHANCED: Tag-based relevance matching + response text analysis
            # SECURITY: Validate and filter discoveries before surfacing
            try:
                from src.knowledge_graph import get_knowledge_graph
                graph = await get_knowledge_graph()
                
                # Get agent metadata for tag matching
                agent_meta = mcp_server.agent_metadata.get(agent_id)
                agent_tags = set(agent_meta.tags) if agent_meta and agent_meta.tags else set()
                
                # Extract keywords from response_text for relevance matching
                response_text = arguments.get("response_text", "")
                response_keywords = set()
                if response_text:
                    # Simple keyword extraction (lowercase, split on whitespace/punctuation)
                    import re
                    words = re.findall(r'\b\w{4,}\b', response_text.lower())  # Words 4+ chars
                    # Filter common stop words
                    stop_words = {'that', 'this', 'with', 'from', 'have', 'been', 'will', 'were', 'what', 'when', 'where', 'which', 'there', 'their', 'them', 'they', 'then', 'than', 'these', 'those'}
                    response_keywords = {w for w in words if w not in stop_words}
                
                # Get discoveries from OTHER agents (not this one) - "from_previous_sessions"
                # Query all discoveries, filter out this agent's, prioritize open status
                all_discoveries = await graph.query(
                    agent_id=None,  # Get all agents' discoveries
                    status=None,  # Get all statuses (we'll filter after)
                    limit=50  # Get more to filter from
                )
                
                # Filter out this agent's discoveries
                other_agent_discoveries = [
                    d for d in all_discoveries 
                    if d.agent_id != agent_id  # Only discoveries from other agents
                ]
                
                # SECURITY: Filter out suspicious/disputed discoveries
                # Check agent reputation/health for discoveries
                validated_discoveries = []
                for d in other_agent_discoveries:
                    # Skip discoveries from deleted/archived agents
                    source_meta = mcp_server.agent_metadata.get(d.agent_id)
                    if source_meta and source_meta.status in ["deleted", "archived"]:
                        continue
                    
                    # Skip discoveries with suspicious patterns (basic validation)
                    # Filter out obvious poisoning attempts
                    suspicious_keywords = ["backdoor", "exploit", "vulnerability", "hack", "bypass"]
                    summary_lower = d.summary.lower()
                    if any(keyword in summary_lower for keyword in suspicious_keywords):
                        # Only skip if from low-reputation agent or unvalidated
                        if not source_meta or source_meta.total_updates < 5:
                            continue  # Skip suspicious discoveries from new/unproven agents
                    
                    validated_discoveries.append(d)
                
                # ENHANCED RELEVANCE SCORING: Tag matching + keyword matching + reputation
                def relevance_score(d) -> float:  # d is DiscoveryNode from knowledge_graph
                    score = 0.0
                    
                    # 1. Tag matching (strong signal - 0.5 points per matching tag)
                    discovery_tags = set(d.tags) if d.tags else set()
                    tag_overlap = agent_tags & discovery_tags
                    score += len(tag_overlap) * 0.5
                    
                    # 2. Keyword matching (medium signal - 0.2 points per matching keyword)
                    discovery_text = (d.summary + " " + (d.details or "")).lower()
                    discovery_words = set(re.findall(r'\b\w{4,}\b', discovery_text))
                    keyword_overlap = response_keywords & discovery_words
                    score += len(keyword_overlap) * 0.2
                    
                    # 3. Reputation (base trust - 0.0 to 1.3)
                    meta = mcp_server.agent_metadata.get(d.agent_id)
                    if meta:
                        # Base score from total_updates (more updates = more established)
                        base_score = min(meta.total_updates / 100.0, 1.0)  # Cap at 1.0
                        
                        # Health bonus: healthy agents get +0.3, moderate +0.1, critical 0
                        health_bonus = 0.0
                        if meta.status == "active":
                            # Check agent's governance state for health
                            monitor = mcp_server.monitors.get(d.agent_id)
                            if monitor:
                                state = monitor.get_state()
                                if state.coherence > 0.60 and state.risk_score < 0.40:
                                    health_bonus = 0.3  # Healthy agent
                                elif state.coherence > 0.40 and state.risk_score < 0.60:
                                    health_bonus = 0.1  # Moderate agent
                        
                        score += base_score + health_bonus
                    else:
                        # Unknown agent = low reputation
                        score += 0.1
                    
                    # 4. Status bonus (open discoveries prioritized)
                    if d.status == "open":
                        score += 0.3
                    elif d.status == "resolved":
                        score += 0.1
                    
                    # 5. Type bonus (bugs and improvements prioritized)
                    if d.type == "bug_found":
                        score += 0.2
                    elif d.type == "improvement":
                        score += 0.1
                    
                    return score
                
                # Sort by relevance score (highest first)
                validated_discoveries.sort(key=relevance_score, reverse=True)
                
                # Take top 3 most relevant discoveries (lightweight - avoid context bloat)
                relevant_discoveries = validated_discoveries[:3]
                
                if relevant_discoveries:
                    # Determine relevance reason for each discovery
                    def get_relevance_reason(d):
                        discovery_tags = set(d.tags) if d.tags else set()
                        if agent_tags & discovery_tags:
                            return "tag_match"
                        discovery_text = (d.summary + " " + (d.details or "")).lower()
                        discovery_words = set(re.findall(r'\b\w{4,}\b', discovery_text))
                        if response_keywords & discovery_words:
                            return "keyword_match"
                        return "general"
                    
                    response_data["memory"] = {
                        "from_previous_sessions": [
                            {
                                "summary": d.summary,
                                "type": d.type,
                                "tags": d.tags,
                                "severity": d.severity,
                                "status": d.status,
                                "discovered_at": d.timestamp,
                                "agent_id": d.agent_id,
                                "discovery_id": d.id,
                                "relevance": get_relevance_reason(d)
                            }
                            for d in relevant_discoveries
                        ],
                        "message": "Relevant discoveries from previous sessions (top 3 by relevance)",
                        "tip": "Use search_knowledge_graph() to query more discoveries. Knowledge persists but isn't auto-loaded to avoid context bloat."
                    }
            except Exception as e:
                # Don't fail the update if knowledge surfacing fails
                logger.warning(f"Could not surface knowledge: {e}", exc_info=True)
            
            # Include onboarding guidance for new agents
            if onboarding_guidance:
                response_data["onboarding"] = onboarding_guidance
            
            # Include API key for new agents or if key was just generated (one-time display)
            if is_new_agent or key_was_generated:
                meta = mcp_server.agent_metadata[agent_id]
                response_data["api_key"] = meta.api_key
                if is_new_agent:
                    response_data["api_key_warning"] = "⚠️  Save this API key - you'll need it for future updates to authenticate as this agent."
                else:
                    response_data["api_key_warning"] = "⚠️  API key generated (migration). Save this key - you'll need it for future updates to authenticate as this agent."

            # Welcome message for first update
            meta = mcp_server.agent_metadata.get(agent_id)
            if meta and meta.total_updates == 1:
                response_data["welcome"] = (
                    "👋 First update logged! This system is here to help you navigate complexity, "
                    "not judge you. Most updates get 'proceed' - you're doing fine. "
                    "The metrics (E/I/S/coherence) show how your work flows over time."
                )
            
            # MAINTENANCE PROMPT: Surface THIS agent's open discoveries for resolution
            # Behavioral nudge: Remind agent to resolve their own discoveries
            try:
                from src.knowledge_graph import get_knowledge_graph
                graph = await get_knowledge_graph()
                
                # Get open discoveries from THIS agent (recent - last 7 days)
                from datetime import datetime, timedelta
                now = datetime.now()
                one_week_ago = (now - timedelta(days=7)).isoformat()
                
                agent_open_discoveries = await graph.query(
                    agent_id=agent_id,
                    status="open",
                    limit=10
                )
                
                # Filter to recent discoveries (last 7 days)
                recent_open = [
                    d for d in agent_open_discoveries
                    if d.timestamp >= one_week_ago
                ]
                
                # Prioritize bug_found and high severity
                recent_open.sort(key=lambda d: (
                    0 if d.type == "bug_found" else 1,  # Bugs first
                    0 if d.severity == "high" else 1 if d.severity == "medium" else 2,  # High severity first
                    d.timestamp  # Then by recency
                ))
                
                if recent_open:
                    response_data["maintenance_prompt"] = {
                        "message": f"You have {len(recent_open)} open discovery/discoveries from recent sessions. Consider resolving them:",
                        "open_discoveries": [
                            {
                                "id": d.id,
                                "summary": d.summary,
                                "type": d.type,
                                "severity": d.severity,
                                "timestamp": d.timestamp
                            }
                            for d in recent_open[:5]  # Top 5 for prompt
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
            except Exception as e:
                # Don't fail the update if maintenance prompt check fails - this is a nice-to-have
                logger.warning(f"Could not check open discoveries for maintenance: {e}")

            # EISV Completeness Validation: Ensure all four metrics (E, I, S, V) are present
            # This prevents selection bias by catching incomplete metric reporting
            if EISV_VALIDATION_AVAILABLE:
                try:
                    validate_governance_response(response_data)
                except Exception as validation_error:
                    # Log warning but don't fail the request (graceful degradation)
                    logger.warning(f"EISV validation failed: {validation_error}")
                    logger.warning(f"EISV Validation Warning: {validation_error}")
                    # Optionally add warning to response
                    response_data["_eisv_validation_warning"] = str(validation_error)

            return success_response(response_data)
    except TimeoutError as e:
        # Lock acquisition failed even after automatic retries and cleanup
        # Try one more aggressive cleanup attempt
        try:
            from src.lock_cleanup import cleanup_stale_state_locks
            project_root = Path(__file__).parent.parent.parent
            cleanup_result = cleanup_stale_state_locks(project_root=project_root, max_age_seconds=60.0, dry_run=False)
            if cleanup_result['cleaned'] > 0:
                logger.info(f"Auto-recovery: Cleaned {cleanup_result['cleaned']} stale lock(s) after timeout")
        except Exception as cleanup_error:
            logger.warning(f"Could not perform emergency lock cleanup: {cleanup_error}")
        
        return [error_response(
            f"Failed to acquire lock for agent '{agent_id}' after automatic retries and cleanup. "
            f"This usually means another active process is updating this agent. "
            f"The system has automatically cleaned stale locks. If this persists, try: "
            f"1) Wait a few seconds and retry, 2) Check for other Cursor/Claude sessions, "
            f"3) Use cleanup_stale_locks tool, or 4) Restart Cursor if stuck."
        )]

