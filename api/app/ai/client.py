"""Chat-completion client with free-tier budgets, fallback, and JSON validation."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.providers import AIProvider, configured_ai_providers
from app.core.config import settings
from app.services.robots import RateLimiter
from app.services.usage import Budget, record_usage, remaining

T = TypeVar("T", bound=BaseModel)


class AIUnavailableError(RuntimeError):
    """No configured provider could answer (none set up, limits hit, or all failed)."""


@dataclass(frozen=True)
class AIResult:
    text: str
    provider: str
    model: str


_limiters: dict[str, RateLimiter] = {}


def _limiter(provider: AIProvider) -> RateLimiter:
    limiter = _limiters.get(provider.name)
    if limiter is None:
        limiter = RateLimiter(settings.ai_requests_per_minute, min_interval_seconds=0)
        _limiters[provider.name] = limiter
    return limiter


def _call(provider: AIProvider, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str:
    response = httpx.post(
        f"{provider.base_url}/chat/completions",
        json={
            "model": provider.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        headers={"Authorization": f"Bearer {provider.api_key}"},
        timeout=settings.api_timeout_seconds * 3,
    )
    if response.status_code == 429:
        raise _Skip("rate limited (HTTP 429)")
    if response.status_code in (401, 403):
        raise _Skip(f"credentials rejected (HTTP {response.status_code})")
    if response.status_code >= 500:
        raise _Retry(f"server error (HTTP {response.status_code})")
    response.raise_for_status()
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise _Skip("unexpected response shape") from error
    if not isinstance(content, str) or not content.strip():
        raise _Skip("empty response")
    return content.strip()


class _Skip(Exception):
    """Do not retry this provider; move on to the next one."""


class _Retry(Exception):
    """Transient failure; try the same provider once more."""


def complete(
    db: Session,
    messages: list[dict[str, str]],
    *,
    sensitive: bool = False,
    max_tokens: int = 900,
    temperature: float = 0.4,
    providers: list[AIProvider] | None = None,
) -> AIResult:
    """Ask the first eligible provider that has budget left, falling back on failure."""
    candidates = configured_ai_providers() if providers is None else providers
    if sensitive:
        candidates = [provider for provider in candidates if provider.no_training]
    if not candidates:
        raise AIUnavailableError(
            "no AI provider is configured for this request"
            + (" (sensitive requests need a no-training provider)" if sensitive else "")
        )

    reasons: list[str] = []
    for provider in candidates:
        if remaining(db, provider.usage_key, Budget(daily=provider.daily_cap)) <= 0:
            reasons.append(f"{provider.name}: daily free-tier cap reached")
            continue
        for attempt in range(2):
            _limiter(provider).acquire()
            record_usage(db, provider.usage_key)
            db.commit()
            try:
                text = _call(provider, messages, max_tokens, temperature)
                return AIResult(text=text, provider=provider.name, model=provider.model)
            except _Retry as error:
                reasons.append(f"{provider.name}: {error}")
                if attempt == 0:
                    time.sleep(1.5)
                    continue
            except _Skip as error:
                reasons.append(f"{provider.name}: {error}")
            except httpx.HTTPError as error:
                reasons.append(f"{provider.name}: {type(error).__name__}")
                if attempt == 0:
                    time.sleep(1.5)
                    continue
            break
    raise AIUnavailableError("; ".join(reasons))


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_object(text: str) -> Any:
    """Parse a JSON object even when the model wrapped it in prose or code fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except ValueError:
        match = _JSON_BLOCK.search(cleaned)
        if match is None:
            raise
        return json.loads(match.group(0))


def complete_json(
    db: Session,
    messages: list[dict[str, str]],
    schema: type[T],
    *,
    sensitive: bool = False,
    max_tokens: int = 700,
    providers: list[AIProvider] | None = None,
) -> T:
    """Get a response validated against ``schema``; retry once if it is malformed."""
    conversation = list(messages)
    last_error = "invalid JSON"
    for _attempt in range(2):
        result = complete(
            db,
            conversation,
            sensitive=sensitive,
            max_tokens=max_tokens,
            temperature=0.1,
            providers=providers,
        )
        try:
            return schema.model_validate(parse_json_object(result.text))
        except (ValueError, ValidationError) as error:
            last_error = str(error)[:200]
            conversation = conversation + [
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": "That was not valid JSON for the requested shape. "
                    "Reply again with only the JSON object.",
                },
            ]
    raise AIUnavailableError(f"model did not return valid JSON: {last_error}")
