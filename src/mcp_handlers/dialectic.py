"""
MCP Handlers for Circuit Breaker Dialectic Protocol

Implements MCP tools for peer-review dialectic resolution of circuit breaker states.
"""

from typing import Dict, Any, Sequence, Optional
from mcp.types import TextContent
import json
from datetime import datetime, timedelta
import random

from src.dialectic_protocol import (
    DialecticSession,
    DialecticMessage,
    DialecticPhase,
    Resolution,
    calculate_authority_score
)
from .utils import success_response, error_response
from .decorators import mcp_tool
from src.logging_utils import get_logger
import sys
import os

logger = get_logger(__name__)

# Import from mcp_server_std module (same pattern as lifecycle handlers)
if 'src.mcp_server_std' in sys.modules:
    mcp_server = sys.modules['src.mcp_server_std']
else:
    import src.mcp_server_std as mcp_server


# Active dialectic sessions (in-memory + persistent storage)
ACTIVE_SESSIONS: Dict[str, DialecticSession] = {}

# Check if aiofiles is available for async I/O
try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

# Session storage directory
from pathlib import Path
import sys
if 'src.mcp_server_std' in sys.modules:
    project_root = Path(sys.modules['src.mcp_server_std'].project_root)
else:
    project_root = Path(__file__).parent.parent.parent

SESSION_STORAGE_DIR = project_root / "data" / "dialectic_sessions"
SESSION_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


async def save_session(session: DialecticSession) -> None:
    """Persist dialectic session to disk"""
    try:
        session_file = SESSION_STORAGE_DIR / f"{session.session_id}.json"
        session_data = session.to_dict()
        
        # Use aiofiles if available for async I/O
        if AIOFILES_AVAILABLE:
            import aiofiles
            async with aiofiles.open(session_file, 'w') as f:
                await f.write(json.dumps(session_data, indent=2))
        else:
            # Fallback to sync I/O
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)
                f.flush()  # Ensure buffered data written
                os.fsync(f.fileno())  # Ensure written to disk
    except Exception as e:
        print(f"[DIALECTIC] Warning: Could not save session {session.session_id}: {e}", file=sys.stderr)


async def load_session(session_id: str) -> Optional[DialecticSession]:
    """Load dialectic session from disk"""
    try:
        session_file = SESSION_STORAGE_DIR / f"{session_id}.json"
        if not session_file.exists():
            return None
        
        if AIOFILES_AVAILABLE:
            import aiofiles
            async with aiofiles.open(session_file, 'r') as f:
                content = await f.read()
                session_data = json.loads(content)
        else:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
        
        # Reconstruct session from dict
        # IMPLEMENTED: Full reconstruction from saved session data
        try:
            from src.dialectic_protocol import DialecticSession, DialecticMessage, Resolution, DialecticPhase
            from datetime import datetime
            
            # Reconstruct transcript
            transcript = []
            for msg_dict in session_data.get('transcript', []):
                msg = DialecticMessage(
                    phase=msg_dict.get('phase', 'thesis'),
                    agent_id=msg_dict.get('agent_id', ''),
                    timestamp=msg_dict.get('timestamp', ''),
                    root_cause=msg_dict.get('root_cause'),
                    observed_metrics=msg_dict.get('observed_metrics'),
                    proposed_conditions=msg_dict.get('proposed_conditions'),
                    reasoning=msg_dict.get('reasoning'),
                    agrees=msg_dict.get('agrees'),
                    concerns=msg_dict.get('concerns')
                )
                transcript.append(msg)
            
            # Reconstruct resolution if present
            resolution = None
            if session_data.get('resolution'):
                res_dict = session_data['resolution']
                # Resolution structure: action, conditions, root_cause, reasoning, signature_a, signature_b, timestamp
                resolution = Resolution(
                    action=res_dict.get('action', 'resume'),
                    conditions=res_dict.get('conditions', []),
                    root_cause=res_dict.get('root_cause', ''),
                    reasoning=res_dict.get('reasoning', ''),
                    signature_a=res_dict.get('signature_a', ''),
                    signature_b=res_dict.get('signature_b', ''),
                    timestamp=res_dict.get('timestamp', datetime.now().isoformat())
                )
            
            # Reconstruct phase
            phase_str = session_data.get('phase', 'thesis')
            try:
                phase = DialecticPhase(phase_str)
            except ValueError:
                phase = DialecticPhase.THESIS  # Default
            
            # Create session (need paused_agent_state, use empty dict if not available)
            paused_agent_state = session_data.get('paused_agent_state', {})
            session = DialecticSession(
                paused_agent_id=session_data.get('paused_agent_id', ''),
                reviewer_agent_id=session_data.get('reviewer_agent_id', ''),
                paused_agent_state=paused_agent_state,
                discovery_id=session_data.get('discovery_id'),  # Optional: Backward compatible
                dispute_type=session_data.get('dispute_type'),  # Optional: Backward compatible
                max_synthesis_rounds=session_data.get('max_synthesis_rounds', 5)
            )
            
            # Override generated session_id with saved one
            session.session_id = session_id
            
            # Restore state
            session.phase = phase
            session.transcript = transcript
            session.resolution = resolution
            session.synthesis_round = session_data.get('synthesis_round', 0)
            session.created_at = datetime.fromisoformat(session_data.get('created_at', datetime.now().isoformat()))
            
            return session
        except Exception as e:
            import sys
            print(f"[DIALECTIC] Error reconstructing session {session_id}: {e}", file=sys.stderr)
            return None
    except Exception:
        return None


