"""FastAPI application entry point."""

import json as _json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config import settings

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Regulatory Intelligence Agent",
    description="Governed multi-agent system for regulatory intelligence",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Session management (signed cookies, no database) ──────────────────
_SESSION_COOKIE = "regintel_session"
_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="regintel-auth")
# Railway injects RAILWAY_ENVIRONMENT for every deployed service; absent locally.
# Used to mark the session cookie Secure only where we know traffic is HTTPS.
_IS_DEPLOYED = "RAILWAY_ENVIRONMENT" in os.environ


def create_session_cookie(response: Response) -> Response:
    """Attach a signed session cookie to the response (24h expiry).

    Each session gets a unique `sid` used to track its metered-action budget
    server-side. A fresh sign-in mints a new sid and therefore a fresh budget.
    """
    token = _serializer.dumps(
        {
            "user": "demo",
            "sid": uuid.uuid4().hex,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_IS_DEPLOYED,  # HTTPS-only on Railway; plain HTTP allowed for local dev
        path="/",
    )
    return response


def get_session(request: Request) -> dict | None:
    """Return the decoded session payload, or None if missing/invalid/expired."""
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=settings.SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def verify_session(request: Request) -> bool:
    """Check if the request has a valid (non-expired) session cookie."""
    return get_session(request) is not None


def require_session(request: Request) -> dict:
    """Return the session payload or raise 401. Guards the API endpoints so the
    login gate actually protects LLM cost — not just the UI."""
    session = get_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return session


def _enforce_session_budget(session: dict, response: Response) -> None:
    """Charge one metered action against the session's budget. Raises 429 when
    the per-session limit is reached. Adds usage headers for the UI."""
    sid = session.get("sid")
    limit = settings.SESSION_ACTION_LIMIT
    if not sid:
        # Legacy cookie minted before sids existed — cannot meter; expires in 24h.
        return
    from src.db import increment_session_usage

    allowed, count = increment_session_usage(sid, limit)
    response.headers["X-Session-Limit"] = str(limit)
    response.headers["X-Session-Used"] = str(count)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Session limit reached — you've used all {limit} requests for this "
                f"session. Sign out and sign back in to continue, or contact Faiz "
                f"for extended access."
            ),
        )


def clear_session_cookie(response: Response) -> Response:
    """Delete the session cookie."""
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return response


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class QueryResponse(BaseModel):
    question: str
    response: str
    citations: list[str]
    is_cited: bool
    retrieval_mode: str  # "vector" or "hybrid" — see RETRIEVAL_MODE, ADR-007


class ProposeResponse(BaseModel):
    question: str
    response: str
    citations: list[str]
    is_cited: bool
    proposed_action: dict  # {title, body, labels} — never executed via API
    retrieval_mode: str  # "vector" or "hybrid" — see RETRIEVAL_MODE, ADR-007


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


class SignInRequest(BaseModel):
    username: str
    password: str
    access_code: str = ""


class GenerateCodeRequest(BaseModel):
    ttl_hours: float = settings.ACCESS_CODE_DEFAULT_TTL_HOURS


_UI_PATH = Path(__file__).parent / "static" / "index.html"
_LOGIN_PATH = Path(__file__).parent / "static" / "login.html"
_MRA_REPORT_PATH = Path(__file__).parent / "static" / "mra-report.pdf"


# ── Auth routes ────────────────────────────────────────────────────────
@app.get("/auth/signin", response_class=HTMLResponse, include_in_schema=False)
async def signin_page(request: Request) -> HTMLResponse:
    """Serve the login page. Redirect to / if already authenticated."""
    if verify_session(request):
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=_LOGIN_PATH.read_text())


