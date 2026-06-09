"""Knowledge Agent: embeds the query and retrieves relevant documents via pgvector."""

import logging
import time
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from src.config import settings
from src.db import similarity_search, write_audit_log
from src.state import AgentState

logger = logging.getLogger(__name__)

AGENT_NAME = "knowledge_agent"


@lru_cache(maxsize=1)
def _embeddings_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        dimensions=settings.EMBEDDING_DIMENSIONS,
        timeout=20,
        max_retries=2,
    )


def _embed_with_retry(model: OpenAIEmbeddings, text: str, max_attempts: int = 3) -> list[float]:
    """Retry embedding calls on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return model.embed_query(text)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = 2 ** attempt
                logger.warning("Embedding call failed (attempt %d/%d), retrying in %ds: %s", attempt + 1, max_attempts, wait, exc)
                time.sleep(wait)
    raise last_exc


def knowledge_agent(state: AgentState) -> AgentState:
    """
    Retrieve the top-k documents most relevant to state["question"].
    Writes input/output to the audit log.
    """
    question: str = state["question"]
    top_k: int = state.get("top_k", 5)

    logger.info("%s: embedding question", AGENT_NAME)
    embedding = _embed_with_retry(_embeddings_model(), question)

    chunks = similarity_search(embedding, top_k=top_k)
    logger.info("%s: retrieved %d chunks", AGENT_NAME, len(chunks))

    write_audit_log(
        agent_name=AGENT_NAME,
        step_type="retrieval",
        input_data={"question": question, "top_k": top_k},
        output_data={"chunks_retrieved": len(chunks), "sources": [c["source"] for c in chunks]},
    )

    return {"retrieved_chunks": chunks}
