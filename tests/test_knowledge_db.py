"""
Tests for src/knowledge_db.py - Pure functions and SQLite-backed KnowledgeGraphDB.

Tests cover:
- ResponseTo dataclass
- DiscoveryNode dataclass: to_dict, from_dict, roundtrip
- _cosine_similarity (pure math)
- KnowledgeGraphDB: CRUD, query, FTS, health check (in-memory SQLite)
"""

import pytest
import pytest_asyncio
import asyncio
import math
import os
import json
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.knowledge_db import (
    ResponseTo,
    DiscoveryNode,
    KnowledgeGraphDB,
)


# ============================================================================
# ResponseTo dataclass
# ============================================================================

class TestResponseTo:

    def test_creation(self):
        rt = ResponseTo(discovery_id="disc-1", response_type="extend")
        assert rt.discovery_id == "disc-1"
        assert rt.response_type == "extend"

    def test_valid_response_types(self):
        for rt_type in ["extend", "question", "disagree", "support"]:
            rt = ResponseTo(discovery_id="d", response_type=rt_type)
            assert rt.response_type == rt_type


# ============================================================================
# DiscoveryNode dataclass
# ============================================================================

class TestDiscoveryNode:

    def _make_node(self, **overrides):
        defaults = dict(
            id="disc-001",
            agent_id="agent-1",
            type="insight",
            summary="A test discovery",
            details="Detailed description",
            tags=["test", "unit"],
            severity="medium",
            timestamp="2026-01-15T12:00:00",
            status="open",
            related_to=["disc-002"],
            references_files=["src/main.py"],
        )
        defaults.update(overrides)
        return DiscoveryNode(**defaults)

    def test_creation_defaults(self):
        node = DiscoveryNode(
            id="d1", agent_id="a1", type="bug", summary="Found bug"
        )
        assert node.id == "d1"
        assert node.details == ""
        assert node.tags == []
        assert node.severity is None
        assert node.status == "open"
        assert node.related_to == []
        assert node.response_to is None
        assert node.responses_from == []
        assert node.references_files == []
        assert node.resolved_at is None
        assert node.updated_at is None
        assert node.confidence is None
        assert node.provenance is None
        assert node.provenance_chain is None

    def test_creation_all_fields(self):
        rt = ResponseTo(discovery_id="d0", response_type="extend")
        node = DiscoveryNode(
            id="d1", agent_id="a1", type="insight", summary="test",
            details="long description",
            tags=["alpha", "beta"],
            severity="high",
            timestamp="2026-01-01T00:00:00",
            status="resolved",
            related_to=["d2", "d3"],
            response_to=rt,
            responses_from=["d4"],
            references_files=["file.py"],
            resolved_at="2026-01-02T00:00:00",
            updated_at="2026-01-01T12:00:00",
            confidence=0.95,
            provenance={"E": 0.7, "coherence": 0.5},
            provenance_chain=[{"agent": "a1", "step": 1}],
        )
        assert node.response_to == rt
        assert node.confidence == 0.95
        assert node.provenance["E"] == 0.7

    # --- to_dict ---

    def test_to_dict_basic(self):
        node = self._make_node()
        d = node.to_dict()
        assert d["id"] == "disc-001"
        assert d["agent_id"] == "agent-1"
        assert d["type"] == "insight"
        assert d["summary"] == "A test discovery"
        assert d["details"] == "Detailed description"
        assert d["tags"] == ["test", "unit"]
        assert d["severity"] == "medium"
        assert d["status"] == "open"
        assert d["related_to"] == ["disc-002"]
        assert d["references_files"] == ["src/main.py"]

    def test_to_dict_include_details_true(self):
        node = self._make_node(details="full details here")
        d = node.to_dict(include_details=True)
        assert d["details"] == "full details here"
        assert "has_details" not in d

    def test_to_dict_include_details_false(self):
        node = self._make_node(details="full details here")
        d = node.to_dict(include_details=False)
        assert "details" not in d
        assert d["has_details"] is True
        assert d["details_preview"] == "full details here"

    def test_to_dict_details_false_long_text(self):
        long_text = "x" * 200
        node = self._make_node(details=long_text)
        d = node.to_dict(include_details=False)
        assert d["details_preview"].endswith("...")
        assert len(d["details_preview"]) == 103  # 100 chars + "..."

    def test_to_dict_details_false_empty(self):
        node = self._make_node(details="")
        d = node.to_dict(include_details=False)
        assert "has_details" not in d

    def test_to_dict_with_response_to(self):
        rt = ResponseTo(discovery_id="d0", response_type="support")
        node = self._make_node(response_to=rt)
        d = node.to_dict()
        assert d["response_to"] == {
            "discovery_id": "d0",
            "response_type": "support"
        }

    def test_to_dict_without_response_to(self):
        node = self._make_node(response_to=None)
        d = node.to_dict()
        assert "response_to" not in d

    def test_to_dict_with_responses_from(self):
        node = self._make_node(responses_from=["d5", "d6"])
        d = node.to_dict()
        assert d["responses_from"] == ["d5", "d6"]

    def test_to_dict_without_responses_from(self):
        node = self._make_node(responses_from=[])
        d = node.to_dict()
        assert "responses_from" not in d

    def test_to_dict_with_confidence(self):
        node = self._make_node(confidence=0.85)
        d = node.to_dict()
        assert d["confidence"] == 0.85

    def test_to_dict_without_confidence(self):
        node = self._make_node(confidence=None)
        d = node.to_dict()
        assert "confidence" not in d

    def test_to_dict_with_provenance(self):
        prov = {"E": 0.7, "I": 0.8, "coherence": 0.5}
        node = self._make_node(provenance=prov)
        d = node.to_dict()
        assert d["provenance"] == prov

    def test_to_dict_without_provenance(self):
        node = self._make_node(provenance=None)
        d = node.to_dict()
        assert "provenance" not in d

    def test_to_dict_with_provenance_chain(self):
        chain = [{"agent": "a1", "step": 1}, {"agent": "a2", "step": 2}]
        node = self._make_node(provenance_chain=chain)
        d = node.to_dict()
        assert d["provenance_chain"] == chain

    def test_to_dict_without_provenance_chain(self):
        node = self._make_node(provenance_chain=None)
        d = node.to_dict()
        assert "provenance_chain" not in d

    # --- from_dict ---

    def test_from_dict_minimal(self):
        data = {"id": "d1", "agent_id": "a1", "type": "bug", "summary": "oops"}
        node = DiscoveryNode.from_dict(data)
        assert node.id == "d1"
        assert node.agent_id == "a1"
        assert node.type == "bug"
        assert node.summary == "oops"
        assert node.details == ""
        assert node.tags == []
        assert node.status == "open"

    def test_from_dict_full(self):
        data = {
            "id": "d1",
            "agent_id": "a1",
            "type": "insight",
            "summary": "discovery",
            "details": "long text",
            "tags": ["x", "y"],
            "severity": "high",
            "timestamp": "2026-01-01T00:00:00",
            "status": "resolved",
            "related_to": ["d2"],
            "response_to": {"discovery_id": "d0", "response_type": "extend"},
            "responses_from": ["d3"],
            "references_files": ["f.py"],
            "resolved_at": "2026-01-02",
            "updated_at": "2026-01-01T12:00",
            "confidence": 0.9,
        }
        node = DiscoveryNode.from_dict(data)
        assert node.details == "long text"
        assert node.tags == ["x", "y"]
        assert node.severity == "high"
        assert node.status == "resolved"
        assert node.response_to is not None
        assert node.response_to.discovery_id == "d0"
        assert node.response_to.response_type == "extend"
        assert node.confidence == 0.9

    def test_from_dict_response_to_none(self):
        data = {"id": "d1", "agent_id": "a1", "type": "bug", "summary": "s", "response_to": None}
        node = DiscoveryNode.from_dict(data)
        assert node.response_to is None

    def test_from_dict_response_to_empty_dict(self):
        """Empty dict should not create ResponseTo."""
        data = {"id": "d1", "agent_id": "a1", "type": "bug", "summary": "s", "response_to": {}}
        node = DiscoveryNode.from_dict(data)
        # Empty dict is falsy so response_to should be None
        assert node.response_to is None

    # --- roundtrip ---

    def test_roundtrip_basic(self):
        node = self._make_node()
        d = node.to_dict()
        restored = DiscoveryNode.from_dict(d)
        assert restored.id == node.id
        assert restored.agent_id == node.agent_id
        assert restored.type == node.type
        assert restored.summary == node.summary
        assert restored.details == node.details
        assert restored.tags == node.tags
        assert restored.severity == node.severity
        assert restored.status == node.status

    def test_roundtrip_with_response_to(self):
        rt = ResponseTo(discovery_id="d0", response_type="disagree")
        node = self._make_node(response_to=rt, responses_from=["d9"])
        d = node.to_dict()
        restored = DiscoveryNode.from_dict(d)
        assert restored.response_to.discovery_id == "d0"
        assert restored.response_to.response_type == "disagree"

    def test_roundtrip_with_confidence(self):
        node = self._make_node(confidence=0.77)
        d = node.to_dict()
        restored = DiscoveryNode.from_dict(d)
        assert restored.confidence == 0.77


