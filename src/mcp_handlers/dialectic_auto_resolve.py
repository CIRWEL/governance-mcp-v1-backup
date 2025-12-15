"""
Auto-Resolve Stuck Dialectic Sessions

Quick Win A: Automatically resolve sessions that are stuck/inactive for >5 minutes.
This removes artificial barriers and prevents session conflicts.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
import asyncio

from src.logging_utils import get_logger
from src.dialectic_db import DialecticDB, DEFAULT_DB_PATH
from src.dialectic_protocol import DialecticPhase

logger = get_logger(__name__)

# Stuck session threshold: 5 minutes of inactivity
STUCK_SESSION_THRESHOLD = timedelta(minutes=5)


async def auto_resolve_stuck_sessions() -> Dict[str, Any]:
    """
    Automatically resolve sessions that are stuck/inactive for >5 minutes.
    
    A session is considered "stuck" if:
    1. Status is 'active' but no activity for >5 minutes
    2. Phase is AWAITING_THESIS and created >5 minutes ago
    3. Phase is ANTITHESIS and thesis submitted >5 minutes ago with no antithesis
    4. Phase is SYNTHESIS and last update >5 minutes ago
    
    Returns:
        Dict with counts of resolved sessions and details
    """
    db = DialecticDB(DEFAULT_DB_PATH)
    conn = None
    
    try:
        conn = db._get_connection()
        now = datetime.now()
        threshold_time = (now - STUCK_SESSION_THRESHOLD).isoformat()
        
        # Find stuck sessions
        # Check updated_at if available, otherwise use created_at
        cursor = conn.execute("""
            SELECT session_id, paused_agent_id, reviewer_agent_id, phase, status, 
                   created_at, updated_at
            FROM dialectic_sessions
            WHERE status = 'active'
            AND (
                (updated_at IS NOT NULL AND updated_at < ?) OR
                (updated_at IS NULL AND created_at < ?)
            )
        """, (threshold_time, threshold_time))
        
        stuck_sessions = [dict(row) for row in cursor.fetchall()]
        
        if not stuck_sessions:
            return {
                "resolved_count": 0,
                "message": "No stuck sessions found"
            }
        
        # Resolve each stuck session
        resolved_count = 0
        resolved_details = []
        
        for session in stuck_sessions:
            session_id = session["session_id"]
            paused_agent_id = session["paused_agent_id"]
            phase = session["phase"]
            
            # Mark as failed with reason
            conn.execute("""
                UPDATE dialectic_sessions
                SET status = 'failed',
                    phase = ?,
                    updated_at = ?
                WHERE session_id = ?
            """, ("failed", now.isoformat(), session_id))
            
            # Add failure message to transcript
            failure_reason = f"Session auto-resolved: inactive for >{STUCK_SESSION_THRESHOLD.total_seconds()/60:.0f} minutes"
            
            # Save failure message
            conn.execute("""
                INSERT INTO dialectic_messages
                (session_id, agent_id, message_type, timestamp, reasoning)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                "system",
                "failed",
                now.isoformat(),
                failure_reason
            ))
            
            resolved_count += 1
            resolved_details.append({
                "session_id": session_id,
                "paused_agent_id": paused_agent_id,
                "phase": phase,
                "reason": "inactive_too_long"
            })
            
            logger.info(f"Auto-resolved stuck session {session_id[:16]}... (paused_agent: {paused_agent_id}, phase: {phase})")
        
        conn.commit()
        
        return {
            "resolved_count": resolved_count,
            "resolved_sessions": resolved_details,
            "message": f"Auto-resolved {resolved_count} stuck session(s)"
        }
        
    except Exception as e:
        logger.error(f"Error auto-resolving stuck sessions: {e}", exc_info=True)
        if conn is not None:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.warning(f"Error rolling back transaction: {rollback_error}")
        return {
            "resolved_count": 0,
            "error": str(e),
            "message": "Failed to auto-resolve stuck sessions"
        }
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as close_error:
                logger.warning(f"Error closing database connection: {close_error}")


async def check_and_resolve_stuck_sessions() -> Dict[str, Any]:
    """
    Check for stuck sessions and auto-resolve them.
    Called automatically when checking for active sessions.
    
    Returns:
        Dict with resolution results
    """
    try:
        return await auto_resolve_stuck_sessions()
    except Exception as e:
        logger.warning(f"Could not auto-resolve stuck sessions: {e}")
        return {"resolved_count": 0, "error": str(e)}

