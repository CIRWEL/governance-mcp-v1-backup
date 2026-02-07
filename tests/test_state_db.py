"""
Tests for src/state_db.py - AgentStateDB SQLite storage.

Tests schema init, save/load/delete/list operations, statistics,
migration, and async wrappers.
"""

import json
import os
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# AgentStateDB - init and schema
# ============================================================================

class TestAgentStateDBInit:

    def test_creates_db_file(self, tmp_path):
        from src.state_db import AgentStateDB
        db_path = tmp_path / "test.db"
        db = AgentStateDB(db_path=db_path)
        assert db_path.exists()

    def test_creates_parent_dirs(self, tmp_path):
        from src.state_db import AgentStateDB
        db_path = tmp_path / "nested" / "dir" / "test.db"
        db = AgentStateDB(db_path=db_path)
        assert db_path.exists()

    def test_schema_version_recorded(self, tmp_path):
        from src.state_db import AgentStateDB
        db_path = tmp_path / "test.db"
        db = AgentStateDB(db_path=db_path)

        conn = db._get_connection()
        cursor = conn.execute("SELECT version FROM schema_version WHERE name = 'agent_state'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['version'] == 1

    def test_agent_state_table_exists(self, tmp_path):
        from src.state_db import AgentStateDB
        db_path = tmp_path / "test.db"
        db = AgentStateDB(db_path=db_path)

        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_state'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent_init(self, tmp_path):
        """Calling init twice should not error."""
        from src.state_db import AgentStateDB
        db_path = tmp_path / "test.db"
        db = AgentStateDB(db_path=db_path)
        db2 = AgentStateDB(db_path=db_path)
        assert db2 is not None


# ============================================================================
# save_state
# ============================================================================

class TestSaveState:

    def test_save_new_agent(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        state = {"E": 0.7, "I": 0.8, "S": 0.2, "V": 0.1, "coherence": 0.9, "regime": "CONVERGENCE"}
        result = db.save_state("agent_001", state)
        assert result is True

    def test_save_and_load_roundtrip(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        state = {
            "E": 0.65, "I": 0.85, "S": 0.15, "V": 0.05,
            "coherence": 0.95, "regime": "CONVERGENCE",
            "update_count": 42, "void_active": True,
            "extra_field": "preserved"
        }
        db.save_state("roundtrip_agent", state)
        loaded = db.load_state("roundtrip_agent")

        assert loaded is not None
        assert loaded["E"] == 0.65
        assert loaded["I"] == 0.85
        assert loaded["extra_field"] == "preserved"

    def test_update_existing_agent(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        state1 = {"E": 0.5, "I": 0.5, "S": 0.5, "V": 0.0}
        db.save_state("update_agent", state1)

        state2 = {"E": 0.9, "I": 0.9, "S": 0.1, "V": 0.0}
        db.save_state("update_agent", state2)

        loaded = db.load_state("update_agent")
        assert loaded["E"] == 0.9
        assert loaded["I"] == 0.9

    def test_default_values(self, tmp_path):
        """Missing fields should use defaults."""
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        db.save_state("default_agent", {})

        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT E, I, S, V, coherence, regime FROM agent_state WHERE agent_id = ?",
            ("default_agent",)
        )
        row = cursor.fetchone()
        conn.close()

        assert row["E"] == 0.5
        assert row["I"] == 1.0
        assert row["S"] == 0.2
        assert row["V"] == 0.0
        assert row["regime"] == "DIVERGENCE"

    def test_void_active_boolean_conversion(self, tmp_path):
        """void_active should be stored as integer."""
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        db.save_state("void_agent", {"void_active": True})

        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT void_active FROM agent_state WHERE agent_id = ?",
            ("void_agent",)
        )
        assert cursor.fetchone()["void_active"] == 1
        conn.close()


# ============================================================================
# load_state
# ============================================================================

class TestLoadState:

    def test_load_nonexistent_returns_none(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        result = db.load_state("nonexistent")
        assert result is None

    def test_load_existing(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        db.save_state("existing", {"E": 0.8, "custom": "data"})
        result = db.load_state("existing")

        assert result is not None
        assert result["E"] == 0.8
        assert result["custom"] == "data"


# ============================================================================
# delete_state
# ============================================================================

class TestDeleteState:

    def test_delete_existing(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        db.save_state("to_delete", {"E": 0.5})
        assert db.load_state("to_delete") is not None

        result = db.delete_state("to_delete")
        assert result is True
        assert db.load_state("to_delete") is None

    def test_delete_nonexistent(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        result = db.delete_state("ghost_agent")
        assert result is True  # No error on deleting non-existent


# ============================================================================
# list_agents
# ============================================================================

class TestListAgents:

    def _seed_agents(self, db):
        """Helper to seed test agents."""
        agents = [
            ("agent_A", {"E": 0.9, "I": 0.9, "S": 0.1, "V": 0.0, "coherence": 0.95, "regime": "CONVERGENCE", "update_count": 10}),
            ("agent_B", {"E": 0.5, "I": 0.5, "S": 0.5, "V": 0.3, "coherence": 0.6, "regime": "DIVERGENCE", "update_count": 5}),
            ("agent_C", {"E": 0.3, "I": 0.4, "S": 0.7, "V": 0.5, "coherence": 0.3, "regime": "DIVERGENCE", "update_count": 20}),
        ]
        for agent_id, state in agents:
            db.save_state(agent_id, state)

    def test_list_all(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents()
        assert len(result) == 3

    def test_filter_by_regime(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents(regime="DIVERGENCE")
        assert len(result) == 2
        assert all(r["regime"] == "DIVERGENCE" for r in result)

    def test_filter_by_min_coherence(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents(min_coherence=0.5)
        assert len(result) == 2

    def test_filter_by_max_coherence(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents(max_coherence=0.5)
        assert len(result) == 1

    def test_filter_by_coherence_range(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents(min_coherence=0.4, max_coherence=0.8)
        assert len(result) == 1
        assert result[0]["agent_id"] == "agent_B"

    def test_limit(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents(limit=2)
        assert len(result) == 2

    def test_combined_filters(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        self._seed_agents(db)

        result = db.list_agents(regime="DIVERGENCE", max_coherence=0.5)
        assert len(result) == 1
        assert result[0]["agent_id"] == "agent_C"

    def test_empty_db(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        result = db.list_agents()
        assert result == []

    def test_result_fields(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")
        db.save_state("field_test", {"E": 0.7, "I": 0.8, "S": 0.2, "V": 0.1, "coherence": 0.9, "regime": "CONVERGENCE", "update_count": 5})

        result = db.list_agents()
        assert len(result) == 1
        r = result[0]
        assert "agent_id" in r
        assert "E" in r
        assert "I" in r
        assert "S" in r
        assert "V" in r
        assert "coherence" in r
        assert "regime" in r
        assert "update_count" in r
        assert "updated_at" in r


# ============================================================================
# get_statistics
# ============================================================================

class TestGetStatistics:

    def test_empty_db(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        stats = db.get_statistics()
        assert stats["total_agents"] == 0
        assert stats["by_regime"] == {}

    def test_with_agents(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        db.save_state("a1", {"E": 0.8, "I": 0.9, "S": 0.1, "V": 0.0, "regime": "CONVERGENCE"})
        db.save_state("a2", {"E": 0.4, "I": 0.5, "S": 0.6, "V": 0.2, "regime": "DIVERGENCE"})

        stats = db.get_statistics()
        assert stats["total_agents"] == 2
        assert stats["by_regime"]["CONVERGENCE"] == 1
        assert stats["by_regime"]["DIVERGENCE"] == 1
        assert "averages" in stats
        assert stats["averages"]["E"] == pytest.approx(0.6, abs=0.01)


# ============================================================================
# migrate_from_json
# ============================================================================

class TestMigrateFromJson:

    def test_nonexistent_dir(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        stats = db.migrate_from_json(tmp_path / "nonexistent_agents")
        assert stats["migrated"] == 0
        assert stats["skipped"] == 0

    def test_migrate_json_files(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # Create test state files
        (agents_dir / "agent_1_state.json").write_text(
            json.dumps({"E": 0.7, "I": 0.8, "S": 0.2, "V": 0.0})
        )
        (agents_dir / "agent_2_state.json").write_text(
            json.dumps({"E": 0.5, "I": 0.6, "S": 0.4, "V": 0.1})
        )

        stats = db.migrate_from_json(agents_dir)
        assert stats["migrated"] == 2

        # Verify migrated data
        assert db.load_state("agent_1") is not None
        assert db.load_state("agent_2") is not None

    def test_migrate_corrupted_file(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        (agents_dir / "bad_state.json").write_text("not valid json")

        stats = db.migrate_from_json(agents_dir)
        assert len(stats["errors"]) == 1

    def test_ignores_non_state_files(self, tmp_path):
        from src.state_db import AgentStateDB
        db = AgentStateDB(db_path=tmp_path / "test.db")

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        (agents_dir / "config.json").write_text("{}")
        (agents_dir / "readme.txt").write_text("hello")

        stats = db.migrate_from_json(agents_dir)
        assert stats["migrated"] == 0


# ============================================================================
# _use_postgres helper
# ============================================================================

class TestUsePostgres:

    def test_default_not_postgres(self):
        from src.state_db import _use_postgres
        with pytest.MonkeyPatch.context() as m:
            m.delenv("DB_BACKEND", raising=False)
            assert _use_postgres() is False

    def test_postgres_when_set(self):
        from src.state_db import _use_postgres
        with pytest.MonkeyPatch.context() as m:
            m.setenv("DB_BACKEND", "postgres")
            assert _use_postgres() is True

    def test_postgres_case_insensitive(self):
        from src.state_db import _use_postgres
        with pytest.MonkeyPatch.context() as m:
            m.setenv("DB_BACKEND", "POSTGRES")
            assert _use_postgres() is True

    def test_other_values(self):
        from src.state_db import _use_postgres
        with pytest.MonkeyPatch.context() as m:
            m.setenv("DB_BACKEND", "sqlite")
            assert _use_postgres() is False
