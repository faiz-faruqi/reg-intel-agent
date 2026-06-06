"""Supervisor node: routes between Knowledge Agent and Analysis Agent."""

import logging

from langgraph.graph import END

from src.state import AgentState

logger = logging.getLogger(__name__)


def supervisor(state: AgentState) -> AgentState:
    """
    Decide which agent to call next based on what is already in state.

    Routing logic:
      no retrieved_chunks        → knowledge_agent
      chunks but no draft        → analysis_agent
      draft present              → END
    """
    if not state.get("retrieved_chunks"):
        next_node = "knowledge_agent"
    elif not state.get("draft_response"):
        next_node = "analysis_agent"
    else:
        next_node = END

    logger.debug("supervisor: routing to %s", next_node)
    return {"next": next_node}
