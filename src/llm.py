"""Shared chat/embedding model factories — branches on settings.MODEL_PROVIDER.

Keeps the OpenRouter vs. Azure OpenAI vs. Bedrock decision in one place (ADR-005,
ADR-006) so agent modules and the ingest script don't each hardcode a provider.
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings, ChatOpenAI, OpenAIEmbeddings

from src.config import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_chat_model() -> BaseChatModel:
    if settings.MODEL_PROVIDER == "openrouter":
        return ChatOpenAI(
            model=settings.OPENROUTER_MODEL_ID,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            temperature=0,
            timeout=30,
            max_retries=2,
        )
    if settings.MODEL_PROVIDER == "azure_openai":
        # No `temperature` override: newer reasoning-style deployments (e.g.
        # gpt-5-mini) reject any value other than their default (1) — unlike
        # the OpenRouter model, which is pinned to temperature=0 for
        # deterministic, low-creativity compliance answers.
        return AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            api_key=settings.AZURE_OPENAI_API_KEY,
            timeout=30,
            max_retries=2,
        )
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")


def build_embeddings_model() -> Embeddings:
    if settings.MODEL_PROVIDER == "openrouter":
        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            timeout=20,
            max_retries=2,
        )
    if settings.MODEL_PROVIDER == "azure_openai":
        # Azure's text-embedding-3-small defaults to 1536 dims, matching
        # init-db.sql's vector(1536) — do not override `dimensions` down.
        return AzureOpenAIEmbeddings(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            azure_deployment=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            api_key=settings.AZURE_OPENAI_API_KEY,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            timeout=20,
            max_retries=2,
        )
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")
