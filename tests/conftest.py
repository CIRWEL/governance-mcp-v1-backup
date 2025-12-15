"""
Pytest configuration and fixtures for governance-mcp-v1 tests.
"""
import pytest
import warnings
import sys

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


@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary database path for tests."""
    db_path = tmp_path / "test.db"
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()
