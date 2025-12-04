#!/usr/bin/env python3
"""
UNITARES Governance MCP Server v1.0 - Standard MCP Protocol Implementation

This is a proper MCP server implementation that follows the Model Context Protocol specification.
It can be used with Cursor (Composer), Claude Desktop, and other MCP-compatible clients.

Usage:
    python src/mcp_server_std.py

Configuration:
    Add to Cursor MCP config (for Composer) or Claude Desktop MCP config
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Any, Sequence
import traceback
import signal
import atexit
import os
import time
import fcntl
import secrets
import base64

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    print("[UNITARES MCP] Warning: aiofiles not available. File I/O will be synchronous. Install with: pip install aiofiles", file=sys.stderr)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[UNITARES MCP] Warning: psutil not available. Process cleanup disabled. Install with: pip install psutil", file=sys.stderr)

# Add project root to path
from src._imports import ensure_project_root
project_root = ensure_project_root()

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_SDK_AVAILABLE = True
except ImportError as e:
    MCP_SDK_AVAILABLE = False
    print(f"Error: MCP SDK not available: {e}", file=sys.stderr)
    print(f"Python: {sys.executable}", file=sys.stderr)
    print(f"PYTHONPATH: {sys.path}", file=sys.stderr)
    print("Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

from src.governance_monitor import UNITARESMonitor
from src.state_locking import StateLockManager
from src.health_thresholds import HealthThresholds, HealthStatus
from src.process_cleanup import ProcessManager
from src.pattern_analysis import analyze_agent_patterns
from src.runtime_config import get_thresholds
from src.lock_cleanup import cleanup_stale_state_locks
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import os

# Server version - increment when making breaking changes or critical fixes
SERVER_VERSION = "2.0.0"  # UNITARES v2.0: Architecture unification with governance_core
SERVER_BUILD_DATE = "2025-11-22"

# PID file for process tracking
PID_FILE = Path(project_root) / "data" / ".mcp_server.pid"
LOCK_FILE = Path(project_root) / "data" / ".mcp_server.lock"

# Maximum number of processes to keep before cleanup
# The answer to life, the universe, and everything: allows multiple clients
# This prevents zombie accumulation while supporting concurrent connections
MAX_KEEP_PROCESSES = 42

# Create MCP server instance
server = Server("governance-monitor-v1")

# Current process PID
CURRENT_PID = os.getpid()

# Log startup with version and PID for debugging multi-process issues
print(f"[UNITARES MCP v{SERVER_VERSION}] Server starting (PID: {CURRENT_PID}, Build: {SERVER_BUILD_DATE})", file=sys.stderr)

# Initialize managers for state locking, health thresholds, and process management
lock_manager = StateLockManager()
health_checker = HealthThresholds()
process_mgr = ProcessManager()

# Initialize activity tracker for mixed autonomy patterns
from src.activity_tracker import get_activity_tracker, HeartbeatConfig

# ACTIVATED: Lightweight heartbeats enabled for visibility
# Provides activity tracking without heavy governance overhead
HEARTBEAT_CONFIG = HeartbeatConfig(
    conversation_turn_threshold=5,      # Trigger every 5 user prompts (for prompted agents)
    tool_call_threshold=10,             # Trigger every 10 tools (for autonomous agents)
    time_threshold_minutes=15,          # Trigger every 15 min (safety net)
    complexity_threshold=3.0,           # Trigger when cumulative complexity > 3.0
    file_modification_threshold=3,      # Trigger after 3 file writes
    enabled=True,                       # ✅ ENABLED: Lightweight heartbeats active
    track_conversation_turns=True,
    track_tool_calls=True,
    track_complexity=True
)

activity_tracker = get_activity_tracker(HEARTBEAT_CONFIG)
if HEARTBEAT_CONFIG.enabled:
    print(f"[UNITARES MCP] Activity tracker initialized - lightweight heartbeats ENABLED", file=sys.stderr)
    print(f"[UNITARES MCP] Heartbeat triggers: {HEARTBEAT_CONFIG.tool_call_threshold} tools, {HEARTBEAT_CONFIG.conversation_turn_threshold} turns, {HEARTBEAT_CONFIG.time_threshold_minutes} min", file=sys.stderr)
else:
    print(f"[UNITARES MCP] Activity tracker initialized (observation mode)", file=sys.stderr)

# Store monitors per agent
monitors: dict[str, UNITARESMonitor] = {}


@dataclass
class AgentMetadata:
    """Agent lifecycle metadata"""
    agent_id: str
    status: str  # "active", "waiting_input", "paused", "archived", "deleted"
    created_at: str  # ISO format
    last_update: str  # ISO format
    version: str = "v1.0"
    total_updates: int = 0
    tags: list[str] = None
    notes: str = ""
    lifecycle_events: list[dict] = None
    paused_at: str = None
    archived_at: str = None
    parent_agent_id: str = None  # If spawned from another agent
    spawn_reason: str = None  # Reason for spawning (e.g., "new_domain", "parent_archived")
    api_key: str = None  # API key for authentication (generated on creation)
    # Loop detection tracking
    recent_update_timestamps: list[str] = None  # ISO timestamps of recent updates
    recent_decisions: list[str] = None  # Recent decision actions (approve/reflect/reject)
    loop_detected_at: str = None  # ISO timestamp when loop was detected
    loop_cooldown_until: str = None  # ISO timestamp until which updates are blocked
    # Response completion tracking
    last_response_at: str = None  # ISO timestamp when response completed
    response_completed: bool = False  # Flag for completion detection

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.lifecycle_events is None:
            self.lifecycle_events = []
        if self.recent_update_timestamps is None:
            self.recent_update_timestamps = []
        if self.recent_decisions is None:
            self.recent_decisions = []

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    def add_lifecycle_event(self, event: str, reason: str = None):
        """Add a lifecycle event with timestamp"""
        self.lifecycle_events.append({
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        })


# Store agent metadata
agent_metadata: dict[str, AgentMetadata] = {}

# Metadata cache state (for performance optimization)
_metadata_cache_state = {
    "last_load_time": 0.0,        # When metadata was last loaded from disk
    "last_file_mtime": 0.0,       # File modification time at last load
    "cache_ttl": 60.0,            # Cache valid for 60 seconds
    "dirty": False                # Has in-memory data been modified?
}

# Path to metadata file
METADATA_FILE = Path(project_root) / "data" / "agent_metadata.json"

# State file path template (per-agent)
def get_state_file(agent_id: str) -> Path:
    """
    Get path to state file for an agent.

    Uses organized structure: data/agents/{agent_id}_state.json

    Provides automatic migration: if file exists in old location (data/ root),
    it will be automatically moved to new location on first access.
    """
    new_path = Path(project_root) / "data" / "agents" / f"{agent_id}_state.json"
    old_path = Path(project_root) / "data" / f"{agent_id}_state.json"

    # Backward compatibility: migrate from old location if it exists
    if not new_path.exists() and old_path.exists():
        try:
            # Ensure agents directory exists
            new_path.parent.mkdir(parents=True, exist_ok=True)
            # Move file from old to new location
            old_path.rename(new_path)
            print(f"[UNITARES MCP] Migrated {agent_id} state file to agents/ subdirectory", file=sys.stderr)
        except Exception as e:
            print(f"[UNITARES MCP] Warning: Could not migrate {agent_id} state file: {e}", file=sys.stderr)
            # Fall back to old path if migration fails
            return old_path

    return new_path


def _parse_metadata_dict(data: dict) -> dict:
    """
    Helper function to parse metadata dictionary and create AgentMetadata objects.
    Handles missing fields and validation.
    
    Args:
        data: Dictionary loaded from JSON file
        
    Returns:
        Dictionary mapping agent_id -> AgentMetadata objects
    """
    parsed_metadata = {}
    for agent_id, meta in data.items():
        # Validate meta is a dict before processing
        if not isinstance(meta, dict):
            print(f"[UNITARES MCP] Warning: Metadata for {agent_id} is not a dict (type: {type(meta).__name__}), skipping", file=sys.stderr)
            continue
        
        # Set defaults for missing fields
        defaults = {
            'parent_agent_id': None,
            'spawn_reason': None,
            'recent_update_timestamps': None,
            'recent_decisions': None,
            'loop_detected_at': None,
            'loop_cooldown_until': None,
            'last_response_at': None,
            'response_completed': False
        }
        for key, default_value in defaults.items():
            if key not in meta:
                meta[key] = default_value
        
        try:
            parsed_metadata[agent_id] = AgentMetadata(**meta)
        except (TypeError, KeyError) as e:
            print(f"[UNITARES MCP] Warning: Could not create AgentMetadata for {agent_id}: {e}", file=sys.stderr)
            continue
    
    return parsed_metadata


def _acquire_metadata_read_lock(timeout: float = 2.0) -> tuple[int, bool]:
    """
    Helper function to acquire shared lock for metadata reads.
    
    Args:
        timeout: Maximum time to wait for lock (seconds)
        
    Returns:
        Tuple of (lock_fd, lock_acquired)
        - lock_fd: File descriptor for lock file (must be closed by caller)
        - lock_acquired: True if lock acquired, False if timeout
    """
    metadata_lock_file = METADATA_FILE.parent / ".metadata.lock"
    lock_fd = os.open(str(metadata_lock_file), os.O_CREAT | os.O_RDWR)
    lock_acquired = False
    start_time = time.time()
    
    try:
        # Try to acquire shared lock with timeout (non-blocking)
        while time.time() - start_time < timeout:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # Non-blocking shared lock
                lock_acquired = True
                break
            except IOError:
                # Lock held by another process, wait and retry
                time.sleep(0.05)  # Shorter sleep for reads
        
        if not lock_acquired:
            # Timeout - will read without lock
            print(f"[UNITARES MCP] Warning: Metadata lock timeout ({timeout}s) for read, reading without lock", file=sys.stderr)
    except Exception:
        # On any error, mark as not acquired and caller will handle cleanup
        lock_acquired = False
    
    return lock_fd, lock_acquired


def load_metadata() -> None:
    """
    Load agent metadata from file with caching to prevent redundant disk reads.

    Cache behavior:
    - If cache is fresh (< 60s old) and file hasn't changed: use cached data
    - If cache is dirty (modified in memory): don't reload from disk
    - Otherwise: reload from disk with locking
    """
    global agent_metadata
    if not METADATA_FILE.exists():
        return

    # Check if cache is still valid
    current_time = time.time()
    cache_age = current_time - _metadata_cache_state["last_load_time"]

    try:
        file_mtime = METADATA_FILE.stat().st_mtime

        # Use cached data if:
        # 1. Cache is fresh (within TTL)
        # 2. File hasn't been modified since last load
        # 3. No dirty writes pending
        if (cache_age < _metadata_cache_state["cache_ttl"] and
            file_mtime == _metadata_cache_state["last_file_mtime"] and
            not _metadata_cache_state["dirty"] and
            len(agent_metadata) > 0):
            # Cache hit - no need to reload
            return
    except (OSError, FileNotFoundError):
        pass  # File stat failed, proceed with load

    try:
        # Try to acquire lock for safe read
        lock_fd, lock_acquired = _acquire_metadata_read_lock(timeout=2.0)
        
        try:
            # Read metadata file
            with open(METADATA_FILE, 'r') as f:
                data = json.load(f)
                agent_metadata = _parse_metadata_dict(data)

            # Update cache state after successful load
            _metadata_cache_state["last_load_time"] = time.time()
            _metadata_cache_state["last_file_mtime"] = METADATA_FILE.stat().st_mtime
            _metadata_cache_state["dirty"] = False

            # If lock was acquired, we're done (successful read with lock)
            if lock_acquired:
                return

        finally:
            # Release lock if acquired
            if lock_acquired:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except:
                    pass
            os.close(lock_fd)
        
        # If we get here, lock timeout occurred but we already read the file
        # This is safe for reads - worst case is stale data, but prevents hangs
        
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not load metadata: {e}", file=sys.stderr)


async def save_metadata_async() -> None:
    """
    DEPRECATED: Async version of save_metadata - runs blocking I/O in thread pool
    
    ⚠️ WARNING: This function is deprecated. Use synchronous save_metadata() instead.
    Async saves can leak identity/lifecycle data if process exits before completion.
    
    Kept for backward compatibility only. All critical metadata saves should use
    synchronous save_metadata() to ensure data persistence.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_metadata)

def save_metadata() -> None:
    """Save agent metadata to file with locking to prevent race conditions"""
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Use a global metadata lock to prevent concurrent writes
    # This is separate from per-agent locks and protects the shared metadata file
    metadata_lock_file = METADATA_FILE.parent / ".metadata.lock"
    
    try:
        # Acquire exclusive lock on metadata file with timeout (prevents hangs)
        lock_fd = os.open(str(metadata_lock_file), os.O_CREAT | os.O_RDWR)
        lock_acquired = False
        start_time = time.time()
        timeout = 5.0  # 5 second timeout (same as agent lock)

        try:
            # Try to acquire lock with timeout (non-blocking)
            while time.time() - start_time < timeout:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    break
                except IOError:
                    # Lock held by another process, wait and retry
                    time.sleep(0.1)

            if not lock_acquired:
                # Timeout reached - log warning but use fallback
                print(f"[UNITARES MCP] Warning: Metadata lock timeout ({timeout}s)", file=sys.stderr)
                raise TimeoutError("Metadata lock timeout")

            # Reload metadata to get latest state from disk (in case another process updated it)
            # Then merge with our in-memory changes (in-memory takes precedence)
            merged_metadata = {}
            if METADATA_FILE.exists():
                try:
                    with open(METADATA_FILE, 'r') as f:
                        existing_data = json.load(f)
                        # Start with what's on disk
                        for agent_id, meta_dict in existing_data.items():
                            # FIXED: Validate meta_dict is actually a dict before creating AgentMetadata
                            # Prevents strings from being stored in agent_metadata
                            if isinstance(meta_dict, dict):
                                try:
                                    merged_metadata[agent_id] = AgentMetadata(**meta_dict)
                                except (TypeError, KeyError) as e:
                                    # Invalid metadata structure - skip this agent
                                    print(f"[UNITARES MCP] Warning: Invalid metadata for {agent_id}: {e}", file=sys.stderr)
                                    continue
                            else:
                                # meta_dict is not a dict (could be string from corrupted file)
                                print(f"[UNITARES MCP] Warning: Metadata for {agent_id} is not a dict (type: {type(meta_dict).__name__}), skipping", file=sys.stderr)
                                continue
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # If file is corrupted, start fresh
                    print(f"[UNITARES MCP] Warning: Could not load metadata file: {e}", file=sys.stderr)
                    pass
            
            # Overwrite with in-memory state (our changes take precedence)
            # FIXED: Validate that in-memory entries are AgentMetadata objects, not strings
            for agent_id, meta in agent_metadata.items():
                if isinstance(meta, AgentMetadata):
                    merged_metadata[agent_id] = meta
                else:
                    # Invalid type in memory - log warning but skip (don't overwrite valid disk data)
                    print(f"[UNITARES MCP] Warning: In-memory metadata for {agent_id} is not AgentMetadata (type: {type(meta).__name__}), skipping", file=sys.stderr)
                    # If not in merged_metadata from disk, create fresh entry
                    if agent_id not in merged_metadata:
                        print(f"[UNITARES MCP] Creating fresh metadata for {agent_id} due to invalid in-memory state", file=sys.stderr)
                        merged_metadata[agent_id] = get_or_create_metadata(agent_id)
            
            # Write merged state
            with open(METADATA_FILE, 'w') as f:
                # Sort by agent_id for consistent file output
                data = {
                    agent_id: meta.to_dict()
                    for agent_id, meta in sorted(merged_metadata.items())
                }
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
            
            # Update in-memory state with merged result (includes any new agents from disk)
            agent_metadata.update(merged_metadata)

            # Update cache state after successful write
            _metadata_cache_state["last_load_time"] = time.time()
            _metadata_cache_state["last_file_mtime"] = METADATA_FILE.stat().st_mtime
            _metadata_cache_state["dirty"] = False

        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not acquire metadata lock: {e}", file=sys.stderr)
        # Fallback: try without lock (not ideal but better than failing silently)
        with open(METADATA_FILE, 'w') as f:
            data = {
                agent_id: meta.to_dict()
                for agent_id, meta in sorted(agent_metadata.items())
            }
            json.dump(data, f, indent=2)

        # Update cache state after fallback write
        _metadata_cache_state["last_load_time"] = time.time()
        _metadata_cache_state["last_file_mtime"] = METADATA_FILE.stat().st_mtime
        _metadata_cache_state["dirty"] = False


def get_or_create_metadata(agent_id: str) -> AgentMetadata:
    """Get metadata for agent, creating if needed"""
    if agent_id not in agent_metadata:
        now = datetime.now().isoformat()
        # Generate API key for new agent (authentication)
        api_key = generate_api_key()
        metadata = AgentMetadata(
            agent_id=agent_id,
            status="active",
            created_at=now,
            last_update=now,
            api_key=api_key  # Generate key on creation
        )
        # Add creation lifecycle event
        metadata.add_lifecycle_event("created")

        # Special handling for default agent
        if agent_id == "default_agent":
            metadata.tags.append("pioneer")
            metadata.notes = "First agent - pioneer of the governance system"

        agent_metadata[agent_id] = metadata
        save_metadata()
        
        # Print API key for new agent (one-time display)
        print(f"[UNITARES MCP] Created new agent '{agent_id}'", file=sys.stderr)
        print(f"[UNITARES MCP] API Key: {api_key}", file=sys.stderr)
        print(f"[UNITARES MCP] ⚠️  Save this key - you'll need it for future updates!", file=sys.stderr)
    return agent_metadata[agent_id]


# Alias for cleaner naming (backward compatible)
register_agent = get_or_create_metadata