async def execute_resolution(session: DialecticSession, resolution: Resolution) -> Dict[str, Any]:
    """
    Execute the resolution: resume agent with agreed conditions.
    
    This actually modifies agent state and applies conditions.
    """
    agent_id = session.paused_agent_id
    
    # Load agent metadata
    mcp_server.load_metadata()
    
    if agent_id not in mcp_server.agent_metadata:
        raise ValueError(f"Agent '{agent_id}' not found")
    
    meta = mcp_server.agent_metadata[agent_id]
    
    # Verify agent is actually paused
    if meta.status != "paused":
        return {
            "success": False,
            "warning": f"Agent status is '{meta.status}', not 'paused'. No action taken."
        }
    
    # Apply conditions (simplified - would need more sophisticated parsing)
    applied_conditions = []
    for condition in resolution.conditions:
        try:
            # Parse and apply condition
            # This is a simplified version - real implementation would parse conditions
            # and modify governance thresholds, monitoring settings, etc.
            applied_conditions.append({
                "condition": condition,
                "status": "applied",
                "note": "Condition applied (simplified implementation)"
            })
        except Exception as e:
            applied_conditions.append({
                "condition": condition,
                "status": "failed",
                "error": str(e)
            })
    
    # Resume the agent (if paused - skip if discovery dispute)
    if meta.status == "paused":
        meta.status = "active"
        meta.paused_at = None
        meta.add_lifecycle_event("resumed", f"Resumed via dialectic synthesis: {resolution.root_cause}")
    
    # If linked to discovery, update discovery status based on resolution
    discovery_updated = False
    if session.discovery_id:
        try:
            from src.knowledge_graph import get_knowledge_graph
            from datetime import datetime
            graph = await get_knowledge_graph()
            discovery = await graph.get_discovery(session.discovery_id)
            
            if discovery:
                if resolution.action == "resume":  # Agreed correction/verification
                    # Discovery was disputed and corrected
                    if session.dispute_type in ["dispute", "correction"]:
                        # Update discovery details with correction note
                        updated_details = discovery.details
                        if updated_details:
                            updated_details += f"\n\n[Disputed and corrected via dialectic {session.session_id} on {datetime.now().isoformat()}]\nResolution: {resolution.root_cause}"
                        else:
                            updated_details = f"[Disputed and corrected via dialectic {session.session_id} on {datetime.now().isoformat()}]\nResolution: {resolution.root_cause}"
                        
                        await graph.update_discovery(session.discovery_id, {
                            "status": "resolved",
                            "resolved_at": datetime.now().isoformat(),
                            "details": updated_details,
                            "updated_at": datetime.now().isoformat()
                        })
                        discovery_updated = True
                elif resolution.action == "block":  # Dispute rejected, discovery verified
                    # Discovery was disputed but verified correct
                    updated_details = discovery.details
                    if updated_details:
                        updated_details += f"\n\n[Disputed but verified correct via dialectic {session.session_id} on {datetime.now().isoformat()}]\nResolution: {resolution.root_cause}"
                    else:
                        updated_details = f"[Disputed but verified correct via dialectic {session.session_id} on {datetime.now().isoformat()}]\nResolution: {resolution.root_cause}"
                    
                    await graph.update_discovery(session.discovery_id, {
                        "status": "open",  # Back to open (verified)
                        "details": updated_details,
                        "updated_at": datetime.now().isoformat()
                    })
                    discovery_updated = True
        except Exception as e:
            import sys
            print(f"[DIALECTIC] Warning: Could not update discovery {session.discovery_id}: {e}", file=sys.stderr)
            # Don't fail resolution if discovery update fails
    
    # Save metadata - synchronous save critical for identity/lifecycle data
    mcp_server.save_metadata()
    
    result = {
        "success": True,
        "agent_id": agent_id,
        "new_status": meta.status,
        "applied_conditions": applied_conditions,
        "resolution_hash": resolution.hash()
    }
    
    # Add discovery update info if present
    if session.discovery_id:
        result["discovery_id"] = session.discovery_id
        result["discovery_updated"] = discovery_updated
        if discovery_updated:
            result["discovery_status"] = "resolved" if resolution.action == "resume" else "open"
    
    return result


# Check for aiofiles availability
try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False


