"""
src/core/config.py
──────────────────
Single source of truth for all application configuration.
Uses Pydantic Settings — values are pulled from environment variables / .env file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    api_secret_key: str = "change-this-to-a-secure-random-secret-key"
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # ── LLM Provider ────────────────────────────────────────────────────────
    llm_provider: Literal["openai", "gemini"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # ── Qdrant ──────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "agentic_rag_docs"
    qdrant_memory_collection: str = "user_long_term_memory"
    qdrant_vector_size: int = 1536  # text-embedding-3-small dimension

    # ── Redis ───────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_ttl_seconds: int = 3600
    short_term_memory_turns: int = 5

    # ── Guardrails ──────────────────────────────────────────────────────────
    pii_threshold: float = 0.85
    injection_block_on_detect: bool = True
    grounding_strict_mode: bool = True

    # ── Data Connectors ─────────────────────────────────────────────────────
    use_mock_connectors: bool = True
    ingestion_poll_interval_seconds: int = 60

    # Gmail
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_max_results: int = 50

    # Notion
    notion_api_token: str = ""
    notion_database_id: str = ""

    # Jira
    jira_server_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "PROJ"
    jira_max_results: int = 50

    # ── Observability ───────────────────────────────────────────────────────
    prometheus_port: int = 9090
    grafana_port: int = 3000

    # ── Derived helpers ─────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def configs_dir(self) -> Path:
        return Path(__file__).parent.parent.parent / "configs"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings (singleton)."""
    return Settings()