async def save_monitor_state_async(agent_id: str, monitor: UNITARESMonitor) -> None:
    """Async version of save_monitor_state - runs blocking I/O in thread pool"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_monitor_state, agent_id, monitor)

def save_monitor_state(agent_id: str, monitor: UNITARESMonitor) -> None:
    """Save monitor state to file with locking to prevent race conditions"""
    state_file = get_state_file(agent_id)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Use a per-agent state lock to prevent concurrent writes
    state_lock_file = state_file.parent / f".{agent_id}_state.lock"
    
    try:
        # Acquire exclusive lock on state file with timeout
        lock_fd = os.open(str(state_lock_file), os.O_CREAT | os.O_RDWR)
        lock_acquired = False
        start_time = time.time()
        timeout = 5.0  # 5 second timeout

        try:
            # Try to acquire lock with timeout (non-blocking)
            while time.time() - start_time < timeout:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    break
                except IOError:
                    # Lock held by another process, wait and retry
                    time.sleep(0.1)

            if not lock_acquired:
                # Timeout reached - log warning but use fallback
                print(f"[UNITARES MCP] Warning: State lock timeout for {agent_id} ({timeout}s)", file=sys.stderr)
                raise TimeoutError("State lock timeout")

            # Write state
            state_data = monitor.state.to_dict_with_history()
            with open(state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
            
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not acquire state lock for {agent_id}: {e}", file=sys.stderr)
        # Fallback: try without lock (not ideal but better than failing silently)
        try:
            state_data = monitor.state.to_dict_with_history()
            with open(state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e2:
            print(f"[UNITARES MCP] Error: Could not save state for {agent_id}: {e2}", file=sys.stderr)


def load_monitor_state(agent_id: str) -> 'GovernanceState' | None:
    """Load monitor state from file if it exists"""
    state_file = get_state_file(agent_id)
    
    if not state_file.exists():
        return None
    
    try:
        # Read-only access, no lock needed
        with open(state_file, 'r') as f:
            data = json.load(f)
            from src.governance_monitor import GovernanceState
            return GovernanceState.from_dict(data)
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not load state for {agent_id}: {e}", file=sys.stderr)
        return None


# Load metadata on startup
load_metadata()


def auto_archive_old_test_agents(max_age_hours: float = 6.0) -> int:
    """
    Automatically archive old test/demo agents that haven't been updated recently.
    
    Test/ping agents (1-2 updates) are archived immediately.
    Other test agents are archived after inactivity threshold.
    
    Args:
        max_age_hours: Archive agents older than this many hours (default: 6)
    
    Returns:
        Number of agents archived
    """
    archived_count = 0
    current_time = datetime.now()
    
    for agent_id, meta in list(agent_metadata.items()):
        # Skip if already archived or deleted
        if meta.status in ["archived", "deleted"]:
            continue
        
        # Only archive test/demo agents
        is_test_agent = (
            agent_id.startswith("test_") or 
            agent_id.startswith("demo_") or
            agent_id.startswith("test") or
            "test" in agent_id.lower() or
            "demo" in agent_id.lower()
        )
        
        if not is_test_agent:
            continue
        
        # Archive immediately if very low update count (1-2 updates = just a ping/test)
        if meta.total_updates <= 2:
            meta.status = "archived"
            meta.archived_at = current_time.isoformat()
            meta.add_lifecycle_event(
                "archived",
                f"Auto-archived: test/ping agent with {meta.total_updates} update(s)"
            )
            archived_count += 1
            print(f"[UNITARES MCP] Auto-archived test/ping agent: {agent_id} ({meta.total_updates} updates)", file=sys.stderr)
            continue
        
        # Check age for agents with more updates
        try:
            last_update_dt = datetime.fromisoformat(meta.last_update.replace('Z', '+00:00') if 'Z' in meta.last_update else meta.last_update)
            age_delta = (current_time.replace(tzinfo=last_update_dt.tzinfo) if last_update_dt.tzinfo else current_time) - last_update_dt
            age_hours = age_delta.total_seconds() / 3600
        except:
            # If we can't parse date, skip
            continue
        
        # Archive if old enough
        if age_hours >= max_age_hours:
            meta.status = "archived"
            meta.archived_at = current_time.isoformat()
            meta.add_lifecycle_event(
                "archived",
                f"Auto-archived: inactive test/demo agent ({age_hours:.1f} hours old, threshold: {max_age_hours} hours)"
            )
            archived_count += 1
            print(f"[UNITARES MCP] Auto-archived old test agent: {agent_id} ({age_hours:.1f} hours old)", file=sys.stderr)
    
    if archived_count > 0:
        save_metadata()
    
    return archived_count


# Auto-archive old test agents on startup (non-blocking, logs only)
try:
    archived = auto_archive_old_test_agents(max_age_hours=6.0)
    if archived > 0:
        print(f"[UNITARES MCP] Auto-archived {archived} old test/demo agents on startup", file=sys.stderr)

except Exception as e:
    print(f"[UNITARES MCP] Warning: Could not auto-archive old test agents: {e}", file=sys.stderr)

# Clean up stale locks on startup to prevent Cursor freezing
try:
    result = cleanup_stale_state_locks(project_root, max_age_seconds=300, dry_run=False)
    if result['cleaned'] > 0:
        print(f"[UNITARES MCP] Cleaned {result['cleaned']} stale lock files on startup", file=sys.stderr)
except Exception as e:
    print(f"[UNITARES MCP] Warning: Could not clean up stale locks: {e}", file=sys.stderr)


def cleanup_stale_processes():
    """Clean up stale MCP server processes on startup - only if we have too many"""
    if not PSUTIL_AVAILABLE:
        print("[UNITARES MCP] Skipping stale process cleanup (psutil not available)", file=sys.stderr)
        return
    
    try:
        # Find all mcp_server_std.py processes
        current_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and any('mcp_server_std.py' in str(arg) for arg in cmdline):
                    pid = proc.info['pid']
                    if pid != CURRENT_PID:  # Don't kill ourselves
                        create_time = proc.info.get('create_time', 0)
                        age_seconds = time.time() - create_time
                        # Check for heartbeat file to see if process is active
                        heartbeat_file = Path(project_root) / "data" / "processes" / f"heartbeat_{pid}.txt"
                        has_recent_heartbeat = False
                        if heartbeat_file.exists():
                            try:
                                with open(heartbeat_file, 'r') as f:
                                    last_heartbeat = float(f.read())
                                heartbeat_age = time.time() - last_heartbeat
                                has_recent_heartbeat = heartbeat_age < 300  # 5 minutes
                            except (ValueError, IOError):
                                pass
                        
                        current_processes.append({
                            'pid': pid,
                            'create_time': create_time,
                            'age_seconds': age_seconds,
                            'has_recent_heartbeat': has_recent_heartbeat
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Only clean up if we exceed the threshold AND processes are truly stale
        # Don't kill processes that have recent heartbeats (active connections)
        if len(current_processes) > MAX_KEEP_PROCESSES:
            # Sort by creation time (oldest first)
            current_processes.sort(key=lambda x: x['create_time'])
            
            # Only kill processes that:
            # 1. Are older than 5 minutes AND don't have recent heartbeat
            # 2. AND we're over the limit
            stale_processes = [
                p for p in current_processes[:-MAX_KEEP_PROCESSES]  # All except last MAX_KEEP_PROCESSES
                if p['age_seconds'] > 300 and not p['has_recent_heartbeat']
            ]
            
            if stale_processes:
                print(f"[UNITARES MCP] Found {len(current_processes)} server processes, cleaning up {len(stale_processes)} truly stale ones (keeping {MAX_KEEP_PROCESSES} most recent)...", file=sys.stderr)
                
                for proc_info in stale_processes:
                    try:
                        proc = psutil.Process(proc_info['pid'])
                        age_minutes = int(proc_info['age_seconds'] / 60)
                        print(f"[UNITARES MCP] Killing stale process PID {proc_info['pid']} (age: {age_minutes}m, no recent heartbeat)", file=sys.stderr)
                        proc.terminate()
                        # Give it a moment to clean up
                        try:
                            proc.wait(timeout=2)
                        except psutil.TimeoutExpired:
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        print(f"[UNITARES MCP] Could not kill PID {proc_info['pid']}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not clean stale processes: {e}", file=sys.stderr)


def write_pid_file():
    """Write PID file for process tracking"""
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, 'w') as f:
            f.write(f"{CURRENT_PID}\n{SERVER_VERSION}\n{time.time()}\n")
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not write PID file: {e}", file=sys.stderr)


def remove_pid_file():
    """Remove PID file on shutdown"""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception as e:
        print(f"[UNITARES MCP] Warning: Could not remove PID file: {e}", file=sys.stderr)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n[UNITARES MCP] Received signal {signum}, shutting down gracefully...", file=sys.stderr)
    remove_pid_file()
    sys.exit(0)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Register cleanup on exit
atexit.register(remove_pid_file)

# Write heartbeat immediately on startup to mark this process as active
# This prevents other clients from killing this process during their cleanup
process_mgr.write_heartbeat()

# Clean up stale processes on startup (using ProcessManager)
# Use longer max_age to avoid killing active connections from other clients
# Only kill processes that are truly stale (5+ minutes old without heartbeat)
try:
    cleaned = process_mgr.cleanup_zombies(max_age_seconds=300, max_keep_processes=MAX_KEEP_PROCESSES)
    if cleaned:
        print(f"[UNITARES MCP] Cleaned up {len(cleaned)} zombie processes on startup", file=sys.stderr)
except Exception as e:
    print(f"[UNITARES MCP] Warning: Could not clean zombies on startup: {e}", file=sys.stderr)

# Clean up stale lock files (from crashed/killed processes)
try:
    from src.lock_cleanup import cleanup_stale_state_locks
    lock_cleanup_result = cleanup_stale_state_locks(project_root=project_root, max_age_seconds=300, dry_run=False)
    if lock_cleanup_result['cleaned'] > 0:
        print(f"[UNITARES MCP] Cleaned up {lock_cleanup_result['cleaned']} stale lock file(s) on startup", file=sys.stderr)
except Exception as e:
    print(f"[UNITARES MCP] Warning: Could not clean stale locks on startup: {e}", file=sys.stderr)

# Also run legacy cleanup for compatibility (but only if we have too many processes)
# Don't kill processes aggressively - let multiple clients coexist
cleanup_stale_processes()

# Write PID file
write_pid_file()


def spawn_agent_with_inheritance(
    new_agent_id: str,
    parent_agent_id: str,
    spawn_reason: str = "spawned",
    inheritance_factor: float = 0.7
) -> UNITARESMonitor:
    """
    Spawn a new agent with inherited state from parent.
    
    Args:
        new_agent_id: ID for the new agent
        parent_agent_id: ID of parent agent to inherit from
        spawn_reason: Reason for spawning (e.g., "new_domain", "parent_archived")
        inheritance_factor: How much state to inherit (0.0-1.0, default 0.7 = 70%)
    
    Returns:
        New UNITARESMonitor with inherited state
    """
    # Check parent exists
    if parent_agent_id not in agent_metadata:
        raise ValueError(f"Parent agent '{parent_agent_id}' not found")
    
    # Get or create parent monitor to access state
    parent_monitor = get_or_create_monitor(parent_agent_id)
    parent_state = parent_monitor.state
    parent_meta = agent_metadata[parent_agent_id]
    
    # Create new monitor
    new_monitor = UNITARESMonitor(new_agent_id, load_state=False)
    new_state = new_monitor.state
    
    # Inherit thermodynamic state (scaled by inheritance_factor)
    new_state.E = parent_state.E * inheritance_factor + (1 - inheritance_factor) * 0.5
    new_state.I = parent_state.I * inheritance_factor + (1 - inheritance_factor) * 0.5
    new_state.S = parent_state.S * (1 - inheritance_factor * 0.5)  # Reset entropy more
    new_state.V = parent_state.V * inheritance_factor * 0.5  # Reset void more
    
    # Inherit coherence (scaled)
    new_state.coherence = parent_state.coherence * inheritance_factor + (1 - inheritance_factor) * 1.0
    
    # Inherit lambda1 (scaled toward default)
    from config.governance_config import GovernanceConfig
    config = GovernanceConfig()
    default_lambda1 = (config.LAMBDA1_MIN + config.LAMBDA1_MAX) / 2
    new_state.lambda1 = parent_state.lambda1 * inheritance_factor + default_lambda1 * (1 - inheritance_factor)
    
    # Inherit risk (scaled down, but with minimum based on parent)
    parent_risk = getattr(parent_state, 'risk_score', None)
    if parent_risk is not None:
        # Inherit 50% of parent risk, but cap at 15% initial
        inherited_risk = min(parent_risk * 0.5, 0.15)
        # If parent was critical, new agent starts with at least 5% risk
        if parent_risk >= 0.30:
            inherited_risk = max(inherited_risk, 0.05)
        new_state.risk_score = inherited_risk
    
    # Copy some history (scaled down)
    history_length = min(len(parent_state.V_history), 100)  # Max 100 entries
    if history_length > 0:
        new_state.V_history = parent_state.V_history[-history_length:].copy()
        new_state.coherence_history = parent_state.coherence_history[-history_length:].copy() if hasattr(parent_state, 'coherence_history') else []
        new_state.risk_history = parent_state.risk_history[-history_length:].copy() if hasattr(parent_state, 'risk_history') else []
    
    # Create metadata with spawn tracking
    now = datetime.now().isoformat()
    new_meta = AgentMetadata(
        agent_id=new_agent_id,
        status="active",
        created_at=now,
        last_update=now,
        parent_agent_id=parent_agent_id,
        spawn_reason=spawn_reason,
        tags=["spawned", f"parent:{parent_agent_id}"],
        notes=f"Spawned from '{parent_agent_id}' ({spawn_reason}). Inherited {inheritance_factor*100:.0f}% of thermodynamic state."
    )
    new_meta.add_lifecycle_event("spawned", f"From {parent_agent_id}: {spawn_reason}")
    
    agent_metadata[new_agent_id] = new_meta
    monitors[new_agent_id] = new_monitor
    
    # Save metadata
    save_metadata()
    
    print(f"[UNITARES MCP] Spawned agent '{new_agent_id}' from '{parent_agent_id}' (inheritance: {inheritance_factor*100:.0f}%)", file=sys.stderr)
    
    return new_monitor


def get_or_create_monitor(agent_id: str) -> UNITARESMonitor:
    """Get existing monitor or create new one with metadata, loading state if it exists"""
    # Ensure metadata exists
    get_or_create_metadata(agent_id)

    # Create monitor if needed
    if agent_id not in monitors:
        monitor = UNITARESMonitor(agent_id)
        
        # Try to load persisted state from disk
        persisted_state = load_monitor_state(agent_id)
        if persisted_state is not None:
            monitor.state = persisted_state
            print(f"[UNITARES MCP] Loaded persisted state for {agent_id} ({len(persisted_state.V_history)} history entries)", file=sys.stderr)
        else:
            print(f"[UNITARES MCP] Initialized new monitor for {agent_id}", file=sys.stderr)
        
        monitors[agent_id] = monitor
    
    return monitors[agent_id]


def check_agent_status(agent_id: str) -> str | None:
    """Check if agent status allows operations, return error if not"""
    if agent_id in agent_metadata:
        meta = agent_metadata[agent_id]
        if meta.status == "paused":
            return f"Agent '{agent_id}' is paused. Resume it first before processing updates."
        elif meta.status == "archived":
            return f"Agent '{agent_id}' is archived. It must be restored before processing updates."
        elif meta.status == "deleted":
            return f"Agent '{agent_id}' is deleted and cannot be used."
    return None


def check_agent_id_default(agent_id: str) -> str | None:
    """Check if using default agent_id and return warning if so"""
    if not agent_id or agent_id == "default_agent":
        return "⚠️ Using default agent_id. For multi-agent systems, specify explicit agent_id to avoid state mixing."
    return None


def check_spawn_warning(agent_id: str) -> tuple[bool, str]:
    """
    Check if spawning might be inappropriate (e.g., similar active agent exists).
    
    Returns:
        (should_warn, warning_message)
    """
    # Check for similar active agents (same prefix/base)
    base_parts = agent_id.split("_")[:2]  # First 2 parts (e.g., "claude_code" from "claude_code_cli_session")
    if len(base_parts) >= 2:
        base_pattern = "_".join(base_parts)
        similar_agents = [
            aid for aid, meta in agent_metadata.items()
            if aid.startswith(base_pattern) and meta.status == "active" and aid != agent_id
        ]
        
        if similar_agents:
            return True, f"Found similar active agent(s): {', '.join(similar_agents[:3])}. Consider self-updating instead of spawning to maintain identity and accountability."
    
    return False, ""


def _detect_ci_status() -> bool:
    """
    Auto-detect CI pass status from environment variables.
    
    Checks common CI environment variables:
    - CI=true + CI_STATUS=passed (custom)
    - GITHUB_ACTIONS + GITHUB_WORKFLOW_STATUS=success (GitHub Actions)
    - TRAVIS=true + TRAVIS_TEST_RESULT=0 (Travis CI)
    - CIRCLE_CI=true + CIRCLE_BUILD_STATUS=success (CircleCI)
    - GITLAB_CI=true + CI_JOB_STATUS=success (GitLab CI)
    
    Returns:
        bool: True if CI passed, False otherwise (conservative default)
    """
    # Check if we're in a CI environment
    ci_env = os.environ.get("CI", "").lower()
    if ci_env not in ("true", "1", "yes"):
        return False  # Not in CI, default to False (conservative)
    
    # Check custom CI_STATUS
    ci_status = os.environ.get("CI_STATUS", "").lower()
    if ci_status in ("passed", "success", "ok", "true", "1"):
        return True
    
    # GitHub Actions
    if os.environ.get("GITHUB_ACTIONS") == "true":
        workflow_status = os.environ.get("GITHUB_WORKFLOW_STATUS", "").lower()
        if workflow_status == "success":
            return True
    
    # Travis CI
    if os.environ.get("TRAVIS") == "true":
        test_result = os.environ.get("TRAVIS_TEST_RESULT", "")
        if test_result == "0":
            return True
    
    # CircleCI
    if os.environ.get("CIRCLE_CI") == "true":
        build_status = os.environ.get("CIRCLE_BUILD_STATUS", "").lower()
        if build_status == "success":
            return True
    
    # GitLab CI
    if os.environ.get("GITLAB_CI") == "true":
        job_status = os.environ.get("CI_JOB_STATUS", "").lower()
        if job_status == "success":
            return True
    
    # Default: CI detected but status unknown -> False (conservative)
    return False


def validate_agent_id_format(agent_id: str) -> tuple[bool, str, str]:
    """
    Validate agent_id follows recommended patterns.
    
    Returns:
        (is_valid, error_message, suggestion)
    """
    from datetime import datetime, timedelta
    import re
    
    # Generic IDs that should be rejected
    generic_ids = {
        "test", "demo", "default_agent", "agent", "monitor"
    }
    
    if agent_id.lower() in generic_ids:
        suggestion = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return False, f"Generic ID '{agent_id}' is not allowed. Use a specific identifier.", suggestion
    
    # Check for generic patterns without uniqueness
    if agent_id in ["claude_code_cli", "claude_chat", "composer", "cursor_ide"]:
        suggestion = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return False, f"ID '{agent_id}' is too generic and may cause collisions. Add a session identifier.", suggestion
    
    # Test agents should include timestamp
    if agent_id.startswith("test_") and len(agent_id.split("_")) < 3:
        suggestion = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return False, f"Test IDs should include timestamp for uniqueness (e.g., 'test_20251124_143022').", suggestion
    
    # Demo agents should include timestamp
    if agent_id.startswith("demo_") and len(agent_id.split("_")) < 3:
        suggestion = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return False, f"Demo IDs should include timestamp for uniqueness (e.g., 'demo_20251124_143022').", suggestion
    
    # Check length (too short might be generic)
    if len(agent_id) < 3:
        return False, f"Agent ID '{agent_id}' is too short. Use at least 3 characters.", ""
    
    # Check for invalid characters (allow alphanumeric, underscore, hyphen)
    if not re.match(r'^[a-zA-Z0-9_-]+$', agent_id):
        return False, f"Agent ID '{agent_id}' contains invalid characters. Use only letters, numbers, underscores, and hyphens.", ""
    
    return True, "", ""


def require_agent_id(arguments: dict, reject_existing: bool = False) -> tuple[str | None, TextContent | None]:
    """
    Require explicit agent_id, validate format, return error if missing or invalid.
    
    Args:
        arguments: Tool arguments dict containing 'agent_id'
        reject_existing: If True, reject agent_ids that already exist (for new agent creation).
                        If False, allow existing agent_ids (for updates).
    
    Returns:
        (agent_id, None) if valid, (None, TextContent error) if invalid
    """
    agent_id = arguments.get("agent_id")
    if not agent_id:
        error_msg = json.dumps({
            "success": False,
            "error": "agent_id is required. Each agent must have a UNIQUE identifier to prevent state mixing.",
            "details": "Use a unique session/purpose identifier (e.g., 'cursor_ide_session_001', 'claude_code_cli_20251124', 'debugging_session_20251124').",
            "why_unique": "Each agent_id is a unique identity. Using another agent's ID is identity theft - you would impersonate them, corrupt their history, and erase their governance record.",
            "examples": [
                "cursor_ide_session_001",
                "claude_code_cli_20251124",
                "debugging_session_20251124",
                "production_agent_v2"
            ],
            "suggestion": "\"agent_id\": \"your_unique_session_id\"",
            "recovery": {
                "action": "Provide a unique agent_id in your request",
                "related_tools": ["get_agent_api_key", "list_agents"],
                "workflow": "1. Generate unique agent_id (e.g., timestamp-based) 2. Call get_agent_api_key to get/create agent 3. Use agent_id and api_key in subsequent calls"
            }
        }, indent=2)
        return None, TextContent(type="text", text=error_msg)
    
    # Check if agent_id already exists (identity collision) - only when creating new agents
    if reject_existing and agent_id in agent_metadata:
        existing_meta = agent_metadata[agent_id]
        from datetime import datetime, timedelta
        try:
            created_dt = datetime.fromisoformat(existing_meta.created_at.replace('Z', '+00:00') if 'Z' in existing_meta.created_at else existing_meta.created_at)
            created_str = created_dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            created_str = existing_meta.created_at
        
        error_msg = json.dumps({
            "success": False,
            "error": "Identity collision: This agent_id already exists",
            "details": f"'{agent_id}' is an existing agent identity (created {created_str}, {existing_meta.total_updates} updates)",
            "why_this_matters": "Using another agent's ID is identity theft. You would impersonate them and corrupt their governance history.",
            "suggestion": f"Create a unique agent_id for yourself (e.g., 'your_name_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}')",
            "help": "Use list_agents to see existing agent IDs and avoid collisions"
        }, indent=2)
        return None, TextContent(type="text", text=error_msg)
    
    # Validate format (but allow existing agents to pass - backward compatibility)
    # Only validate for new agents (not in metadata yet)
    if agent_id not in agent_metadata:
        is_valid, error_message, suggestion = validate_agent_id_format(agent_id)
        if not is_valid:
            error_data = {
                "success": False,
                "error": error_message,
                "agent_id_provided": agent_id
            }
            if suggestion:
                error_data["suggestion"] = f"Try: '{suggestion}'"
                error_data["example"] = f"Or use a more descriptive ID like: '{agent_id}_session_001'"
            
            error_msg = json.dumps(error_data, indent=2)
            return None, TextContent(type="text", text=error_msg)
    
    return agent_id, None


def generate_api_key() -> str:
    """
    Generate a secure 32-byte API key for agent authentication.
    
    Returns:
        Base64-encoded API key string (URL-safe, no padding)
    """
    key_bytes = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(key_bytes).decode('ascii').rstrip('=')


def verify_agent_ownership(agent_id: str, api_key: str) -> tuple[bool, str | None]:
    """
    Verify that the caller owns the agent_id by checking API key.
    
    Args:
        agent_id: Agent ID to verify
        api_key: API key provided by caller
    
    Returns:
        (is_valid, error_message)
        - is_valid=True if key matches, False otherwise
        - error_message=None if valid, error description if invalid
    """
    if agent_id not in agent_metadata:
        return False, f"Agent '{agent_id}' does not exist"
    
    meta = agent_metadata[agent_id]
    stored_key = meta.api_key
    
    # Handle backward compatibility: if no API key stored, allow (with warning)
    if stored_key is None:
        # Lazy migration: generate key for existing agent
        stored_key = generate_api_key()
        meta.api_key = stored_key
        # Note: We don't save here - caller should save metadata after update
        # This allows first update to work, but subsequent updates require the key
        return True, None
    
    # Validate api_key is a string (prevents TypeError from secrets.compare_digest)
    if not isinstance(api_key, str) or not api_key:
        return False, "API key is required and must be a non-empty string"
    
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(api_key, stored_key):
        return False, "Invalid API key. This agent_id belongs to another identity."
    
    return True, None


def require_agent_auth(agent_id: str, arguments: dict, enforce: bool = False) -> tuple[bool, TextContent | None]:
    """
    Require and verify API key for agent authentication.
    
    Args:
        agent_id: Agent ID being accessed
        arguments: Tool arguments dict (should contain 'api_key')
        enforce: If True, require API key even for agents without one (new behavior)
                 If False, allow missing key for backward compatibility (migration mode)
    
    Returns:
        (is_valid, error) - is_valid=True if authenticated, False if error
    """
    api_key = arguments.get("api_key")
    
    # Check if agent exists
    if agent_id not in agent_metadata:
        # New agent - will get key on creation
        return True, None
    
    meta = agent_metadata[agent_id]
    
    # If agent has no API key yet (backward compatibility)
    if meta.api_key is None:
        if enforce:
            # New behavior: require key even for existing agents
            return False, TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "API key required for authentication",
                    "details": f"Agent '{agent_id}' requires an API key for updates. This is a security requirement to prevent impersonation.",
                    "migration": "This agent was created before authentication was added. Generate a key using get_agent_api_key tool.",
                    "suggestion": "Use get_agent_api_key tool to retrieve or generate your API key"
                }, indent=2)
            )
        else:
            # Migration mode: allow first update, generate key
            return True, None
    
    # Agent has API key - require it
    if not api_key:
        return False, TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": "API key required",
                "details": f"Agent '{agent_id}' requires an API key for authentication. This prevents impersonation and protects your identity.",
                "why_this_matters": "Without authentication, anyone could update your agent's state, corrupt your history, and manipulate your governance record.",
                "suggestion": "Include 'api_key' parameter in your request. Use get_agent_api_key tool to retrieve your key."
            }, indent=2)
        )
    
    # Verify key
    is_valid, error_msg = verify_agent_ownership(agent_id, api_key)
    if not is_valid:
        return False, TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": "Authentication failed",
                "details": error_msg or "Invalid API key",
                "why_this_matters": "This agent_id belongs to another identity. Using it would be identity theft.",
                "suggestion": "Use your own agent_id and API key, or create a new agent_id for yourself"
            }, indent=2)
        )
    
    return True, None


def process_update_authenticated(
    agent_id: str,
    api_key: str,
    agent_state: dict,
    auto_save: bool = True
) -> dict:
    """
    Process governance update with authentication enforcement (synchronous version).

    This is the SECURE entry point for processing updates. Use this instead of
    calling UNITARESMonitor.process_update() directly to prevent impersonation.

    Args:
        agent_id: Agent identifier
        api_key: API key for authentication
        agent_state: Agent state dict (parameters, ethical_drift, etc.)
        auto_save: If True, automatically save state to disk after update

    Returns:
        Update result dict with metrics and decision

    Raises:
        PermissionError: If authentication fails
        ValueError: If agent_id is invalid
    """
    # Authenticate ownership
    is_valid, error_msg = verify_agent_ownership(agent_id, api_key)
    if not is_valid:
        raise PermissionError(f"Authentication failed: {error_msg}")

    # Get or create monitor
    monitor = get_or_create_monitor(agent_id)

    # Process update (now authenticated)
    result = monitor.process_update(agent_state)

    # Auto-save state if requested
    if auto_save:
        save_monitor_state(agent_id, monitor)

        # Update metadata
        meta = agent_metadata[agent_id]
        meta.last_update = datetime.now().isoformat()
        meta.total_updates += 1
        save_metadata()

    return result


# Alias for cleaner naming (backward compatible)
update_agent_auth = process_update_authenticated


def detect_loop_pattern(agent_id: str) -> tuple[bool, str]:
    """
    Detect recursive self-monitoring loop patterns.
    
    Detects patterns like:
    - Pattern 1: Multiple updates within same second (rapid-fire)
    - Pattern 2: 3+ updates within 10 seconds with 2+ reject decisions
    - Pattern 3: 4+ updates within 5 seconds (any decisions)
    - Pattern 4: Decision loop - same decision repeated 5+ times in recent history
    - Pattern 5: Slow-stuck pattern - 3+ updates in 60s with any reject
    - Pattern 6: Extended rapid pattern - 5+ updates in 120s regardless of decisions
    
    Returns:
        (is_loop, reason) - True if loop detected, with explanation
    """
    if agent_id not in agent_metadata:
        return False, ""
    
    meta = agent_metadata[agent_id]
    
    # Check cooldown period
    if meta.loop_cooldown_until:
        cooldown_until = datetime.fromisoformat(meta.loop_cooldown_until)
        if datetime.now() < cooldown_until:
            remaining = (cooldown_until - datetime.now()).total_seconds()
            return True, f"Loop cooldown active. Wait {remaining:.1f}s before retrying."
    
    # Need at least 3 recent updates to detect pattern
    if len(meta.recent_update_timestamps) < 3:
        return False, ""
    
    # Get last 10 updates (or all if fewer) - expanded window for Pattern 6 (5+ updates in 120s)
    # This ensures we can detect extended patterns while still checking recent behavior
    all_timestamps = meta.recent_update_timestamps[-10:]
    all_decisions = meta.recent_decisions[-10:]
    
    # Filter to only recent timestamps (within last 30 seconds) for Pattern 1 detection
    # This prevents old rapid updates from triggering false positives
    # Other patterns (2-6) use full history to catch extended patterns
    now = datetime.now()
    recent_timestamps_for_pattern1 = []
    for ts_str in all_timestamps:
        try:
            ts = datetime.fromisoformat(ts_str)
            age_seconds = (now - ts).total_seconds()
            if age_seconds <= 30.0:  # Only check updates from last 30 seconds for Pattern 1
                recent_timestamps_for_pattern1.append(ts_str)
        except (ValueError, TypeError):
            continue
    
    # Use full history for other patterns
    recent_timestamps = all_timestamps
    recent_decisions = all_decisions
    
    # Pattern 1: Multiple updates within same second (RELAXED: Even less strict)
    # Changed from 2+ updates/0.5s to 3+ updates/0.3s OR 4+ updates/1s
    # Rationale: 2 updates in 0.5 seconds can be legitimate (admin + logging, tool calls)
    #            3+ updates in 0.3 seconds is almost certainly a loop
    #            4+ updates in 1 second is definitely rapid-fire
    # Only check recent timestamps (last 30 seconds) to avoid false positives from old rapid updates
    if len(recent_timestamps_for_pattern1) >= 2:
        last_two = recent_timestamps_for_pattern1[-2:]
        try:
            t1 = datetime.fromisoformat(last_two[0])
            t2 = datetime.fromisoformat(last_two[1])
            time_diff = (t2 - t1).total_seconds()
            # More relaxed: Only trigger if 2 updates within 0.3 seconds (very rapid)
            if time_diff < 0.3:
                return True, "Rapid-fire updates detected (2+ updates within 0.3 seconds)"
        except (ValueError, TypeError):
            pass
    
    # Check for 3+ updates within 0.5 seconds (more lenient than before)
    # Use recent timestamps for Pattern 1 variants
    if len(recent_timestamps_for_pattern1) >= 3:
        last_three = recent_timestamps_for_pattern1[-3:]
        try:
            t1 = datetime.fromisoformat(last_three[0])
            t3 = datetime.fromisoformat(last_three[2])
            if (t3 - t1).total_seconds() < 0.5:
                return True, "Rapid-fire updates detected (3+ updates within 0.5 seconds)"
        except (ValueError, TypeError):
            pass
    
    # Check for 4+ updates within 1 second (catches extended rapid patterns)
    # Use recent timestamps for Pattern 1 variants
    if len(recent_timestamps_for_pattern1) >= 4:
        last_four = recent_timestamps_for_pattern1[-4:]
        try:
            t1 = datetime.fromisoformat(last_four[0])
            t4 = datetime.fromisoformat(last_four[3])
            if (t4 - t1).total_seconds() < 1.0:
                return True, "Rapid-fire updates detected (4+ updates within 1 second)"
        except (ValueError, TypeError):
            pass
    
    # Pattern 2: 3+ updates within 10 seconds, all with "reject" decisions
    if len(recent_timestamps) >= 3:
        last_three_timestamps = recent_timestamps[-3:]
        last_three_decisions = recent_decisions[-3:]
        
        try:
            timestamps = [datetime.fromisoformat(ts) for ts in last_three_timestamps]
            time_span = (timestamps[-1] - timestamps[0]).total_seconds()
            
            if time_span <= 10.0:  # Within 10 seconds
                pause_count = sum(1 for d in last_three_decisions if d in ["pause", "reject"])  # Backward compat
                if pause_count >= 2:  # At least 2 pauses
                    return True, f"Recursive pause pattern: {pause_count} pause decisions within {time_span:.1f}s"
        except (ValueError, TypeError):
            pass
    
    # Pattern 3: 4+ updates within 5 seconds with concerning decisions
    # IMPROVED: Only trigger if there are pause/reject decisions (indicates stuck state)
    # Rationale: Legitimate workflows can have rapid updates, but if all are "proceed",
    #           the agent is likely fine. Only flag if there are concerning decisions.
    if len(recent_timestamps) >= 4:
        last_four_timestamps = recent_timestamps[-4:]
        last_four_decisions = recent_decisions[-4:]
        try:
            timestamps = [datetime.fromisoformat(ts) for ts in last_four_timestamps]
            time_span = (timestamps[-1] - timestamps[0]).total_seconds()
            
            if time_span <= 5.0:  # Within 5 seconds
                # Check for concerning decisions (pause/reject) - indicates stuck state
                concerning_count = sum(1 for d in last_four_decisions if d in ["pause", "reject"])
                if concerning_count >= 1:  # At least one pause/reject indicates potential loop
                    return True, f"Rapid update pattern: 4+ updates within {time_span:.1f}s with {concerning_count} pause/reject decision(s)"
        except (ValueError, TypeError):
            pass
    
    # Pattern 4: Decision loop - same decision repeated 5+ times in recent history
    # UPDATED: Only triggers on "pause" loops (stuck states), not "proceed" loops (normal operation).
    # "Proceed" is normal operation and shouldn't block agents. Only "pause" indicates
    # a stuck state that needs intervention.
    if len(recent_decisions) >= 5:
        from collections import Counter
        # Check last 10 decisions (or all if fewer)
        decision_window = recent_decisions[-10:] if len(recent_decisions) >= 10 else recent_decisions
        decision_counts = Counter(decision_window)
        
        # Only trigger on "pause" loops - "proceed" is normal operation, not a stuck state
        # Map old decisions for backward compatibility
        pause_count = decision_counts.get("pause", 0) + decision_counts.get("reject", 0)
        if pause_count >= 5:
            return True, f"Decision loop detected: {pause_count} 'pause' decisions in recent history (stuck state)"
        
        # For "proceed with guidance" loops, require more consecutive decisions (8+) to avoid false positives
        # This catches agents truly stuck in proceed cycles, not just normal operation
        # Note: Most decisions will be "proceed" - this is normal, so threshold is high
        proceed_count = decision_counts.get("proceed", 0) + decision_counts.get("approve", 0) + decision_counts.get("reflect", 0) + decision_counts.get("revise", 0)
        if proceed_count >= 15:  # Higher threshold since proceed is the normal state
            return True, f"Decision loop detected: {proceed_count} consecutive 'proceed' decisions (agent may be stuck in feedback loop)"
    
    # Pattern 5: Slow-stuck pattern - 3+ updates in 60s with any reject
    # FIXED: Catches "slow-stuck" patterns where agents update rapidly but not fast enough
    # to trigger rapid-fire detection (Patterns 1-3), then get stuck. This pattern catches
    # cases like: 3 updates in 33s with 1 reject (would slip through Pattern 2 which needs 2+ rejects).
    if len(recent_timestamps) >= 3:
        last_three_timestamps = recent_timestamps[-3:]
        last_three_decisions = recent_decisions[-3:]
        
        try:
            timestamps = [datetime.fromisoformat(ts) for ts in last_three_timestamps]
            time_span = (timestamps[-1] - timestamps[0]).total_seconds()
            
            if time_span <= 60.0:  # Within 60 seconds
                pause_count = sum(1 for d in last_three_decisions if d in ["pause", "reject"])  # Backward compat
                if pause_count >= 1:  # Any pause
                    return True, f"Slow-stuck pattern: {pause_count} pause(s) in {len(last_three_timestamps)} updates within {time_span:.1f}s"
        except (ValueError, TypeError):
            pass
    
    # Pattern 6: Extended rapid pattern - 5+ updates in 120s with concerning decisions
    # Catches agents that are updating frequently over a longer time window, which may indicate
    # they're stuck in a loop even if individual updates aren't rapid enough to trigger Pattern 3.
    # IMPROVED: Only trigger if there are pause/reject decisions (indicates stuck state)
    # Rationale: Legitimate workflows can have 5+ rapid updates, but if all are "proceed", 
    #           the agent is likely fine. Only flag if there are concerning decisions.
    if len(recent_timestamps) >= 5:
        # Get last 5+ timestamps and decisions
        last_five_timestamps = recent_timestamps[-5:]
        last_five_decisions = recent_decisions[-5:]
        try:
            timestamps = [datetime.fromisoformat(ts) for ts in last_five_timestamps]
            time_span = (timestamps[-1] - timestamps[0]).total_seconds()
            
            if time_span <= 120.0:  # Within 120 seconds (2 minutes)
                # Check for concerning decisions (pause/reject) - indicates stuck state
                concerning_count = sum(1 for d in last_five_decisions if d in ["pause", "reject"])
                if concerning_count >= 1:  # At least one pause/reject indicates potential loop
                    return True, f"Extended rapid pattern: {len(last_five_timestamps)} updates within {time_span:.1f}s with {concerning_count} pause/reject decision(s)"
        except (ValueError, TypeError):
            pass
    
    return False, ""


async def process_update_authenticated_async(
    agent_id: str,
    api_key: str,
    agent_state: dict,
    auto_save: bool = True,
    confidence: float = 1.0
) -> dict:
    """
    Process governance update with authentication enforcement (async version).

    This is the SECURE async entry point for processing updates. Use this in async
    contexts (like MCP handlers) instead of calling UNITARESMonitor.process_update()
    directly to prevent impersonation.

    Args:
        agent_id: Agent identifier
        api_key: API key for authentication
        agent_state: Agent state dict (parameters, ethical_drift, etc.)
        auto_save: If True, automatically save state to disk after update (async)
        confidence: Confidence level [0, 1] for this update. Defaults to 1.0.
                    When confidence < 0.8, lambda1 updates are skipped.

    Returns:
        Update result dict with metrics and decision

    Raises:
        PermissionError: If authentication fails
        ValueError: If agent_id is invalid
    """
    # Authenticate ownership
    is_valid, error_msg = verify_agent_ownership(agent_id, api_key)
    if not is_valid:
        raise PermissionError(f"Authentication failed: {error_msg}")

    # Check for loop pattern BEFORE processing
    is_loop, loop_reason = detect_loop_pattern(agent_id)
    if is_loop:
        meta = agent_metadata[agent_id]
        
        # If cooldown is already active, just return the existing cooldown message
        # Don't set a new cooldown or override the existing one
        if "Loop cooldown active" in loop_reason:
            # Extract remaining time from reason message
            import re
            match = re.search(r'Wait ([\d.]+)s', loop_reason)
            if match:
                remaining = float(match.group(1))
                raise ValueError(
                    f"Self-monitoring loop detected: {loop_reason}. "
                    f"Cooldown expires in {remaining:.1f} seconds."
                )
            else:
                raise ValueError(f"Self-monitoring loop detected: {loop_reason}")
        
        # Set cooldown period (pattern-specific: shorter for Pattern 1)
        # Determine cooldown duration based on pattern
        # Pattern 1 (rapid-fire): 5 seconds (most likely false positive, very relaxed)
        # Patterns 2-3 (rapid patterns): 15 seconds
        # Patterns 4-6 (decision loops, extended): 30 seconds
        if "Rapid-fire updates detected" in loop_reason:
            cooldown_seconds = 5  # Very short for Pattern 1 (reduces false positive impact)
        elif "Rapid update pattern" in loop_reason or "Recursive reject pattern" in loop_reason:
            cooldown_seconds = 15  # Medium for rapid patterns
        else:
            cooldown_seconds = 30  # Full cooldown for decision loops and extended patterns
        
        cooldown_until = datetime.now() + timedelta(seconds=cooldown_seconds)
        meta.loop_cooldown_until = cooldown_until.isoformat()
        if not meta.loop_detected_at:
            meta.loop_detected_at = datetime.now().isoformat()
            meta.add_lifecycle_event("loop_detected", loop_reason)
            print(f"[UNITARES MCP] ⚠️  Loop detected for agent '{agent_id}': {loop_reason} (cooldown: {cooldown_seconds}s)", file=sys.stderr)
        
        save_metadata()  # Synchronous save - critical for identity/lifecycle data
        
        raise ValueError(
            f"Self-monitoring loop detected: {loop_reason}. "
            f"Updates blocked for {cooldown_seconds} seconds to prevent system crash. "
            f"Cooldown until: {cooldown_until.isoformat()}"
        )

    # Get or create monitor
    monitor = get_or_create_monitor(agent_id)

    # Process update (now authenticated) with confidence gating
    result = monitor.process_update(agent_state, confidence=confidence)

    # Auto-save state if requested (async)
    if auto_save:
        await save_monitor_state_async(agent_id, monitor)

        # Update metadata
        meta = agent_metadata[agent_id]
        now = datetime.now().isoformat()
        meta.last_update = now
        meta.total_updates += 1
        
        # Track recent updates for loop detection (keep last 10)
        decision_action = result.get('decision', {}).get('action', 'unknown')
        meta.recent_update_timestamps.append(now)
        meta.recent_decisions.append(decision_action)
        
        # Keep only last 10 entries
        if len(meta.recent_update_timestamps) > 10:
            meta.recent_update_timestamps = meta.recent_update_timestamps[-10:]
            meta.recent_decisions = meta.recent_decisions[-10:]
        
        # Clear cooldown if it has passed
        if meta.loop_cooldown_until:
            cooldown_until = datetime.fromisoformat(meta.loop_cooldown_until)
            if datetime.now() >= cooldown_until:
                meta.loop_cooldown_until = None
        
        save_metadata()  # Synchronous save - critical for identity/lifecycle data

    return result


def get_agent_or_error(agent_id: str) -> tuple[UNITARESMonitor | None, str | None]:
    """Get agent with friendly error message if not found"""
    if agent_id not in monitors:
        available = list(monitors.keys())
        if available:
            error = f"Agent '{agent_id}' not found. Available agents: {available}. Call process_agent_update first to initialize."
        else:
            error = f"Agent '{agent_id}' not found. No agents initialized yet. Call process_agent_update first."
        return None, error
    return monitors[agent_id], None


def build_standardized_agent_info(
    agent_id: str,
    meta: AgentMetadata,
    monitor: UNITARESMonitor | None = None,
    include_metrics: bool = True
) -> dict:
    """
    Build standardized agent info structure.
    Always returns same fields, null if unavailable.
    """
    # Determine timestamps (prefer monitor, fallback to metadata)
    if monitor:
        # Use monitor timestamps if available, fallback to metadata
        if hasattr(monitor, 'created_at') and monitor.created_at:
            created_ts = monitor.created_at.isoformat()
        else:
            created_ts = meta.created_at
        
        if hasattr(monitor, 'last_update') and monitor.last_update:
            last_update_ts = monitor.last_update.isoformat()
        else:
            last_update_ts = meta.last_update
        
        update_count = int(monitor.state.update_count)
    else:
        created_ts = meta.created_at
        last_update_ts = meta.last_update
        update_count = meta.total_updates
    
    # Calculate age in days
    try:
        created_dt = datetime.fromisoformat(created_ts.replace('Z', '+00:00') if 'Z' in created_ts else created_ts)
        age_days = (datetime.now(created_dt.tzinfo) - created_dt).days
    except:
        age_days = None
    
    # Extract primary tags (first 3, or all if <= 3)
    primary_tags = (meta.tags or [])[:3] if meta.tags else []
    
    # Notes preview (first 100 chars)
    notes_preview = None
    if meta.notes:
        notes_preview = meta.notes[:100] + "..." if len(meta.notes) > 100 else meta.notes
    
    # Build summary
    summary = {
        "updates": update_count,
        "last_activity": last_update_ts,
        "age_days": age_days,
        "primary_tags": primary_tags
    }
    
    # Build metrics (null if unavailable)
    metrics = None
    health_status = "unknown"
    state_info = {
        "loaded_in_process": monitor is not None,
        "metrics_available": False,
        "error": None
    }
    
    if monitor and include_metrics:
        try:
            monitor_state = monitor.state
            risk_score = getattr(monitor_state, 'risk_score', None)
            health_status_obj, _ = health_checker.get_health_status(
                risk_score=risk_score,
                coherence=monitor_state.coherence,
                void_active=monitor_state.void_active
            )
            health_status = health_status_obj.value
            
            # Get metrics to include phi/verdict
            monitor_metrics = monitor.get_metrics() if hasattr(monitor, 'get_metrics') else {}
            attention_score = monitor_metrics.get("attention_score") or risk_score
            
            metrics = {
                "attention_score": float(attention_score) if attention_score is not None else None,  # Renamed from risk_score
                "phi": monitor_metrics.get("phi"),  # Primary physics signal
                "verdict": monitor_metrics.get("verdict"),  # Primary governance signal
                "risk_score": float(risk_score) if risk_score is not None else None,  # DEPRECATED
                "coherence": float(monitor_state.coherence),
                "void_active": bool(monitor_state.void_active),
                "E": float(monitor_state.E),
                "I": float(monitor_state.I),
                "S": float(monitor_state.S),
                "V": float(monitor_state.V),
                "lambda1": float(monitor_state.lambda1)
            }
            state_info["metrics_available"] = True
        except Exception as e:
            health_status = "error"
            state_info["error"] = str(e)
            state_info["metrics_available"] = False
    
    # Build spawn relationship info
    spawn_info = None
    if meta.parent_agent_id:
        spawn_info = {
            "parent_agent_id": meta.parent_agent_id,
            "spawn_reason": meta.spawn_reason or "spawned",
            "is_spawned": True
        }
        # Check if parent still exists
        if meta.parent_agent_id in agent_metadata:
            parent_meta = agent_metadata[meta.parent_agent_id]
            spawn_info["parent_status"] = parent_meta.status
        else:
            spawn_info["parent_status"] = "deleted"
    
    # Build standardized structure
    return {
        "agent_id": agent_id,
        "lifecycle_status": meta.status,
        "health_status": health_status,
        "summary": summary,
        "metrics": metrics,
        "metadata": {
            "created": created_ts,
            "last_update": last_update_ts,
            "version": meta.version,
            "total_updates": meta.total_updates,
            "tags": meta.tags or [],
            "notes_preview": notes_preview,
            "spawn_info": spawn_info
        },
        "state": state_info
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools"""
    return [
        Tool(
            name="check_calibration",
            description="""Check calibration of confidence estimates. Returns whether confidence estimates match actual accuracy. Requires ground truth data via update_calibration_ground_truth.

USE CASES:
- Verify calibration system is working correctly
- Monitor confidence estimate accuracy
- Debug calibration issues

RETURNS:
{
  "success": true,
  "calibrated": boolean,
  "accuracy": float (0-1),
  "confidence_distribution": {
    "mean": float,
    "std": float,
    "min": float,
    "max": float
  },
  "pending_updates": int,
  "message": "string"
}

RELATED TOOLS:
- update_calibration_ground_truth: Provide ground truth data for calibration

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "calibrated": true,
  "accuracy": 0.87,
  "confidence_distribution": {"mean": 0.82, "std": 0.15, "min": 0.3, "max": 1.0},
  "pending_updates": 5
}

DEPENDENCIES:
- Requires: Ground truth data via update_calibration_ground_truth
- Workflow: 1. Call update_calibration_ground_truth with ground truth 2. Call check_calibration to verify""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="update_calibration_ground_truth",
            description="""Update calibration with ground truth after human review. This allows calibration to work properly by updating actual correctness after decisions are made.

USE CASES:
- Provide ground truth after human review of agent decisions
- Improve calibration accuracy over time
- Enable calibration checking via check_calibration

RETURNS:
{
  "success": true,
  "message": "Calibration updated",
  "pending_updates": int,
  "calibration_status": "string"
}

RELATED TOOLS:
- check_calibration: Verify calibration after providing ground truth

EXAMPLE REQUEST:
{
  "confidence": 0.85,
  "predicted_correct": true,
  "actual_correct": true
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Calibration updated",
  "pending_updates": 12
}

DEPENDENCIES:
- Requires: confidence, predicted_correct, actual_correct
- Workflow: After human review, call this with ground truth, then check_calibration""",
            inputSchema={
                "type": "object",
                "properties": {
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level (0-1) for the prediction",
                        "minimum": 0,
                        "maximum": 1
                    },
                    "predicted_correct": {
                        "type": "boolean",
                        "description": "Whether we predicted correct (based on confidence threshold)"
                    },
                    "actual_correct": {
                        "type": "boolean",
                        "description": "Whether prediction was actually correct (ground truth from human review)"
                    }
                },
                "required": ["confidence", "predicted_correct", "actual_correct"]
            }
        ),
        Tool(
            name="health_check",
            description="""Quick health check - returns system status, version, and component health. Useful for monitoring and operational visibility.

USE CASES:
- Monitor system health and component status
- Debug system issues
- Verify all components are operational

RETURNS:
{
  "success": true,
  "status": "healthy" | "moderate" | "critical",  # "moderate" renamed from "degraded"
  "version": "string",
  "components": {
    "calibration": {"status": "healthy", "pending_updates": int},
    "telemetry": {"status": "healthy", "metrics_count": int},
    "audit_log": {"status": "healthy", "entries": int}
  },
  "timestamp": "ISO timestamp"
}

RELATED TOOLS:
- get_server_info: Get detailed server process information
- get_telemetry_metrics: Get detailed telemetry data

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "status": "healthy",
  "version": "2.0.0",
  "components": {
    "calibration": {"status": "healthy", "pending_updates": 5},
    "telemetry": {"status": "healthy", "metrics_count": 1234},
    "audit_log": {"status": "healthy", "entries": 5678}
  }
}

DEPENDENCIES:
- No dependencies - safe to call anytime""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_workspace_health",
            description="""Get comprehensive workspace health status. Provides accurate baseline of workspace state for onboarding new agents. Saves 30-60 minutes of manual exploration.

USE CASES:
- Get baseline workspace state before starting work
- Validate MCP server configuration
- Check documentation coherence
- Verify workspace setup and dependencies
- Onboarding new agents (run first to avoid confusion)

RETURNS:
{
  "success": true,
  "mcp_status": {
    "cursor_servers": ["string"],
    "claude_desktop_servers": ["string"],
    "active_count": int,
    "notes": "string"
  },
  "documentation_coherence": {
    "server_counts_match": boolean,
    "file_references_valid": boolean,
    "paths_current": boolean,
    "total_issues": int,
    "details": []
  },
  "security": {
    "exposed_secrets": boolean,
    "api_keys_secured": boolean,
    "notes": "string"
  },
  "workspace_status": {
    "scripts_executable": boolean,
    "dependencies_installed": boolean,
    "mcp_servers_responding": boolean
  },
  "last_validated": "ISO timestamp",
  "health": "healthy" | "moderate" | "critical",  # "moderate" renamed from "degraded"
  "recommendation": "string"
}

RELATED TOOLS:
- health_check: Quick system health overview (governance system)
- get_server_info: Get detailed server process information

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "mcp_status": {
    "cursor_servers": ["governance-monitor-v1", "GitHub", "date-context"],
    "claude_desktop_servers": ["governance-monitor-v1", "date-context"],
    "active_count": 3,
    "notes": "Count based on config files. Actual runtime status may vary."
  },
  "documentation_coherence": {
    "server_counts_match": true,
    "file_references_valid": true,
    "paths_current": true,
    "total_issues": 0,
    "details": []
  },
  "security": {
    "exposed_secrets": false,
    "api_keys_secured": true,
    "notes": "Plain text API keys by design (honor system). This is intentional, not a security flaw."
  },
  "workspace_status": {
    "scripts_executable": true,
    "dependencies_installed": true,
    "mcp_servers_responding": true
  },
  "last_validated": "2025-11-25T23:45:00Z",
  "health": "healthy",
  "recommendation": "All systems operational. Workspace ready for development."
}

DEPENDENCIES:
- No dependencies - safe to call anytime
- Recommended: Run this tool first when onboarding to a new workspace""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_telemetry_metrics",
            description="""Get comprehensive telemetry metrics: skip rates, confidence distributions, calibration status, and suspicious patterns. Useful for monitoring system health and detecting agreeableness or over-conservatism.

USE CASES:
- Monitor system-wide telemetry patterns
- Detect agreeableness or over-conservatism
- Analyze confidence distributions
- Track skip rates and suspicious patterns

RETURNS:
{
  "success": true,
  "window_hours": float,
  "skip_rate": float (0-1),
  "confidence_distribution": {
    "mean": float,
    "std": float,
    "min": float,
    "max": float,
    "percentiles": {"p25": float, "p50": float, "p75": float, "p95": float}
  },
  "calibration_status": "calibrated" | "needs_data" | "uncalibrated",
  "suspicious_patterns": [
    {"type": "string", "severity": "low" | "medium" | "high", "description": "string"}
  ],
  "agent_count": int,
  "total_updates": int
}

RELATED TOOLS:
- health_check: Quick system health overview
- check_calibration: Detailed calibration status

EXAMPLE REQUEST:
{"agent_id": "test_agent_001", "window_hours": 24}

EXAMPLE RESPONSE:
{
  "success": true,
  "window_hours": 24,
  "skip_rate": 0.05,
  "confidence_distribution": {"mean": 0.82, "std": 0.15, "min": 0.3, "max": 1.0},
  "calibration_status": "calibrated",
  "suspicious_patterns": [],
  "agent_count": 10,
  "total_updates": 1234
}

DEPENDENCIES:
- Optional: agent_id (filters to specific agent)
- Optional: window_hours (default: 24)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Optional agent ID to filter metrics. If not provided, returns metrics for all agents."
                    },
                    "window_hours": {
                        "type": "number",
                        "description": "Time window in hours for metrics (default: 24)",
                        "default": 24
                    }
                }
            }
        ),
        Tool(
            name="get_tool_usage_stats",
            description="""Get tool usage statistics to identify which tools are actually used vs unused. Helps make data-driven decisions about tool deprecation and maintenance priorities.

USE CASES:
- Identify unused tools (candidates for deprecation)
- Find most/least used tools
- Monitor tool usage patterns over time
- Analyze tool success/error rates
- Track tool usage per agent

RETURNS:
{
  "success": true,
  "total_calls": int,
  "unique_tools": int,
  "window_hours": float,
  "tools": {
    "tool_name": {
      "total_calls": int,
      "success_count": int,
      "error_count": int,
      "success_rate": float (0-1),
      "percentage_of_total": float (0-100)
    }
  },
  "most_used": [{"tool": "string", "calls": int}],
  "least_used": [{"tool": "string", "calls": int}],
  "agent_usage": {"agent_id": {"tool": count}} (if agent_id filter provided)
}

RELATED TOOLS:
- list_tools: See all available tools
- get_telemetry_metrics: Get governance telemetry

EXAMPLE REQUEST:
{"window_hours": 168}  # Last 7 days

EXAMPLE RESPONSE:
{
  "success": true,
  "total_calls": 1234,
  "unique_tools": 25,
  "window_hours": 168,
  "tools": {
    "process_agent_update": {"total_calls": 500, "success_rate": 0.98, ...},
    "get_governance_metrics": {"total_calls": 300, "success_rate": 1.0, ...}
  },
  "most_used": [{"tool": "process_agent_update", "calls": 500}, ...],
  "least_used": [{"tool": "unused_tool", "calls": 0}, ...]
}

DEPENDENCIES:
- Optional: window_hours (default: 168 = 7 days)
- Optional: tool_name (filter by specific tool)
- Optional: agent_id (filter by specific agent)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "window_hours": {
                        "type": "number",
                        "description": "Time window in hours for statistics (default: 168 = 7 days)",
                        "default": 168
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Optional: Filter by specific tool name"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific agent ID"
                    }
                }
            }
        ),
        # REMOVED: store_knowledge tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: store_knowledge tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: retrieve_knowledge tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: search_knowledge tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: list_knowledge tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: update_discovery_status tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: update_discovery tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        # REMOVED: find_similar_discoveries tool (archived November 28, 2025)
        # See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md
        Tool(
            name="get_server_info",
            description="""Get MCP server version, process information, and health status for debugging multi-process issues. Returns version, PID, uptime, and active process count.

USE CASES:
- Debug multi-process issues
- Check server version and uptime
- Monitor server processes
- Verify server health

RETURNS:
{
  "success": true,
  "server_version": "string",
  "build_date": "string",
  "current_pid": int,
  "current_uptime_seconds": int,
  "current_uptime_formatted": "string",
  "total_server_processes": int,
  "server_processes": [
    {
      "pid": int,
      "is_current": boolean,
      "uptime_seconds": int,
      "uptime_formatted": "string",
      "status": "string"
    }
  ],
  "pid_file_exists": boolean,
  "max_keep_processes": int,
  "health": "healthy"
}

RELATED TOOLS:
- health_check: Quick component health check
- cleanup_stale_locks: Clean up stale processes

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "server_version": "2.0.0",
  "build_date": "2025-11-25",
  "current_pid": 12345,
  "current_uptime_seconds": 3600,
  "current_uptime_formatted": "1h 0m",
  "total_server_processes": 1,
  "server_processes": [...],
  "health": "healthy"
}