@app.post("/auth/signin", tags=["auth"])
@limiter.limit("5/minute;15/day")
async def signin_submit(request: Request, body: SignInRequest) -> JSONResponse:
    """
    Validate credentials and set a signed session cookie.
    Rate limited: 5/minute, 15/day per IP.
    """
    from src.db import verify_access_code

    # Validate username & password
    valid_user = body.username == settings.DEMO_USERNAME and body.password == settings.DEMO_PASSWORD

    # Validate the time-limited access code (checked against the DB, fails closed)
    valid_code = verify_access_code(body.access_code)

    if not (valid_user and valid_code):
        return JSONResponse(
            status_code=401,
            content={"ok": False, "detail": "Invalid credentials or access code."},
        )

    # Success — set session cookie
    response = JSONResponse(content={"ok": True, "redirect": "/"})
    create_session_cookie(response)
    return response


@app.post("/auth/generate-code", tags=["auth"])
async def generate_code(
    body: GenerateCodeRequest, x_admin_key: str = Header(default="")
) -> JSONResponse:
    """
    Admin-only: create a new access code, retiring whichever one was active
    before — there is only ever one valid code at a time.
    """
    if not settings.ADMIN_KEY:
        raise HTTPException(status_code=503, detail="Admin key not configured.")
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key.")

    from src.db import generate_access_code

    code, expires_at = generate_access_code(body.ttl_hours)
    return JSONResponse(
        content={"code": code, "expires_at": expires_at, "ttl_hours": body.ttl_hours}
    )


@app.post("/auth/signout", tags=["auth"])
async def signout() -> JSONResponse:
    """Clear the session cookie and return success."""
    response = JSONResponse(content={"ok": True})
    clear_session_cookie(response)
    return response


# ── Protected root route ───────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def root(request: Request) -> HTMLResponse | RedirectResponse:
    if not verify_session(request):
        return RedirectResponse(url="/auth/signin", status_code=302)
    return HTMLResponse(content=_UI_PATH.read_text())


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint. Also surfaces retrieval_mode so the UI can
    reflect the active config without a query round-trip."""
    return {"status": "ok", "retrieval_mode": settings.RETRIEVAL_MODE}


@app.get("/mra-report.pdf", include_in_schema=False)
async def mra_report() -> FileResponse:
    """Serve the static Model Risk Assessment report (Assurance section download)."""
    return FileResponse(
        _MRA_REPORT_PATH,
        media_type="application/pdf",
        filename="model-risk-assessment.pdf",
    )


@app.post("/query", response_model=QueryResponse, tags=["query"])
@limiter.limit("10/minute;20/day")
async def query(request: Request, body: QueryRequest, response: Response) -> QueryResponse:
    """
    Run a compliance question through the Knowledge + Analysis agents.
    Requires a valid session. Rate limited 10/minute, 20/day per IP, and capped
    at SESSION_ACTION_LIMIT metered actions per login session.
    """
    from src.graph import graph

    session = require_session(request)

    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    _enforce_session_budget(session, response)

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
        retrieval_mode=settings.RETRIEVAL_MODE,
    )


@app.post("/propose", response_model=ProposeResponse, tags=["query"])
@limiter.limit("5/minute;10/day")
async def propose(request: Request, body: QueryRequest, response: Response) -> ProposeResponse:
    """
    Run the full 3-agent pipeline (Knowledge → Analysis → Action) and return the
    proposed GitHub issue. The proposal is NEVER executed via this endpoint —
    execution requires human approval via the CLI HITL gate.
    Requires a valid session. Rate limited 5/minute, 10/day per IP, and capped
    at SESSION_ACTION_LIMIT metered actions per login session.
    """
    from src.graph import propose_graph

    session = require_session(request)

    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    _enforce_session_budget(session, response)

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
        retrieval_mode=settings.RETRIEVAL_MODE,
    )


@app.post("/execute", response_model=ExecuteResponse, tags=["governance"])
@limiter.limit("2/minute;5/day")
async def execute(request: Request, body: ExecuteRequest) -> ExecuteResponse:
    """
    Human-approved execution: create a ticket in the configured backend (Jira or GitHub).
    Rate limited: 2/minute, 5/day per IP.
    Only called after the user explicitly clicks Approve in the UI.
    """
    from src.db import write_audit_log

    require_session(request)

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

    require_session(request)

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
