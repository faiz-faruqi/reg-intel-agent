"""Shared LangGraph state schema."""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    question: str
    top_k: int
    retrieved_chunks: list[dict]
    draft_response: str
    citations: list[str]
    is_cited: bool
    next: str