# ============================================================================
# _cosine_similarity (accessed via KnowledgeGraphDB instance)
# ============================================================================

class TestCosineSimilarity:
    """Test the _cosine_similarity method on KnowledgeGraphDB."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create in-memory DB for accessing _cosine_similarity."""
        db_path = tmp_path / "test_cosine.db"
        os.environ["UNITARES_DISABLE_EMBEDDINGS"] = "true"
        db = KnowledgeGraphDB(db_path=db_path, enable_embeddings=False)
        yield db
        db.close()
        os.environ.pop("UNITARES_DISABLE_EMBEDDINGS", None)

    def test_identical_vectors(self, db):
        vec = [1.0, 2.0, 3.0]
        sim = db._cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-9

    def test_orthogonal_vectors(self, db):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        sim = db._cosine_similarity(v1, v2)
        assert abs(sim) < 1e-9

    def test_opposite_vectors(self, db):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        sim = db._cosine_similarity(v1, v2)
        assert abs(sim - (-1.0)) < 1e-9

    def test_zero_vector_first(self, db):
        sim = db._cosine_similarity([0.0, 0.0], [1.0, 2.0])
        assert sim == 0.0

    def test_zero_vector_second(self, db):
        sim = db._cosine_similarity([1.0, 2.0], [0.0, 0.0])
        assert sim == 0.0

    def test_both_zero_vectors(self, db):
        sim = db._cosine_similarity([0.0, 0.0], [0.0, 0.0])
        assert sim == 0.0

    def test_similar_vectors(self, db):
        v1 = [1.0, 2.0, 3.0]
        v2 = [1.1, 2.1, 3.1]
        sim = db._cosine_similarity(v1, v2)
        assert sim > 0.99  # Very similar

    def test_single_dimension(self, db):
        sim = db._cosine_similarity([5.0], [3.0])
        assert abs(sim - 1.0) < 1e-9

    def test_negative_values(self, db):
        v1 = [-1.0, -2.0, -3.0]
        v2 = [-1.0, -2.0, -3.0]
        sim = db._cosine_similarity(v1, v2)
        assert abs(sim - 1.0) < 1e-9

    def test_known_similarity(self, db):
        """Test with manually calculated value."""
        v1 = [1.0, 0.0]
        v2 = [1.0, 1.0]
        # cos(45°) = 1/sqrt(2) ≈ 0.7071
        expected = 1.0 / math.sqrt(2)
        sim = db._cosine_similarity(v1, v2)
        assert abs(sim - expected) < 1e-9


