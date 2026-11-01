from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_settings_load_from_env_example_even_with_compose_and_frontend_keys() -> None:
    """Regression: unknown keys in the repo-level .env used to crash Settings."""
    settings = Settings(_env_file=ROOT / ".env.example")

    assert settings.app_name == "openHunt"
    assert settings.api_port == 8000
    assert settings.brave_api_key == ""
    assert settings.groq_model == "openai/gpt-oss-120b"


def test_plain_postgres_urls_are_converted_to_the_psycopg_driver() -> None:
    for url in ("postgresql://u:p@host/db?sslmode=require", "postgres://u:p@host/db"):
        settings = Settings(
            _env_file=None, database_url=url, secret_key="x" * 40, default_password="y" * 20
        )
        assert settings.database_url.startswith("postgresql+psycopg://u:p@host/db")


def test_non_secret_settings_have_defaults_for_small_entry_points() -> None:
    settings = Settings(
        _env_file=None, database_url="postgresql://u:p@h/d", secret_key="s", default_password="p"
    )

    assert settings.requests_per_minute == 20
    assert settings.default_username == "admin"
