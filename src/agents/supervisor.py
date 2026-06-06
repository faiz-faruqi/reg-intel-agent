"""Supervisor node: routes between Knowledge Agent and Analysis Agent."""

import logging

from langgraph.graph import END

from src.state import AgentState

logger = logging.getLogger(__name__)


def supervisor(state: AgentState) -> AgentState:
    """
    Readonly routing: knowledge → analysis → END.
    Used by the API graph (Phase 1 compatible).
    """
    if not state.get("retrieved_chunks"):
        next_node = "knowledge_agent"
    elif not state.get("draft_response"):
        next_node = "analysis_agent"
    else:
        next_node = END

    logger.debug("supervisor: routing to %s", next_node)
    return {"next": next_node}


def full_supervisor(state: AgentState) -> AgentState:
    """
    Full routing: knowledge → analysis → action → END.
    Used by the CLI graph (Phase 2 with HITL).
    """
    if not state.get("retrieved_chunks"):
        next_node = "knowledge_agent"
    elif not state.get("draft_response"):
        next_node = "analysis_agent"
    elif not state.get("proposed_action"):
        next_node = "action_agent"
    else:
        next_node = END

    logger.debug("full_supervisor: routing to %s", next_node)
    return {"next": next_node}