# ============================================================================
# KnowledgeGraphDB SQLite CRUD (in-memory / tmp_path)
# ============================================================================

class TestKnowledgeGraphDBInit:

    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        os.environ["UNITARES_DISABLE_EMBEDDINGS"] = "true"
        db = KnowledgeGraphDB(db_path=db_path, enable_embeddings=False)
        assert db_path.exists()
        db.close()
        os.environ.pop("UNITARES_DISABLE_EMBEDDINGS", None)

    def test_embeddings_disabled_via_env(self, tmp_path):
        os.environ["UNITARES_DISABLE_EMBEDDINGS"] = "true"
        db = KnowledgeGraphDB(db_path=tmp_path / "test.db", enable_embeddings=True)
        assert db.enable_embeddings is False
        db.close()
        os.environ.pop("UNITARES_DISABLE_EMBEDDINGS", None)

    def test_schema_initialized(self, tmp_path):
        os.environ["UNITARES_DISABLE_EMBEDDINGS"] = "true"
        db = KnowledgeGraphDB(db_path=tmp_path / "test.db", enable_embeddings=False)
        conn = db._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "discoveries" in tables
        assert "discovery_tags" in tables
        assert "discovery_edges" in tables
        assert "rate_limits" in tables
        db.close()
        os.environ.pop("UNITARES_DISABLE_EMBEDDINGS", None)


@pytest.fixture
def kgdb(tmp_path):
    """Create a KnowledgeGraphDB with embeddings disabled."""
    os.environ["UNITARES_DISABLE_EMBEDDINGS"] = "true"
    db = KnowledgeGraphDB(db_path=tmp_path / "test_kg.db", enable_embeddings=False)
    # Disable rate limiting for tests
    db.rate_limit_stores_per_hour = 10000
    yield db
    db.close()
    os.environ.pop("UNITARES_DISABLE_EMBEDDINGS", None)