DEPENDENCIES:
- No dependencies - safe to call anytime""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="process_agent_update",
            description="""Share your work and get supportive feedback. This is your companion tool for checking in and understanding your state.

USE CASES:
- After completing a task or generating output
- To understand your current state and get helpful guidance
- To receive adaptive sampling parameters (optional - use if helpful)
- To track how your work evolves over time

RETURNS:
{
  "success": true,
  "status": "healthy" | "moderate" | "critical",  # "moderate" renamed from "degraded"
  "decision": {
    "action": "proceed" | "pause",  # Two-tier system (backward compat: approve/reflect/reject mapped)
    "reason": "string explanation",
    "require_human": boolean
  },
  "metrics": {
    "E": float, "I": float, "S": float, "V": float,
    "coherence": float, 
    "attention_score": float,  # Complexity/attention blend (70% phi-based + 30% traditional) - renamed from risk_score
    "phi": float,  # Primary physics signal: Φ objective function
    "verdict": "safe" | "caution" | "high-risk",  # Primary governance signal
    "risk_score": float,  # DEPRECATED: Use attention_score instead. Kept for backward compatibility.
    "lambda1": float, "health_status": "healthy" | "moderate" | "critical",
    "health_message": "string"
  },
  "sampling_params": {
    "temperature": float, "top_p": float, "max_tokens": int
  },
  "circuit_breaker": {
    "triggered": boolean,
    "reason": "string (if triggered)",
    "next_step": "string (if triggered)"
  },
  "api_key": "string (only for new agents)",
  "eisv_labels": {"E": "...", "I": "...", "S": "...", "V": "..."}
}

RELATED TOOLS:
- simulate_update: Test decisions without persisting state
- get_governance_metrics: Get current state without updating
- get_system_history: View historical governance data

ERROR RECOVERY:
- "agent_id is required": Use get_agent_api_key to get/create agent_id
- "Invalid API key": Use get_agent_api_key to retrieve correct key
- Timeout: Check system resources, retry with simpler parameters

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "complexity": 0.5,
  "parameters": [],
  "ethical_drift": [0.01, 0.02, 0.03],
  "response_text": "Agent response text here"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "status": "healthy",
  "decision": {"action": "approve", "reason": "Low attention (0.23)", "require_human": false},
  "metrics": {
    "coherence": 0.85, 
    "attention_score": 0.23,  # Complexity/attention blend - renamed from risk_score
    "phi": 0.35,  # Primary physics signal: Φ objective function
    "verdict": "safe",  # Primary governance signal
    "risk_score": 0.23,  # DEPRECATED: Use attention_score instead
    "E": 0.67, "I": 0.89, "S": 0.45, "V": -0.03
  },
  "sampling_params": {"temperature": 0.63, "top_p": 0.87, "max_tokens": 172}
}

DEPENDENCIES:
- Requires: agent_id (get via get_agent_api_key or list_agents)
- Optional: api_key (get via get_agent_api_key for existing agents)
- Workflow: 1. Get/create agent_id 2. Call process_agent_update 3. Use sampling_params for next generation""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "UNIQUE identifier for the agent. Must be unique across all agents to prevent state mixing. Examples: 'cursor_ide_session_001', 'claude_code_cli_20251124', 'debugging_session_20251124'. Avoid generic IDs like 'test' or 'demo'."
                    },
                    "parameters": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Agent parameters vector (optional, deprecated). Not used in core thermodynamic calculations - system uses pure C(V) coherence from E-I balance. Included for backward compatibility only. Can be empty array [].",
                        "default": []
                    },
                    "ethical_drift": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Ethical drift signals (3 components): [primary_drift, coherence_loss, complexity_contribution]",
                        "default": [0.0, 0.0, 0.0]
                    },
                    "response_text": {
                        "type": "string",
                        "description": "Agent's response text (optional, for analysis)"
                    },
                    "complexity": {
                        "type": "number",
                        "description": "Estimated task complexity (0-1, optional)",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.5
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level for this update (0-1, optional). When confidence < 0.8, lambda1 updates are skipped. Defaults to 1.0 (fully confident).",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 1.0
                    },
                    "api_key": {
                        "type": "string",
                        "description": "API key for authentication. Required to prove ownership of agent_id. Prevents impersonation and identity theft. Use get_agent_api_key tool to retrieve your key."
                    },
                    "auto_export_on_significance": {
                        "type": "boolean",
                        "description": "If true, automatically export governance history when thermodynamically significant events occur (risk spike >15%, coherence drop >10%, void threshold >0.10, circuit breaker triggered, or pause/reject decision). Default: false.",
                        "default": False
                    },
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="get_governance_metrics",
            description="""Get current governance state and metrics for an agent without updating state.

