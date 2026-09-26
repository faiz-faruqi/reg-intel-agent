"""
Add full-text search support to an existing `documents` table.

`init-db.sql` only runs against a fresh database. This migrates a live one
(e.g. the deployed Neon instance, which already has seeded rows) by adding
the generated tsvector column + GIN index idempotently — safe to run more
than once, and safe to run against a table that already has data (no
embedding dimension change, no reseed required). See ADR-007.

Usage:
    DATABASE_URL=postgresql://... python scripts/migrate_add_fts.py
"""

import logging
import os
import sys

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

MIGRATION_SQL = """
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS documents_content_tsv_idx ON documents USING gin (content_tsv);
"""


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.error("DATABASE_URL is not set.")
        sys.exit(1)

    # psycopg2 doesn't understand the asyncpg URL scheme used elsewhere in this app.
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()
        logger.info("content_tsv column + GIN index are present.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
