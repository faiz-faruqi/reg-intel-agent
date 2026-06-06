"""Action Agent: proposes a GitHub issue from the compliance analysis. Never executes."""

import json
import logging
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config import settings
from src.db import write_audit_log
from src.state import AgentState

logger = logging.getLogger(__name__)
AGENT_NAME = "action_agent"

SYSTEM_PROMPT = """\
You are a regulatory compliance coordinator. Given a compliance analysis, propose a GitHub
issue to track the identified gap or required action.

Respond ONLY with valid JSON in this exact schema — no markdown, no prose:
{
  "title": "Compliance Gap: <short description under 80 chars>",
  "body": "## Finding\\n<1-2 sentence summary>\\n\\n## Supporting Analysis\\n<key cited points>\\n\\n## Recommended Action\\n<concrete next steps>",
  "labels": ["compliance-gap"]
}"""

HUMAN_TEMPLATE = """\
Question: {question}

Analysis:
{draft_response}

Citations:
{citations}

Propose a GitHub issue to track this compliance finding."""


@lru_cache(maxsize=1)
def _chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENROUTER_MODEL_ID,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
    )


def _extract_json(content: str) -> dict:
    """Extract JSON dict from LLM response, tolerating markdown code fences."""
    text = content.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: find the outermost {...}
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {}


def action_agent(state: AgentState) -> AgentState:
    """
    Propose a GitHub issue from the analysis. Writes the proposal to audit log.
    Does NOT create the issue — that requires human approval via the HITL gate.
    """
    question = state.get("question", "")
    draft = state.get("draft_response", "")
    citations = state.get("citations", [])

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=HUMAN_TEMPLATE.format(
            question=question,
            draft_response=draft,
            citations="\n".join(citations),
        )),
    ]

    logger.info("%s: generating action proposal", AGENT_NAME)
    response = _chat_model().invoke(messages)
    proposal = _extract_json(response.content)

    if not proposal:
        proposal = {
            "title": f"Compliance Review Required: {question[:70]}",
            "body": f"## Finding\n{draft[:800]}\n\n## Recommended Action\nReview and address the identified compliance gap.",
            "labels": ["compliance-gap"],
        }

    write_audit_log(
        agent_name=AGENT_NAME,
        step_type="action_proposal",
        input_data={"question": question, "draft_length": len(draft)},
        output_data={"proposal_title": proposal.get("title", "")},
        tool_call="github_issue",
        decision="proposed",
    )

    return {"proposed_action": json.dumps(proposal)}
