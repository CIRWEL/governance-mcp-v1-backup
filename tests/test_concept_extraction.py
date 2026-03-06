"""Tests for ConceptExtractor — Option D concept graph pipeline."""

from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.concept_extraction import ConceptExtractor, UnionFind


class TestUnionFind:
    def test_basic_union(self):
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")
        assert uf.find("a") == uf.find("b")
        assert uf.find("c") != uf.find("a")

    def test_groups(self):
        uf = UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")
        uf.union("c", "d")
        groups = uf.groups()
        assert len(groups) == 2
        for members in groups.values():
            assert len(members) == 2


class TestMergeSimilarTags:
    def test_high_cosine_and_cooccurrence_merges(self):
        """Two tags with high cosine + co-occurrence merge into one Concept."""
        extractor = ConceptExtractor()
        # Nearly identical embeddings
        tag_embeddings = {
            "python": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "python3": np.array([0.99, 0.1, 0.0], dtype=np.float32),
            "javascript": np.array([0.0, 1.0, 0.0], dtype=np.float32),
        }
        co_occurrence = {("python", "python3"): 5}

        clusters = extractor._merge_similar_tags(tag_embeddings, co_occurrence)

        # python and python3 should be merged; javascript separate
        merged = False
        for members in clusters.values():
            if "python" in members and "python3" in members:
                merged = True
        assert merged, "python and python3 should merge"

        # javascript should be separate
        for members in clusters.values():
            if "javascript" in members:
                assert len(members) == 1

    def test_low_cosine_no_merge(self):
        """Orthogonal tags should not merge."""
        extractor = ConceptExtractor()
        tag_embeddings = {
            "python": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "rust": np.array([0.0, 1.0, 0.0], dtype=np.float32),
        }
        co_occurrence = {("python", "rust"): 10}

        clusters = extractor._merge_similar_tags(tag_embeddings, co_occurrence)
        assert len(clusters) == 2

    def test_low_cooccurrence_no_merge(self):
        """High cosine but low co-occurrence should not merge."""
        extractor = ConceptExtractor()
        tag_embeddings = {
            "python": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "python3": np.array([0.99, 0.1, 0.0], dtype=np.float32),
        }
        co_occurrence = {("python", "python3"): 1}  # below threshold of 2

        clusters = extractor._merge_similar_tags(tag_embeddings, co_occurrence)
        assert len(clusters) == 2


class TestSplitBroadTag:
    def test_split_distinct_clusters(self):
        """Tag with bimodal discoveries splits into sub-Concepts."""
        extractor = ConceptExtractor(split_min_discoveries=4)

        # Two distinct clusters in embedding space
        embeddings = {}
        for i in range(5):
            embeddings[f"d_a_{i}"] = np.array([1.0, 0.0, 0.0], dtype=np.float32) + np.random.randn(3) * 0.01
        for i in range(5):
            embeddings[f"d_b_{i}"] = np.array([0.0, 1.0, 0.0], dtype=np.float32) + np.random.randn(3) * 0.01

        tag_discoveries = {
            "broad_tag": [f"d_a_{i}" for i in range(5)] + [f"d_b_{i}" for i in range(5)],
        }

        clusters = {"broad_tag": ["broad_tag"]}
        result = extractor._split_broad_tags(clusters, tag_discoveries, embeddings)

        # Should produce more than one cluster
        assert len(result) >= 2, f"Expected split but got {len(result)} clusters"

    def test_no_split_when_few_discoveries(self):
        """Tag with few discoveries should not split."""
        extractor = ConceptExtractor(split_min_discoveries=10)

        embeddings = {f"d_{i}": np.random.randn(3).astype(np.float32) for i in range(3)}
        tag_discoveries = {"small_tag": [f"d_{i}" for i in range(3)]}

        clusters = {"small_tag": ["small_tag"]}
        result = extractor._split_broad_tags(clusters, tag_discoveries, embeddings)

        assert len(result) == 1
        assert result[0] == ["small_tag"]