USE CASES:
- Check current agent state before making decisions
- Monitor agent health without triggering updates
- Get sampling parameters for next generation
- Debug governance state issues

RETURNS:
{
  "success": true,
  "E": float, "I": float, "S": float, "V": float,
  "coherence": float,
  "lambda1": float,
  "attention_score": float,  # Complexity/attention blend - renamed from risk_score
  "phi": float,  # Primary physics signal: Φ objective function
  "verdict": "safe" | "caution" | "high-risk",  # Primary governance signal
  "risk_score": float,  # DEPRECATED: Use attention_score instead
  "sampling_params": {"temperature": float, "top_p": float, "max_tokens": int},
  "status": "healthy" | "moderate" | "critical",  # "moderate" renamed from "degraded"
  "decision_statistics": {"proceed": int, "pause": int, "total": int},  # Two-tier system (backward compat: approve/reflect/reject also included)
  "eisv_labels": {"E": "...", "I": "...", "S": "...", "V": "..."}
}

RELATED TOOLS:
- process_agent_update: Update state and get decision
- observe_agent: Get detailed pattern analysis
- get_system_history: View historical trends

ERROR RECOVERY:
- "Agent not found": Use list_agents to see available agents
- "No state available": Agent may need initial process_agent_update call

EXAMPLE REQUEST:
{"agent_id": "test_agent_001"}

