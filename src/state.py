"""Shared LangGraph state schema."""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Phase 1 — read-only pipeline
    question: str
    top_k: int
    retrieved_chunks: list[dict]
    draft_response: str
    citations: list[str]
    is_cited: bool
    next: str
    # Phase 2 — governance layer
    guardrail_blocked: bool
    guardrail_reason: str
    proposed_action: str   # JSON string: {title, body, labels}
    action_approved: bool  # set by CLI before graph resumes
    action_result: str     # GitHub issue URL or "rejected"
