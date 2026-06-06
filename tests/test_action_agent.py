"""Tests for the Action Agent."""

import json
from unittest.mock import MagicMock, patch


class TestActionAgent:
    FAKE_STATE = {
        "question": "What are GDPR data minimisation requirements?",
        "draft_response": "Data must be adequate, relevant, and limited [1].",
        "citations": ["[1] GDPR Article 5 — EU GDPR 2016/679"],
        "retrieved_chunks": [{"id": 1, "title": "GDPR", "content": "...", "source": "EU GDPR"}],
    }

    @patch("src.agents.action_agent.write_audit_log")
    @patch("src.agents.action_agent._chat_model")
    def test_returns_proposed_action(self, mock_model, mock_audit):
        from src.agents.action_agent import action_agent

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "title": "Compliance Gap: GDPR data minimisation",
            "body": "## Finding\nData minimisation gap identified.",
            "labels": ["compliance-gap"],
        })
        mock_model.return_value.invoke.return_value = mock_response

        result = action_agent(self.FAKE_STATE)

        assert "proposed_action" in result
        proposal = json.loads(result["proposed_action"])
        assert "title" in proposal
        assert "body" in proposal
        assert "labels" in proposal

    @patch("src.agents.action_agent.write_audit_log")
    @patch("src.agents.action_agent._chat_model")
    def test_falls_back_on_invalid_json(self, mock_model, mock_audit):
        from src.agents.action_agent import action_agent

        mock_response = MagicMock()
        mock_response.content = "This is not JSON at all."
        mock_model.return_value.invoke.return_value = mock_response

        result = action_agent(self.FAKE_STATE)

        assert "proposed_action" in result
        proposal = json.loads(result["proposed_action"])
        assert "title" in proposal  # fallback proposal

    @patch("src.agents.action_agent.write_audit_log")
    @patch("src.agents.action_agent._chat_model")
    def test_strips_markdown_fences(self, mock_model, mock_audit):
        from src.agents.action_agent import action_agent

        mock_response = MagicMock()
        mock_response.content = '```json\n{"title": "Test", "body": "Body", "labels": []}\n```'
        mock_model.return_value.invoke.return_value = mock_response

        result = action_agent(self.FAKE_STATE)
        proposal = json.loads(result["proposed_action"])
        assert proposal["title"] == "Test"

    @patch("src.agents.action_agent.write_audit_log")
    @patch("src.agents.action_agent._chat_model")
    def test_audit_log_written(self, mock_model, mock_audit):
        from src.agents.action_agent import action_agent

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "title": "Gap", "body": "Body", "labels": ["compliance-gap"]
        })
        mock_model.return_value.invoke.return_value = mock_response

        action_agent(self.FAKE_STATE)
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["step_type"] == "action_proposal"
        assert call_kwargs["tool_call"] == "github_issue"