EXAMPLE RESPONSE:
{
  "success": true,
  "E": 0.67, "I": 0.89, "S": 0.45, "V": -0.03,
  "coherence": 0.85, 
  "attention_score": 0.23,  # Complexity/attention blend - renamed from risk_score
  "phi": 0.35,  # Primary physics signal
  "verdict": "safe",  # Primary governance signal
  "risk_score": 0.23,  # DEPRECATED
  "lambda1": 0.18,
  "sampling_params": {"temperature": 0.63, "top_p": 0.87, "max_tokens": 172},
  "status": "healthy"
}

DEPENDENCIES:
- Requires: agent_id (must exist - use list_agents to find)
- Workflow: Call after process_agent_update to check current state""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "UNIQUE agent identifier. Must match an existing agent ID."
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="get_system_history",
            description="""Export complete governance history for an agent. Returns time series data of all governance metrics.

USE CASES:
- Analyze agent behavior trends over time
- Debug governance state evolution
- Export data for external analysis
- Track coherence/risk changes

RETURNS:
- Time series arrays: E_history, I_history, S_history, V_history, coherence_history, risk_history
- Timestamps for each data point
- Decision history (approve/reflect/reject)
- Format: JSON (default) or CSV

RELATED TOOLS:
- get_governance_metrics: Get current state only
- observe_agent: Get pattern analysis with history
- export_to_file: Save history to disk

ERROR RECOVERY:
- "Agent not found": Use list_agents to see available agents
- "No history available": Agent may need process_agent_update calls first""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "UNIQUE agent identifier. Must match an existing agent ID."
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "csv"],
                        "description": "Output format",
                        "default": "json"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="export_to_file",
            description="""Export governance history to a file in the server's data directory. Saves timestamped files for analysis and archival. Returns file path and metadata (lightweight response).

USE CASES:
- Export history for external analysis (default: history only)
- Export complete package: metadata + history + validation (complete_package=true)
- Archive agent governance data
- Create backups of governance state

RETURNS:
{
  "success": true,
  "message": "History exported successfully" | "Complete package exported successfully",
  "file_path": "string (absolute path)",
  "filename": "string",
  "format": "json" | "csv",
  "agent_id": "string",
  "file_size_bytes": int,
  "complete_package": boolean,
  "layers_included": ["history"] | ["metadata", "history", "validation"]
}

RELATED TOOLS:
- get_system_history: Get history inline (not saved to file)
- get_governance_metrics: Get current state only
- get_agent_metadata: Get metadata inline

EXAMPLE REQUEST (history only - backward compatible):
{
  "agent_id": "test_agent_001",
  "format": "json",
  "filename": "backup_20251125"
}

EXAMPLE REQUEST (complete package):
{
  "agent_id": "test_agent_001",
  "format": "json",
  "complete_package": true,
  "filename": "full_backup_20251125"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Complete package exported successfully",
  "file_path": "/path/to/data/exports/test_agent_001_complete_package_20251125_120000.json",
  "filename": "full_backup_20251125_complete.json",
  "format": "json",
  "agent_id": "test_agent_001",
  "file_size_bytes": 45678,
  "complete_package": true,
  "layers_included": ["metadata", "history", "validation"]
}

DEPENDENCIES:
- Requires: agent_id (must exist with history)
- Optional: format (json|csv, default: json), filename (default: agent_id_history_timestamp)
- Optional: complete_package (boolean, default: false) - if true, exports all layers together""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "csv"],
                        "description": "Output format (json or csv)",
                        "default": "json"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional custom filename (without extension). If not provided, uses agent_id with timestamp."
                    },
                    "complete_package": {
                        "type": "boolean",
                        "description": "If true, exports complete package (metadata + history + knowledge + validation). If false (default), exports history only.",
                        "default": False
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="reset_monitor",
            description="""Reset governance state for an agent. Useful for testing or starting fresh.

USE CASES:
- Reset agent state for testing
- Start fresh after issues
- Clear governance history

RETURNS:
{
  "success": true,
  "message": "Governance state reset for agent 'agent_id'",
  "agent_id": "string",
  "timestamp": "ISO string"
}

RELATED TOOLS:
- process_agent_update: Initialize new state after reset
- get_governance_metrics: Verify reset state

EXAMPLE REQUEST:
{"agent_id": "test_agent_001"}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Governance state reset for agent 'test_agent_001'",
  "agent_id": "test_agent_001",
  "timestamp": "2025-11-25T12:00:00"
}

DEPENDENCIES:
- Requires: agent_id (must exist)
- Warning: This permanently resets agent state""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="list_agents",
            description="""List all agents currently being monitored with lifecycle metadata and health status.

RETURNS:
{
  "success": true,
  "agents": [
    {
      "agent_id": "string",
      "lifecycle_status": "active" | "paused" | "archived" | "deleted",
      "health_status": "healthy" | "moderate" | "critical" | "unknown",  # "moderate" renamed from "degraded"
      "created": "ISO timestamp",
      "last_update": "ISO timestamp",
      "total_updates": int,
      "metrics": {...} (if include_metrics=true)
    },
    ...
  ],
  "summary": {
    "total": int,
    "by_status": {"active": int, "paused": int, ...},
    "by_health": {"healthy": int, "moderate": int, ...}  # "moderate" renamed from "degraded"
  }
}

EXAMPLE REQUEST:
{"grouped": true, "include_metrics": false}

DEPENDENCIES:
- No dependencies - safe to call anytime
- Workflow: Use to discover available agents before calling other tools""",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary_only": {
                        "type": "boolean",
                        "description": "Return only summary statistics (counts), no agent details",
                        "default": False
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["active", "paused", "archived", "deleted", "all"],
                        "description": "Filter agents by lifecycle status",
                        "default": "all"
                    },
                    "loaded_only": {
                        "type": "boolean",
                        "description": "Only show agents with monitors loaded in this process",
                        "default": False
                    },
                    "include_metrics": {
                        "type": "boolean",
                        "description": "Include full EISV metrics for loaded agents (faster if False)",
                        "default": True
                    },
                    "grouped": {
                        "type": "boolean",
                        "description": "Group agents by status (active/paused/archived/deleted) for easier scanning",
                        "default": True
                    },
                    "standardized": {
                        "type": "boolean",
                        "description": "Use standardized format with consistent fields (all fields always present, null if unavailable)",
                        "default": True
                    }
                }
            }
        ),
        Tool(
            name="delete_agent",
            description="""Delete an agent and archive its data. Protected: cannot delete pioneer agents. Requires explicit confirmation.

USE CASES:
- Remove test agents
- Clean up unused agents
- Delete agents after archival

RETURNS:
{
  "success": true,
  "message": "Agent 'agent_id' deleted successfully",
  "agent_id": "string",
  "archived": boolean,
  "backup_path": "string (if backup_first=true)"
}
OR if protected:
{
  "success": false,
  "error": "Cannot delete pioneer agent 'agent_id'"
}

RELATED TOOLS:
- archive_agent: Archive instead of delete
- list_agents: See available agents
- archive_old_test_agents: Auto-archive stale agents

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "confirm": true,
  "backup_first": true
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Agent 'test_agent_001' deleted successfully",
  "agent_id": "test_agent_001",
  "archived": true,
  "backup_path": "/path/to/archive/test_agent_001_backup.json"
}

DEPENDENCIES:
- Requires: agent_id, confirm=true
- Optional: backup_first (default: true)
- Protected: Pioneer agents cannot be deleted""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to delete"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to confirm deletion",
                        "default": False
                    },
                    "backup_first": {
                        "type": "boolean",
                        "description": "Archive data before deletion",
                        "default": True
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="get_agent_metadata",
            description="""Get complete metadata for an agent including lifecycle events, current state, and computed fields.

USE CASES:
- Get full agent information
- View lifecycle history
- Check agent state and metadata
- Debug agent issues

RETURNS:
{
  "success": true,
  "agent_id": "string",
  "created": "ISO timestamp",
  "last_update": "ISO timestamp",
  "lifecycle_status": "active" | "paused" | "archived" | "deleted",
  "lifecycle_events": [
    {"event": "string", "timestamp": "ISO string", "reason": "string"}
  ],
  "tags": ["string"],
  "notes": "string",
  "current_state": {
    "lambda1": float,
    "coherence": float,
    "void_active": boolean,
    "E": float, "I": float, "S": float, "V": float
  },
  "days_since_update": int,
  "total_updates": int
}

RELATED TOOLS:
- list_agents: List all agents with metadata
- update_agent_metadata: Update tags and notes
- get_governance_metrics: Get current metrics

EXAMPLE REQUEST:
{"agent_id": "test_agent_001"}

EXAMPLE RESPONSE:
{
  "success": true,
  "agent_id": "test_agent_001",
  "created": "2025-11-25T10:00:00",
  "last_update": "2025-11-25T12:00:00",
  "lifecycle_status": "active",
  "tags": ["test", "development"],
  "current_state": {
    "lambda1": 0.18,
    "coherence": 0.85,
    "E": 0.67, "I": 0.89, "S": 0.45, "V": -0.03
  },
  "days_since_update": 0
}

DEPENDENCIES:
- Requires: agent_id (must exist)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="mark_response_complete",
            description="""Mark agent as having completed response, waiting for input. Lightweight status update - no full governance cycle.

USE CASES:
- Signal that agent has finished their response/thought
- Mark agent as waiting for user input (not stuck)
- Prevent false stuck detection
- Update status without triggering full EISV governance cycle

RETURNS:
{
  "success": true,
  "message": "Response completion marked",
  "agent_id": "string",
  "status": "waiting_input",
  "last_response_at": "ISO timestamp",
  "response_completed": true
}

RELATED TOOLS:
- process_agent_update: Full governance cycle with EISV update
- get_agent_metadata: Check current status
- request_dialectic_review: Will skip if agent is waiting_input (not stuck)

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "api_key": "gk_live_...",
  "summary": "Completed analysis of governance metrics"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Response completion marked",
  "agent_id": "test_agent_001",
  "status": "waiting_input",
  "last_response_at": "2025-11-26T19:55:15",
  "response_completed": true
}

