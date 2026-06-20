"""FastAPI application entry point."""

import json as _json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Regulatory Intelligence Agent",
    description="Governed multi-agent system for regulatory intelligence",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class QueryResponse(BaseModel):
    question: str
    response: str
    citations: list[str]
    is_cited: bool


class ProposeResponse(BaseModel):
    question: str
    response: str
    citations: list[str]
    is_cited: bool
    proposed_action: dict  # {title, body, labels} — never executed via API


class ExecuteRequest(BaseModel):
    title: str
    body: str
    labels: list[str] = []


class ExecuteResponse(BaseModel):
    key: str    # Jira issue key (e.g. COMP-12) or GitHub issue number as string
    url: str
    title: str
    backend: str  # "jira" or "github"


class RejectRequest(BaseModel):
    title: str


class SignupRequest(BaseModel):
    email: str


_UI_PATH = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    return HTMLResponse(content=_UI_PATH.read_text())


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse, tags=["query"])
@limiter.limit("10/minute;20/day")
async def query(request: Request, body: QueryRequest) -> QueryResponse:
    """
    Run a compliance question through the Knowledge + Analysis agents.
    Rate limited: 10/minute, 30/day per IP.
    """
    from src.graph import graph

    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    initial_state: dict = {
        "question": body.question,
        "top_k": body.top_k,
        "retrieved_chunks": [],
        "draft_response": "",
        "citations": [],
        "is_cited": False,
        "next": "",
    }

    try:
        result = graph.invoke(initial_state)
    except Exception as exc:
        logger.exception("graph invocation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent graph failed. See server logs.")

    return QueryResponse(
        question=body.question,
        response=result.get("draft_response", ""),
        citations=result.get("citations", []),
        is_cited=result.get("is_cited", False),
    )


@app.post("/propose", response_model=ProposeResponse, tags=["query"])
@limiter.limit("5/minute;10/day")
async def propose(request: Request, body: QueryRequest) -> ProposeResponse:
    """
    Run the full 3-agent pipeline (Knowledge → Analysis → Action) and return the
    proposed GitHub issue. The proposal is NEVER executed via this endpoint —
    execution requires human approval via the CLI HITL gate.
    Rate limited: 5/minute, 15/day per IP.
    """
    from src.graph import propose_graph

    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    initial_state: dict = {
        "question": body.question,
        "top_k": body.top_k,
        "retrieved_chunks": [],
        "draft_response": "",
        "citations": [],
        "is_cited": False,
        "next": "",
    }

    try:
        result = propose_graph.invoke(initial_state)
    except Exception as exc:
        logger.exception("propose graph invocation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent graph failed. See server logs.")

    raw_proposal = result.get("proposed_action", "{}")
    try:
        proposal = _json.loads(raw_proposal) if isinstance(raw_proposal, str) else raw_proposal
    except Exception:
        proposal = {}

    return ProposeResponse(
        question=body.question,
        response=result.get("draft_response", ""),
        citations=result.get("citations", []),
        is_cited=result.get("is_cited", False),
        proposed_action=proposal,
    )


@app.post("/execute", response_model=ExecuteResponse, tags=["governance"])
@limiter.limit("2/minute;5/day")
async def execute(request: Request, body: ExecuteRequest) -> ExecuteResponse:
    """
    Human-approved execution: create a ticket in the configured backend (Jira or GitHub).
    Rate limited: 2/minute, 5/day per IP.
    Only called after the user explicitly clicks Approve in the UI.
    """
    from src.config import settings
    from src.db import write_audit_log

    backend = settings.TICKET_BACKEND.lower()

    try:
        if backend == "jira":
            from src.tools.jira_tool import create_jira_issue
            result = create_jira_issue(
                title=body.title,
                body=body.body,
                labels=body.labels or [],
            )
            key = result["key"]
        else:
            from src.tools.github_tool import create_github_issue
            result = create_github_issue(
                title=body.title,
                body=body.body,
                labels=body.labels or [],
            )
            key = str(result["number"])

        write_audit_log(
            agent_name="ui_hitl_gate",
            step_type="tool_call",
            input_data={"title": body.title, "labels": body.labels, "backend": backend},
            output_data=result,
            tool_call=f"{backend}_issue",
            decision="approve",
            approved=True,
        )
        return ExecuteResponse(key=key, url=result["url"], title=body.title, backend=backend)

    except Exception as exc:
        logger.exception("/execute failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/reject", tags=["governance"])
