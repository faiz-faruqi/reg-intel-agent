"""
Interactive CLI runner for the full Phase 2 governance workflow.

Usage:
    python3 -m src.cli "What are the GDPR data minimisation requirements?"

Flow:
    1. Input guardrail check
    2. Knowledge Agent → retrieval
    3. Analysis Agent → cited draft
    4. Output guardrail check on draft
    5. Action Agent → proposes GitHub issue
    6. Human approval gate (CLI prompt) — graph pauses here
    7. If approved: create GitHub issue, write audit log
    8. If rejected: write rejection to audit log
"""

import json
import logging
import sys

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.action_agent import action_agent
from src.agents.analysis_agent import analysis_agent
from src.agents.knowledge_agent import knowledge_agent
from src.agents.supervisor import full_supervisor
from src.db import write_audit_log
from src.guardrails import check_input, check_output
from src.state import AgentState
from src.tools.github_tool import create_github_issue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SEPARATOR = "=" * 60


# ---------------------------------------------------------------------------
# HITL gate and execute nodes (CLI graph only)
# ---------------------------------------------------------------------------

def human_gate(state: AgentState) -> AgentState:
    """
    Reads action_approved from state (set by the CLI before graph resumes).
    Writes the approval decision to the audit log.
    """
    approved = state.get("action_approved", False)
    write_audit_log(
        agent_name="human_gate",
        step_type="approval",
        input_data={"proposed_action": state.get("proposed_action", "")},
        output_data={"decision": "approve" if approved else "reject"},
        decision="approve" if approved else "reject",
        approved=approved,
    )
    return {}


def _route_after_gate(state: AgentState) -> str:
    return "execute_action" if state.get("action_approved") else END


def execute_action(state: AgentState) -> AgentState:
    """Create the GitHub issue after human approval."""
    proposal = json.loads(state.get("proposed_action", "{}"))
    try:
        result = create_github_issue(
            title=proposal.get("title", "Compliance Gap"),
            body=proposal.get("body", ""),
            labels=proposal.get("labels", ["compliance-gap"]),
        )
        write_audit_log(
            agent_name="execute_action",
            step_type="tool_call",
            input_data={"proposal": proposal},
            output_data=result,
            tool_call="github_issue",
            decision="executed",
            approved=True,
        )
        return {"action_result": result.get("url", "created")}
    except Exception as exc:
        logger.error("Failed to create GitHub issue: %s", exc)
        write_audit_log(
            agent_name="execute_action",
            step_type="tool_call",
            input_data={"proposal": proposal},
            output_data={"error": str(exc)},
            tool_call="github_issue",
            decision="error",
            approved=True,
        )
        return {"action_result": f"error: {exc}"}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _route(state: AgentState) -> str:
    return state["next"]


def build_cli_graph():
    """Full governance graph with HITL — pauses before human_gate."""
    checkpointer = MemorySaver()
    builder = StateGraph(AgentState)

    builder.add_node("supervisor", full_supervisor)
    builder.add_node("knowledge_agent", knowledge_agent)
    builder.add_node("analysis_agent", analysis_agent)
    builder.add_node("action_agent", action_agent)
    builder.add_node("human_gate", human_gate)
    builder.add_node("execute_action", execute_action)

    builder.set_entry_point("supervisor")
    builder.add_conditional_edges("supervisor", _route, {
        "knowledge_agent": "knowledge_agent",
        "analysis_agent": "analysis_agent",
        "action_agent": "action_agent",
        END: END,
    })
    builder.add_edge("knowledge_agent", "supervisor")
    builder.add_edge("analysis_agent", "supervisor")
    # action_agent bypasses supervisor → go straight to HITL gate
    builder.add_edge("action_agent", "human_gate")
    builder.add_conditional_edges("human_gate", _route_after_gate, {
        "execute_action": "execute_action",
        END: END,
    })
    builder.add_edge("execute_action", END)

    # interrupt_before pauses execution just before human_gate runs
    return builder.compile(checkpointer=checkpointer, interrupt_before=["human_gate"])


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(question: str, top_k: int = 5) -> None:
    # 1. Input guardrail
    guard_in = check_input(question)
    if not guard_in.allowed:
        print(f"\n[GUARDRAIL BLOCKED — INPUT]\n{guard_in.reason}")
        write_audit_log(
            agent_name="guardrail",
            step_type="input_check",
            input_data={"question": question},
            output_data={"blocked": True, "reason": guard_in.reason},
            decision="blocked",
            approved=False,
        )
        return

    graph = build_cli_graph()
    config = {"configurable": {"thread_id": "cli-session"}}
    initial_state: AgentState = {
        "question": question,
        "top_k": top_k,
        "retrieved_chunks": [],
        "draft_response": "",
        "citations": [],
        "is_cited": False,
        "next": "",
    }

    print(f"\n{_SEPARATOR}")
    print("REGULATORY INTELLIGENCE AGENT — FULL GOVERNANCE WORKFLOW")
    print(_SEPARATOR)
    print(f"Question: {question}\n")

    # 2. Run graph — stops before human_gate
    print("[Phase 1 + 2] Retrieving context, drafting response, generating proposal...")
    graph.invoke(initial_state, config)

    # 3. Inspect state after pause
    snapshot = graph.get_state(config)
    state_values = snapshot.values

    # 4. Output guardrail on draft
    draft = state_values.get("draft_response", "")
    guard_out = check_output(draft)
    if not guard_out.allowed:
        print(f"\n[GUARDRAIL BLOCKED — OUTPUT]\n{guard_out.reason}")
        write_audit_log(
            agent_name="guardrail",
            step_type="output_check",
            input_data={"draft_length": len(draft)},
            output_data={"blocked": True, "reason": guard_out.reason},
            decision="blocked",
            approved=False,
        )
        return

    # 5. Display analysis
    print(f"\n{_SEPARATOR}")
    print("ANALYSIS")
    print(_SEPARATOR)
    print(draft)
    if state_values.get("citations"):
        print("\nCITATIONS")
        for c in state_values["citations"]:
            print(f"  {c}")
    if not state_values.get("is_cited"):
        print("\n[WARNING] Response contains no inline citations.")

    # 6. Display proposed action
    proposed_raw = state_values.get("proposed_action", "{}")
    proposal = json.loads(proposed_raw)
    print(f"\n{_SEPARATOR}")
    print("PROPOSED ACTION (GitHub Issue)")
    print(_SEPARATOR)
    print(f"Title:  {proposal.get('title', 'N/A')}")
    print(f"Labels: {proposal.get('labels', [])}")
    print(f"\nBody:\n{proposal.get('body', 'N/A')}")

    # 7. Human approval gate
    print(f"\n{_SEPARATOR}")
    raw = input("Approve this action? (approve / reject): ").strip().lower()
    approved = raw == "approve"

    # 8. Inject decision and resume
    graph.update_state(config, {"action_approved": approved})
    graph.invoke(None, config)

    # 9. Final result
    final = graph.get_state(config).values
    result = final.get("action_result", "")
    print(f"\n{_SEPARATOR}")
    if result == "rejected" or not approved:
        print("REJECTED — no action taken. Decision recorded in audit log.")
    elif result.startswith("error"):
        print(f"ERROR — {result}")
    else:
        print(f"EXECUTED — GitHub issue created: {result}")
    print(_SEPARATOR)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m src.cli 'Your compliance question here'")
        sys.exit(1)
    run(" ".join(sys.argv[1:]))