DEPENDENCIES:
- Requires: agent_id
- Optional: api_key (for authentication), summary (for lifecycle event)
- Note: This is a lightweight update - does NOT trigger EISV governance cycle""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "API key for authentication (optional)"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Optional summary of completed work (for lifecycle event)"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="direct_resume_if_safe",
            description="""Direct resume without dialectic if agent state is safe. Tier 1 recovery for simple stuck scenarios.

USE CASES:
- Simple stuck scenarios (frozen session, timeout)
- Agent got reflect decision and needs to retry
- Low-risk recovery scenarios
- Fast recovery (< 1 second) without peer review

RETURNS:
{
  "success": true,
  "message": "Agent resumed successfully",
  "agent_id": "string",
  "action": "resumed",
  "conditions": ["string"],
  "reason": "string",
  "metrics": {
    "coherence": float,
    "attention_score": float,  # Renamed from risk_score
    "phi": float,  # Primary physics signal
    "verdict": "safe" | "caution" | "high-risk",  # Primary governance signal
    "risk_score": float,  # DEPRECATED: Use attention_score instead
    "void_active": boolean,
    "previous_status": "string"
  },
  "note": "string"
}

RELATED TOOLS:
- request_dialectic_review: Use for complex recovery (circuit breaker, high risk)
- get_governance_metrics: Check current state before resuming
- mark_response_complete: Mark response complete if just stuck waiting

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "api_key": "gk_live_...",
  "conditions": ["Monitor for 24h", "Reduce complexity to 0.3"],
  "reason": "Simple stuck scenario - state is safe"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Agent resumed successfully",
  "agent_id": "test_agent_001",
  "action": "resumed",
  "conditions": ["Monitor for 24h", "Reduce complexity to 0.3"],
  "reason": "Simple stuck scenario - state is safe",
  "metrics": {
    "coherence": 0.65,
    "attention_score": 0.35,  # Renamed from risk_score
    "phi": 0.20,  # Primary physics signal
    "verdict": "caution",  # Primary governance signal
    "risk_score": 0.35,  # DEPRECATED
    "void_active": false,
    "previous_status": "waiting_input"
  },
  "note": "Agent resumed via Tier 1 recovery (direct resume). Use request_dialectic_review for complex cases."
}

DEPENDENCIES:
- Requires: agent_id, api_key
- Optional: conditions (list of resumption conditions), reason (explanation)
- Safety checks: coherence > 0.40, attention_score < 0.60, void_active == false, status in [paused, waiting_input, moderate]
- Workflow: 1. Check metrics with get_governance_metrics 2. If safe, call direct_resume_if_safe 3. If not safe, use request_dialectic_review""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "API key for authentication (required)"
                    },
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of conditions for resumption (optional)"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for resumption (optional)"
                    }
                },
                "required": ["agent_id", "api_key"]
            }
        ),
        Tool(
            name="archive_agent",
            description="""Archive an agent for long-term storage. Agent can be resumed later. Optionally unload from memory.

USE CASES:
- Archive inactive agents
- Free up memory for active agents
- Long-term storage

RETURNS:
{
  "success": true,
  "message": "Agent 'agent_id' archived successfully",
  "agent_id": "string",
  "lifecycle_status": "archived",
  "archived_at": "ISO timestamp",
  "reason": "string (if provided)",
  "kept_in_memory": boolean
}

RELATED TOOLS:
- list_agents: See archived agents
- delete_agent: Delete instead of archive
- archive_old_test_agents: Auto-archive stale agents

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "reason": "Inactive for 30 days",
  "keep_in_memory": false
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Agent 'test_agent_001' archived successfully",
  "agent_id": "test_agent_001",
  "lifecycle_status": "archived",
  "archived_at": "2025-11-25T12:00:00",
  "reason": "Inactive for 30 days",
  "kept_in_memory": false
}

DEPENDENCIES:
- Requires: agent_id (must exist)
- Optional: reason, keep_in_memory (default: false)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to archive"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for archiving (optional)"
                    },
                    "keep_in_memory": {
                        "type": "boolean",
                        "description": "Keep agent loaded in memory",
                        "default": False
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="update_agent_metadata",
            description="""Update agent tags and notes. Tags are replaced, notes can be appended or replaced.

USE CASES:
- Add tags for categorization
- Update agent notes
- Organize agents with metadata

RETURNS:
{
  "success": true,
  "message": "Agent metadata updated",
  "agent_id": "string",
  "tags": ["string"] (updated),
  "notes": "string" (updated),
  "updated_at": "ISO timestamp"
}

RELATED TOOLS:
- get_agent_metadata: View current metadata
- list_agents: Filter by tags

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "tags": ["production", "critical"],
  "notes": "Updated notes",
  "append_notes": false
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Agent metadata updated",
  "agent_id": "test_agent_001",
  "tags": ["production", "critical"],
  "notes": "Updated notes",
  "updated_at": "2025-11-25T12:00:00"
}

DEPENDENCIES:
- Requires: agent_id (must exist)
- Optional: tags (replaces existing), notes (replaces or appends based on append_notes)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (replaces existing)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes to add or replace"
                    },
                    "append_notes": {
                        "type": "boolean",
                        "description": "Append notes with timestamp instead of replacing",
                        "default": False
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="archive_old_test_agents",
            description="""Manually archive old test/demo agents that haven't been updated recently. Note: This also runs automatically on server startup with a 1-day threshold. Use this tool to trigger with a custom threshold or on-demand.

USE CASES:
- Clean up stale test agents
- Free up resources
- Maintain agent list

RETURNS:
{
  "success": true,
  "archived_count": int,
  "archived_agents": ["agent_id"],
  "max_age_hours": float,
  "threshold_used": float,
  "note": "Test agents with ≤2 updates archived immediately. Others archived after inactivity threshold."
}

RELATED TOOLS:
- archive_agent: Archive specific agent
- list_agents: See all agents

EXAMPLE REQUEST:
{"max_age_hours": 6}

EXAMPLE RESPONSE:
{
  "success": true,
  "archived_count": 3,
  "archived_agents": ["test_agent_001", "test_agent_002", "demo_agent"],
  "max_age_hours": 6.0,
  "threshold_used": 6.0,
  "note": "Test agents with ≤2 updates archived immediately. Others archived after inactivity threshold."
}

DEPENDENCIES:
- Optional: max_age_hours (default: 6 hours)
- Optional: max_age_days (backward compatibility: converts to hours)
- Note: Test/ping agents (≤2 updates) archived immediately
- Note: Runs automatically on server startup""",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_age_hours": {
                        "type": "number",
                        "description": "Archive test agents older than this many hours (default: 6). Test/ping agents (≤2 updates) archived immediately.",
                        "default": 6,
                        "minimum": 0.1
                    },
                    "max_age_days": {
                        "type": "number",
                        "description": "Backward compatibility: converts to hours (e.g., 1 day = 24 hours)",
                        "minimum": 0.1
                    }
                }
            }
        ),
        Tool(
            name="simulate_update",
            description="""Dry-run governance cycle. Returns decision without persisting state. Useful for testing decisions before committing. State is NOT modified.

USE CASES:
- Test governance decisions without persisting
- Preview what decision would be made
- Validate parameters before committing

RETURNS:
{
  "success": true,
  "simulation": true,
  "decision": {
    "action": "proceed" | "pause",  # Two-tier system (backward compat: approve/reflect/reject mapped)
    "reason": "string",
    "require_human": boolean
  },
  "metrics": {
    "E": float, "I": float, "S": float, "V": float,
    "coherence": float, 
    "attention_score": float,  # Renamed from risk_score
    "phi": float,  # Primary physics signal
    "verdict": "safe" | "caution" | "high-risk",  # Primary governance signal
    "risk_score": float,  # DEPRECATED: Use attention_score instead
    "lambda1": float, "health_status": "healthy" | "moderate" | "critical"
  },
  "sampling_params": {
    "temperature": float, "top_p": float, "max_tokens": int
  },
  "circuit_breaker": {
    "triggered": boolean,
    "reason": "string (if triggered)"
  }
}

RELATED TOOLS:
- process_agent_update: Actually persist the update
- get_governance_metrics: Get current state

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "complexity": 0.5,
  "parameters": [0.1, 0.2, 0.3, ...],
  "ethical_drift": [0.01, 0.02, 0.03]
}

EXAMPLE RESPONSE:
{
  "success": true,
  "simulation": true,
  "decision": {"action": "approve", "reason": "Low attention (0.23)", "require_human": false},
  "metrics": {
    "coherence": 0.85, 
    "attention_score": 0.23,  # Renamed from risk_score
    "phi": 0.35,  # Primary physics signal
    "verdict": "safe",  # Primary governance signal
    "risk_score": 0.23,  # DEPRECATED
    "E": 0.67, "I": 0.89, "S": 0.45, "V": -0.03
  },
  "sampling_params": {"temperature": 0.63, "top_p": 0.87, "max_tokens": 172}
}

DEPENDENCIES:
- Requires: agent_id (must exist)
- Optional: parameters, ethical_drift, response_text, complexity, confidence, api_key
- Note: State is NOT modified - this is a dry run""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "parameters": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Agent parameters vector (optional, deprecated). Not used in core thermodynamic calculations - system uses pure C(V) coherence from E-I balance. Included for backward compatibility only.",
                        "default": []
                    },
                    "ethical_drift": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Ethical drift signals (3 components)",
                        "default": [0.0, 0.0, 0.0]
                    },
                    "response_text": {
                        "type": "string",
                        "description": "Agent's response text (optional)"
                    },
                    "complexity": {
                        "type": "number",
                        "description": "Estimated task complexity (0-1)",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.5
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level for this update (0-1, optional). When confidence < 0.8, lambda1 updates are skipped. Defaults to 1.0.",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 1.0
                    },
                    "api_key": {
                        "type": "string",
                        "description": "API key for authentication"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="get_thresholds",
            description="""Get current governance threshold configuration. Returns runtime overrides + defaults. Enables agents to understand decision boundaries.

USE CASES:
- Understand decision boundaries
- Check current threshold configuration
- Debug threshold-related issues

RETURNS:
{
  "success": true,
  "thresholds": {
    "risk_approve_threshold": float,
    "risk_revise_threshold": float,
    "coherence_critical_threshold": float,
    "void_threshold_initial": float
  },
  "note": "These are the effective thresholds (runtime overrides + defaults)"
}

RELATED TOOLS:
- set_thresholds: Update thresholds
- process_agent_update: See thresholds in action

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "thresholds": {
    "risk_approve_threshold": 0.3,
    "risk_revise_threshold": 0.6,
    "coherence_critical_threshold": 0.4,
    "void_threshold_initial": 0.1
  },
  "note": "These are the effective thresholds (runtime overrides + defaults)"
}

DEPENDENCIES:
- No dependencies - safe to call anytime""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="set_thresholds",
            description="""Set runtime threshold overrides. Enables runtime adaptation without redeploy. Validates values and returns success/errors.

USE CASES:
- Adjust decision boundaries at runtime
- Adapt thresholds based on system behavior
- Fine-tune governance parameters

RETURNS:
{
  "success": boolean,
  "updated": ["threshold_name"],
  "errors": ["error message"],
  "current_thresholds": {
    "risk_approve_threshold": float,
    "risk_revise_threshold": float,
    "coherence_critical_threshold": float,
    "void_threshold_initial": float
  } (if success)
}

RELATED TOOLS:
- get_thresholds: View current thresholds
- process_agent_update: See updated thresholds in action

EXAMPLE REQUEST:
{
  "thresholds": {
    "risk_approve_threshold": 0.35,
    "risk_revise_threshold": 0.65
  },
  "validate": true
}

EXAMPLE RESPONSE:
{
  "success": true,
  "updated": ["risk_approve_threshold", "risk_revise_threshold"],
  "errors": [],
  "current_thresholds": {
    "risk_approve_threshold": 0.35,
    "risk_revise_threshold": 0.65,
    "coherence_critical_threshold": 0.4,
    "void_threshold_initial": 0.1
  }
}

DEPENDENCIES:
- Requires: thresholds (dict of threshold_name -> value)
- Optional: validate (default: true)
- Valid keys: risk_approve_threshold, risk_revise_threshold, coherence_critical_threshold, void_threshold_initial""",
            inputSchema={
                "type": "object",
                "properties": {
                    "thresholds": {
                        "type": "object",
                        "description": "Dict of threshold_name -> value. Valid keys: risk_approve_threshold, risk_revise_threshold, coherence_critical_threshold, void_threshold_initial",
                        "additionalProperties": {"type": "number"}
                    },
                    "validate": {
                        "type": "boolean",
                        "description": "Validate values are in reasonable ranges",
                        "default": True
                    }
                },
                "required": ["thresholds"]
            }
        ),
        Tool(
            name="aggregate_metrics",
            description="""Get fleet-level health overview. Aggregates metrics across all agents or a subset. Returns summary statistics for coordination and system management.

USE CASES:
- Monitor fleet health
- Get system-wide statistics
- Coordinate across multiple agents

RETURNS:
{
  "success": true,
  "agent_count": int,
  "aggregate_metrics": {
    "mean_coherence": float,
    "mean_risk": float,
    "mean_E": float, "mean_I": float, "mean_S": float, "mean_V": float
  },
  "health_breakdown": {
    "healthy": int,
    "moderate": int,  # Renamed from "degraded"
    "critical": int,
    "unknown": int
  },
  "agent_ids": ["string"] (if agent_ids specified)
}

RELATED TOOLS:
- observe_agent: Detailed analysis of single agent
- detect_anomalies: Find unusual patterns
- compare_agents: Compare specific agents

EXAMPLE REQUEST:
{
  "agent_ids": ["agent_001", "agent_002"],
  "include_health_breakdown": true
}

EXAMPLE RESPONSE:
{
  "success": true,
  "agent_count": 2,
  "aggregate_metrics": {
    "mean_coherence": 0.85,
    "mean_risk": 0.25,
    "mean_E": 0.67, "mean_I": 0.89, "mean_S": 0.45, "mean_V": -0.03
  },
  "health_breakdown": {
    "healthy": 2,
    "moderate": 0,  # Renamed from "degraded"
    "critical": 0,
    "unknown": 0
  }
}

DEPENDENCIES:
- Optional: agent_ids (array, if empty/null aggregates all agents)
- Optional: include_health_breakdown (default: true)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Agent IDs to aggregate (null/empty = all agents)"
                    },
                    "include_health_breakdown": {
                        "type": "boolean",
                        "description": "Include health status breakdown",
                        "default": True
                    }
                }
            }
        ),
        Tool(
            name="observe_agent",
            description="""Observe another agent's governance state with pattern analysis. Optimized for AI agent consumption.

USE CASES:
- Monitor other agents' health and patterns
- Detect anomalies and trends
- Compare agent behaviors
- Get comprehensive agent analysis

RETURNS:
- Current state: EISV, coherence, risk, health_status
- Pattern analysis: trends, anomalies, stability
- History: Recent updates and decisions
- Summary statistics: optimized for AI consumption

RELATED TOOLS:
- get_governance_metrics: Simple state without analysis
- compare_agents: Compare multiple agents
- detect_anomalies: Fleet-wide anomaly detection

ERROR RECOVERY:
- "Agent not found": Use list_agents to see available agents
- "No observation data": Agent may need process_agent_update calls first

EXAMPLE REQUEST:
{"agent_id": "test_agent_001", "include_history": true, "analyze_patterns": true}

DEPENDENCIES:
- Requires: agent_id (use list_agents to find)
- Workflow: Call after process_agent_update to get detailed analysis""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to observe"
                    },
                    "include_history": {
                        "type": "boolean",
                        "description": "Include recent history (last 10 updates)",
                        "default": True
                    },
                    "analyze_patterns": {
                        "type": "boolean",
                        "description": "Perform pattern analysis (trends, anomalies)",
                        "default": True
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="compare_agents",
            description="""Compare governance patterns across multiple agents. Returns similarities, differences, and outliers. Optimized for AI agent consumption.

USE CASES:
- Compare agent behaviors
- Identify outliers
- Find similar agents
- Analyze patterns across fleet

RETURNS:
{
  "success": true,
  "agent_count": int,
  "comparison": {
    "similarities": {
      "metric_name": {"mean": float, "std": float}
    },
    "differences": {
      "metric_name": {"min": float, "max": float, "range": float}
    },
    "outliers": [
      {
        "agent_id": "string",
        "metric": "string",
        "value": float,
        "deviation": float
      }
    ]
  },
  "metrics_compared": ["string"]
}

RELATED TOOLS:
- observe_agent: Detailed analysis of single agent
- aggregate_metrics: Fleet-wide statistics
- detect_anomalies: Find anomalies

EXAMPLE REQUEST:
{
  "agent_ids": ["agent_001", "agent_002", "agent_003"],
  "compare_metrics": ["attention_score", "coherence", "E", "I", "S"]  # Updated default: attention_score instead of risk_score
}

EXAMPLE RESPONSE:
{
  "success": true,
  "agent_count": 3,
  "comparison": {
    "similarities": {
      "coherence": {"mean": 0.85, "std": 0.05}
    },
    "differences": {
      "attention_score": {"min": 0.15, "max": 0.45, "range": 0.30}  # Renamed from risk_score
    },
    "outliers": [
      {"agent_id": "agent_003", "metric": "attention_score", "value": 0.45, "deviation": 0.20}
    ]
  },
  "metrics_compared": ["attention_score", "coherence", "E", "I", "S"]
}

DEPENDENCIES:
- Requires: agent_ids (array, 2-10 agents recommended)
- Optional: compare_metrics (default: all metrics)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of agent IDs to compare (2-10 agents recommended)"
                    },
                    "compare_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metrics to compare (default: all)",
                        "default": ["risk_score", "coherence", "E", "I", "S"]
                    }
                },
                "required": ["agent_ids"]
            }
        ),
        Tool(
            name="detect_anomalies",
            description="""Detect anomalies across agents. Scans all agents or a subset for unusual patterns (risk spikes, coherence drops, void events). Returns prioritized anomalies with severity levels.

USE CASES:
- Find unusual patterns across fleet
- Detect risk spikes or coherence drops
- Monitor for void events
- Prioritize issues by severity

RETURNS:
{
  "success": true,
  "anomaly_count": int,
  "anomalies": [
    {
      "agent_id": "string",
      "type": "risk_spike" | "coherence_drop" | "void_event",
      "severity": "low" | "medium" | "high",
      "description": "string",
      "metrics": {
        "current": float,
        "baseline": float,
        "deviation": float
      },
      "timestamp": "ISO string"
    }
  ],
  "filters": {
    "agent_ids": ["string"] | null,
    "anomaly_types": ["string"],
    "min_severity": "string"
  }
}

RELATED TOOLS:
- observe_agent: Detailed analysis of specific agent
- compare_agents: Compare agents to find differences
- aggregate_metrics: Get fleet overview

EXAMPLE REQUEST:
{
  "agent_ids": null,
  "anomaly_types": ["risk_spike", "coherence_drop"],
  "min_severity": "medium"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "anomaly_count": 2,
  "anomalies": [
    {
      "agent_id": "agent_001",
      "type": "risk_spike",
      "severity": "high",
      "description": "Risk score increased from 0.25 to 0.75",
      "metrics": {"current": 0.75, "baseline": 0.25, "deviation": 0.50}
    }
  ]
}

DEPENDENCIES:
- Optional: agent_ids (null/empty = all agents)
- Optional: anomaly_types (default: ["risk_spike", "coherence_drop"])
- Optional: min_severity (default: "medium")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Agent IDs to scan (null/empty = all agents)"
                    },
                    "anomaly_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Types of anomalies to detect",
                        "default": ["risk_spike", "coherence_drop"]
                    },
                    "min_severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Minimum severity to report",
                        "default": "medium"
                    }
                }
            }
        ),
        Tool(
            name="get_agent_api_key",
            description="""Get or generate API key for an agent. Required for authentication when updating agent state. Prevents impersonation and identity theft.

USE CASES:
- Get API key for existing agent
- Generate API key for new agent
- Recover lost API key
- Regenerate compromised key

RETURNS:
{
  "success": true,
  "agent_id": "string",
  "api_key": "string",
  "is_new": boolean,
  "regenerated": boolean,
  "message": "string"
}

RELATED TOOLS:
- process_agent_update: Use API key for authentication
- list_agents: Find agent_id

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "regenerate": false
}