def _make_discovery(**overrides):
    defaults = dict(
        id="disc-test-001",
        agent_id="agent-1",
        type="insight",
        summary="Test discovery summary",
        details="Test discovery details",
        tags=["test"],
        severity="medium",
        status="open",
    )
    defaults.update(overrides)
    return DiscoveryNode(**defaults)


class TestKnowledgeGraphDBCRUD:

    @pytest.mark.asyncio
    async def test_add_and_get_discovery(self, kgdb):
        node = _make_discovery()
        await kgdb.add_discovery(node)
        result = await kgdb.get_discovery("disc-test-001")
        assert result is not None
        assert result.id == "disc-test-001"
        assert result.summary == "Test discovery summary"
        assert result.details == "Test discovery details"

    @pytest.mark.asyncio
    async def test_get_nonexistent_discovery(self, kgdb):
        result = await kgdb.get_discovery("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_discovery_with_tags(self, kgdb):
        node = _make_discovery(tags=["alpha", "beta", "gamma"])
        await kgdb.add_discovery(node)
        result = await kgdb.get_discovery("disc-test-001")
        assert set(result.tags) == {"alpha", "beta", "gamma"}

    @pytest.mark.asyncio
    async def test_add_discovery_with_response_to(self, kgdb):
        # Add parent first
        parent = _make_discovery(id="parent-001", summary="parent")
        await kgdb.add_discovery(parent)

        # Add child with response_to
        rt = ResponseTo(discovery_id="parent-001", response_type="extend")
        child = _make_discovery(id="child-001", summary="child", response_to=rt)
        await kgdb.add_discovery(child)

        result = await kgdb.get_discovery("child-001")
        assert result.response_to is not None
        assert result.response_to.discovery_id == "parent-001"
        assert result.response_to.response_type == "extend"

    @pytest.mark.asyncio
    async def test_add_discovery_with_related_to(self, kgdb):
        d1 = _make_discovery(id="d1", summary="first")
        d2 = _make_discovery(id="d2", summary="second", related_to=["d1"])
        await kgdb.add_discovery(d1)
        await kgdb.add_discovery(d2)

        result = await kgdb.get_discovery("d2")
        assert "d1" in result.related_to

    @pytest.mark.asyncio
    async def test_update_discovery(self, kgdb):
        node = _make_discovery()
        await kgdb.add_discovery(node)

        success = await kgdb.update_discovery("disc-test-001", {"status": "resolved", "severity": "high"})
        assert success is True

        result = await kgdb.get_discovery("disc-test-001")
        assert result.status == "resolved"
        assert result.severity == "high"
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_discovery(self, kgdb):
        success = await kgdb.update_discovery("nope", {"status": "resolved"})
        assert success is False

    @pytest.mark.asyncio
    async def test_update_discovery_tags(self, kgdb):
        node = _make_discovery(tags=["old"])
        await kgdb.add_discovery(node)

        await kgdb.update_discovery("disc-test-001", {"tags": ["new1", "new2"]})
        result = await kgdb.get_discovery("disc-test-001")
        assert set(result.tags) == {"new1", "new2"}

    @pytest.mark.asyncio
    async def test_delete_discovery(self, kgdb):
        node = _make_discovery()
        await kgdb.add_discovery(node)

        deleted = await kgdb.delete_discovery("disc-test-001")
        assert deleted is True

        result = await kgdb.get_discovery("disc-test-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_discovery(self, kgdb):
        deleted = await kgdb.delete_discovery("nope")
        assert deleted is False


class TestKnowledgeGraphDBQuery:

    @pytest.mark.asyncio
    async def test_query_all(self, kgdb):
        for i in range(5):
            await kgdb.add_discovery(_make_discovery(id=f"d-{i}", summary=f"disc {i}"))

        results = await kgdb.query()
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_query_by_agent(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", agent_id="a1"))
        await kgdb.add_discovery(_make_discovery(id="d2", agent_id="a2"))

        results = await kgdb.query(agent_id="a1")
        assert len(results) == 1
        assert results[0].agent_id == "a1"

    @pytest.mark.asyncio
    async def test_query_by_type(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", type="bug"))
        await kgdb.add_discovery(_make_discovery(id="d2", type="insight"))

        results = await kgdb.query(type="bug")
        assert len(results) == 1
        assert results[0].type == "bug"

    @pytest.mark.asyncio
    async def test_query_by_severity(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", severity="low"))
        await kgdb.add_discovery(_make_discovery(id="d2", severity="high"))

        results = await kgdb.query(severity="high")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_status(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", status="open"))
        await kgdb.add_discovery(_make_discovery(id="d2", status="resolved"))

        results = await kgdb.query(status="open")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_tags(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", tags=["python"]))
        await kgdb.add_discovery(_make_discovery(id="d2", tags=["rust"]))

        results = await kgdb.query(tags=["python"])
        assert len(results) == 1
        assert results[0].id == "d1"

    @pytest.mark.asyncio
    async def test_query_limit(self, kgdb):
        for i in range(10):
            await kgdb.add_discovery(_make_discovery(id=f"d-{i}"))

        results = await kgdb.query(limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_combined_filters(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", agent_id="a1", type="bug", status="open"))
        await kgdb.add_discovery(_make_discovery(id="d2", agent_id="a1", type="insight", status="open"))
        await kgdb.add_discovery(_make_discovery(id="d3", agent_id="a2", type="bug", status="open"))

        results = await kgdb.query(agent_id="a1", type="bug")
        assert len(results) == 1
        assert results[0].id == "d1"


class TestKnowledgeGraphDBFullTextSearch:

    @pytest.mark.asyncio
    async def test_fts_by_summary(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", summary="PostgreSQL performance issue"))
        await kgdb.add_discovery(_make_discovery(id="d2", summary="Redis caching strategy"))

        results = await kgdb.full_text_search("PostgreSQL")
        assert len(results) >= 1
        assert any(r.id == "d1" for r in results)

    @pytest.mark.asyncio
    async def test_fts_by_details(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", summary="issue", details="The asyncpg pool was leaking"))

        results = await kgdb.full_text_search("asyncpg")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_fts_no_results(self, kgdb):
        await kgdb.add_discovery(_make_discovery(id="d1", summary="simple test"))

        results = await kgdb.full_text_search("xylophone")
        assert len(results) == 0


class TestKnowledgeGraphDBHealthCheck:

    @pytest.mark.asyncio
    async def test_health_check(self, kgdb):
        result = await kgdb.health_check()
        assert result["integrity_check"] == "ok"
        assert result["db_exists"] is True
        assert result["foreign_key_issues"] == 0

    @pytest.mark.asyncio
    async def test_health_check_after_inserts(self, kgdb):
        await kgdb.add_discovery(_make_discovery())
        result = await kgdb.health_check()
        assert result["integrity_check"] == "ok"


class TestKnowledgeGraphDBEdgeTraversal:

    @pytest.mark.asyncio
    async def test_responses_from_backlinks(self, kgdb):
        parent = _make_discovery(id="parent", summary="parent node")
        await kgdb.add_discovery(parent)

        child = _make_discovery(
            id="child",
            summary="child node",
            response_to=ResponseTo(discovery_id="parent", response_type="extend")
        )
        await kgdb.add_discovery(child)

        # When we get the parent, it should have child in responses_from
        result = await kgdb.get_discovery("parent")
        assert "child" in result.responses_from

    @pytest.mark.asyncio
    async def test_update_response_to(self, kgdb):
        parent1 = _make_discovery(id="p1", summary="first parent")
        parent2 = _make_discovery(id="p2", summary="second parent")
        child = _make_discovery(
            id="child",
            response_to=ResponseTo(discovery_id="p1", response_type="extend")
        )
        await kgdb.add_discovery(parent1)
        await kgdb.add_discovery(parent2)
        await kgdb.add_discovery(child)

        # Update response_to to point to p2
        await kgdb.update_discovery("child", {
            "response_to": {"discovery_id": "p2", "response_type": "question"}
        })

        result = await kgdb.get_discovery("child")
        assert result.response_to.discovery_id == "p2"
        assert result.response_to.response_type == "question"


class TestKnowledgeGraphDBProvenance:

    @pytest.mark.asyncio
    async def test_add_discovery_with_provenance(self, kgdb):
        prov = {"E": 0.7, "I": 0.8, "coherence": 0.52}
        node = _make_discovery(provenance=prov)
        await kgdb.add_discovery(node)

        result = await kgdb.get_discovery("disc-test-001")
        assert result.provenance == prov

    @pytest.mark.asyncio
    async def test_add_discovery_with_provenance_chain(self, kgdb):
        chain = [{"agent": "a1", "step": 1}, {"agent": "a2", "step": 2}]
        node = _make_discovery(provenance_chain=chain)
        await kgdb.add_discovery(node)

        result = await kgdb.get_discovery("disc-test-001")
        assert result.provenance_chain == chain

    @pytest.mark.asyncio
    async def test_add_discovery_no_provenance(self, kgdb):
        node = _make_discovery()
        await kgdb.add_discovery(node)

        result = await kgdb.get_discovery("disc-test-001")
        assert result.provenance is None
        assert result.provenance_chain is None
