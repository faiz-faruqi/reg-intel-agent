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


if __name__ == "__main__":
    import uvicorn
    from src.config import settings

    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
