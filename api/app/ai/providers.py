"""Free-tier AI providers that expose OpenAI-compatible chat completions."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class AIProvider:
    name: str
    base_url: str
    api_key: str
    model: str
    daily_cap: int
    # True when the provider states in writing that it does not train on free-tier
    # inputs. Sensitive prompts (for example email content) only go to these.
    no_training: bool

    @property
    def usage_key(self) -> str:
        return f"ai:{self.name}"


def configured_ai_providers() -> list[AIProvider]:
    """Providers with credentials, in the order they are tried."""
    providers: list[AIProvider] = []
    if settings.groq_api_key:
        providers.append(
            AIProvider(
                name="groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                daily_cap=settings.groq_daily_cap,
                no_training=True,
            )
        )
    if settings.cloudflare_api_token and settings.cloudflare_account_id:
        providers.append(
            AIProvider(
                name="cloudflare",
                base_url=(
                    "https://api.cloudflare.com/client/v4/accounts/"
                    f"{settings.cloudflare_account_id}/ai/v1"
                ),
                api_key=settings.cloudflare_api_token,
                model=settings.cloudflare_model,
                daily_cap=settings.cloudflare_daily_cap,
                no_training=True,
            )
        )
    if settings.gemini_api_key:
        providers.append(
            AIProvider(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                daily_cap=settings.gemini_daily_cap,
                no_training=False,
            )
        )
    return providers
