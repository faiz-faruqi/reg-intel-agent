"""Database layer: pgvector document store and append-only audit log."""

import json
import logging
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
