"""Single source of environment configuration for the whole backend.

Every other layer reads config through `get_settings()` — never `os.environ`
directly, never a hardcoded value (AGENT.md SS7, Rule.md SS8). LLM provider, vector
DB, and connector choices are switched here, not by editing business-logic code
(BRD.md SS4/SS7, Plan.md Executive Architecture Decision).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    environment: str = "development"

    # --- LLM provider (packages/clients/llm_client.py resolves the concrete client) ---
    llm_provider: str = "ollama"  # "ollama" | "hosted"
    ollama_base_url: str = "http://localhost:11434"
    local_llm_model: str = "qwen2.5:7b-instruct"
    hosted_llm_api_key: str | None = None
    hosted_llm_base_url: str = "https://api.anthropic.com"
    hosted_llm_model: str = "claude-sonnet-5"

    # --- Embeddings ---
    embedding_provider: str = "ollama"  # "ollama" | "hosted"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # --- Vector store ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # --- Relational store ---
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    database_pool_size: int = 5
    database_max_overflow: int = 2
    database_pool_timeout_seconds: int = 10
    database_pool_recycle_seconds: int = 1800

    # --- Auth ---
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12

    # --- Credential encryption (Fernet key, 32 url-safe base64 bytes) ---
    credential_encryption_key: str = "wZ0nQ3z6r6t2c8m0y6q0k0k3m4h9j1p6y6b3z8t5u4o="

    # --- MCP connectors ---
    google_drive_client_id: str | None = None
    google_drive_client_secret: str | None = None
    notion_client_id: str | None = None
    notion_client_secret: str | None = None
    mcp_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["www.googleapis.com", "api.notion.com"]
    )

    # --- OAuth connect flow (FR-6) ---
    # `api_base_url` must exactly match the redirect URI registered in each
    # provider's OAuth app console (`{api_base_url}/api/connectors/{provider}/callback`).
    api_base_url: str = "http://localhost:8000"
    # Where the callback sends the browser back to after connecting/failing.
    frontend_base_url: str = "http://localhost:3000"

    # --- Periodic connector re-sync (FR-6), run via Render Cron ---
    ingestion_resync_interval_hours: int = 6

    # --- Rate limiting (Phase 5) ---
    rate_limit_per_minute: int = 30

    # --- CORS (Phase 4/5) ---
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- Retrieval defaults (Plan.md SS7) ---
    retrieval_top_k: int = 6
    tool_output_max_chars: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
