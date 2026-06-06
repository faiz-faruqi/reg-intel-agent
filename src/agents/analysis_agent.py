"""Analysis Agent: drafts a cited response from the retrieved context."""

import logging
import re
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config import settings
from src.db import write_audit_log
from src.state import AgentState

logger = logging.getLogger(__name__)

AGENT_NAME = "analysis_agent"

SYSTEM_PROMPT = """\
You are a regulatory compliance analyst. Answer questions strictly from the
provided reference documents. Every factual claim MUST carry an inline citation
in [N] format (e.g. "Firms must retain records for seven years [1].").
Un-cited claims are not permitted — if a point cannot be supported by the
documents, say so explicitly. Do not invent or infer information."""

HUMAN_TEMPLATE = """\
Question: {question}

Reference Documents:
{context}

Provide a cited compliance analysis. Use [N] notation for every factual claim."""


@lru_cache(maxsize=1)
def _chat_model() -> ChatOpenAI:
    """Return a cached ChatOpenAI instance pointed at OpenRouter."""
    return ChatOpenAI(
        model=settings.OPENROUTER_MODEL_ID,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
    )


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] {chunk['title']} (Source: {chunk['source']})\n{chunk['content']}"
        )
    return "\n\n".join(parts)


def _extract_citations(response_text: str, chunks: list[dict[str, Any]]) -> list[str]:
    """Map [N] markers in the response back to their source strings."""
    indices = {int(m) for m in re.findall(r"\[(\d+)\]", response_text)}
    return [
        f"[{i}] {chunks[i - 1]['title']} — {chunks[i - 1]['source']}"
        for i in sorted(indices)
        if 1 <= i <= len(chunks)
    ]


def analysis_agent(state: AgentState) -> AgentState:
    """
    Draft a cited compliance response from retrieved chunks.
    Flags the response as uncited if no [N] markers are found.
    Writes input/output to the audit log.
    """
    question: str = state["question"]
    chunks: list[dict[str, Any]] = state["retrieved_chunks"]

    if not chunks:
        logger.warning("%s: no retrieved chunks — cannot draft response", AGENT_NAME)
        return {
            "draft_response": "No relevant documents were found to answer this question.",
            "citations": [],
            "is_cited": False,
        }

    context = _format_context(chunks)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=HUMAN_TEMPLATE.format(question=question, context=context)),
    ]

    logger.info("%s: calling LLM", AGENT_NAME)
    response = _chat_model().invoke(messages)
    response_text: str = response.content

    citations = _extract_citations(response_text, chunks)
    is_cited = len(citations) > 0
    if not is_cited:
        logger.warning("%s: response contains no citations", AGENT_NAME)

    write_audit_log(
        agent_name=AGENT_NAME,
        step_type="generation",
        input_data={"question": question, "chunks_used": len(chunks)},
        output_data={
            "response_length": len(response_text),
            "citations_found": len(citations),
            "is_cited": is_cited,
        },
        decision="draft_generated",
    )

    return {
        "draft_response": response_text,
        "citations": citations,
        "is_cited": is_cited,
    }
