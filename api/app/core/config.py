from __future__ import annotations

from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets and the database URL have no defaults on purpose: they must be
    # provided by the environment.
    secret_key: str
    database_url: str
    default_password: str

    # Non-secret settings have safe defaults so small entry points (for example
    # the scheduled collector job) only need to provide what they really use.
    app_name: str = "openHunt"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]
    access_token_expire_minutes: int = 60
    job_fetch_interval_minutes: int = 30
    max_jobs_per_run: int = 50
    request_timeout_seconds: int = 20
    requests_per_minute: int = 20
    user_agent: str = "openHunt/0.1 (+https://example.com; contact@example.com)"
    api_timeout_seconds: int = 20
    default_username: str = "admin"

    # Company discovery (all optional; each source is skipped when not configured).
    discovery_max_queries_per_run: int = 4
    discovery_max_validations_per_run: int = 15
    brave_api_key: str = ""
    brave_daily_cap: int = 20
    brave_monthly_cap: int = 400
    serper_api_key: str = ""
    serper_daily_cap: int = 20
    serper_total_cap: int = 2000
    commoncrawl_enabled: bool = True
    commoncrawl_max_urls_per_host: int = 500

    # Optional free-tier AI providers (OpenAI-compatible APIs). Model names change
    # over time, so every model is configurable. The app works without any of them.
    ai_requests_per_minute: int = 10
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_daily_cap: int = 200
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_daily_cap: int = 100
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    cloudflare_daily_cap: int = 100

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The repo-level .env also holds Docker Compose and frontend variables
        # (POSTGRES_*, COMPOSE_DATABASE_URL, NEXT_PUBLIC_API_URL) that this class
        # does not declare. Ignore them instead of crashing at import time.
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Hosted providers such as Neon hand out plain postgresql:// URLs."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @model_validator(mode="after")
    def validate_production_credentials(self) -> Settings:
        if self.app_env.lower() == "production":
            if len(self.secret_key) < 32 or "replace" in self.secret_key.lower():
                raise ValueError("production SECRET_KEY must be a strong random value")
            if len(self.default_password) < 12 or "replace" in self.default_password.lower():
                raise ValueError("production DEFAULT_PASSWORD must be a strong password")
        return self


settings = Settings()
