"""Application settings loaded from environment variables (12-factor).

Values can be provided via real environment variables or a local ``.env`` file
(see ``.env.example``). In production (ECS), these come from the task
definition / AWS Secrets Manager.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "governance-graph-builder"
    environment: str = "development"  # development | staging | production
    log_level: str = "INFO"
    log_json: bool = True

    # --- HTTP / CORS ---
    # Comma-separated list of allowed origins for the browser frontend.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "localdevpassword"
    # Database name. Leave empty/None to use the server's home database. A
    # managed instance (e.g. Neo4j Aura) may not have a database literally named
    # "neo4j", so forcing that name breaks routing; None resolves the home db.
    neo4j_database: str | None = None
    # Seconds to wait when verifying connectivity for readiness checks.
    neo4j_connection_timeout: float = 5.0

    # --- LLM (policy-document parsing) ---
    # auto  -> use the first configured real provider, else the offline heuristic
    # bedrock | openai | anthropic | heuristic -> force a specific provider
    llm_provider: str = "auto"
    llm_max_tokens: int = 2000
    llm_temperature: float = 0.0
    # AWS Bedrock (primary real provider)
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    # Optional direct providers
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # --- Frontend (Strategy 1: unified container serving the built SPA) ---
    # When enabled AND a build exists at `static_dir`, FastAPI serves the SPA
    # at "/". With no build present (local dev, tests), the API runs on its own.
    serve_frontend: bool = True
    static_dir: str = "static"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance (created once per process)."""
    return Settings()
