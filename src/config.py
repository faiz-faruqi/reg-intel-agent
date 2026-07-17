"""Configuration and environment variable loading."""

from typing import Literal

from pydantic import AliasChoices, Field
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
    # Generation model. Reads GENERATION_MODEL (deployment env var) first, then
    # OPENROUTER_MODEL_ID for backward compatibility. The free Gemma model is a
    # fallback only — it is frequently rate-limited (429) upstream, so set an
    # explicit GENERATION_MODEL in the deployment environment for a reliable demo.
    OPENROUTER_MODEL_ID: str = Field(
        default="google/gemma-4-31b-it:free",
        validation_alias=AliasChoices("GENERATION_MODEL", "OPENROUTER_MODEL_ID"),
    )

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

    # Ticket backend — "github" or "jira" (controls /execute endpoint)
    TICKET_BACKEND: str = "github"

    # GitHub
    GITHUB_TOKEN: str | None = None
    GITHUB_REPO: str = "faiz-faruqi/reg-intel-agent"

    # Jira Cloud (optional — set TICKET_BACKEND=jira to activate)
    JIRA_URL: str | None = None          # e.g. https://yourorg.atlassian.net
    JIRA_EMAIL: str | None = None        # Atlassian account email
    JIRA_API_TOKEN: str | None = None    # Atlassian API token
    JIRA_PROJECT_KEY: str | None = None  # e.g. COMP

    # Application
    PORT: int = 8000
    DEBUG: bool = False

    # Authentication (session-based, no database)
    # Generate SESSION_SECRET with: openssl rand -base64 32
    SESSION_SECRET: str = "dev-secret-change-me-in-production"
    DEMO_USERNAME: str = "demo"
    DEMO_PASSWORD: str = "demo123"
    # Leave blank to disable the access-code gate; set a value to require it
    DEMO_ACCESS_CODE: str = "EARIG2026"
    # Session lifetime in seconds (default: 24 hours)
    SESSION_MAX_AGE: int = 86400
    # Max metered actions (/query + /propose) per login session. Caps LLM cost
    # and deters misuse. Resetting the budget requires a fresh sign-in.
    SESSION_ACTION_LIMIT: int = 15


settings = Settings()
