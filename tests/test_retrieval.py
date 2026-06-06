"""Tests for the retrieval and draft flow (unit — all external calls mocked)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Knowledge Agent
# ---------------------------------------------------------------------------

class TestKnowledgeAgent:
    FAKE_CHUNKS = [
        {
            "id": 1,
            "title": "OSFI E-23 Model Risk",
            "content": "Models must be validated independently.",
            "source": "OSFI E-23 (2023)",
            "similarity": 0.92,
        }
    ]

    @patch("src.agents.knowledge_agent.similarity_search", return_value=FAKE_CHUNKS)
    @patch("src.agents.knowledge_agent._embeddings_model")
    def test_returns_chunks(self, mock_model, mock_search):
        from src.agents.knowledge_agent import knowledge_agent

        mock_model.return_value.embed_query.return_value = [0.1] * 1536

        state = {"question": "What are OSFI model validation requirements?", "top_k": 5}
        result = knowledge_agent(state)

        assert "retrieved_chunks" in result
        assert len(result["retrieved_chunks"]) == 1
        assert result["retrieved_chunks"][0]["title"] == "OSFI E-23 Model Risk"

    @patch("src.agents.knowledge_agent.similarity_search", return_value=[])
    @patch("src.agents.knowledge_agent._embeddings_model")
    def test_empty_retrieval(self, mock_model, mock_search):
        from src.agents.knowledge_agent import knowledge_agent

        mock_model.return_value.embed_query.return_value = [0.0] * 1536

        result = knowledge_agent({"question": "unrelated question", "top_k": 5})
        assert result["retrieved_chunks"] == []


# ---------------------------------------------------------------------------
# Analysis Agent
# ---------------------------------------------------------------------------

class TestAnalysisAgent:
    FAKE_CHUNKS = [
        {
            "id": 1,
            "title": "OSFI E-23 Model Risk",
            "content": "Models must be validated independently.",
            "source": "OSFI E-23 (2023)",
            "similarity": 0.92,
        }
    ]

    @patch("src.agents.analysis_agent.write_audit_log")
    @patch("src.agents.analysis_agent._chat_model")
    def test_cited_response(self, mock_model, mock_audit):
        from src.agents.analysis_agent import analysis_agent

        mock_response = MagicMock()
        mock_response.content = "Models must be independently validated [1]."
        mock_model.return_value.invoke.return_value = mock_response

        state = {"question": "What are model validation requirements?", "retrieved_chunks": self.FAKE_CHUNKS}
        result = analysis_agent(state)

        assert "draft_response" in result
        assert result["is_cited"] is True
        assert len(result["citations"]) == 1
        assert "OSFI E-23" in result["citations"][0]

    @patch("src.agents.analysis_agent.write_audit_log")
    @patch("src.agents.analysis_agent._chat_model")
    def test_uncited_response_flagged(self, mock_model, mock_audit):
        from src.agents.analysis_agent import analysis_agent

        mock_response = MagicMock()
        mock_response.content = "Models must be validated. No citations here."
        mock_model.return_value.invoke.return_value = mock_response

        state = {"question": "What are model validation requirements?", "retrieved_chunks": self.FAKE_CHUNKS}
        result = analysis_agent(state)

        assert result["is_cited"] is False
        assert result["citations"] == []

    def test_no_chunks_returns_fallback(self):
        from src.agents.analysis_agent import analysis_agent

        result = analysis_agent({"question": "anything", "retrieved_chunks": []})
        assert result["is_cited"] is False
        assert "No relevant documents" in result["draft_response"]


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

class TestSupervisor:
    def test_routes_to_knowledge_agent_when_no_chunks(self):
        from src.agents.supervisor import supervisor

        result = supervisor({"retrieved_chunks": [], "draft_response": ""})
        assert result["next"] == "knowledge_agent"

    def test_routes_to_analysis_agent_when_chunks_present(self):
        from src.agents.supervisor import supervisor

        result = supervisor({"retrieved_chunks": [{"id": 1}], "draft_response": ""})
        assert result["next"] == "analysis_agent"

    def test_routes_to_end_when_draft_present(self):
        from langgraph.graph import END
        from src.agents.supervisor import supervisor

        result = supervisor({"retrieved_chunks": [{"id": 1}], "draft_response": "Some answer."})
        assert result["next"] == END


# ---------------------------------------------------------------------------
# API — /query endpoint
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    def test_empty_question_returns_400(self):
        response = client.post("/query", json={"question": "   "})
        assert response.status_code == 400

    @patch("src.graph.graph")
    def test_successful_query(self, mock_graph):
        mock_graph.invoke.return_value = {
            "draft_response": "Models must be validated [1].",
            "citations": ["[1] OSFI E-23 — OSFI E-23 (2023)"],
            "is_cited": True,
        }

        response = client.post("/query", json={"question": "What is model validation?"})

        assert response.status_code == 200
        data = response.json()
        assert data["is_cited"] is True
        assert len(data["citations"]) == 1
