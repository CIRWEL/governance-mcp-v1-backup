"""
Extended tests for src/process_cleanup.py - Zombie cleanup and active process listing.

Tests cleanup_zombies and get_active_processes with mocked psutil.
"""

import os
import time
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.process_cleanup import ProcessManager


# ============================================================================
# cleanup_zombies
# ============================================================================

class TestCleanupZombies:

    def test_returns_empty_without_psutil(self, tmp_path):
        """Without psutil, should return empty list."""
        pm = ProcessManager(pid_dir=tmp_path)
        with patch('src.process_cleanup.PSUTIL_AVAILABLE', False):
            result = pm.cleanup_zombies()
            assert result == []

    def test_skips_current_process(self, tmp_path):
        """Should never terminate the current process."""
        pm = ProcessManager(pid_dir=tmp_path)

        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': os.getpid(),
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 100,
        }

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception

            result = pm.cleanup_zombies()
            assert result == []

    def test_terminates_stale_heartbeat(self, tmp_path):
        """Should terminate process with stale heartbeat."""
        pm = ProcessManager(pid_dir=tmp_path)
        fake_pid = 99998

        # Create stale heartbeat
        heartbeat = tmp_path / f"heartbeat_{fake_pid}.txt"
        heartbeat.write_text(str(time.time() - 600))  # 10 min old

        mock_proc_info = MagicMock()
        mock_proc_info.info = {
            'pid': fake_pid,
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 600,
        }

        mock_process = MagicMock()

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc_info]
            mock_psutil.Process.return_value = mock_process
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception
            mock_psutil.TimeoutExpired = Exception

            result = pm.cleanup_zombies(max_age_seconds=300)
            assert fake_pid in result
            mock_process.terminate.assert_called_once()

    def test_terminates_no_heartbeat(self, tmp_path):
        """Should terminate process with no heartbeat file."""
        pm = ProcessManager(pid_dir=tmp_path)
        fake_pid = 99997

        mock_proc_info = MagicMock()
        mock_proc_info.info = {
            'pid': fake_pid,
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 100,
        }

        mock_process = MagicMock()

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc_info]
            mock_psutil.Process.return_value = mock_process
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception
            mock_psutil.TimeoutExpired = Exception

            result = pm.cleanup_zombies()
            assert fake_pid in result

    def test_handles_already_dead_process(self, tmp_path):
        """Should handle NoSuchProcess gracefully."""
        pm = ProcessManager(pid_dir=tmp_path)
        fake_pid = 99996

        mock_proc_info = MagicMock()
        mock_proc_info.info = {
            'pid': fake_pid,
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 100,
        }

        # Create heartbeat to clean up
        heartbeat = tmp_path / f"heartbeat_{fake_pid}.txt"
        heartbeat.write_text("invalid")

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            # Process dies before we can terminate it
            class FakeNoSuchProcess(Exception):
                pass
            mock_psutil.NoSuchProcess = FakeNoSuchProcess
            mock_psutil.AccessDenied = Exception
            mock_psutil.TimeoutExpired = Exception
            mock_psutil.process_iter.return_value = [mock_proc_info]
            mock_psutil.Process.side_effect = FakeNoSuchProcess()

            result = pm.cleanup_zombies()
            # Heartbeat file should be cleaned up even though process is dead
            assert not heartbeat.exists()

    def test_keeps_fresh_heartbeat(self, tmp_path):
        """Should not terminate process with fresh heartbeat."""
        pm = ProcessManager(pid_dir=tmp_path)
        fake_pid = 99995

        # Create fresh heartbeat
        heartbeat = tmp_path / f"heartbeat_{fake_pid}.txt"
        heartbeat.write_text(str(time.time()))

        mock_proc_info = MagicMock()
        mock_proc_info.info = {
            'pid': fake_pid,
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 10,
        }

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc_info]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception

            result = pm.cleanup_zombies(max_age_seconds=300)
            assert fake_pid not in result

    def test_ignores_non_mcp_processes(self, tmp_path):
        """Should only target mcp_server_std.py processes."""
        pm = ProcessManager(pid_dir=tmp_path)

        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 12345,
            'name': 'python',
            'cmdline': ['python', 'some_other_script.py'],
            'create_time': time.time(),
        }

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception

            result = pm.cleanup_zombies()
            assert result == []


# ============================================================================
# get_active_processes
# ============================================================================

class TestGetActiveProcesses:

    def test_returns_empty_without_psutil(self, tmp_path):
        pm = ProcessManager(pid_dir=tmp_path)
        with patch('src.process_cleanup.PSUTIL_AVAILABLE', False):
            result = pm.get_active_processes()
            assert result == []

    def test_returns_process_info(self, tmp_path):
        pm = ProcessManager(pid_dir=tmp_path)

        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 54321,
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 60,
            'status': 'running',
        }

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception

            result = pm.get_active_processes()
            assert len(result) == 1
            assert result[0]['pid'] == 54321
            assert result[0]['status'] == 'running'
            assert 'uptime' in result[0]
            assert 'has_heartbeat' in result[0]

    def test_includes_heartbeat_age(self, tmp_path):
        pm = ProcessManager(pid_dir=tmp_path)

        # Create heartbeat
        heartbeat = tmp_path / "heartbeat_54320.txt"
        heartbeat.write_text(str(time.time() - 5))

        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 54320,
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 60,
            'status': 'running',
        }

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception

            result = pm.get_active_processes()
            assert len(result) == 1
            assert result[0]['has_heartbeat'] is True
            assert result[0]['heartbeat_age_seconds'] is not None
            assert result[0]['heartbeat_age_seconds'] >= 5

    def test_marks_current_process(self, tmp_path):
        pm = ProcessManager(pid_dir=tmp_path)

        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': os.getpid(),
            'name': 'python',
            'cmdline': ['python', 'mcp_server_std.py'],
            'create_time': time.time() - 10,
            'status': 'running',
        }

        with patch('src.process_cleanup.PSUTIL_AVAILABLE', True), \
             patch('src.process_cleanup.psutil') as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = Exception
            mock_psutil.AccessDenied = Exception

            result = pm.get_active_processes()
            assert result[0]['is_current'] is True
