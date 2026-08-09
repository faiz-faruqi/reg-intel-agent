"""Configuration and environment variable loading."""

from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Model provider: openrouter for Phase 1 (default), azure_openai as a
    # validated config-only alternative (ADR-006), bedrock for Phase 2+ production
    MODEL_PROVIDER: Literal["openrouter", "azure_openai", "bedrock"] = "openrouter"

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

    # Azure OpenAI (config-only alternative to OpenRouter — see ADR-006).
    # Azure routes on a *deployment name*, not a bare model string, so both the
    # chat and embedding deployments must be created in the Azure resource first.
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None  # e.g. https://<resource>.openai.azure.com/
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"
    AZURE_OPENAI_CHAT_DEPLOYMENT: str | None = None
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str | None = None

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
    # Session lifetime in seconds (default: 24 hours)
    SESSION_MAX_AGE: int = 86400
    # Admin key for POST /auth/generate-code (X-Admin-Key header). A code must
    # be generated at least once — via scripts/generate_access_code.py — before
    # anyone, including local dev, can sign in. Leave blank to disable the
    # endpoint (sign-in will then always reject, since no code can ever exist).
    ADMIN_KEY: str = ""
    # Default TTL (in hours) for a generated access code when the caller
    # doesn't specify one. 168 = 7 days.
    ACCESS_CODE_DEFAULT_TTL_HOURS: float = 168
    # Max metered actions (/query + /propose) per login session. Caps LLM cost
    # and deters misuse. Resetting the budget requires a fresh sign-in.
    SESSION_ACTION_LIMIT: int = 15

    @model_validator(mode="after")
    def _require_azure_fields_when_selected(self) -> "Settings":
        if self.MODEL_PROVIDER == "azure_openai":
            required = {
                "AZURE_OPENAI_API_KEY": self.AZURE_OPENAI_API_KEY,
                "AZURE_OPENAI_ENDPOINT": self.AZURE_OPENAI_ENDPOINT,
                "AZURE_OPENAI_CHAT_DEPLOYMENT": self.AZURE_OPENAI_CHAT_DEPLOYMENT,
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": self.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(
                    "MODEL_PROVIDER=azure_openai requires: " + ", ".join(missing)
                )
        return self


settings = Settings()
