"""FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Regulatory Intelligence Agent",
    description="Governed multi-agent system for regulatory intelligence",
    version="0.1.0",
)


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


_UI_PATH = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    return HTMLResponse(content=_UI_PATH.read_text())


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse, tags=["query"])
async def query(request: QueryRequest) -> QueryResponse:
    """
    Run a compliance question through the full agent graph.
    Returns a cited response grounded in the retrieved regulatory documents.
    """
    from src.graph import graph  # deferred import keeps startup fast if graph isn't used

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    initial_state: dict = {
        "question": request.question,
        "top_k": request.top_k,
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
        question=request.question,
        response=result.get("draft_response", ""),
        citations=result.get("citations", []),
        is_cited=result.get("is_cited", False),
    )


@app.post("/propose", response_model=ProposeResponse, tags=["query"])
async def propose(request: QueryRequest) -> ProposeResponse:
    """
    Run the full 3-agent pipeline (Knowledge → Analysis → Action) and return the
    proposed GitHub issue. The proposal is NEVER executed via this endpoint —
    execution requires human approval via the CLI HITL gate.
    """
    from src.graph import propose_graph

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    initial_state: dict = {
        "question": request.question,
        "top_k": request.top_k,
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

    import json as _json
    raw_proposal = result.get("proposed_action", "{}")
    try:
        proposal = _json.loads(raw_proposal) if isinstance(raw_proposal, str) else raw_proposal
    except Exception:
        proposal = {}

    return ProposeResponse(
        question=request.question,
        response=result.get("draft_response", ""),
        citations=result.get("citations", []),
        is_cited=result.get("is_cited", False),
        proposed_action=proposal,
    )


if __name__ == "__main__":
    import uvicorn
    from src.config import settings

    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