@limiter.limit("5/minute;10/day")
async def reject(request: Request, body: RejectRequest) -> dict[str, str]:
    """
    Record a human rejection in the audit log. No ticket is created.
    Rate limited: 5/minute, 10/day per IP.
    """
    from src.db import write_audit_log

    write_audit_log(
        agent_name="ui_hitl_gate",
        step_type="approval",
        input_data={"title": body.title},
        output_data={"decision": "reject"},
        decision="reject",
        approved=False,
    )
    return {"status": "rejected", "message": "Decision recorded in audit log."}


@app.post("/signup", tags=["demo"])
@limiter.limit("1/minute;3/day")
async def signup(request: Request, body: SignupRequest) -> dict[str, str]:
    """
    Capture a demo visitor's email. Stored in demo_signups table.
    Rate limited: 1/minute, 3/day per IP.
    """
    from src.db import store_signup
    store_signup(email=body.email, ip_address=request.client.host if request.client else None)
    return {"status": "ok", "message": "Thanks — you're on the list."}


_EVAL_CASES = [
    {"question": "What are the GDPR data minimisation requirements?",            "expected": ["GDPR"]},
    {"question": "What are the Basel III minimum capital adequacy requirements?", "expected": ["Basel"]},
    {"question": "What does OSFI E-23 require for model validation?",            "expected": ["E-23"]},
    {"question": "What are the PIPEDA consent requirements for personal data?",  "expected": ["PIPEDA"]},
]


def _eval_invoke(question: str, expected: list[str]) -> dict:
    """Run one eval case synchronously. Imported graph is cached after first /query."""
    from src.graph import graph

    state: dict = {
        "question": question, "top_k": 5,
        "retrieved_chunks": [], "draft_response": "",
        "citations": [], "is_cited": False, "next": "",
    }
    try:
        result = graph.invoke(state)
        cited = result.get("is_cited", False)
        citations = result.get("citations", [])
        source_hit = any(kw.lower() in " ".join(citations).lower() for kw in expected)
        status = "PASS" if (cited and source_hit) else ("WRONG_SRC" if cited else "FAIL")
        return {"question": question, "cited": cited, "source_hit": source_hit,
                "status": status, "citations": citations[:3], "error": None}
    except Exception as exc:
        return {"question": question, "cited": False, "source_hit": False,
                "status": "ERROR", "citations": [], "error": str(exc)[:120]}


@app.post("/eval", tags=["evaluation"])
@limiter.limit("1/minute;2/day")
def run_eval(request: Request) -> dict:
    """
    Run 4 representative compliance questions through the live agent pipeline and score
    faithfulness (cited AND correct source). Sync endpoint — FastAPI runs it in a thread
    pool so the event loop stays free. Expect 1-3 min to complete.
    Rate limited: 1/minute, 2/day per IP.
    """
    cases_out = [_eval_invoke(c["question"], c["expected"]) for c in _EVAL_CASES]
    n = len(cases_out)
    n_pass = sum(1 for r in cases_out if r["status"] == "PASS")
    return {
        "cases": cases_out,
        "summary": {
            "total": n,
            "passed": n_pass,
            "cited": sum(1 for r in cases_out if r["cited"]),
            "faithful_pct": round(n_pass / n, 3) if n else 0,
        },
    }


class SignupRequest(BaseModel):
    email: str


if __name__ == "__main__":
    import uvicorn

    from src.config import settings

    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
