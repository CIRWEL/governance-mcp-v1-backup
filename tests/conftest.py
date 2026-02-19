"""
Pytest configuration and fixtures for governance-mcp-v1 tests.
"""
import pytest
import warnings
import sys
from unittest.mock import AsyncMock

# Filter ResourceWarnings globally before any imports
warnings.filterwarnings("ignore", category=ResourceWarning)


def pytest_configure(config):
    """Configure pytest to filter ResourceWarnings from SQLite."""
    # This catches warnings during collection phase
    warnings.filterwarnings(
        "ignore",
        message="unclosed database",
        category=ResourceWarning
    )


@pytest.fixture(autouse=True)
def _isolate_db_backend(monkeypatch):
    """
    Prevent tests from accidentally connecting to production PostgreSQL.

    Sets a mock DB backend as the get_db() singleton, so any code path that
    reaches get_db() without explicit mocking gets a safe no-op mock instead
    of a real database connection. This prevents ghost agents from being
    created in the production database during test runs.

    Tests that need real DB access (e.g. test_postgres_backend_integration.py)
    create their own backend instances directly, bypassing get_db().

    Tests that already mock at higher levels (agent_storage, get_db patches)
    are unaffected — their mocks intercept before reaching the singleton.
    """
    import src.db as db_module
    import src.agent_storage as storage_module

    mock_backend = AsyncMock()
    # Identity operations
    mock_backend.get_identity.return_value = None
    mock_backend.get_identity_by_id.return_value = None
    mock_backend.upsert_identity.return_value = 1
    mock_backend.upsert_agent.return_value = True
    mock_backend.update_agent_fields.return_value = True
    mock_backend.list_identities.return_value = []
    mock_backend.update_identity_status.return_value = True
    mock_backend.update_identity_metadata.return_value = True
    mock_backend.verify_api_key.return_value = True
    mock_backend.get_agent_label.return_value = None
    mock_backend.find_agent_by_label.return_value = None
    # Session operations
    mock_backend.create_session.return_value = True
    mock_backend.get_session.return_value = None
    mock_backend.update_session_activity.return_value = True
    mock_backend.end_session.return_value = True
    mock_backend.get_active_sessions_for_identity.return_value = []
    mock_backend.cleanup_expired_sessions.return_value = 0
    # State operations
    mock_backend.record_agent_state.return_value = 1
    mock_backend.get_latest_agent_state.return_value = None
    mock_backend.get_agent_state_history.return_value = []
    # Audit/tool operations
    mock_backend.append_audit_event.return_value = True
    mock_backend.query_audit_events.return_value = []
    mock_backend.search_audit_events.return_value = []
    mock_backend.append_tool_usage.return_value = True
    mock_backend.query_tool_usage.return_value = []
    # Calibration
    mock_backend.get_calibration.return_value = {}
    mock_backend.update_calibration.return_value = True
    # Graph
    mock_backend.graph_query.return_value = []
    mock_backend.graph_available.return_value = False
    # Dialectic
    mock_backend.create_dialectic_session.return_value = {"session_id": "test", "created": True}
    mock_backend.get_dialectic_session.return_value = None
    mock_backend.get_dialectic_session_by_agent.return_value = None
    mock_backend.get_all_active_dialectic_sessions_for_agent.return_value = []
    mock_backend.update_dialectic_session_phase.return_value = True
    mock_backend.update_dialectic_session_reviewer.return_value = True
    mock_backend.add_dialectic_message.return_value = 1
    mock_backend.resolve_dialectic_session.return_value = True
    mock_backend.is_agent_in_active_dialectic_session.return_value = False
    mock_backend.get_pending_dialectic_sessions.return_value = []
    # Health
    mock_backend.init.return_value = None
    mock_backend.close.return_value = None
    mock_backend.health_check.return_value = {"status": "ok", "backend": "test_mock"}

    # Set mock as the singleton — ALL get_db() calls return this
    monkeypatch.setattr(db_module, "_db_instance", mock_backend)
    # Clear the db-ready cache so _ensure_db_ready() doesn't skip init
    storage_module._db_ready_cache.clear()

    yield mock_backend

    # monkeypatch auto-restores _db_instance on teardown
    storage_module._db_ready_cache.clear()


@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary database path for tests."""
    db_path = tmp_path / "test.db"
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()