class TestCoOccurrence:
    def test_correct_co_occurrence(self):
        """Co-occurrence counts shared discoveries between tag pairs."""
        extractor = ConceptExtractor()
        tag_discoveries = {
            "python": ["d1", "d2", "d3"],
            "async": ["d2", "d3", "d4"],
            "rust": ["d5"],
        }

        co = extractor._compute_co_occurrence(tag_discoveries)

        # python and async share d2, d3
        assert co.get(("async", "python"), 0) == 2
        # rust shares nothing
        assert co.get(("python", "rust"), 0) == 0
        assert co.get(("async", "rust"), 0) == 0


class TestBuildConcepts:
    def test_concept_id_deterministic(self):
        """Same tags produce same concept_id."""
        extractor = ConceptExtractor()
        tag_discoveries = {"a": ["d1", "d2"], "b": ["d2", "d3"]}

        concepts1 = extractor._build_concepts([["a", "b"]], tag_discoveries)
        concepts2 = extractor._build_concepts([["b", "a"]], tag_discoveries)

        assert concepts1[0]["concept_id"] == concepts2[0]["concept_id"]

    def test_label_is_most_frequent(self):
        """Label should be the tag with most discoveries."""
        extractor = ConceptExtractor()
        tag_discoveries = {
            "rare": ["d1"],
            "common": ["d1", "d2", "d3"],
        }

        concepts = extractor._build_concepts([["rare", "common"]], tag_discoveries)
        assert concepts[0]["label"] == "common"


class TestNoEmbeddingsSkipsGracefully:
    @pytest.mark.asyncio
    async def test_no_embeddings_returns_skipped(self):
        """Missing embeddings don't crash — returns skipped status."""
        extractor = ConceptExtractor()

        mock_db = MagicMock()
        # graph_query returns tag-discovery pairs but no embeddings exist
        mock_db.graph_query = AsyncMock(return_value=[
            {"tag_name": "python", "discovery_id": "d1"},
            {"tag_name": "python", "discovery_id": "d2"},
        ])

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])  # no embeddings

        mock_db.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.concept_extraction.get_db", return_value=mock_db):
            result = await extractor.run()

        assert result["status"] == "skipped"
        assert "no embeddings" in result["reason"]


class TestEndToEndMock:
    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocked_db(self):
        """Full pipeline with mocked DB returns expected Concepts."""
        extractor = ConceptExtractor(
            merge_cosine_threshold=0.75,
            merge_co_occurrence_min=2,
            split_min_discoveries=100,  # high threshold to avoid splits
        )

        # Phase 1: Tags with discoveries
        graph_rows = [
            {"tag_name": "python", "discovery_id": "d1"},
            {"tag_name": "python", "discovery_id": "d2"},
            {"tag_name": "python", "discovery_id": "d3"},
            {"tag_name": "py3", "discovery_id": "d1"},
            {"tag_name": "py3", "discovery_id": "d2"},
            {"tag_name": "rust", "discovery_id": "d4"},
            {"tag_name": "rust", "discovery_id": "d5"},
        ]

        # Phase 2: Embeddings — python and py3 are similar, rust is different
        embedding_rows = [
            {"discovery_id": "d1", "embedding": "[1.0,0.0,0.0]"},
            {"discovery_id": "d2", "embedding": "[0.98,0.1,0.0]"},
            {"discovery_id": "d3", "embedding": "[0.95,0.15,0.0]"},
            {"discovery_id": "d4", "embedding": "[0.0,1.0,0.0]"},
            {"discovery_id": "d5", "embedding": "[0.0,0.95,0.1]"},
        ]

        mock_db = MagicMock()
        mock_db.graph_query = AsyncMock(side_effect=[
            graph_rows,  # Phase 1: tag query
            [],  # Phase 7: concept node 1
            [], [], [],  # Phase 7: ABOUT edges for concept 1
            [],  # Phase 7: concept node 2
            [], [],  # Phase 7: ABOUT edges for concept 2
            [],  # Phase 7: RELATES_TO edge (if shared discoveries)
        ])

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=embedding_rows)

        mock_db.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.concept_extraction.get_db", return_value=mock_db):
            result = await extractor.run()

        assert result["status"] == "completed"
        assert result["concepts_created"] >= 1
        assert result["tags_processed"] >= 2
