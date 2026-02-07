"""
Tests for src/mcp_handlers/pattern_helpers.py — Code change detection.

detect_code_changes is pure. Other functions need mocked pattern_tracker.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.mcp_handlers.pattern_helpers import (
    detect_code_changes,
    record_hypothesis_if_needed,
    check_untested_hypotheses,
    mark_hypothesis_tested,
)


# ============================================================================
# detect_code_changes (pure function)
# ============================================================================

class TestDetectCodeChanges:

    def test_search_replace_python(self):
        result = detect_code_changes("search_replace", {"file_path": "src/main.py"})
        assert result is not None
        assert result["change_type"] == "code_edit"
        assert "src/main.py" in result["files_changed"]
        assert result["tool"] == "search_replace"

    def test_write_typescript(self):
        result = detect_code_changes("write", {"file_path": "src/app.ts"})
        assert result is not None
        assert "src/app.ts" in result["files_changed"]

    def test_edit_notebook(self):
        result = detect_code_changes("edit_notebook", {"target_notebook": "analysis.py"})
        assert result is not None

    def test_non_code_tool(self):
        result = detect_code_changes("read_file", {"file_path": "src/main.py"})
        assert result is None

    def test_non_code_file(self):
        result = detect_code_changes("write", {"file_path": "README.md"})
        assert result is None

    def test_json_file(self):
        result = detect_code_changes("write", {"file_path": "config.json"})
        assert result is None

    def test_no_file_path(self):
        result = detect_code_changes("search_replace", {"content": "something"})
        assert result is None

    def test_multiple_extensions(self):
        for ext in [".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c", ".h"]:
            result = detect_code_changes("write", {"file_path": f"test{ext}"})
            assert result is not None, f"Failed for extension {ext}"

    def test_list_file_paths(self):
        result = detect_code_changes("search_replace", {"file_path": ["a.py", "b.js"]})
        assert result is not None
        assert len(result["files_changed"]) == 2

    def test_mixed_code_and_non_code(self):
        result = detect_code_changes("search_replace", {"file_path": ["a.py", "b.md"]})
        assert result is not None
        assert result["files_changed"] == ["a.py"]

    def test_all_non_code_in_list(self):
        result = detect_code_changes("search_replace", {"file_path": ["a.md", "b.txt"]})
        assert result is None

    def test_empty_arguments(self):
        result = detect_code_changes("write", {})
        assert result is None


# ============================================================================
# record_hypothesis_if_needed (needs mocked tracker)
# ============================================================================

class TestRecordHypothesisIfNeeded:

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_records_for_code_change(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        record_hypothesis_if_needed("agent-123", "write", {"file_path": "main.py"})
        mock_tracker.record_hypothesis.assert_called_once()
        call_kwargs = mock_tracker.record_hypothesis.call_args[1]
        assert call_kwargs["agent_id"] == "agent-123"
        assert "main.py" in call_kwargs["files_changed"]

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_skips_for_non_code(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        record_hypothesis_if_needed("agent-123", "read_file", {"file_path": "main.py"})
        mock_tracker.record_hypothesis.assert_not_called()


# ============================================================================
# check_untested_hypotheses (needs mocked tracker)
# ============================================================================

class TestCheckUntestedHypotheses:

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_returns_message_when_untested(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_tracker.check_untested_hypotheses.return_value = {"message": "You should test main.py"}
        mock_get_tracker.return_value = mock_tracker

        result = check_untested_hypotheses("agent-123")
        assert result == "You should test main.py"

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_returns_none_when_no_untested(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_tracker.check_untested_hypotheses.return_value = None
        mock_get_tracker.return_value = mock_tracker

        result = check_untested_hypotheses("agent-123")
        assert result is None


# ============================================================================
# mark_hypothesis_tested (needs mocked tracker)
# ============================================================================

class TestMarkHypothesisTested:

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_marks_for_test_tool(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        mark_hypothesis_tested("agent-123", "run_test", {"file_path": "test_main.py"})
        mock_tracker.mark_hypothesis_tested.assert_called_once_with("agent-123", ["test_main.py"])

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_marks_for_verify_in_args(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        mark_hypothesis_tested("agent-123", "some_tool", {"file_path": "main.py", "command": "verify output"})
        mock_tracker.mark_hypothesis_tested.assert_called_once()

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_skips_for_non_testing_tool(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        mark_hypothesis_tested("agent-123", "write", {"file_path": "main.py"})
        mock_tracker.mark_hypothesis_tested.assert_not_called()

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_skips_when_no_file_paths(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        mark_hypothesis_tested("agent-123", "run_test", {"command": "pytest"})
        mock_tracker.mark_hypothesis_tested.assert_not_called()

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_extracts_multiple_path_keys(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        mark_hypothesis_tested("agent-123", "check_file", {
            "file_path": "a.py",
            "target_file": "b.py",
            "path": "c.py",
            "file": "d.py",
        })
        call_args = mock_tracker.mark_hypothesis_tested.call_args[0]
        assert len(call_args[1]) == 4

    @patch("src.mcp_handlers.pattern_helpers.get_pattern_tracker")
    def test_handles_list_file_paths(self, mock_get_tracker):
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker

        mark_hypothesis_tested("agent-123", "test_files", {"file_path": ["a.py", "b.py"]})
        call_args = mock_tracker.mark_hypothesis_tested.call_args[0]
        assert "a.py" in call_args[1]
        assert "b.py" in call_args[1]
