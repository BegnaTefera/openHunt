from __future__ import annotations

from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets and the database URL have no defaults on purpose: they must be
    # provided by the environment.
    secret_key: str
    database_url: str

    # Non-secret settings have safe defaults so small entry points (for example
    # the scheduled collector job) only need to provide what they really use.
    app_name: str = "openHunt"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]
    access_token_expire_minutes: int = 15
    job_fetch_interval_minutes: int = 30
    max_jobs_per_run: int = 50
    request_timeout_seconds: int = 20
    requests_per_minute: int = 20
    user_agent: str = "openHunt/0.1 (+https://example.com; contact@example.com)"
    api_timeout_seconds: int = 20

    # Accounts and sessions.
    refresh_token_days: int = 30
    refresh_cookie_name: str = "openhunt_refresh"
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Who may create an account. Admin privileges are provisioned separately via the CLI.
    # List allowed addresses (comma separated) or set SIGNUP_ENABLED=false to close sign-up.
    signup_enabled: bool = True
    allowed_signup_emails: str = ""
    cv_max_bytes: int = 3_000_000

    # Company discovery (all optional; each source is skipped when not configured).
    discovery_max_queries_per_run: int = 4
    discovery_max_validations_per_run: int = 15
    serpapi_api_key: str = ""
    serpapi_monthly_cap: int = 250
    serper_api_key: str = ""
    serper_daily_cap: int = 20
    serper_total_cap: int = 2000
    commoncrawl_enabled: bool = True
    commoncrawl_max_urls_per_host: int = 500
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = ""
    web_app_url: str = "http://localhost:3000"
    gmail_poll_interval_minutes: int = 10
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

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

    @property
    def allowed_signup_email_set(self) -> set[str]:
        return {
            item.strip().casefold() for item in self.allowed_signup_emails.split(",") if item.strip()
        }

    @property
    def cookie_secure(self) -> bool:
        return self.app_env.lower() == "production"

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
        return self


settings = Settings()
