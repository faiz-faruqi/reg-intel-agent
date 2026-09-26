"""Database layer: pgvector document store and append-only audit log."""

import json
import logging
import secrets
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from src.config import settings

logger = logging.getLogger(__name__)

# Convert asyncpg URL scheme to psycopg2-compatible scheme
def _sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a psycopg2 connection with the pgvector type registered."""
    conn = psycopg2.connect(_sync_url())
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Document store
# ---------------------------------------------------------------------------

def store_document(title: str, content: str, source: str, embedding: list[float]) -> int:
    """Insert a document + its embedding. Returns the new row id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (title, content, source, embedding)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (title, content, source, embedding),
            )
            row = cur.fetchone()
            return row[0]


def similarity_search(query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    """Return the top_k documents closest to query_embedding by cosine similarity."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, content, source,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, top_k),
            )
            return [dict(row) for row in cur.fetchall()]


def keyword_search(query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Return the top_k documents ranked by Postgres full-text search (ts_rank)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, content, source,
                       ts_rank(content_tsv, plainto_tsquery('english', %s)) AS similarity
                FROM documents
                WHERE content_tsv @@ plainto_tsquery('english', %s)
                ORDER BY similarity DESC
                LIMIT %s
                """,
                (query_text, query_text, top_k),
            )
            return [dict(row) for row in cur.fetchall()]


def _reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]], top_k: int, k: int = 60
) -> list[dict[str, Any]]:
    """
    Merge multiple ranked result lists (e.g. vector + keyword) by Reciprocal
    Rank Fusion: score = sum(1 / (k + rank)) across lists a document appears
    in. RRF combines *rank position* rather than raw scores, sidestepping the
    problem of normalizing cosine similarity and ts_rank onto the same scale.
    """
    fused: dict[int, float] = {}
    rows: dict[int, dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            doc_id = row["id"]
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            rows.setdefault(doc_id, row)

    ordered_ids = sorted(fused, key=lambda doc_id: fused[doc_id], reverse=True)[:top_k]
    results = []
    for doc_id in ordered_ids:
        row = dict(rows[doc_id])
        row["similarity"] = fused[doc_id]
        results.append(row)
    return results


def hybrid_search(query_embedding: list[float], query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    Retrieve by fusing pgvector cosine search and Postgres full-text search
    (Reciprocal Rank Fusion). See ADR-007 for why RRF over score-blending.
    """
    candidates = max(top_k * 3, top_k)
    vector_hits = similarity_search(query_embedding, top_k=candidates)
    keyword_hits = keyword_search(query_text, top_k=candidates)
    return _reciprocal_rank_fusion([vector_hits, keyword_hits], top_k=top_k)


def document_count() -> int:
    """Return the total number of documents in the store."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Audit log (append-only — DELETE and UPDATE are blocked by DB triggers)
# ---------------------------------------------------------------------------

def write_audit_log(
    agent_name: str,
    step_type: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    tool_call: str | None = None,
    decision: str | None = None,
    approved: bool | None = None,
) -> None:
    """Append one record to the audit log. Never updates or deletes."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log
                    (agent_name, step_type, tool_call, input, output, decision, approved)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    agent_name,
                    step_type,
                    tool_call,
                    json.dumps(input_data),
                    json.dumps(output_data),
                    decision,
                    approved,
                ),
            )
    logger.debug("audit_log: agent=%s step=%s", agent_name, step_type)


# ---------------------------------------------------------------------------
# Per-session usage budget (caps LLM cost / deters misuse)
# ---------------------------------------------------------------------------

_session_table_ready = False


def _ensure_session_usage_table(cur: Any) -> None:
    """Create the session_usage table on first use (idempotent, per-process)."""
    global _session_table_ready
    if _session_table_ready:
        return
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS session_usage (
            sid          TEXT PRIMARY KEY,
            action_count INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    _session_table_ready = True


def increment_session_usage(sid: str, limit: int) -> tuple[bool, int]:
    """
    Atomically bump the action counter for a login session.

    Returns (allowed, count). `allowed` is False once the session has already
    reached `limit`; in that case the counter is NOT incremented further.
    The increment is a single statement so concurrent calls cannot race past
    the cap.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_session_usage_table(cur)
            cur.execute(
                """
                INSERT INTO session_usage (sid, action_count)
                VALUES (%s, 1)
                ON CONFLICT (sid) DO UPDATE
                    SET action_count = session_usage.action_count + 1,
                        updated_at = now()
                    WHERE session_usage.action_count < %s
                RETURNING action_count
                """,
                (sid, limit),
            )
            row = cur.fetchone()
            if row is None:
                # Row exists and is already at the cap → blocked, no increment.
                return False, limit
            return True, row[0]


# ---------------------------------------------------------------------------
# Demo visitor email capture
# ---------------------------------------------------------------------------

def store_signup(email: str, ip_address: str | None = None) -> None:
    """Insert a demo visitor email into demo_signups."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO demo_signups (email, ip_address) VALUES (%s, %s)",
                (email, ip_address),
            )
    logger.debug("demo_signup: %s", email)


# ---------------------------------------------------------------------------
# Time-limited access code (single active code, admin-generated)
# ---------------------------------------------------------------------------

_access_code_table_ready = False


def _ensure_access_code_table(cur: Any) -> None:
    """Create the access_code table on first use (idempotent, per-process)."""
    global _access_code_table_ready
    if _access_code_table_ready:
        return
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS access_code (
            id         INTEGER PRIMARY KEY DEFAULT 1,
            code       TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT access_code_single_row CHECK (id = 1)
        )
        """
    )
    _access_code_table_ready = True


def generate_access_code(ttl_hours: float) -> tuple[str, str]:
    """
    Create a new access code, replacing whichever one was active before —
    there is only ever one valid code at a time. Returns (code, expires_at_iso).
    """
    code = secrets.token_urlsafe(9)
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_access_code_table(cur)
            cur.execute(
                """
                INSERT INTO access_code (id, code, expires_at, created_at)
                VALUES (1, %s, now() + %s * interval '1 hour', now())
                ON CONFLICT (id) DO UPDATE
                    SET code = EXCLUDED.code,
                        expires_at = EXCLUDED.expires_at,
                        created_at = EXCLUDED.created_at
                RETURNING expires_at
                """,
                (code, ttl_hours),
            )
            row = cur.fetchone()
            return code, row[0].isoformat()


def verify_access_code(code: str) -> bool:
    """
    Check whether `code` matches the currently active, non-expired access code.
    Fails closed: any DB error is treated as invalid — never fail open on auth.
    """
    if not code:
        return False
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _ensure_access_code_table(cur)
                cur.execute("SELECT code FROM access_code WHERE id = 1 AND expires_at > now()")
                row = cur.fetchone()
                return row is not None and row[0] == code
    except Exception:
        logger.exception("verify_access_code: DB error, failing closed")
        return False
