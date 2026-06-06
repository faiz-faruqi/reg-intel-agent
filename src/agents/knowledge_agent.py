"""Knowledge Agent: embeds the query and retrieves relevant documents via pgvector."""

import logging
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from src.config import settings
from src.db import similarity_search, write_audit_log
from src.state import AgentState

logger = logging.getLogger(__name__)

AGENT_NAME = "knowledge_agent"


@lru_cache(maxsize=1)
def _embeddings_model() -> OpenAIEmbeddings:
    """Return a cached embeddings model instance pointed at OpenRouter."""
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )


def knowledge_agent(state: AgentState) -> AgentState:
    """
    Retrieve the top-k documents most relevant to state["question"].
    Writes input/output to the audit log.
    """
    question: str = state["question"]
    top_k: int = state.get("top_k", 5)

    logger.info("%s: embedding question", AGENT_NAME)
    embedding = _embeddings_model().embed_query(question)

    chunks = similarity_search(embedding, top_k=top_k)
    logger.info("%s: retrieved %d chunks", AGENT_NAME, len(chunks))

    write_audit_log(
        agent_name=AGENT_NAME,
        step_type="retrieval",
        input_data={"question": question, "top_k": top_k},
        output_data={"chunks_retrieved": len(chunks), "sources": [c["source"] for c in chunks]},
    )

    return {"retrieved_chunks": chunks}
