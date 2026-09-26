"""Tests for hybrid (vector + keyword) retrieval — unit, all DB calls mocked."""

from unittest.mock import patch

from src.db import _reciprocal_rank_fusion, hybrid_search

# ---------------------------------------------------------------------------
# Reciprocal rank fusion — pure function, no mocking needed
# ---------------------------------------------------------------------------

class TestReciprocalRankFusion:
    def test_ranks_agreeing_document_highest(self):
        vector_hits = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
        keyword_hits = [{"id": 1, "title": "A"}, {"id": 3, "title": "C"}]

        result = _reciprocal_rank_fusion([vector_hits, keyword_hits], top_k=3)

        assert result[0]["id"] == 1  # appears first in both lists
        assert {row["id"] for row in result} == {1, 2, 3}

    def test_respects_top_k(self):
        vector_hits = [{"id": i} for i in range(1, 6)]
        result = _reciprocal_rank_fusion([vector_hits], top_k=2)
        assert len(result) == 2
        assert [row["id"] for row in result] == [1, 2]

    def test_empty_lists_return_empty(self):
        assert _reciprocal_rank_fusion([[], []], top_k=5) == []

    def test_disjoint_lists_still_merge(self):
        vector_hits = [{"id": 1}]
        keyword_hits = [{"id": 2}]
        result = _reciprocal_rank_fusion([vector_hits, keyword_hits], top_k=5)
        assert {row["id"] for row in result} == {1, 2}

    def test_fused_similarity_is_populated(self):
        result = _reciprocal_rank_fusion([[{"id": 1}]], top_k=1)
        assert result[0]["similarity"] > 0


# ---------------------------------------------------------------------------
# hybrid_search — merges similarity_search + keyword_search
# ---------------------------------------------------------------------------

class TestHybridSearch:
    VECTOR_HITS = [
        {"id": 1, "title": "OSFI E-23 Model Risk", "content": "...", "source": "OSFI E-23", "similarity": 0.9},
        {"id": 2, "title": "GDPR Article 17", "content": "...", "source": "GDPR", "similarity": 0.7},
    ]
    KEYWORD_HITS = [
        {"id": 2, "title": "GDPR Article 17", "content": "...", "source": "GDPR", "similarity": 0.5},
    ]

    @patch("src.db.keyword_search", return_value=KEYWORD_HITS)
    @patch("src.db.similarity_search", return_value=VECTOR_HITS)
    def test_merges_and_ranks_agreement_first(self, mock_vector, mock_keyword):
        result = hybrid_search([0.1] * 1536, "model validation", top_k=2)

        assert len(result) == 2
        assert result[0]["id"] == 2  # present in both vector and keyword hits
        mock_vector.assert_called_once()
        mock_keyword.assert_called_once()

    @patch("src.db.keyword_search", return_value=[])
    @patch("src.db.similarity_search", return_value=VECTOR_HITS)
    def test_falls_back_to_vector_only_when_no_keyword_hits(self, mock_vector, mock_keyword):
        result = hybrid_search([0.1] * 1536, "no keyword match at all", top_k=2)
        assert {row["id"] for row in result} == {1, 2}


# ---------------------------------------------------------------------------
# Knowledge Agent — RETRIEVAL_MODE branch
# ---------------------------------------------------------------------------

class TestKnowledgeAgentRetrievalMode:
    FAKE_CHUNKS = [
        {"id": 1, "title": "OSFI E-23 Model Risk", "content": "...", "source": "OSFI E-23", "similarity": 0.92},
    ]

    @patch("src.agents.knowledge_agent.write_audit_log")
    @patch("src.agents.knowledge_agent.hybrid_search", return_value=FAKE_CHUNKS)
    @patch("src.agents.knowledge_agent.similarity_search")
    @patch("src.agents.knowledge_agent._embeddings_model")
    @patch("src.agents.knowledge_agent.settings")
    def test_hybrid_mode_calls_hybrid_search(
        self, mock_settings, mock_model, mock_vector, mock_hybrid, mock_audit
    ):
        from src.agents.knowledge_agent import knowledge_agent

        mock_settings.RETRIEVAL_MODE = "hybrid"
        mock_model.return_value.embed_query.return_value = [0.1] * 1536

        result = knowledge_agent({"question": "What are OSFI model validation requirements?", "top_k": 5})

        assert result["retrieved_chunks"] == self.FAKE_CHUNKS
        mock_hybrid.assert_called_once()
        mock_vector.assert_not_called()

    @patch("src.agents.knowledge_agent.write_audit_log")
    @patch("src.agents.knowledge_agent.hybrid_search")
    @patch("src.agents.knowledge_agent.similarity_search", return_value=FAKE_CHUNKS)
    @patch("src.agents.knowledge_agent._embeddings_model")
    @patch("src.agents.knowledge_agent.settings")
    def test_vector_mode_calls_similarity_search(
        self, mock_settings, mock_model, mock_vector, mock_hybrid, mock_audit
    ):
        from src.agents.knowledge_agent import knowledge_agent

        mock_settings.RETRIEVAL_MODE = "vector"
        mock_model.return_value.embed_query.return_value = [0.1] * 1536

        result = knowledge_agent({"question": "What are OSFI model validation requirements?", "top_k": 5})

        assert result["retrieved_chunks"] == self.FAKE_CHUNKS
        mock_vector.assert_called_once()
        mock_hybrid.assert_not_called()
