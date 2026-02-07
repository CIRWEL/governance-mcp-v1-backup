"""
Tests for src/state_locking.py - State lock manager and process liveness checking.

Tests is_process_alive, StateLockManager init, stale lock cleanup,
and synchronous lock acquisition.
"""

import fcntl
import json
import os
import time
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.state_locking import is_process_alive, StateLockManager


# ============================================================================
# is_process_alive
# ============================================================================

class TestIsProcessAlive:

    def test_current_process_alive(self):
        assert is_process_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        assert is_process_alive(999999999) is False

    def test_negative_pid(self):
        # os.kill(-1, 0) sends to all processes in process group on some platforms
        # so the result is platform-dependent. Just verify no crash.
        result = is_process_alive(-1)
        assert isinstance(result, bool)

    def test_zero_pid(self):
        result = is_process_alive(0)
        assert isinstance(result, bool)


# ============================================================================
# StateLockManager - init
# ============================================================================

class TestStateLockManagerInit:

    def test_creates_lock_dir(self, tmp_path):
        lock_dir = tmp_path / "locks"
        mgr = StateLockManager(lock_dir=lock_dir)
        assert lock_dir.exists()

    def test_auto_cleanup_default(self, tmp_path):
        mgr = StateLockManager(lock_dir=tmp_path)
        assert mgr.auto_cleanup_stale is True

    def test_stale_threshold_default(self, tmp_path):
        mgr = StateLockManager(lock_dir=tmp_path)
        assert mgr.stale_threshold == 60.0

    def test_custom_stale_threshold(self, tmp_path):
        mgr = StateLockManager(lock_dir=tmp_path, stale_threshold=120.0)
        assert mgr.stale_threshold == 120.0

    def test_auto_cleanup_disabled(self, tmp_path):
        mgr = StateLockManager(lock_dir=tmp_path, auto_cleanup_stale=False)
        assert mgr.auto_cleanup_stale is False


# ============================================================================
# _check_and_clean_stale_lock
# ============================================================================

class TestCheckAndCleanStaleLock:

    def test_nonexistent_lock_returns_false(self, tmp_path):
        mgr = StateLockManager(lock_dir=tmp_path)
        result = mgr._check_and_clean_stale_lock(tmp_path / "missing.lock")
        assert result is False

    def test_unheld_lock_cleaned(self, tmp_path):
        """Lock file that is NOT held by any process should be cleaned."""
        mgr = StateLockManager(lock_dir=tmp_path)
        lock_file = tmp_path / "stale.lock"
        lock_file.write_text(json.dumps({
            "pid": 999999999,
            "timestamp": time.time() - 300
        }))

        result = mgr._check_and_clean_stale_lock(lock_file)
        assert result is True
        assert not lock_file.exists()

    def test_corrupted_json_cleaned(self, tmp_path):
        """Lock file with corrupted JSON should be cleaned if not held."""
        mgr = StateLockManager(lock_dir=tmp_path)
        lock_file = tmp_path / "corrupt.lock"
        lock_file.write_text("not valid json {{{")

        result = mgr._check_and_clean_stale_lock(lock_file)
        assert result is True
        assert not lock_file.exists()

    def test_empty_lock_cleaned(self, tmp_path):
        """Empty lock file should be cleaned if not held."""
        mgr = StateLockManager(lock_dir=tmp_path)
        lock_file = tmp_path / "empty.lock"
        lock_file.write_text("")

        result = mgr._check_and_clean_stale_lock(lock_file)
        assert result is True
        assert not lock_file.exists()

    def test_lock_with_no_pid_cleaned(self, tmp_path):
        """Lock without PID should be cleaned if not held."""
        mgr = StateLockManager(lock_dir=tmp_path)
        lock_file = tmp_path / "no_pid.lock"
        lock_file.write_text(json.dumps({"timestamp": time.time()}))

        result = mgr._check_and_clean_stale_lock(lock_file)
        assert result is True
        assert not lock_file.exists()


# ============================================================================
# acquire_agent_lock - sync
# ============================================================================

