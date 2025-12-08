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
import asyncio
from .utils import success_response, error_response, require_agent_id, _make_json_serializable
from .decorators import mcp_tool
from .validators import validate_complexity, validate_confidence, validate_ethical_drift
from src.logging_utils import get_logger

logger = get_logger(__name__)

# EISV validation utilities (enforce completeness to prevent selection bias)
try:
    from src.eisv_validator import validate_governance_response
    EISV_VALIDATION_AVAILABLE = True
except ImportError:
    EISV_VALIDATION_AVAILABLE = False
    logger.warning("EISV validation not available - install eisv_validator.py")

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
    
    # Check circuit breaker (extract once to avoid nested .get() calls)
    circuit_breaker = result.get('circuit_breaker', {})
    if circuit_breaker.get('triggered'):
        reasons.append("circuit_breaker_triggered")
    
    # Check decision type (extract once to avoid nested .get() calls)
    decision_dict = result.get('decision', {})
    decision = decision_dict.get('action', '')
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
    
    # Validate parameters for simulation
    reported_complexity = arguments.get("complexity", 0.5)
    complexity, error = validate_complexity(reported_complexity)
    if error:
        return [error]
    complexity = complexity or 0.5  # Default if None
    
    reported_confidence = arguments.get("confidence", 1.0)
    confidence, error = validate_confidence(reported_confidence)
    if error:
        return [error]
    confidence = confidence or 1.0  # Default if None
    
    ethical_drift_raw = arguments.get("ethical_drift", [0.0, 0.0, 0.0])
    ethical_drift, error = validate_ethical_drift(ethical_drift_raw)
    if error:
        return [error]
    ethical_drift = ethical_drift or [0.0, 0.0, 0.0]  # Default if None
    
    # Prepare agent state
    import numpy as np
    agent_state = {
        "parameters": np.array(arguments.get("parameters", [])),
        "ethical_drift": np.array(ethical_drift),
        "response_text": arguments.get("response_text", ""),
        "complexity": complexity  # Use validated value
    }
    
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

    # Load metadata if needed (non-blocking)
    loop = asyncio.get_running_loop()  # Use get_running_loop() instead of deprecated get_event_loop()
    await loop.run_in_executor(None, mcp_server.load_metadata)
    
    # Authenticate agent ownership (prevents impersonation)
    # For new agents, allow creation without key (will generate one)
    # For existing agents, require API key
    is_new_agent = agent_id not in mcp_server.agent_metadata
    key_was_generated = False
    
    # ONBOARDING GUIDANCE - Re-enabled (knowledge graph now non-blocking)
    onboarding_guidance = None
    open_questions = []
    if is_new_agent:
        try:
            from src.knowledge_graph import get_knowledge_graph
            graph = await get_knowledge_graph()
            stats = await graph.get_stats()
            
            # Surface open questions for new agents - invite them to participate
            try:
                questions = await graph.query(
                    type="question",
                    status="open",
                    limit=5  # Show top 5 open questions
                )
                # Sort by recency (newest first) and take top 3
                questions.sort(key=lambda q: q.timestamp, reverse=True)
                open_questions = [q.to_dict(include_details=False) for q in questions[:3]]
                logger.debug(f"Found {len(open_questions)} open questions for onboarding")
            except Exception as e:
                logger.warning(f"Could not fetch open questions for onboarding: {e}", exc_info=True)
                open_questions = []  # Ensure it's set even on error
            
            if stats.get("total_discoveries", 0) > 0:
                question_count = stats.get("by_type", {}).get("question", 0)
                onboarding_guidance = {
                    "message": f"Welcome! The knowledge graph contains {stats['total_discoveries']} discoveries from {stats['total_agents']} agents.",
                    "suggestion": "Use search_knowledge_graph to find relevant discoveries by tags or type.",
                    "example_tags": list(stats.get("by_type", {}).keys())[:5] if stats.get("by_type") else []
                }
                
                # Add question invitation if there are open questions
                if open_questions:
                    onboarding_guidance["open_questions"] = {
                        "message": f"Found {len(open_questions)} open question(s) waiting for answers. Want to try responding to one?",
                        "questions": open_questions,
                        "invitation": "Use reply_to_question tool to answer any of these questions and help build shared knowledge.",
                        "tool": "reply_to_question"
                    }
                elif question_count > 0:
                    onboarding_guidance["open_questions"] = {
                        "message": f"There are {question_count} open question(s) in the knowledge graph.",
                        "suggestion": "Use search_knowledge_graph with discovery_type='question' and status='open' to find them.",
                        "tool": "reply_to_question"
                    }
        except Exception as e:
            logger.warning(f"Could not check knowledge graph for onboarding: {e}")
    
    # Get or ensure API key exists
    api_key = arguments.get("api_key")
    if not is_new_agent:
        # Existing agent - require authentication (run in executor to avoid blocking)
        # Reuse loop from line 187 (avoid redundant get_running_loop() call)
        auth_valid, auth_error = await loop.run_in_executor(
            None, 
            mcp_server.require_agent_auth, 
            agent_id, 
            arguments, 
            False  # enforce=False
        )
        if not auth_valid:
            return [auth_error] if auth_error else [error_response("Authentication failed")]
        # Lazy migration: if agent has no key, generate one on first update
        # Note: agent_metadata dict access is fast (no I/O), but generate_api_key might block
        meta = mcp_server.agent_metadata[agent_id]
        if meta.api_key is None:
            meta.api_key = await loop.run_in_executor(None, mcp_server.generate_api_key)
            key_was_generated = True
            logger.info(f"Generated API key for existing agent '{agent_id}' (migration)")
        # Use metadata key if not provided in arguments
        if not api_key:
            api_key = meta.api_key
    else:
        # New agent - will generate key in get_or_create_metadata
        pass
    
    # Check agent status - auto-resume archived agents on engagement
    # (metadata already loaded above at line 185)
    # Get metadata once for reuse throughout function
    meta = mcp_server.agent_metadata.get(agent_id) if agent_id in mcp_server.agent_metadata else None
    
    if meta:
        if meta.status == "archived":
            # Auto-resume: Any engagement resumes archived agents
            meta.status = "active"
            meta.archived_at = None
            meta.add_lifecycle_event("resumed", "Auto-resumed on engagement")
            # Save metadata in executor to avoid blocking
            await loop.run_in_executor(None, mcp_server.save_metadata)
        elif meta.status == "paused":
            # Paused agents still need explicit resume
            return [error_response(
                f"Agent '{agent_id}' is paused. Resume it first before processing updates."
            )]
        elif meta.status == "deleted":
            return [error_response(f"Agent '{agent_id}' is deleted and cannot be used.")]

    # VALIDATION: Derive/validate self-reported complexity and confidence
    # Agents can report these, but we validate against behavior where possible
    # Validate complexity and confidence parameters
    reported_complexity = arguments.get("complexity", 0.5)
    reported_confidence = arguments.get("confidence", 1.0)
    
    complexity, error = validate_complexity(reported_complexity)
    if error:
        return [error]
    complexity = complexity or 0.5  # Default if None
    
    confidence, error = validate_confidence(reported_confidence)
    if error:
        return [error]
    confidence = confidence or 1.0  # Default if None
    
    # Note: Complexity derivation happens in estimate_risk() via GovernanceConfig.derive_complexity()
    # which analyzes response_text content, coherence trends, and validates against self-reported values.
    # The reported complexity here is validated/clamped, but final complexity is derived from behavior.
    
    # Note: Zombie cleanup disabled - adds latency, not critical per-request
    # Cleanup happens in background tasks instead

    # Acquire lock for agent state update (prevents race conditions)
    # Use async lock to avoid blocking event loop (fixes Claude Desktop hangs)
    try:
        async with mcp_server.lock_manager.acquire_agent_lock_async(agent_id, timeout=2.0, max_retries=1):
            # Prepare agent state (use validated complexity and confidence from above)
            import numpy as np
            
            # Validate ethical_drift parameter
            ethical_drift_raw = arguments.get("ethical_drift", [0.0, 0.0, 0.0])
            ethical_drift, error = validate_ethical_drift(ethical_drift_raw)
            if error:
                return [error]
            ethical_drift = ethical_drift or [0.0, 0.0, 0.0]  # Default if None
            
            agent_state = {
                "parameters": np.array(arguments.get("parameters", [])),
                "ethical_drift": np.array(ethical_drift),
                "response_text": arguments.get("response_text", ""),
                "complexity": complexity  # Use validated value
            }

            # Ensure metadata exists (for new agents, this creates it with API key)
            if is_new_agent:
                # Run blocking metadata creation in executor to avoid blocking event loop
                # Reuse loop from line 187 (avoid redundant get_running_loop() call)
                meta = await loop.run_in_executor(None, mcp_server.get_or_create_metadata, agent_id)
                api_key = meta.api_key  # Get generated key
                # Schedule immediate save for new agent creation (critical operation)
                await mcp_server.schedule_metadata_save(force=True)
            else:
                # Reuse metadata fetched earlier (avoid duplicate lookup)
                if not meta:
                    meta = mcp_server.agent_metadata.get(agent_id)
            
            # Use validated confidence (already clamped to [0, 1] above)
            
            # Extract and validate task_type for context-aware EISV interpretation
            from .validators import validate_task_type
            task_type = arguments.get("task_type", "mixed")
            validated_task_type, error = validate_task_type(task_type)
            if error:
                # Invalid task_type - default to mixed and log warning (don't fail, just warn)
                logger.warning(f"Invalid task_type '{task_type}' for agent '{agent_id}', defaulting to 'mixed'")
                task_type = "mixed"
            else:
                task_type = validated_task_type
            
            # Use authenticated update function (async version)
            # Wrap in try/except to catch any exceptions from process_update_authenticated_async
            try:
                # Add task_type to agent_state for context-aware interpretation
                agent_state["task_type"] = task_type
                
                result = await mcp_server.process_update_authenticated_async(
                    agent_id=agent_id,
                    api_key=api_key,
                    agent_state=agent_state,
                    auto_save=True,
                    confidence=confidence
                )
            except PermissionError as e:
                # Re-raise PermissionError to be caught by outer handler
                raise
            except ValueError as e:
                # Re-raise ValueError to be caught by outer handler
                raise
            except Exception as e:
                # Catch any other unexpected exceptions from process_update_authenticated_async
                logger.error(f"Unexpected error in process_update_authenticated_async: {e}", exc_info=True)
                raise Exception(f"Error processing update: {str(e)}") from e
            
            # Update heartbeat (run in executor to avoid blocking)
            # Reuse loop from line 187 (avoid redundant get_running_loop() call)
            await loop.run_in_executor(None, mcp_server.process_mgr.write_heartbeat)

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

            # Add EISV labels for reflexivity - essential for agents to understand their state
            # Bridges physics (Energy, Entropy, Void Integral) with practical understanding
            result['eisv_labels'] = UNITARESMonitor.get_eisv_labels()

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
            
            # Add helpful explanation for sampling_params (helps agents understand what they mean)
            if "sampling_params" in response_data:
                sampling_params = response_data["sampling_params"]
                temp = sampling_params.get("temperature", 0.5)
                max_tokens = sampling_params.get("max_tokens", 100)
                
                # Interpret temperature
                if temp < 0.65:
                    temp_desc = "focused, precise"
                elif temp < 0.9:
                    temp_desc = "balanced approach"
                else:
                    temp_desc = "creative, exploratory"
                
                response_data["sampling_params_note"] = (
                    f"Optional suggestions based on your current state. "
                    f"You can use these for your next generation, or ignore them - they're just recommendations. "
                    f"Temperature {temp:.2f} = {temp_desc}. "
                    f"Max tokens {max_tokens} = suggested response length."
                )

            # Proactive knowledge surfacing - Re-enabled (lightweight, tag-based only)
            # Surface top 3 most relevant discoveries based on agent tags
            # Note: meta already fetched earlier, reuse it (avoid duplicate lookup)
            relevant_discoveries = []
            try:
                agent_tags = meta.tags if meta and meta.tags else []
                
                if agent_tags:
                    from src.knowledge_graph import get_knowledge_graph
                    graph = await get_knowledge_graph()
                    
                    # Query discoveries matching agent tags (open status preferred)
                    tag_matches = await graph.query(
                        tags=agent_tags,
                        status="open",
                        limit=10
                    )
                    
                    # Score by tag overlap (simple relevance)
                    scored = []
                    agent_tags_set = set(agent_tags)
                    for disc in tag_matches:
                        disc_tags_set = set(disc.tags)
                        overlap = len(agent_tags_set & disc_tags_set)
                        if overlap > 0:
                            scored.append((overlap, disc))
                    
                    # Sort by overlap (descending) and take top 3
                    scored.sort(reverse=True, key=lambda x: x[0])
                    relevant_discoveries = [disc.to_dict(include_details=False) for _, disc in scored[:3]]
            except Exception as e:
                # Don't fail if knowledge surfacing fails - this is optional
                logger.debug(f"Could not surface relevant discoveries: {e}")
            
            if relevant_discoveries:
                response_data["relevant_discoveries"] = {
                    "message": f"Found {len(relevant_discoveries)} relevant discovery/discoveries matching your tags",
                    "discoveries": relevant_discoveries
                }
            
            # Include onboarding guidance
            if onboarding_guidance:
                response_data["onboarding"] = onboarding_guidance
            
            # Include API key for new agents or if key was just generated (one-time display)
            # Note: meta already available from earlier (avoid duplicate lookup)
            if is_new_agent or key_was_generated:
                if not meta:
                    meta = mcp_server.agent_metadata.get(agent_id)
                if meta:
                    response_data["api_key"] = meta.api_key
                if is_new_agent:
                    response_data["api_key_warning"] = "⚠️  Save this API key - you'll need it for future updates to authenticate as this agent."
                else:
                    response_data["api_key_warning"] = "⚠️  API key generated (migration). Save this key - you'll need it for future updates to authenticate as this agent. Your old key (if any) is now invalid."

            # Welcome message for first update (helps new agents understand the system)
            # Note: meta already available from earlier in function (line 292 or 365)
            if meta and meta.total_updates == 1:
                response_data["welcome"] = (
                    "Welcome to the governance system! This is your first update. "
                    "The system tracks your work's thermodynamic state (E, I, S, V) and provides "
                    "supportive feedback. Use the metrics and sampling parameters as helpful guidance, "
                    "not requirements. The knowledge graph contains discoveries from other agents - "
                    "feel free to explore it when relevant."
                )
            
            # EQUILIBRIUM-BASED CONVERGENCE ACCELERATION
            # Provide proactive guidance to help agents reach equilibrium (I=1.0, S=0.0) faster
            # Only show for agents with < 20 updates (new agents still converging)
            try:
                # Reload meta to get latest total_updates after the update (it was incremented in process_update_authenticated_async)
                meta = mcp_server.agent_metadata.get(agent_id)
                if meta and meta.total_updates < 20:
                    # Extract metrics from response_data (which comes from result)
                    metrics_dict = response_data.get("metrics", {})
                    E = metrics_dict.get("E", 0.7)
                    I = metrics_dict.get("I", 0.8)
                    S = metrics_dict.get("S", 0.2)
                    V = metrics_dict.get("V", 0.0)
                    
                    # Calculate distance from equilibrium (I=1.0, S=0.0)
                    equilibrium_distance = ((1.0 - I) ** 2 + S ** 2) ** 0.5
                    
                    convergence_guidance = []
                    
                    # High entropy guidance
                    if S > 0.1:
                        convergence_guidance.append({
                            "metric": "S (Entropy)",
                            "current": f"{S:.3f}",
                            "target": "0.0",
                            "guidance": "High entropy detected. Focus on coherent, consistent work to reduce S. "
                                       "Reduce uncertainty by maintaining clear, structured approaches.",
                            "priority": "high" if S > 0.2 else "medium"
                        })
                    
                    # Low integrity guidance
                    if I < 0.9:
                        convergence_guidance.append({
                            "metric": "I (Information Integrity)",
                            "current": f"{I:.3f}",
                            "target": "1.0",
                            "guidance": "Integrity below optimal. Reduce uncertainty, increase coherence. "
                                       "Focus on consistent, well-structured work.",
                            "priority": "high" if I < 0.8 else "medium"
                        })
                    
                    # Low energy guidance
                    if E < 0.7:
                        convergence_guidance.append({
                            "metric": "E (Energy)",
                            "current": f"{E:.3f}",
                            "target": "0.7-1.0",
                            "guidance": "Low energy. Increase exploration and productive capacity. "
                                       "Engage more actively with your work.",
                            "priority": "medium"
                        })
                    
                    # Void guidance (if accumulating imbalance)
                    if abs(V) > 0.1:
                        convergence_guidance.append({
                            "metric": "V (Void Integral)",
                            "current": f"{V:.3f}",
                            "target": "0.0",
                            "guidance": "Energy-integrity imbalance detected. Balance exploration (E) "
                                       "with consistency (I) to reduce void accumulation.",
                            "priority": "medium" if abs(V) > 0.2 else "low"
                        })
                    
                    # Only include if there's actionable guidance
                    if convergence_guidance:
                        response_data["convergence_guidance"] = {
                            "message": f"Equilibrium guidance (distance: {equilibrium_distance:.3f})",
                            "equilibrium_target": {"I": 1.0, "S": 0.0},
                            "current_state": {"E": E, "I": I, "S": S, "V": V},
                            "guidance": convergence_guidance,
                            "note": "These suggestions help you reach equilibrium faster. "
                                   "Mature agents typically converge to I≈1.0, S≈0.0 within 18-24 updates."
                        }
            except Exception as e:
                # Don't fail the update if convergence guidance fails - log and continue
                logger.debug(f"Could not generate convergence guidance: {e}", exc_info=True)
            
            # Note: Maintenance prompt already in mark_response_complete (no need to duplicate)
            
            # EISV Completeness Validation - ensures all four metrics are present (prevents selection bias)
            if EISV_VALIDATION_AVAILABLE:
                try:
                    validate_governance_response(response_data)
                except Exception as validation_error:
                    # Log but don't fail the update - validation is a quality check
                    logger.warning(f"EISV validation warning: {validation_error}")
                    response_data["_eisv_validation_warning"] = str(validation_error)

            # Return immediately - wrap in try/except to catch serialization errors
            # This prevents server crashes if serialization fails
            try:
                return success_response(response_data)
            except Exception as serialization_error:
                # If serialization fails, return minimal error response
                logger.error(f"Failed to serialize response: {serialization_error}", exc_info=True)
                # Return minimal response to prevent server crash
                import json
                from mcp.types import TextContent
                # Extract metrics once to avoid 6 repeated .get() calls
                metrics = result.get("metrics", {})
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "success": True,
                        "status": result.get("status", "unknown"),
                        "decision": result.get("decision", {}),
                        "metrics": {
                            "E": float(metrics.get("E", 0)),
                            "I": float(metrics.get("I", 0)),
                            "S": float(metrics.get("S", 0)),
                            "V": float(metrics.get("V", 0)),
                            "coherence": float(metrics.get("coherence", 0)),
                            "attention_score": float(metrics.get("attention_score", 0))
                        },
                        "sampling_params": result.get("sampling_params", {}),
                        "_warning": "Response serialization had issues - some fields may be missing"
                    })
                )]
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
    except PermissionError as e:
        # Authentication failed
        return [error_response(
            f"Authentication failed: {str(e)}",
            details={"error_type": "authentication_error"},
            recovery={
                "action": "Provide a valid API key for this agent",
                "related_tools": ["get_agent_api_key"],
                "workflow": "1. Use get_agent_api_key to retrieve your key 2. Include api_key in your request"
            }
        )]
    except ValueError as e:
        # Loop detected or validation error
        error_msg = str(e)
        if "Self-monitoring loop detected" in error_msg:
            return [error_response(
                error_msg,
                details={"error_type": "loop_detected"},
                recovery={
                    "action": "Wait for cooldown period to expire before retrying",
                    "related_tools": ["get_governance_metrics"],
                    "workflow": "1. Check current agent status 2. Wait for cooldown to expire 3. Retry with different parameters"
                }
            )]
        else:
            return [error_response(
                f"Validation error: {error_msg}",
                details={"error_type": "validation_error"},
                recovery={
                    "action": "Check your parameters and try again",
                    "related_tools": ["health_check"],
                    "workflow": "1. Verify all parameters are valid 2. Check system health 3. Retry"
                }
            )]
    except Exception as e:
        # Catch any other unexpected errors to prevent disconnection
        logger.error(f"Unexpected error in process_agent_update: {e}", exc_info=True)
        return [error_response(
            f"An unexpected error occurred: {str(e)}",
            details={"error_type": "unexpected_error"},
            recovery={
                "action": "Check server logs for details. If this persists, try restarting the MCP server",
                "related_tools": ["health_check", "get_server_info"],
                "workflow": "1. Check system health 2. Review server logs 3. Restart MCP server if needed"
            }
        )]

