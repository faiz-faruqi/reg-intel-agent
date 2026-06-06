"""LangGraph definition: supervisor + Knowledge Agent + Analysis Agent."""

import logging

from langgraph.graph import END, StateGraph

from src.agents.analysis_agent import analysis_agent
from src.agents.knowledge_agent import knowledge_agent
from src.agents.supervisor import supervisor
from src.state import AgentState

logger = logging.getLogger(__name__)


def _route(state: AgentState) -> str:
    """Extract the routing decision set by the supervisor node."""
    return state["next"]


def build_graph() -> StateGraph:
    """Assemble and compile the regulatory intelligence graph."""
    builder = StateGraph(AgentState)

    builder.add_node("supervisor", supervisor)
    builder.add_node("knowledge_agent", knowledge_agent)
    builder.add_node("analysis_agent", analysis_agent)

    builder.set_entry_point("supervisor")

    builder.add_conditional_edges(
        "supervisor",
        _route,
        {
            "knowledge_agent": "knowledge_agent",
            "analysis_agent": "analysis_agent",
            END: END,
        },
    )

    # After each agent finishes, return to the supervisor for the next routing decision
    builder.add_edge("knowledge_agent", "supervisor")
    builder.add_edge("analysis_agent", "supervisor")

    return builder.compile()


# Module-level singleton — imported by main.py and tests
graph = build_graph()