class TestAcquireAgentLock:

    def test_acquire_and_release(self, tmp_path):
        """Should acquire lock and release on context exit."""
        mgr = StateLockManager(lock_dir=tmp_path)

        with mgr.acquire_agent_lock("test_agent", timeout=2.0, max_retries=1):
            lock_file = tmp_path / "test_agent.lock"
            assert lock_file.exists()
            # Read lock info
            with open(lock_file, 'r') as f:
                data = json.loads(f.read())
            assert data["pid"] == os.getpid()
            assert data["agent_id"] == "test_agent"

    def test_lock_released_after_context(self, tmp_path):
        """Lock should be released after context manager exits."""
        mgr = StateLockManager(lock_dir=tmp_path)

        with mgr.acquire_agent_lock("release_test", timeout=2.0, max_retries=1):
            pass

        # Should be able to acquire again immediately
        with mgr.acquire_agent_lock("release_test", timeout=2.0, max_retries=1):
            pass

    def test_lock_released_on_exception(self, tmp_path):
        """Lock should be released even if an exception occurs inside."""
        mgr = StateLockManager(lock_dir=tmp_path)

        with pytest.raises(ValueError):
            with mgr.acquire_agent_lock("exc_test", timeout=2.0, max_retries=1):
                raise ValueError("test error")

        # Should be able to acquire again
        with mgr.acquire_agent_lock("exc_test", timeout=2.0, max_retries=1):
            pass

    def test_different_agents_independent(self, tmp_path):
        """Different agent IDs should have independent locks."""
        mgr = StateLockManager(lock_dir=tmp_path)

        with mgr.acquire_agent_lock("agent_A", timeout=2.0, max_retries=1):
            # Should be able to lock agent_B while agent_A is locked
            with mgr.acquire_agent_lock("agent_B", timeout=2.0, max_retries=1):
                assert (tmp_path / "agent_A.lock").exists()
                assert (tmp_path / "agent_B.lock").exists()

    def test_timeout_raises_error(self, tmp_path):
        """Should raise TimeoutError when lock can't be acquired."""
        mgr = StateLockManager(lock_dir=tmp_path, auto_cleanup_stale=False)
        lock_file = tmp_path / "held_agent.lock"

        # Hold a lock using low-level fcntl
        fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            with pytest.raises(TimeoutError):
                with mgr.acquire_agent_lock("held_agent", timeout=0.3, max_retries=1):
                    pass
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_auto_cleanup_stale_before_acquire(self, tmp_path):
        """Stale lock should be cleaned before attempting acquisition."""
        mgr = StateLockManager(lock_dir=tmp_path, auto_cleanup_stale=True)
        lock_file = tmp_path / "stale_agent.lock"

        # Create a stale lock file (no process holding it)
        lock_file.write_text(json.dumps({
            "pid": 999999999,
            "timestamp": time.time() - 300
        }))

        # Should succeed because stale lock gets cleaned
        with mgr.acquire_agent_lock("stale_agent", timeout=2.0, max_retries=2):
            pass


# ============================================================================
# acquire_agent_lock_async
# ============================================================================

class TestAcquireAgentLockAsync:

    @pytest.mark.asyncio
    async def test_async_acquire_and_release(self, tmp_path):
        """Async lock should acquire and release correctly."""
        mgr = StateLockManager(lock_dir=tmp_path)

        async with mgr.acquire_agent_lock_async("async_test", timeout=2.0, max_retries=1):
            lock_file = tmp_path / "async_test.lock"
            assert lock_file.exists()

    @pytest.mark.asyncio
    async def test_async_lock_released_on_exception(self, tmp_path):
        """Async lock should release on exception."""
        mgr = StateLockManager(lock_dir=tmp_path)

        with pytest.raises(ValueError):
            async with mgr.acquire_agent_lock_async("async_exc", timeout=2.0, max_retries=1):
                raise ValueError("async test error")

        # Should be able to acquire again
        async with mgr.acquire_agent_lock_async("async_exc", timeout=2.0, max_retries=1):
            pass

    @pytest.mark.asyncio
    async def test_async_timeout_raises_error(self, tmp_path):
        """Async lock should raise TimeoutError on timeout."""
        mgr = StateLockManager(lock_dir=tmp_path, auto_cleanup_stale=True)
        lock_file = tmp_path / "async_held.lock"

        fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            with pytest.raises(TimeoutError):
                async with mgr.acquire_agent_lock_async("async_held", timeout=0.3, max_retries=1):
                    pass
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
