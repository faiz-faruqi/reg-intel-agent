"""
Ingestion script: embed and store the three seed documents in pgvector.

Sources:
  1+2. data/seed_documents.json       — GDPR Articles 5/13/17, ISO 27001 A.8
  3.   docs/seed-data/cloudkraft-ai-governance.txt — CloudKraft AI Governance
       (HTML source; text is extracted before embedding)

Run once before the first query:
    python -m src.ingest
"""

import json
import logging
import sys
from html.parser import HTMLParser
from pathlib import Path

from langchain_openai import OpenAIEmbeddings

from src.config import settings
from src.db import document_count, store_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEED_JSON = Path(__file__).parent.parent / "data" / "seed_documents.json"
CLOUDKRAFT_TXT = Path(__file__).parent.parent / "docs" / "seed-data" / "cloudkraft-ai-governance.txt"


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    """Extract visible text from HTML, skipping <style> and <script> blocks."""

    _SKIP_TAGS = {"style", "script", "head"}
    _BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "td", "br", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip: bool = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip = True
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        _entities = {"ldquo": """, "rdquo": """, "mdash": "—",
                     "ndash": "–", "amp": "&", "lt": "<", "gt": ">",
                     "copy": "©", "trade": "™", "middot": "·"}
        if not self._skip:
            self._parts.append(_entities.get(name, ""))

    def get_text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _html_to_text(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


# ---------------------------------------------------------------------------
# Document loaders
# ---------------------------------------------------------------------------

def _load_json_docs() -> list[dict]:
    return json.loads(SEED_JSON.read_text())


def _load_cloudkraft_doc() -> dict:
    raw_html = CLOUDKRAFT_TXT.read_text(encoding="utf-8")
    text = _html_to_text(raw_html)
    return {
        "title": "CloudKraft AI Governance — Diagnostic Assessment Framework",
        "source": "CloudKraft Consulting Inc., Tier 1 Advisory Services (2026)",
        "content": text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set — cannot create embeddings")
        sys.exit(1)

    docs = _load_json_docs() + [_load_cloudkraft_doc()]
    logger.info("Loaded %d documents total", len(docs))

    existing = document_count()
    if existing > 0:
        logger.warning(
            "%d documents already in the table. Re-running will create duplicates. "
            "Truncate the documents table first if you want a clean seed.",
            existing,
        )

    embeddings_model = OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )

    texts = [doc["content"] for doc in docs]
    logger.info("Embedding %d documents with model=%s ...", len(texts), settings.EMBEDDING_MODEL)
    vectors = embeddings_model.embed_documents(texts)

    for doc, vector in zip(docs, vectors):
        doc_id = store_document(
            title=doc["title"],
            content=doc["content"],
            source=doc["source"],
            embedding=vector,
        )
        logger.info("  stored doc_id=%d  title=%s", doc_id, doc["title"][:70])

    logger.info("Ingestion complete. %d documents now in table.", document_count())


if __name__ == "__main__":
    run()