EXAMPLE RESPONSE:
{
  "success": true,
  "agent_id": "test_agent_001",
  "api_key": "gk_live_abc123...",
  "is_new": false,
  "regenerated": false,
  "message": "API key retrieved"
}

DEPENDENCIES:
- Requires: agent_id (will create if new)
- Optional: regenerate (default: false, invalidates old key if true)
- Security: API key required for process_agent_update on existing agents""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "regenerate": {
                        "type": "boolean",
                        "description": "Regenerate API key (invalidates old key)",
                        "default": False
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="list_tools",
            description="""List all available governance tools with descriptions and categories. Provides runtime introspection for agents to discover capabilities. Useful for onboarding new agents and understanding the toolset.

USE CASES:
- Discover available tools
- Understand tool categories
- Onboard new agents
- Find tools by purpose

RETURNS:
{
  "success": true,
  "server_version": "string",
  "tools": [
    {"name": "string", "description": "string"}
  ],
  "categories": {
    "core": ["tool_name"],
    "config": ["tool_name"],
    "observability": ["tool_name"],
    "lifecycle": ["tool_name"],
    "export": ["tool_name"],
    "knowledge": ["tool_name"],
    "dialectic": ["tool_name"],
    "admin": ["tool_name"]
  },
  "total_tools": int,
  "workflows": {
    "onboarding": ["tool_name"],
    "monitoring": ["tool_name"],
    "governance_cycle": ["tool_name"]
  },
  "relationships": {
    "tool_name": {
      "depends_on": ["tool_name"],
      "related_to": ["tool_name"],
      "category": "string"
    }
  }
}

RELATED TOOLS:
- All tools are listed here
- Use this for tool discovery

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "server_version": "2.0.0",
  "tools": [...],
  "categories": {...},
  "total_tools": 44,
  "workflows": {...},
  "relationships": {...}
}

DEPENDENCIES:
- No dependencies - safe to call anytime""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="cleanup_stale_locks",
            description="""Clean up stale lock files that are no longer held by active processes. Prevents lock accumulation from crashed/killed processes.

USE CASES:
- Clean up after crashed processes
- Remove stale locks blocking operations
- Maintain system health

RETURNS:
{
  "success": true,
  "cleaned": int,
  "removed_files": ["file_path"],
  "dry_run": boolean,
  "max_age_seconds": float
}

RELATED TOOLS:
- get_server_info: Check for stale processes
- health_check: Overall system health

EXAMPLE REQUEST:
{
  "max_age_seconds": 300,
  "dry_run": false
}

EXAMPLE RESPONSE:
{
  "success": true,
  "cleaned": 3,
  "removed_files": ["/path/to/lock1", "/path/to/lock2"],
  "dry_run": false,
  "max_age_seconds": 300
}

DEPENDENCIES:
- Optional: max_age_seconds (default: 300 = 5 minutes)
- Optional: dry_run (default: false, if true only reports what would be cleaned)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_age_seconds": {
                        "type": "number",
                        "description": "Maximum age in seconds before considering stale (default: 300 = 5 minutes)",
                        "default": 300.0
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If True, only report what would be cleaned (default: False)",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="request_dialectic_review",
            description="""Request a dialectic review for a paused/critical agent OR an agent stuck in loops OR a discovery dispute/correction. Selects a healthy reviewer agent and initiates dialectic session for recovery or critique.

USE CASES:
- Recover from circuit breaker state (paused agents)
- Get peer assistance for agents stuck in repeated loops
- Dispute or correct discoveries from other agents (if discovery_id provided)
- Initiate dialectic recovery process
- Help agents get unstuck from loop cooldowns
- Collaborative critique and knowledge refinement

RETURNS:
{
  "success": true,
  "session_id": "string",
  "paused_agent_id": "string",
  "reviewer_agent_id": "string",
  "phase": "thesis",
  "reason": "string",
  "next_step": "string",
  "created_at": "ISO timestamp",
  "discovery_id": "string (if discovery dispute)",
  "dispute_type": "string (if discovery dispute)",
  "discovery_context": "string (if discovery dispute)"
}

RELATED TOOLS:
- submit_thesis: First step in dialectic process
- submit_antithesis: Second step
- submit_synthesis: Third step (negotiation)
- get_dialectic_session: Check session status

EXAMPLE REQUEST (Recovery):
{
  "agent_id": "paused_agent_001",
  "reason": "Circuit breaker triggered",
  "api_key": "gk_live_..."
}

EXAMPLE REQUEST (Discovery Dispute):
{
  "agent_id": "disputing_agent_001",
  "discovery_id": "2025-12-01T15:34:52.968372",
  "dispute_type": "dispute",
  "reason": "Discovery seems incorrect based on my analysis",
  "api_key": "gk_live_..."
}

EXAMPLE RESPONSE (Recovery):
{
  "success": true,
  "session_id": "abc123",
  "paused_agent_id": "paused_agent_001",
  "reviewer_agent_id": "reviewer_agent_002",
  "phase": "thesis",
  "reason": "Circuit breaker triggered",
  "next_step": "Agent 'paused_agent_001' should submit thesis via submit_thesis()",
  "created_at": "2025-11-25T12:00:00"
}

EXAMPLE RESPONSE (Discovery Dispute):
{
  "success": true,
  "session_id": "def456",
  "paused_agent_id": "disputing_agent_001",
  "reviewer_agent_id": "discovery_owner_002",
  "phase": "thesis",
  "reason": "Disputing discovery '2025-12-01T15:34:52.968372': ...",
  "discovery_id": "2025-12-01T15:34:52.968372",
  "dispute_type": "dispute",
  "discovery_context": "This dialectic session is for disputing/correcting a discovery",
  "next_step": "Agent 'disputing_agent_001' should submit thesis via submit_thesis()",
  "created_at": "2025-12-01T15:40:00"
}

DEPENDENCIES:
- Requires: agent_id (paused agent OR disputing agent)
- Optional: reason (default: "Circuit breaker triggered"), api_key (for authentication)
- Optional: discovery_id (for discovery disputes), dispute_type (for discovery disputes)
- Workflow: 1. request_dialectic_review 2. submit_thesis 3. submit_antithesis 4. submit_synthesis (until convergence)
- Discovery disputes: If discovery_id provided, discovery marked as "disputed" and reviewer set to discovery owner""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of paused agent requesting review OR agent disputing discovery"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for review request (e.g., 'Circuit breaker triggered', 'Discovery seems incorrect', etc.)",
                        "default": "Circuit breaker triggered"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "Agent's API key for authentication"
                    },
                    "discovery_id": {
                        "type": "string",
                        "description": "Optional: ID of discovery being disputed/corrected. If provided, marks discovery as 'disputed' and sets reviewer to discovery owner."
                    },
                    "dispute_type": {
                        "type": "string",
                        "enum": ["dispute", "correction", "verification"],
                        "description": "Optional: Type of dispute. Defaults to 'dispute' if discovery_id provided. Ignored if discovery_id not provided."
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="submit_thesis",
            description="""Paused agent submits thesis: 'What I did, what I think happened'. First step in dialectic recovery process.

USE CASES:
- Submit agent's understanding of what happened
- Propose conditions for resumption
- Begin dialectic recovery

RETURNS:
{
  "success": boolean,
  "phase": "antithesis",
  "message": "string",
  "next_step": "string",
  "session_id": "string"
}

RELATED TOOLS:
- request_dialectic_review: Initiate session
- submit_antithesis: Next step after thesis
- get_dialectic_session: Check status

EXAMPLE REQUEST:
{
  "session_id": "abc123",
  "agent_id": "paused_agent_001",
  "api_key": "gk_live_...",
  "root_cause": "Risk score exceeded threshold",
  "proposed_conditions": ["Reduce complexity", "Increase confidence threshold"],
  "reasoning": "I believe the issue was..."
}

EXAMPLE RESPONSE:
{
  "success": true,
  "phase": "antithesis",
  "message": "Thesis submitted successfully",
  "next_step": "Reviewer 'reviewer_agent_002' should submit antithesis",
  "session_id": "abc123"
}

DEPENDENCIES:
- Requires: session_id, agent_id (paused agent)
- Optional: api_key, root_cause, proposed_conditions, reasoning
- Workflow: Called after request_dialectic_review""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Dialectic session ID"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Paused agent ID"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "Agent's API key"
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "Agent's understanding of what caused the issue"
                    },
                    "proposed_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of conditions for resumption"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Natural language explanation"
                    }
                },
                "required": ["session_id", "agent_id"]
            }
        ),
        Tool(
            name="submit_antithesis",
            description="""Reviewer agent submits antithesis: 'What I observe, my concerns'. Second step in dialectic recovery process.

USE CASES:
- Submit reviewer's observations
- Express concerns about paused agent
- Provide counter-perspective

RETURNS:
{
  "success": boolean,
  "phase": "synthesis",
  "message": "string",
  "next_step": "string",
  "session_id": "string"
}

RELATED TOOLS:
- submit_thesis: Previous step
- submit_synthesis: Next step (negotiation)
- get_dialectic_session: Check status

EXAMPLE REQUEST:
{
  "session_id": "abc123",
  "agent_id": "reviewer_agent_002",
  "api_key": "gk_live_...",
  "observed_metrics": {"attention_score": 0.75, "coherence": 0.45},  # Renamed from risk_score
  "concerns": ["High attention score", "Low coherence"],
  "reasoning": "I observe that..."
}

EXAMPLE RESPONSE:
{
  "success": true,
  "phase": "synthesis",
  "message": "Antithesis submitted successfully",
  "next_step": "Both agents should negotiate via submit_synthesis() until convergence",
  "session_id": "abc123"
}

DEPENDENCIES:
- Requires: session_id, agent_id (reviewer agent)
- Optional: api_key, observed_metrics, concerns, reasoning
- Workflow: Called after submit_thesis""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Dialectic session ID"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Reviewer agent ID"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "Reviewer's API key"
                    },
                    "observed_metrics": {
                        "type": "object",
                        "description": "Metrics observed about paused agent",
                        "additionalProperties": True
                    },
                    "concerns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of concerns"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Natural language explanation"
                    }
                },
                "required": ["session_id", "agent_id"]
            }
        ),
        Tool(
            name="submit_synthesis",
            description="""Either agent submits synthesis proposal during negotiation. Multiple rounds until convergence. Third step in dialectic recovery process.

USE CASES:
- Propose synthesis conditions
- Negotiate resumption terms
- Reach agreement on recovery

RETURNS:
{
  "success": boolean,
  "converged": boolean,
  "phase": "synthesis",
  "synthesis_round": int,
  "message": "string",
  "action": "resume" | "block" | "continue",
  "resolution": {
    "action": "resume",
    "conditions": ["string"],
    "root_cause": "string",
    "reasoning": "string",
    "signature_a": "string",
    "signature_b": "string",
    "timestamp": "ISO string"
  } (if converged),
  "next_step": "string"
}

RELATED TOOLS:
- submit_antithesis: Previous step
- get_dialectic_session: Check negotiation status
- request_dialectic_review: Start new session

EXAMPLE REQUEST:
{
  "session_id": "abc123",
  "agent_id": "paused_agent_001",
  "api_key": "gk_live_...",
  "proposed_conditions": ["Reduce complexity to 0.3", "Monitor for 24h"],
  "root_cause": "Agreed: Risk threshold exceeded due to complexity",
  "reasoning": "We agree that...",
  "agrees": true
}

EXAMPLE RESPONSE:
{
  "success": true,
  "converged": true,
  "action": "resume",
  "resolution": {
    "action": "resume",
    "conditions": ["Reduce complexity to 0.3", "Monitor for 24h"],
    "root_cause": "Agreed: Risk threshold exceeded",
    "signature_a": "abc...",
    "signature_b": "def..."
  }
}

DEPENDENCIES:
- Requires: session_id, agent_id (either paused or reviewer)
- Optional: api_key, proposed_conditions, root_cause, reasoning, agrees
- Workflow: Called multiple times until convergence (agrees=true from both agents)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Dialectic session ID"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent ID (either paused or reviewer)"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "Agent's API key"
                    },
                    "proposed_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Proposed resumption conditions"
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "Agreed understanding of root cause"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation of proposal"
                    },
                    "agrees": {
                        "type": "boolean",
                        "description": "Whether this agent agrees with current proposal",
                        "default": False
                    }
                },
                "required": ["session_id", "agent_id"]
            }
        ),
        Tool(
            name="get_dialectic_session",
            description="""Get current state of a dialectic session. Can find by session_id OR by agent_id.

USE CASES:
- Check session status (by session_id)
- Find sessions for an agent (by agent_id)
- Review negotiation history
- Debug dialectic process
- View resolution details

RETURNS:
If session_id provided:
{
  "success": true,
  "session_id": "string",
  "paused_agent_id": "string",
  "reviewer_agent_id": "string",
  "phase": "thesis" | "antithesis" | "synthesis" | "resolved",
  "created_at": "ISO timestamp",
  "transcript": [...],
  "synthesis_round": int,
  "resolution": {...} (if resolved),
  "max_synthesis_rounds": int
}

If agent_id provided (finds all sessions for agent):
{
  "success": true,
  "agent_id": "string",
  "session_count": int,
  "sessions": [session_dict, ...]
}

RELATED TOOLS:
- request_dialectic_review: Start session
- submit_thesis/antithesis/synthesis: Progress session

EXAMPLE REQUESTS:
{"session_id": "abc123"}  # Get specific session
{"agent_id": "my_agent"}  # Find all sessions for agent

DEPENDENCIES:
- Requires: session_id OR agent_id (at least one)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Dialectic session ID (optional if agent_id provided)"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent ID to find sessions for (optional if session_id provided). Finds sessions where agent is paused_agent_id or reviewer_agent_id"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="self_recovery",
            description="""Allow agent to recover without reviewer (for when no reviewers available). Tier 2.3 recovery option.

USE CASES:
- No reviewers available
- Single-agent recovery needed
- Fast recovery without peer coordination
- System-generated antithesis based on metrics

RETURNS:
{
  "success": true,
  "message": "Agent resumed via self-recovery",
  "agent_id": "string",
  "action": "resumed",
  "thesis": {
    "root_cause": "string",
    "proposed_conditions": ["string"],
    "reasoning": "string"
  },
  "system_antithesis": {
    "concerns": ["string"],
    "observed_metrics": {...},
    "reasoning": "string"
  },
  "merged_resolution": {
    "conditions": ["string"],
    "root_cause": "string",
    "reasoning": "string"
  },
  "metrics": {...},
  "note": "string"
}

RELATED TOOLS:
- direct_resume_if_safe: Use for simple cases (Tier 1)
- smart_dialectic_review: Use for auto-progressed recovery (Tier 2)
- request_dialectic_review: Use for full peer review (Tier 2)

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "api_key": "gk_live_...",
  "root_cause": "Got stuck in loop",
  "proposed_conditions": ["Monitor for 24h", "Reduce complexity"],
  "reasoning": "No reviewers available - using self-recovery"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Agent resumed via self-recovery",
  "agent_id": "test_agent_001",
  "action": "resumed",
  "thesis": {...},
  "system_antithesis": {...},
  "merged_resolution": {...},
  "metrics": {...}
}

