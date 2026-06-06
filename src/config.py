"""Configuration and environment variable loading."""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Model provider: openrouter for Phase 1, bedrock for Phase 2+
    MODEL_PROVIDER: Literal["openrouter", "bedrock"] = "openrouter"

    # OpenRouter (Phase 1) — used for both generation and embeddings
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL_ID: str = "anthropic/claude-sonnet-4.5"

    # Bedrock (Phase 2+)
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Embedding model — dimension MUST match vector(N) in init-db.sql
    # Phase 1 (openrouter): text-embedding-3-small = 1536 dims
    # Phase 2 (bedrock):    amazon.titan-embed-text-v2:0 = 1024 dims
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/reg_intel"

    # LangSmith
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "reg-intel-agent"
    LANGSMITH_TRACING_V2: str = "true"

    # GitHub (Phase 2 — Action Agent)
    GITHUB_TOKEN: str | None = None
    GITHUB_REPO: str = "faiz-faruqi/reg-intel-agent"

    # Application
    PORT: int = 8000
    DEBUG: bool = False


settings = Settings()