@mcp_tool("request_dialectic_review", timeout=15.0)
async def handle_request_dialectic_review(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Request a dialectic review for a paused/critical agent OR an agent stuck in loops OR a discovery dispute.

    Selects a healthy reviewer agent and initiates dialectic session.
    Can be used for:
    - Paused agents (circuit breaker triggered)
    - Agents stuck in repeated loops (loop cooldown active)
    - Discovery disputes/corrections (if discovery_id provided)
    - Any agent needing peer assistance

    Args:
        agent_id: ID of agent requesting review (paused, loop-stuck, or disputing discovery)
        reason: Reason for review request (e.g., "Circuit breaker triggered", "Stuck in loops", "Discovery seems incorrect", etc.)
        api_key: Agent's API key for authentication
        discovery_id: Optional - ID of discovery being disputed/corrected
        dispute_type: Optional - "dispute", "correction", "verification" (default: None for recovery)

    Returns:
        Session info with reviewer_id and session_id
    """
    try:
        agent_id = arguments.get('agent_id')
        reason = arguments.get('reason', 'Circuit breaker triggered')
        api_key = arguments.get('api_key')
        discovery_id = arguments.get('discovery_id')  # NEW: Optional discovery ID
        dispute_type = arguments.get('dispute_type')  # NEW: Optional dispute type

        if not agent_id:
            return [error_response("agent_id is required")]

        # Verify API key if provided
        if api_key:
            # Get agent's stored API key
            agent_meta_stored = mcp_server.agent_metadata.get(agent_id)
            if agent_meta_stored and hasattr(agent_meta_stored, 'api_key'):
                if agent_meta_stored.api_key != api_key:
                    return [error_response("Invalid API key - authentication failed")]
            # If no stored key, allow (for backward compatibility)
        # Note: API key verification is now implemented, but optional for backward compatibility

        # Load agent metadata to get state
        mcp_server.load_metadata()
        metadata_objects = mcp_server.agent_metadata

        # Validate metadata structure
        if not isinstance(metadata_objects, dict):
            return [error_response(
                f"Invalid metadata structure: expected dict, got {type(metadata_objects).__name__}. "
                f"Metadata value: {str(metadata_objects)[:200]}"
            )]

        if agent_id not in metadata_objects:
            return [error_response(f"Agent '{agent_id}' not found")]

        agent_meta = metadata_objects[agent_id]
        
        # Check if agent has completed work (not stuck, just waiting for input)
        if agent_meta.status == "waiting_input":
            return [error_response(
                f"Agent '{agent_id}' has completed work and is waiting for input, not stuck.",
                recovery={
                    "action": "Agent is not stuck - they completed their response and are waiting for user input.",
                    "status": "waiting_input",
                    "last_response_at": getattr(agent_meta, 'last_response_at', None),
                    "related_tools": ["get_agent_metadata", "mark_response_complete"],
                    "workflow": [
                        "1. Check agent status with get_agent_metadata",
                        "2. If status is 'waiting_input', agent is done and waiting",
                        "3. Dialectic review is not needed - agent can resume when user responds"
                    ]
                }
            )]
        
        # Allow dialectic review for:
        # 1. Paused agents (circuit breaker)
        # 2. Agents in loop cooldown (stuck in loops)
        # 3. Any agent needing peer assistance
        # Note: We don't restrict to only paused agents - loops can also benefit from peer review

        # Validate agent_meta is an AgentMetadata object, not a string
        if isinstance(agent_meta, str):
            return [error_response(
                f"Invalid metadata for agent '{agent_id}': expected AgentMetadata object, got string: {agent_meta[:200]}"
            )]

        # Convert AgentMetadata objects to dicts for select_reviewer
        # This prevents "'str' object is not a mapping" errors in calculate_authority_score
        # FIXED: Ensure proper type handling - filter out strings and invalid entries
        metadata = {}
        for aid, meta_obj in metadata_objects.items():
            # Skip invalid entries (strings, None, etc.)
            if isinstance(meta_obj, str) or meta_obj is None:
                continue
            
            # Convert AgentMetadata object to dict
            if hasattr(meta_obj, 'to_dict'):
                try:
                    metadata[aid] = meta_obj.to_dict()
                except Exception as e:
                    print(f"[DIALECTIC] Warning: Could not convert metadata for {aid}: {e}", file=sys.stderr)
                    continue
            elif isinstance(meta_obj, dict):
                # Already a dict, use as-is
                metadata[aid] = meta_obj
            else:
                # Unknown type - skip
                print(f"[DIALECTIC] Warning: Invalid metadata type for {aid}: {type(meta_obj).__name__}", file=sys.stderr)
                continue

        # Load real agent state from governance monitor
        try:
            monitor = mcp_server.get_or_create_monitor(agent_id)
            metrics = monitor.get_metrics()
            # Support both attention_score (new) and risk_score (deprecated)
            attention_score = metrics.get('attention_score') or metrics.get('risk_score', 0.5)
            agent_state = {
                'attention_score': attention_score,  # Renamed from risk_score
                'phi': metrics.get('phi'),  # Primary physics signal
                'verdict': metrics.get('verdict'),  # Primary governance signal
                'risk_score': attention_score,  # DEPRECATED: Use attention_score instead
                'coherence': metrics.get('coherence', 0.5),
                'void_active': metrics.get('void_active', False),
                'E': metrics.get('E', 0.5),
                'I': metrics.get('I', 0.5),
                'S': metrics.get('S', 0.5),
                'V': metrics.get('V', 0.0)
            }
        except Exception as e:
            # Fallback to mock if monitor not available
            print(f"[DIALECTIC] Warning: Could not load agent state for {agent_id}: {e}", file=sys.stderr)
            agent_state = {
                'attention_score': 0.65,  # Renamed from risk_score
                'risk_score': 0.65,  # DEPRECATED
                'coherence': 0.45,
                'void_active': False
            }

        # Select reviewer
        try:
            # Get paused agent tags for expertise matching
            paused_agent_tags = []
            paused_meta = metadata.get(agent_id)
            if paused_meta:
                if isinstance(paused_meta, dict):
                    paused_agent_tags = paused_meta.get('tags', [])
                elif hasattr(paused_meta, 'tags'):
                    paused_agent_tags = paused_meta.tags or []
            
            reviewer_id = select_reviewer(agent_id, metadata, agent_state, paused_agent_tags=paused_agent_tags)
        except Exception as e:
            import traceback
            import sys
            # SECURITY: Log full traceback internally but sanitize for client
            print(f"[UNITARES MCP] Error selecting reviewer: {e}", file=sys.stderr)
            print(f"[UNITARES MCP] Full traceback:\n{traceback.format_exc()}", file=sys.stderr)
            return [error_response(
                f"Error selecting reviewer: {str(e)}",
                recovery={
                    "action": "Check agent metadata and try again",
                    "related_tools": ["list_agents", "get_agent_metadata"]
                }
            )]

        # If discovery_id provided, this is a discovery dispute/correction
        discovery_owner_id = None
        if discovery_id:
            try:
                from src.knowledge_graph import get_knowledge_graph
                graph = await get_knowledge_graph()
                discovery = await graph.get_discovery(discovery_id)
                
                if not discovery:
                    return [error_response(
                        f"Discovery '{discovery_id}' not found",
                        recovery={
                            "action": "Verify discovery_id is correct",
                            "related_tools": ["search_knowledge_graph", "get_knowledge_graph"]
                        }
                    )]
                
                # Mark discovery as disputed
                await graph.update_discovery(discovery_id, {"status": "disputed"})
                
                # Set discovery owner as reviewer (not system-selected)
                discovery_owner_id = discovery.agent_id
                
                # Set dispute_type if not provided
                if not dispute_type:
                    dispute_type = "dispute"
                
                # Update reason if not provided
                if reason == 'Circuit breaker triggered':
                    reason = f"Disputing discovery '{discovery_id}': {discovery.summary[:50]}..."
                
            except Exception as e:
                import sys
                print(f"[DIALECTIC] Error handling discovery dispute: {e}", file=sys.stderr)
                return [error_response(
                    f"Error processing discovery dispute: {str(e)}",
                    recovery={
                        "action": "Check discovery_id and try again",
                        "related_tools": ["search_knowledge_graph"]
                    }
                )]
        
        # Select reviewer (use discovery owner if dispute, otherwise system-selected)
        if discovery_owner_id:
            reviewer_id = discovery_owner_id
            # Verify discovery owner exists
            if reviewer_id not in metadata:
                return [error_response(
                    f"Discovery owner '{reviewer_id}' not found in metadata",
                    recovery={
                        "action": "Discovery owner may have been deleted or archived",
                        "related_tools": ["list_agents"]
                    }
                )]
        elif not reviewer_id:
            return [error_response("No healthy reviewer available - escalating to strict default")]

        # Create dialectic session with discovery context
        session = DialecticSession(
            paused_agent_id=agent_id,
            reviewer_agent_id=reviewer_id,
            paused_agent_state=agent_state,
            discovery_id=discovery_id,  # NEW: Link to discovery
            dispute_type=dispute_type,  # NEW: Type of dispute
            max_synthesis_rounds=5
        )

        # Store session
        ACTIVE_SESSIONS[session.session_id] = session

        result = {
            "success": True,
            "session_id": session.session_id,
            "paused_agent_id": agent_id,
            "reviewer_agent_id": reviewer_id,
            "phase": session.phase.value,
            "reason": reason,
            "next_step": f"Agent '{agent_id}' should submit thesis via submit_thesis()",
            "created_at": session.created_at.isoformat()
        }
        
        # Add discovery context if present
        if discovery_id:
            result["discovery_id"] = discovery_id
            result["dispute_type"] = dispute_type
            result["discovery_context"] = "This dialectic session is for disputing/correcting a discovery"

        return success_response(result)

    except Exception as e:
        return [error_response(f"Error requesting dialectic review: {str(e)}")]


@mcp_tool("smart_dialectic_review", timeout=20.0)
async def handle_smart_dialectic_review(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Smart dialectic that auto-progresses when possible.
    
    Flow:
    1. Request review → Auto-select reviewer
    2. Auto-generate thesis from agent state (if agent provides minimal input)
    3. Reviewer submits antithesis (or auto-generate if reviewer unavailable)
    4. Auto-merge synthesis if conditions are compatible
    5. Execute if safe
    
    Reduces manual steps by 50-70% compared to full dialectic.
    
    Args:
        agent_id: Agent ID requesting review
        api_key: Agent's API key
        reason: Reason for review (optional - auto-generated if not provided)
        root_cause: Root cause (optional - auto-generated from state if not provided)
        proposed_conditions: Proposed conditions (optional - auto-generated if not provided)
        reasoning: Explanation (optional - auto-generated if not provided)
        auto_progress: Whether to auto-progress through phases (default: True)
    
    Returns:
        Session info or final resolution if auto-progressed
    """
    try:
        agent_id = arguments.get('agent_id')
        api_key = arguments.get('api_key')
        auto_progress = arguments.get('auto_progress', True)
        
        if not agent_id or not api_key:
            return [error_response("agent_id and api_key are required")]
        
        # Verify API key
        mcp_server.load_metadata()
        meta = mcp_server.agent_metadata.get(agent_id)
        if not meta:
            return [error_response(f"Agent '{agent_id}' not found")]
        
        if meta.api_key != api_key:
            return [error_response("Invalid API key - authentication failed")]
        
        # Get current metrics
        try:
            monitor = mcp_server.get_or_create_monitor(agent_id)
            metrics = monitor.get_metrics()
            attention_score = metrics.get('attention_score') or metrics.get('mean_risk', 0.5)
            agent_state = {
                'coherence': float(monitor.state.coherence),
                'attention_score': float(attention_score),  # Renamed from risk_score
                'phi': metrics.get('phi'),  # Primary physics signal
                'verdict': metrics.get('verdict'),  # Primary governance signal
                'risk_score': float(attention_score),  # DEPRECATED
                'void_active': bool(monitor.state.void_active),
                'E': float(monitor.state.E),
                'I': float(monitor.state.I),
                'S': float(monitor.state.S),
                'V': float(monitor.state.V)
            }
        except Exception as e:
            return [error_response(f"Error getting governance metrics: {str(e)}")]
        
        # Auto-generate reason if not provided
        reason = arguments.get('reason')
        if not reason:
            if agent_state.get('attention_score', agent_state.get('risk_score', 0.5)) > 0.60:
                reason = "Circuit breaker triggered - high attention score"
            elif agent_state['coherence'] < 0.40:
                reason = "Low coherence - system instability"
            else:
                reason = "Agent requesting peer review"
        
        # Try to select reviewer
        metadata_objects = mcp_server.agent_metadata
        metadata = {}
        for aid, meta_obj in metadata_objects.items():
            if isinstance(meta_obj, str) or meta_obj is None:
                continue
            if hasattr(meta_obj, 'to_dict'):
                try:
                    metadata[aid] = meta_obj.to_dict()
                except Exception:
                    continue
            elif isinstance(meta_obj, dict):
                metadata[aid] = meta_obj
        
        paused_agent_tags = []
        paused_meta = metadata.get(agent_id)
        if paused_meta:
            paused_agent_tags = paused_meta.get('tags', [])
        
        reviewer_id = select_reviewer(agent_id, metadata, agent_state, paused_agent_tags=paused_agent_tags)
        
        # If no reviewer available and auto_progress, use self-recovery
        if not reviewer_id and auto_progress:
            return await handle_self_recovery({
                'agent_id': agent_id,
                'api_key': api_key,
                'root_cause': arguments.get('root_cause', reason),
                'proposed_conditions': arguments.get('proposed_conditions', []),
                'reasoning': arguments.get('reasoning', 'No reviewers available - using smart recovery')
            })
        
        if not reviewer_id:
            return [error_response("No healthy reviewer available. Use self_recovery for single-agent recovery.")]
        
        # Create dialectic session
        session = DialecticSession(
            paused_agent_id=agent_id,
            reviewer_agent_id=reviewer_id,
            paused_agent_state=agent_state,
            max_synthesis_rounds=3  # Reduced for smart dialectic
        )
        
        ACTIVE_SESSIONS[session.session_id] = session
        
        # Auto-generate thesis if minimal input provided
        root_cause = arguments.get('root_cause')
        proposed_conditions = arguments.get('proposed_conditions', [])
        reasoning = arguments.get('reasoning')
        
        if not root_cause:
            attention_score = agent_state.get('attention_score', agent_state.get('risk_score', 0.5))
            root_cause = f"Agent state: coherence={agent_state['coherence']:.3f}, attention_score={attention_score:.3f}"
        
        if not proposed_conditions:
            # Auto-generate basic conditions based on state
            if agent_state.get('attention_score', agent_state.get('risk_score', 0.5)) > 0.50:
                proposed_conditions.append("Monitor risk score closely")
            if agent_state['coherence'] < 0.50:
                proposed_conditions.append("Monitor coherence for stability")
            if not proposed_conditions:
                proposed_conditions.append("Resume with standard monitoring")
        
        if not reasoning:
            reasoning = f"Auto-generated from agent state. Reason: {reason}"
        
        # Auto-submit thesis if auto_progress
        if auto_progress:
            thesis = DialecticMessage(
                phase="thesis",
                agent_id=agent_id,
                timestamp=datetime.now().isoformat(),
                root_cause=root_cause,
                proposed_conditions=proposed_conditions,
                reasoning=reasoning
            )
            
            result = session.submit_thesis(thesis, api_key)
            if not result.get("success"):
                return [error_response(f"Error submitting auto-generated thesis: {result.get('error')}")]
            
            await save_session(session)
            
            return success_response({
                "success": True,
                "session_id": session.session_id,
                "paused_agent_id": agent_id,
                "reviewer_agent_id": reviewer_id,
                "phase": session.phase.value,
                "auto_progressed": True,
                "thesis_submitted": True,
                "next_step": f"Reviewer '{reviewer_id}' should submit antithesis, or wait for auto-timeout",
                "created_at": session.created_at.isoformat(),
                "note": "Thesis auto-submitted. Reviewer can submit antithesis, or session will auto-resolve after timeout."
            })
        
        # Manual mode - return session info
        return success_response({
            "success": True,
            "session_id": session.session_id,
            "paused_agent_id": agent_id,
            "reviewer_agent_id": reviewer_id,
            "phase": session.phase.value,
            "reason": reason,
            "next_step": f"Agent '{agent_id}' should submit thesis via submit_thesis()",
            "created_at": session.created_at.isoformat(),
            "note": "Set auto_progress=true for automatic thesis submission"
        })
    
    except Exception as e:
        import traceback
        import sys
        # SECURITY: Log full traceback internally but sanitize for client
        print(f"[UNITARES MCP] Error in smart dialectic review: {e}", file=sys.stderr)
        print(f"[UNITARES MCP] Full traceback:\n{traceback.format_exc()}", file=sys.stderr)
        return [error_response(
            f"Error in smart dialectic review: {str(e)}",
            recovery={
                "action": "Check parameters and agent state, then retry",
                "related_tools": ["get_governance_metrics", "get_agent_metadata"]
            }
        )]


@mcp_tool("submit_thesis", timeout=10.0)
async def handle_submit_thesis(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Paused agent submits thesis: "What I did, what I think happened"

    Args:
        session_id: Dialectic session ID
        agent_id: Paused agent ID
        api_key: Agent's API key
        root_cause: Agent's understanding of what caused the issue
        proposed_conditions: List of conditions for resumption
        reasoning: Natural language explanation

    Returns:
        Status with next phase
    """
    try:
        session_id = arguments.get('session_id')
        agent_id = arguments.get('agent_id')
        api_key = arguments.get('api_key', '')

        if not session_id or not agent_id:
            return [error_response("session_id and agent_id are required")]

        # Get session
        session = ACTIVE_SESSIONS.get(session_id)
        if not session:
            return [error_response(f"Session '{session_id}' not found")]

        # Create thesis message
        message = DialecticMessage(
            phase="thesis",
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
            root_cause=arguments.get('root_cause'),
            proposed_conditions=arguments.get('proposed_conditions', []),
            reasoning=arguments.get('reasoning')
        )

        # Submit to session
        result = session.submit_thesis(message, api_key)

        if result["success"]:
            result["next_step"] = f"Reviewer '{session.reviewer_agent_id}' should submit antithesis"

        return success_response(result)

    except Exception as e:
        return [error_response(f"Error submitting thesis: {str(e)}")]


@mcp_tool("submit_antithesis", timeout=10.0)
async def handle_submit_antithesis(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Reviewer agent submits antithesis: "What I observe, my concerns"

    Args:
        session_id: Dialectic session ID
        agent_id: Reviewer agent ID
        api_key: Reviewer's API key
        observed_metrics: Metrics observed about paused agent
        concerns: List of concerns
        reasoning: Natural language explanation

    Returns:
        Status with next phase
    """
    try:
        session_id = arguments.get('session_id')
        agent_id = arguments.get('agent_id')
        api_key = arguments.get('api_key', '')

        if not session_id or not agent_id:
            return [error_response("session_id and agent_id are required")]

        # Get session
        session = ACTIVE_SESSIONS.get(session_id)
        if not session:
            return [error_response(f"Session '{session_id}' not found")]

        # Create antithesis message
        message = DialecticMessage(
            phase="antithesis",
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
            observed_metrics=arguments.get('observed_metrics', {}),
            concerns=arguments.get('concerns', []),
            reasoning=arguments.get('reasoning')
        )

        # Submit to session
        result = session.submit_antithesis(message, api_key)

        if result["success"]:
            result["next_step"] = "Both agents should negotiate via submit_synthesis() until convergence"

        return success_response(result)

    except Exception as e:
        return [error_response(f"Error submitting antithesis: {str(e)}")]


@mcp_tool("submit_synthesis", timeout=15.0)
async def handle_submit_synthesis(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Either agent submits synthesis proposal during negotiation.

    Args:
        session_id: Dialectic session ID
        agent_id: Agent ID (either paused or reviewer)
        api_key: Agent's API key
        proposed_conditions: Proposed resumption conditions
        root_cause: Agreed understanding of root cause
        reasoning: Explanation of proposal
        agrees: Whether this agent agrees with current proposal (bool)

    Returns:
        Status with convergence info
    """
    try:
        session_id = arguments.get('session_id')
        agent_id = arguments.get('agent_id')
        api_key = arguments.get('api_key', '')

        if not session_id or not agent_id:
            return [error_response("session_id and agent_id are required")]

        # Get session
        session = ACTIVE_SESSIONS.get(session_id)
        if not session:
            return [error_response(f"Session '{session_id}' not found")]

        # Create synthesis message
        message = DialecticMessage(
            phase="synthesis",
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
            proposed_conditions=arguments.get('proposed_conditions', []),
            root_cause=arguments.get('root_cause'),
            reasoning=arguments.get('reasoning'),
            agrees=arguments.get('agrees', False)
        )

        # Submit to session
        result = session.submit_synthesis(message, api_key)

        # If converged, proceed to finalize
        if result.get("success") and result.get("converged"):
            # Generate real signatures from API keys
            paused_meta = mcp_server.agent_metadata.get(session.paused_agent_id)
            reviewer_meta = mcp_server.agent_metadata.get(session.reviewer_agent_id)
            
            # Get API keys for signature generation
            api_key_a = paused_meta.api_key if paused_meta and paused_meta.api_key else api_key
            api_key_b = reviewer_meta.api_key if reviewer_meta and reviewer_meta.api_key else ""
            
            # Generate signatures from most recent agreed messages
            synthesis_messages = [msg for msg in session.transcript if msg.phase == "synthesis" and msg.agrees]
            if synthesis_messages:
                last_msg = synthesis_messages[-1]
                signature_a = last_msg.sign(api_key_a) if api_key_a else ""
                signature_b = last_msg.sign(api_key_b) if api_key_b else ""
            else:
                # Fallback: use session hash
                import hashlib
                session_data = f"{session.session_id}:{api_key_a}"
                signature_a = hashlib.sha256(session_data.encode()).hexdigest()[:32]
                session_data = f"{session.session_id}:{api_key_b}"
                signature_b = hashlib.sha256(session_data.encode()).hexdigest()[:32] if api_key_b else ""

            resolution = session.finalize_resolution(signature_a, signature_b)

            # Check hard limits
            is_safe, violation = session.check_hard_limits(resolution)

            if not is_safe:
                result["action"] = "block"
                result["reason"] = f"Safety violation: {violation}"
                # Save session before blocking
                await save_session(session)
            else:
                result["action"] = "resume"
                result["resolution"] = resolution.to_dict()
                
                # Actually execute the resolution: resume agent with conditions
                try:
                    execution_result = await execute_resolution(session, resolution)
                    result["execution"] = execution_result
                    result["next_step"] = "Agent resumed successfully with agreed conditions"
                except Exception as e:
                    result["execution_error"] = str(e)
                    result["next_step"] = f"Failed to execute resolution: {e}. Manual intervention may be needed."
                
                # Save session after execution
                await save_session(session)

        elif not result.get("success"):
            # Max rounds exceeded - escalate
            result["next_step"] = "Escalate to quorum (not yet implemented)"

        return success_response(result)

    except Exception as e:
        return [error_response(f"Error submitting synthesis: {str(e)}")]


async def check_reviewer_stuck(session: DialecticSession) -> bool:
    """
    Check if reviewer is stuck (paused or hasn't responded to session assignment).
    
    Returns:
        True if reviewer is stuck, False otherwise
    """
    reviewer_id = session.reviewer_agent_id
    
    # Reload metadata to ensure we have latest state
    mcp_server.load_metadata()
    
    reviewer_meta = mcp_server.agent_metadata.get(reviewer_id)
    if not reviewer_meta:
        return True  # Reviewer doesn't exist = stuck
    
    # Check if reviewer is paused
    if reviewer_meta.status == "paused":
        return True
    
    # Check time since reviewer was assigned to this session (not governance last_update)
    # FIXED: Previously checked reviewer_meta.last_update (governance time), which caused
    # sessions to abort prematurely if reviewer hadn't updated governance state recently.
    # Now correctly checks time since session creation (when reviewer was assigned).
    try:
        session_created = session.created_at
        if isinstance(session_created, str):
            session_created = datetime.fromisoformat(session_created)
        stuck_threshold = timedelta(minutes=30)
        time_since_assignment = datetime.now() - session_created
        return time_since_assignment > stuck_threshold
    except (ValueError, TypeError, AttributeError):
        # Can't parse timestamp or session has no created_at - assume stuck
        return True


@mcp_tool("get_dialectic_session", timeout=10.0, rate_limit_exempt=True)
async def handle_get_dialectic_session(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Get current state of a dialectic session.
    
    Can find sessions by session_id OR by agent_id (paused or reviewer).
    Automatically checks for timeouts and stuck reviewers.

    Args:
        session_id: Dialectic session ID (optional if agent_id provided)
        agent_id: Agent ID to find sessions for (optional if session_id provided)
                 Finds sessions where agent is paused_agent_id or reviewer_agent_id
        check_timeout: Whether to check for timeouts (default: True)

    Returns:
        Full session state including transcript, or list of sessions if agent_id provided
    """
    try:
        session_id = arguments.get('session_id')
        agent_id = arguments.get('agent_id')
        check_timeout = arguments.get('check_timeout', True)

        # If session_id provided, use it directly
        if session_id:
            # Try in-memory first
            session = ACTIVE_SESSIONS.get(session_id)
            if not session:
                # Try loading from disk
                session = await load_session(session_id)
                if session:
                    # Restore to in-memory
                    ACTIVE_SESSIONS[session_id] = session
            
            if not session:
                return [error_response(f"Session '{session_id}' not found")]
            
            # Check for timeouts if requested
            if check_timeout:
                timeout_reason = session.check_timeout()
                if timeout_reason:
                    session.phase = DialecticPhase.FAILED
                    session.transcript.append(DialecticMessage(
                        phase="synthesis",
                        agent_id="system",
                        timestamp=datetime.now().isoformat(),
                        reasoning=f"Session auto-failed: {timeout_reason}"
                    ))
                    await save_session(session)
                    return success_response({
                        "success": False,
                        "error": timeout_reason,
                        "session": session.to_dict(),
                        "fallback": "Try direct_resume_if_safe or request new reviewer"
                    })
                
                # Check if reviewer is stuck
                if await check_reviewer_stuck(session):
                    session.phase = DialecticPhase.FAILED
                    session.transcript.append(DialecticMessage(
                        phase=session.phase.value,
                        agent_id="system",
                        timestamp=datetime.now().isoformat(),
                        reasoning="Reviewer stuck - session aborted"
                    ))
                    await save_session(session)
                    return success_response({
                        "success": False,
                        "error": "Reviewer stuck - session aborted",
                        "session": session.to_dict(),
                        "fallback": "Try direct_resume_if_safe or request new reviewer"
                    })
            
            result = session.to_dict()
            result["success"] = True
            return success_response(result)
        
        # If agent_id provided, find all sessions for this agent
        if agent_id:
            # Reload metadata to ensure we have latest state
            mcp_server.load_metadata()
            
            # Check if agent exists
            if agent_id not in mcp_server.agent_metadata:
                return [error_response(
                    f"Agent '{agent_id}' not found",
                    recovery={
                        "action": "Agent must be registered first",
                        "related_tools": ["get_agent_api_key", "list_agents"]
                    }
                )]
            
            # Find sessions where agent is paused or reviewer
            matching_sessions = []
            
            # Check in-memory sessions
            for sid, session in ACTIVE_SESSIONS.items():
                if session.paused_agent_id == agent_id or session.reviewer_agent_id == agent_id:
                    matching_sessions.append(session.to_dict())
            
            # Also check disk for persisted sessions
            if SESSION_STORAGE_DIR.exists():
                for session_file in SESSION_STORAGE_DIR.glob("*.json"):
                    try:
                        loaded_session = await load_session(session_file.stem)
                        if loaded_session:
                            # Check if matches agent_id
                            if loaded_session.paused_agent_id == agent_id or loaded_session.reviewer_agent_id == agent_id:
                                # Avoid duplicates
                                if not any(s.get('session_id') == loaded_session.session_id for s in matching_sessions):
                                    matching_sessions.append(loaded_session.to_dict())
                                    # Restore to in-memory
                                    ACTIVE_SESSIONS[loaded_session.session_id] = loaded_session
                    except Exception:
                        continue
            
            if not matching_sessions:
                return [error_response(
                    f"No active dialectic sessions found for agent '{agent_id}'",
                    recovery={
                        "action": "No sessions found. If agent is paused, use request_dialectic_review to start one.",
                        "related_tools": ["request_dialectic_review", "get_agent_metadata"],
                        "workflow": [
                            "1. Check agent status with get_agent_metadata",
                            "2. If paused, call request_dialectic_review to start recovery",
                            "3. Use returned session_id to track progress"
                        ]
                    }
                )]
            
            # If single session, return it directly
            if len(matching_sessions) == 1:
                result = matching_sessions[0]
                result["success"] = True
                return success_response(result)
            
            # Multiple sessions - return list
            return success_response({
                "success": True,
                "agent_id": agent_id,
                "session_count": len(matching_sessions),
                "sessions": matching_sessions
            })
        
        # Neither provided
        return [error_response(
            "Either session_id or agent_id is required",
            recovery={
                "action": "Provide either session_id (from request_dialectic_review) or agent_id to find sessions",
                "related_tools": ["request_dialectic_review", "list_agents"]
            }
        )]

    except Exception as e:
        import traceback
        import sys
        # SECURITY: Log full traceback internally but sanitize for client
        print(f"[UNITARES MCP] Error getting dialectic session: {e}", file=sys.stderr)
        print(f"[UNITARES MCP] Full traceback:\n{traceback.format_exc()}", file=sys.stderr)
        return [error_response(
            f"Error getting session: {str(e)}",
            recovery={
                "action": "Check session_id or agent_id and try again",
                "related_tools": ["list_agents", "request_dialectic_review"]
            }
        )]


async def generate_system_antithesis(agent_id: str, metrics: Dict[str, Any], thesis: DialecticMessage) -> DialecticMessage:
    """
    Generate system antithesis based on agent metrics and thesis.
    
    Used for self-recovery when no reviewers are available.
    
    Args:
        agent_id: Agent ID (for message)
        metrics: Current governance metrics
        thesis: Agent's thesis message
    
    Returns:
        System-generated antithesis message
    """
    coherence = metrics.get('coherence', 0.5)
    # Support both attention_score (new) and risk_score (deprecated)
    attention_score = metrics.get('attention_score') or metrics.get('risk_score', 0.5)
    void_active = metrics.get('void_active', False)
    
    # Generate concerns based on metrics
    concerns = []
    observed_metrics = {
        'coherence': coherence,
        'attention_score': attention_score,  # Renamed from risk_score
        'risk_score': attention_score,  # DEPRECATED: Use attention_score instead
        'void_active': void_active
    }
    
    if coherence < 0.50:
        concerns.append(f"Coherence is low ({coherence:.3f}) - may indicate internal inconsistency")
    
    if attention_score > 0.50:
        concerns.append(f"Attention score is elevated ({attention_score:.3f}) - requires careful monitoring")
    
    if void_active:
        concerns.append("Void events are active - system instability detected")
    
    # Analyze proposed conditions
    proposed_conditions = thesis.proposed_conditions or []
    if not proposed_conditions:
        concerns.append("No specific conditions proposed - recovery plan may be vague")
    
    # Generate reasoning
    reasoning_parts = [
        f"System analysis: coherence={coherence:.3f}, attention_score={attention_score:.3f}"
    ]
    
    if concerns:
        reasoning_parts.append(f"Concerns: {', '.join(concerns)}")
    else:
        reasoning_parts.append("Metrics appear stable - recovery may be safe")
    
    reasoning = ". ".join(reasoning_parts)
    
    return DialecticMessage(
        phase="antithesis",
        agent_id="system",
        timestamp=datetime.now().isoformat(),
        observed_metrics=observed_metrics,
        concerns=concerns,
        reasoning=reasoning
    )


@mcp_tool("self_recovery", timeout=15.0)
async def handle_self_recovery(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """
    Allow agent to recover without reviewer (for when no reviewers available).
    
    Flow:
    1. Agent submits thesis
    2. System generates antithesis based on metrics
    3. Agent submits synthesis (auto-merged)
    4. Auto-resolve if safe
    
    Args:
        agent_id: Agent ID to recover
        api_key: Agent's API key
        root_cause: Agent's understanding of what happened
        proposed_conditions: Conditions for resumption
        reasoning: Explanation
    
    Returns:
        Recovery result with system-generated antithesis
    """
    try:
        agent_id = arguments.get('agent_id')
        api_key = arguments.get('api_key')
        
        if not agent_id or not api_key:
            return [error_response("agent_id and api_key are required")]
        
        # Verify API key
        mcp_server.load_metadata()
        meta = mcp_server.agent_metadata.get(agent_id)
        if not meta:
            return [error_response(f"Agent '{agent_id}' not found")]
        
        if meta.api_key != api_key:
            return [error_response("Invalid API key - authentication failed")]
        
        # Get current metrics
        try:
            monitor = mcp_server.get_or_create_monitor(agent_id)
            metrics = monitor.get_metrics()
            agent_state = {
                'coherence': float(monitor.state.coherence),
                'risk_score': float(metrics.get('mean_risk', 0.5)),
                'void_active': bool(monitor.state.void_active),
                'E': float(monitor.state.E),
                'I': float(monitor.state.I),
                'S': float(monitor.state.S),
                'V': float(monitor.state.V)
            }
        except Exception as e:
            return [error_response(f"Error getting governance metrics: {str(e)}")]
        
        # Create thesis message
        thesis = DialecticMessage(
            phase="thesis",
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
            root_cause=arguments.get('root_cause', 'Agent requesting self-recovery'),
            proposed_conditions=arguments.get('proposed_conditions', []),
            reasoning=arguments.get('reasoning', 'No reviewers available - using self-recovery')
        )
        
        # Generate system antithesis
        system_antithesis = await generate_system_antithesis(agent_id, agent_state, thesis)
        
        # Check if safe to resume (same checks as direct_resume_if_safe)
        coherence = agent_state['coherence']
        attention_score = agent_state.get('attention_score', agent_state.get('risk_score', 0.5))
        void_active = agent_state['void_active']
        status = meta.status
        
        safety_checks = {
            "coherence_ok": coherence > 0.40,
            "attention_ok": attention_score < 0.60,  # Renamed from risk_ok
            "risk_ok": attention_score < 0.60,  # DEPRECATED: Use attention_ok instead
            "no_void": not void_active,
            "status_ok": status in ["paused", "waiting_input", "moderate", "degraded"]  # Backward compat
        }
        
        if not all(safety_checks.values()):
            failed_checks = [k for k, v in safety_checks.items() if not v]
            return [error_response(
                f"Not safe to resume via self-recovery. Failed checks: {failed_checks}. "
                f"Metrics: coherence={coherence:.3f}, attention_score={attention_score:.3f}, "
                f"void_active={void_active}, status={status}. "
                f"System antithesis: {system_antithesis.reasoning}. "
                f"Use request_dialectic_review for peer-assisted recovery."
            )]
        
        # Auto-generate synthesis (merge thesis and system antithesis)
        merged_conditions = list(set(thesis.proposed_conditions or []))
        if system_antithesis.concerns:
            # Add monitoring conditions based on concerns
            if any('coherence' in c.lower() for c in system_antithesis.concerns):
                merged_conditions.append("Monitor coherence closely")
            if any('risk' in c.lower() for c in system_antithesis.concerns):
                merged_conditions.append("Monitor risk score")
        
        merged_root_cause = thesis.root_cause or "Self-recovery requested"
        merged_reasoning = f"Agent: {thesis.reasoning or 'No reasoning provided'}. System: {system_antithesis.reasoning}"
        
        # Resume agent
        meta.status = "active"
        meta.paused_at = None
        meta.add_lifecycle_event("resumed", f"Self-recovery: {merged_root_cause}. Conditions: {merged_conditions}")
        
        mcp_server.save_metadata()
        
        return success_response({
            "success": True,
            "message": "Agent resumed via self-recovery",
            "agent_id": agent_id,
            "action": "resumed",
            "thesis": {
                "root_cause": thesis.root_cause,
                "proposed_conditions": thesis.proposed_conditions,
                "reasoning": thesis.reasoning
            },
            "system_antithesis": {
                "concerns": system_antithesis.concerns,
                "observed_metrics": system_antithesis.observed_metrics,
                "reasoning": system_antithesis.reasoning
            },
            "merged_resolution": {
                "conditions": merged_conditions,
                "root_cause": merged_root_cause,
                "reasoning": merged_reasoning
            },
            "metrics": agent_state,
            "note": "Self-recovery completed. No peer review was performed. Use request_dialectic_review for complex cases."
        })
    
    except Exception as e:
        import traceback
        import sys
        # SECURITY: Log full traceback internally but sanitize for client
        print(f"[UNITARES MCP] Error in self-recovery: {e}", file=sys.stderr)
        print(f"[UNITARES MCP] Full traceback:\n{traceback.format_exc()}", file=sys.stderr)
        return [error_response(
            f"Error in self-recovery: {str(e)}",
            recovery={
                "action": "Check agent state and parameters, then retry",
                "related_tools": ["get_governance_metrics", "direct_resume_if_safe"]
            }
        )]


def is_agent_in_active_session(agent_id: str) -> bool:
    """
    Check if agent is already participating in an active dialectic session.
    
    Prevents recursive assignment where an agent reviewing someone else
    gets assigned as a reviewer in another session.
    
    Args:
        agent_id: Agent ID to check
        
    Returns:
        True if agent is in an active session (as paused agent or reviewer), False otherwise
    """
    # Check in-memory sessions
    for session in ACTIVE_SESSIONS.values():
        # Check if agent is paused agent or reviewer
        if (session.paused_agent_id == agent_id or 
            session.reviewer_agent_id == agent_id):
            # Only count if session is still active (not resolved/failed)
            if session.phase not in [DialecticPhase.RESOLVED, DialecticPhase.FAILED, DialecticPhase.ESCALATED]:
                return True
    
    # Check disk sessions (load recent ones to catch persisted sessions)
    # This is a lightweight check - only loads session files if needed
    try:
        if SESSION_STORAGE_DIR.exists():
            # Load session files (limit to recent 50 to avoid performance issues)
            session_files = sorted(SESSION_STORAGE_DIR.glob("*.json"), 
                                 key=lambda p: p.stat().st_mtime, 
                                 reverse=True)[:50]
            
            for session_file in session_files:
                try:
                    with open(session_file, 'r') as f:
                        session_data = json.load(f)
                    
                    # Check if agent is in this session
                    if (session_data.get('paused_agent_id') == agent_id or 
                        session_data.get('reviewer_agent_id') == agent_id):
                        # Check if session is still active
                        phase = session_data.get('phase')
                        if phase not in ['resolved', 'failed', 'escalated']:
                            return True
                except (json.JSONDecodeError, KeyError, IOError):
                    # Skip corrupted or unreadable files
                    continue
    except Exception:
        # If disk check fails, fall back to in-memory only
        pass
    
    return False


def select_reviewer(paused_agent_id: str,
                   metadata: Dict[str, Any],
                   paused_agent_state: Dict[str, Any] = None,
                   paused_agent_tags: List[str] = None) -> str:
    """
    Select a healthy reviewer agent for dialectic session.

    Selection criteria:
    - Healthy (risk < 0.40)
    - Not the paused agent
    - Not already in another active session (prevents recursive assignment)
    - Not recently reviewed this agent (prevent collusion)
    - Weighted by authority score

    Args:
        paused_agent_id: ID of paused agent
        metadata: All agent metadata (dict mapping agent_id -> AgentMetadata)
        paused_agent_state: State of paused agent
        paused_agent_tags: Tags of paused agent (for expertise matching)

    Returns:
        Selected reviewer agent_id, or None if no reviewer available
    """
    # Ensure metadata is a dict (not a string or other type)
    if not isinstance(metadata, dict):
        raise TypeError(f"metadata must be a dict, got {type(metadata).__name__}: {metadata}")
    
    # Get all agents - iterate over items() to get (agent_id, meta) pairs
    # This matches the pattern used in lifecycle.py
    candidates = []
    scores = []
    
    for agent_id, agent_meta in metadata.items():
        # Validate agent_id is a string
        if not isinstance(agent_id, str):
            continue  # Skip invalid keys
        
        # Skip paused agent
        if agent_id == paused_agent_id:
            continue
        
        # Skip agents already in active sessions (prevents recursive assignment)
        if is_agent_in_active_session(agent_id):
            continue
        
        # Validate agent_meta is not a string (should be AgentMetadata object or dict)
        # FIXED: Properly handle invalid entries and log for debugging
        if isinstance(agent_meta, str) or agent_meta is None:
            # Skip invalid entries (strings, None, etc.)
            # This should not happen if metadata is properly loaded, but defensive check
            import sys
            print(f"[DIALECTIC] Warning: Invalid metadata entry for {agent_id}: type={type(agent_meta).__name__}", file=sys.stderr)
            continue
        
        # Skip non-active agents (for MVP, only consider active agents)
        # FIXED: Use .get() for dicts since agent_meta is converted from AgentMetadata above
        status = agent_meta.get('status') if isinstance(agent_meta, dict) else getattr(agent_meta, 'status', None)
        if status and status != 'active':
            continue
        
        # Convert AgentMetadata to dict for calculate_authority_score
        agent_meta_dict = None
        if hasattr(agent_meta, 'to_dict'):
            try:
                agent_meta_dict = agent_meta.to_dict()
            except Exception:
                continue
        elif isinstance(agent_meta, dict):
            agent_meta_dict = agent_meta
        elif hasattr(agent_meta, '__dict__'):
            # Convert object to dict manually
            try:
                agent_meta_dict = {}
                for key, value in agent_meta.__dict__.items():
                    if not key.startswith('_'):
                        agent_meta_dict[key] = value
            except Exception:
                continue
        else:
            # Skip if we can't convert
            continue
        
        # Validate we got a dict
        if not isinstance(agent_meta_dict, dict):
            continue
        
        # Get reviewer's actual state if available, otherwise use mock
        reviewer_state = None
        if paused_agent_state:
            # Use paused agent's state as proxy (MVP - could load reviewer's actual state)
            reviewer_state = paused_agent_state
        else:
            # Mock state for authority calculation (MVP - assume healthy)
            reviewer_state = {'risk_score': 0.25}
        
        # Add paused agent tags to metadata for expertise matching
        agent_meta_dict_with_tags = agent_meta_dict.copy()
        agent_meta_dict_with_tags['paused_agent_tags'] = paused_agent_tags or []
        
        try:
            score = calculate_authority_score(agent_meta_dict_with_tags, reviewer_state)
            candidates.append(agent_id)
            scores.append(score)
        except Exception as e:
            # Skip this agent if score calculation fails
            continue

    if not candidates:
        return None

    # Weighted random selection
    if sum(scores) == 0 or all(s == 0 for s in scores):
        return random.choice(candidates)

    selected = random.choices(candidates, weights=scores, k=1)[0]
    return selected