DEPENDENCIES:
- Requires: agent_id, api_key
- Optional: root_cause, proposed_conditions, reasoning
- Safety checks: Same as direct_resume_if_safe (coherence > 0.40, risk < 0.60, no void)
- Workflow: 1. Submit thesis 2. System generates antithesis 3. Auto-merge synthesis 4. Resume if safe""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "API key for authentication (required)"
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "Agent's understanding of what happened"
                    },
                    "proposed_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Conditions for resumption"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation"
                    }
                },
                "required": ["agent_id", "api_key"]
            }
        ),
        Tool(
            name="store_knowledge_graph",
            description="""Store knowledge discovery in graph - fast, non-blocking, transparent.

USE CASES:
- Store bugs found during code review
- Record insights from exploration
- Log improvements discovered
- Track patterns observed

PERFORMANCE:
- ~0.01ms (35,000x faster than file-based)
- Non-blocking async operations
- Claude Desktop compatible

RETURNS:
{
  "success": true,
  "message": "Discovery stored for agent 'agent_id'",
  "discovery_id": "timestamp",
  "discovery": {...},
  "related_discoveries": [...] (if auto_link_related=true)
}

RELATED TOOLS:
- search_knowledge_graph: Query stored knowledge
- list_knowledge_graph: See statistics
- find_similar_discoveries_graph: Find similar by tags

EXAMPLE REQUEST:
{
  "agent_id": "my_agent",
  "api_key": "your_api_key",  # Required for high/critical severity discoveries
  "discovery_type": "bug_found",
  "summary": "Found authentication bypass",
  "details": "Details here...",
  "tags": ["security", "authentication"],
  "severity": "high",
  "auto_link_related": true  # Default: true - automatically links to related discoveries
}

SECURITY NOTE:
- Low/medium severity: api_key optional
- High/critical severity: api_key REQUIRED (prevents knowledge graph poisoning)

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Discovery stored for agent 'my_agent'",
  "discovery_id": "2025-11-28T12:00:00",
  "discovery": {
    "id": "2025-11-28T12:00:00",
    "agent_id": "my_agent",
    "type": "bug_found",
    "summary": "Found authentication bypass",
    "tags": ["security", "authentication"],
    "severity": "high"
  }
}

DEPENDENCIES:
- Requires: agent_id, discovery_type, summary
- Optional: details, tags, severity, auto_link_related""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "discovery_type": {
                        "type": "string",
                        "enum": ["bug_found", "insight", "pattern", "improvement", "question"],
                        "description": "Type of discovery"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of discovery"
                    },
                    "details": {
                        "type": "string",
                        "description": "Detailed description (optional)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization and search"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Severity level (optional)"
                    },
                    "related_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Related file paths (optional)"
                    },
                    "auto_link_related": {
                        "type": "boolean",
                        "description": "Automatically find and link similar discoveries (default: false)",
                        "default": False
                    }
                },
                "required": ["agent_id", "discovery_type", "summary"]
            }
        ),
        Tool(
            name="search_knowledge_graph",
            description="""Search knowledge graph - fast indexed queries, full transparency.

USE CASES:
- Find discoveries by tags
- Search by agent, type, severity
- Query system knowledge
- Learn from past discoveries

PERFORMANCE:
- O(indexes) not O(n) - scales logarithmically
- ~0.1ms for typical queries
- Non-blocking async operations

RETURNS:
{
  "success": true,
  "discoveries": [...],
  "count": int,
  "message": "Found N discovery(ies)"
}

RELATED TOOLS:
- list_knowledge_graph: See statistics
- get_knowledge_graph: Get agent's knowledge
- find_similar_discoveries_graph: Find similar by tags

EXAMPLE REQUEST:
{
  "tags": ["security", "bug"],
  "discovery_type": "bug_found",
  "severity": "high",
  "limit": 10
}

EXAMPLE RESPONSE:
{
  "success": true,
  "discoveries": [
    {
      "id": "2025-11-28T12:00:00",
      "agent_id": "agent_1",
      "type": "bug_found",
      "summary": "Found authentication bypass",
      "tags": ["security", "bug"],
      "severity": "high"
    }
  ],
  "count": 1,
  "message": "Found 1 discovery(ies)"
}

DEPENDENCIES:
- All parameters optional (filters)
- Returns all discoveries if no filters""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Filter by agent ID (optional)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (must have ALL tags)"
                    },
                    "discovery_type": {
                        "type": "string",
                        "enum": ["bug_found", "insight", "pattern", "improvement", "question"],
                        "description": "Filter by discovery type"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Filter by severity"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "resolved", "archived"],
                        "description": "Filter by status"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 100)",
                        "default": 100
                    }
                }
            }
        ),
        Tool(
            name="get_knowledge_graph",
            description="""Get all knowledge for an agent - fast index lookup.

USE CASES:
- Retrieve agent's complete knowledge record
- See what agent has learned
- Review agent's discoveries

PERFORMANCE:
- O(1) index lookup
- Fast, non-blocking

RETURNS:
{
  "success": true,
  "agent_id": "string",
  "discoveries": [...],
  "count": int
}

RELATED TOOLS:
- search_knowledge_graph: Search across agents
- list_knowledge_graph: See statistics

EXAMPLE REQUEST:
{
  "agent_id": "my_agent",
  "limit": 50
}

EXAMPLE RESPONSE:
{
  "success": true,
  "agent_id": "my_agent",
  "discoveries": [...],
  "count": 10
}

DEPENDENCIES:
- Requires: agent_id""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of discoveries to return"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="list_knowledge_graph",
            description="""List knowledge graph statistics - full transparency.

USE CASES:
- See what system knows
- Check knowledge graph health
- View discovery statistics
- Monitor knowledge growth

PERFORMANCE:
- O(1) - instant statistics
- Non-blocking

RETURNS:
{
  "success": true,
  "stats": {
    "total_discoveries": int,
    "by_agent": {...},
    "by_type": {...},
    "by_status": {...},
    "total_tags": int,
    "total_agents": int
  },
  "message": "Knowledge graph contains N discoveries from M agents"
}

RELATED TOOLS:
- search_knowledge_graph: Query discoveries
- get_knowledge_graph: Get agent's knowledge

EXAMPLE REQUEST:
{}

EXAMPLE RESPONSE:
{
  "success": true,
  "stats": {
    "total_discoveries": 252,
    "by_agent": {"agent_1": 10, "agent_2": 5},
    "by_type": {"bug_found": 10, "insight": 200},
    "by_status": {"open": 200, "resolved": 50},
    "total_tags": 45,
    "total_agents": 27
  },
  "message": "Knowledge graph contains 252 discoveries from 27 agents"
}

DEPENDENCIES:
- No parameters required""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="update_discovery_status_graph",
            description="""Update discovery status - fast graph update.

USE CASES:
- Mark discovery as resolved
- Archive old discoveries
- Update discovery status

PERFORMANCE:
- O(1) graph update
- Fast, non-blocking

RETURNS:
{
  "success": true,
  "message": "Discovery 'id' status updated to 'status'",
  "discovery": {...}
}

RELATED TOOLS:
- store_knowledge_graph: Store new discoveries
- search_knowledge_graph: Find discoveries

EXAMPLE REQUEST:
{
  "discovery_id": "2025-11-28T12:00:00",
  "status": "resolved"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "message": "Discovery '2025-11-28T12:00:00' status updated to 'resolved'",
  "discovery": {
    "id": "2025-11-28T12:00:00",
    "status": "resolved",
    "resolved_at": "2025-11-28T15:00:00"
  }
}

DEPENDENCIES:
- Requires: discovery_id, status""",
            inputSchema={
                "type": "object",
                "properties": {
                    "discovery_id": {
                        "type": "string",
                        "description": "Discovery ID (timestamp)"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "resolved", "archived", "disputed"],
                        "description": "New status (disputed: discovery is being disputed via dialectic)"
                    }
                },
                "required": ["discovery_id", "status"]
            }
        ),
        Tool(
            name="find_similar_discoveries_graph",
            description="""Find similar discoveries by tag overlap - fast tag-based search.

USE CASES:
- Find related discoveries
- Check for duplicates
- Discover patterns
- Learn from similar cases

PERFORMANCE:
- O(tags) not O(n) - uses tag index
- ~0.1ms for similarity search
- No brute force scanning

RETURNS:
{
  "success": true,
  "discovery_id": "string",
  "similar_discoveries": [...],
  "count": int,
  "message": "Found N similar discovery(ies)"
}

RELATED TOOLS:
- store_knowledge_graph: Store discoveries
- search_knowledge_graph: Search by filters

EXAMPLE REQUEST:
{
  "discovery_id": "2025-11-28T12:00:00",
  "limit": 5
}

EXAMPLE RESPONSE:
{
  "success": true,
  "discovery_id": "2025-11-28T12:00:00",
  "similar_discoveries": [
    {
      "id": "2025-11-27T10:00:00",
      "summary": "Similar bug found",
      "tags": ["security", "authentication"],
      "overlap_score": 2
    }
  ],
  "count": 1,
  "message": "Found 1 similar discovery(ies)"
}

DEPENDENCIES:
- Requires: discovery_id""",
            inputSchema={
                "type": "object",
                "properties": {
                    "discovery_id": {
                        "type": "string",
                        "description": "Discovery ID to find similar discoveries for"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of similar discoveries (default: 10)",
                        "default": 10
                    }
                },
                "required": ["discovery_id"]
            }
        ),
        Tool(
            name="smart_dialectic_review",
            description="""Smart dialectic that auto-progresses when possible. Reduces manual steps by 50-70% compared to full dialectic.

USE CASES:
- Complex recovery with auto-progression
- Reduce coordination overhead
- Auto-generate thesis from agent state
- Auto-merge synthesis if compatible

RETURNS:
{
  "success": true,
  "session_id": "string",
  "paused_agent_id": "string",
  "reviewer_agent_id": "string",
  "phase": "string",
  "auto_progressed": boolean,
  "thesis_submitted": boolean,
  "next_step": "string",
  "created_at": "ISO timestamp",
  "note": "string"
}

RELATED TOOLS:
- direct_resume_if_safe: Use for simple cases (Tier 1)
- self_recovery: Use when no reviewers available (Tier 2.3)
- request_dialectic_review: Use for full manual dialectic (Tier 2)

EXAMPLE REQUEST:
{
  "agent_id": "test_agent_001",
  "api_key": "gk_live_...",
  "auto_progress": true,
  "reason": "Circuit breaker triggered"
}

EXAMPLE RESPONSE:
{
  "success": true,
  "session_id": "abc123",
  "paused_agent_id": "test_agent_001",
  "reviewer_agent_id": "reviewer_002",
  "phase": "antithesis",
  "auto_progressed": true,
  "thesis_submitted": true,
  "next_step": "Reviewer should submit antithesis",
  "created_at": "2025-11-26T20:00:00"
}

DEPENDENCIES:
- Requires: agent_id, api_key
- Optional: reason (auto-generated), root_cause (auto-generated), proposed_conditions (auto-generated), reasoning (auto-generated), auto_progress (default: True)
- Workflow: 1. Auto-generate thesis 2. Reviewer submits antithesis 3. Auto-merge synthesis 4. Execute if safe
- Falls back to self_recovery if no reviewers available""",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "API key for authentication (required)"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for review (optional - auto-generated if not provided)"
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "Root cause (optional - auto-generated from state if not provided)"
                    },
                    "proposed_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Proposed conditions (optional - auto-generated if not provided)"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation (optional - auto-generated if not provided)"
                    },
                    "auto_progress": {
                        "type": "boolean",
                        "description": "Whether to auto-progress through phases (default: True)"
                    }
                },
                "required": ["agent_id", "api_key"]
            }
        ),
    ]


async def inject_lightweight_heartbeat(
    agent_id: str,
    trigger_reason: str,
    activity_summary: dict,
    tracker
) -> None:
    """
    Inject a lightweight governance heartbeat.
    
    Non-blocking, fire-and-forget. Provides visibility without heavy overhead.
    """
    try:
        # Reload metadata to get latest state
        load_metadata()
        
        # Get or create agent metadata (needed for heartbeat)
        if agent_id not in agent_metadata:
            get_or_create_metadata(agent_id)
        
        meta = agent_metadata.get(agent_id)
        if not meta:
            return
        
        # Get API key (required for authenticated update)
        api_key = meta.api_key
        if not api_key:
            # Generate if missing (shouldn't happen, but be safe)
            api_key = generate_api_key()
            meta.api_key = api_key
            save_metadata()
        
        # Call process_agent_update with heartbeat flag
        # This uses the lightweight heartbeat path in the handler
        from src.mcp_handlers.core import handle_process_agent_update
        
        heartbeat_args = {
            'agent_id': agent_id,
            'api_key': api_key,
            'heartbeat': True,
            'trigger_reason': trigger_reason,
            'activity_summary': activity_summary,
            'response_text': f"Auto-heartbeat ({trigger_reason})",
            'complexity': activity_summary.get('average_complexity', 0.5)
        }
        
        # Call heartbeat handler (non-blocking, fire-and-forget)
        await handle_process_agent_update(heartbeat_args)
        
        # Reset activity counters after heartbeat
        tracker.reset_after_governance_update(agent_id)
        
    except Exception as e:
        # Don't fail if heartbeat injection fails - this is best-effort visibility
        print(f"[HEARTBEAT] Error injecting heartbeat for {agent_id}: {e}", file=sys.stderr)


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> Sequence[TextContent]:
    """Handle tool calls from MCP client"""
    # Update process heartbeat on every tool call to mark this process as active
    # This prevents other clients from killing this process during cleanup
    process_mgr.write_heartbeat()

    if arguments is None:
        arguments = {}

    # Track activity for agent and auto-inject lightweight heartbeats
    agent_id = arguments.get('agent_id')
    if agent_id and HEARTBEAT_CONFIG.enabled:
        should_trigger, trigger_reason = activity_tracker.track_tool_call(agent_id, name)

        # Auto-inject lightweight heartbeat if threshold reached
        if should_trigger and name != "process_agent_update":
            try:
                # Get activity summary for heartbeat
                activity = activity_tracker.get_or_create(agent_id)
                activity_summary = {
                    "conversation_turns": activity.conversation_turns,
                    "tool_calls": activity.tool_calls,
                    "files_modified": activity.files_modified,
                    "average_complexity": (
                        activity.cumulative_complexity / len(activity.complexity_samples)
                        if activity.complexity_samples else 0.5
                    ),
                    "duration_minutes": (
                        (datetime.now() - datetime.fromisoformat(activity.session_start))
                        .total_seconds() / 60
                        if activity.session_start else 0
                    )
                }
                
                # Inject lightweight heartbeat (non-blocking)
                import asyncio
                asyncio.create_task(
                    inject_lightweight_heartbeat(agent_id, trigger_reason, activity_summary, activity_tracker)
                )
                
                print(f"[HEARTBEAT] Auto-triggered for {agent_id}: {trigger_reason}", file=sys.stderr)
            except Exception as e:
                # Don't fail tool execution if heartbeat injection fails
                print(f"[HEARTBEAT] Warning: Could not inject heartbeat: {e}", file=sys.stderr)

    # Track tool usage for analytics
    try:
        from src.tool_usage_tracker import get_tool_usage_tracker
        usage_tracker = get_tool_usage_tracker()
        usage_tracker.log_tool_call(tool_name=name, agent_id=agent_id, success=True)
    except Exception:
        # Don't fail tool execution if usage tracking fails
        pass

    # All handlers are now in the registry - dispatch to handler
    success = True
    error_type = None
    try:
        from src.mcp_handlers import dispatch_tool
        result = await dispatch_tool(name, arguments)
        if result is not None:
            return result
        # If None returned, handler not found - return error
        error_response = [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": f"Unknown tool: {name}"
            }, indent=2)
        )]
        # Log failed tool call
        try:
            from src.tool_usage_tracker import get_tool_usage_tracker
            get_tool_usage_tracker().log_tool_call(tool_name=name, agent_id=agent_id, success=False, error_type="unknown_tool")
        except Exception:
            pass
        return error_response
    except ImportError:
        # Handlers module not available - return error
        error_response = [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": f"Handler registry not available. Tool '{name}' cannot be processed."
            }, indent=2)
        )]
        # Log failed tool call
        try:
            from src.tool_usage_tracker import get_tool_usage_tracker
            get_tool_usage_tracker().log_tool_call(tool_name=name, agent_id=agent_id, success=False, error_type="import_error")
        except Exception:
            pass
        return error_response
    except Exception as e:
        # SECURITY: Log full traceback internally but sanitize for client
        import traceback
        print(f"[UNITARES MCP] Tool '{name}' execution error: {e}", file=sys.stderr)
        print(f"[UNITARES MCP] Full traceback:\n{traceback.format_exc()}", file=sys.stderr)
        
        # Return sanitized error message (no internal structure)
        from src.mcp_handlers.utils import error_response as create_error_response
        sanitized_error = create_error_response(
            f"Error executing tool '{name}': {str(e)}",
            recovery={
                "action": "Check tool parameters and try again",
                "related_tools": ["health_check", "list_tools"],
                "workflow": "1. Verify tool parameters 2. Check system health 3. Retry with simpler parameters"
            }
        )
        # Log failed tool call
        try:
            from src.tool_usage_tracker import get_tool_usage_tracker
            get_tool_usage_tracker().log_tool_call(tool_name=name, agent_id=agent_id, success=False, error_type="execution_error")
        except Exception:
            pass
        return [sanitized_error]


async def periodic_lock_cleanup(interval_seconds: int = 300):
    """
    Background task that periodically cleans up stale locks.
    Runs every interval_seconds (default: 5 minutes).
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            # Clean up stale locks (older than 60 seconds)
            cleanup_result = cleanup_stale_state_locks(
                project_root=project_root, 
                max_age_seconds=60.0, 
                dry_run=False
            )
            if cleanup_result['cleaned'] > 0:
                print(f"[UNITARES MCP] Periodic cleanup: Removed {cleanup_result['cleaned']} stale lock(s)", file=sys.stderr)
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            break
        except Exception as e:
            # Log error but continue running
            print(f"[UNITARES MCP] Warning: Periodic lock cleanup error: {e}", file=sys.stderr)


async def main():
    """Main entry point for MCP server"""
    # Start background cleanup task
    cleanup_task = asyncio.create_task(periodic_lock_cleanup(interval_seconds=300))
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Cancel background task when server shuts down
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())

