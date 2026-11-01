from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.ai import client as ai_client
from app.ai.client import AIUnavailableError, complete, complete_json, parse_json_object
from app.ai.drafting import DraftProfile, generate_draft, strip_html, template_draft
from app.ai.providers import AIProvider


class FakeDB:
    def commit(self) -> None:
        return None


def provider(name: str, *, no_training: bool = True) -> AIProvider:
    return AIProvider(
        name=name,
        base_url=f"https://{name}.test/v1",
        api_key="key",
        model=f"{name}-model",
        daily_cap=100,
        no_training=no_training,
    )


@pytest.fixture(autouse=True)
def no_database_or_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_client, "remaining", lambda *_args, **_kwargs: 100)
    monkeypatch.setattr(ai_client, "record_usage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_client.time, "sleep", lambda _seconds: None)
    ai_client._limiters.clear()


def reply(text: str, status: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://x.test")
    body = {"choices": [{"message": {"content": text}}]} if status == 200 else {}
    return httpx.Response(status, json=body, request=request)


def test_complete_falls_back_when_the_first_provider_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_post(url: str, **_kwargs: Any) -> httpx.Response:
        calls.append(url)
        return reply("", 429) if "groq" in url else reply("hello from gemini")

    monkeypatch.setattr(ai_client.httpx, "post", fake_post)

    result = complete(FakeDB(), [{"role": "user", "content": "hi"}], providers=[provider("groq"), provider("gemini", no_training=False)])  # type: ignore[arg-type]

    assert result.text == "hello from gemini"
    assert result.provider == "gemini"
    assert len(calls) == 2


def test_sensitive_requests_never_reach_providers_that_may_train(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_client.httpx, "post", lambda *_a, **_k: pytest.fail("must not be called"))

    with pytest.raises(AIUnavailableError, match="no-training"):
        complete(FakeDB(), [], sensitive=True, providers=[provider("gemini", no_training=False)])  # type: ignore[arg-type]


def test_no_configured_provider_raises_so_callers_can_use_templates() -> None:
    with pytest.raises(AIUnavailableError):
        complete(FakeDB(), [], providers=[])  # type: ignore[arg-type]


def test_server_errors_are_retried_once_then_fall_through(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        attempts["count"] += 1
        return reply("", 503)

    monkeypatch.setattr(ai_client.httpx, "post", fake_post)

    with pytest.raises(AIUnavailableError):
        complete(FakeDB(), [], providers=[provider("groq")])  # type: ignore[arg-type]
    assert attempts["count"] == 2


def test_daily_cap_skips_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_client, "remaining", lambda *_a, **_k: 0)
    monkeypatch.setattr(ai_client.httpx, "post", lambda *_a, **_k: pytest.fail("must not be called"))

    with pytest.raises(AIUnavailableError, match="cap"):
        complete(FakeDB(), [], providers=[provider("groq")])  # type: ignore[arg-type]


class Shape(BaseModel):
    unsupported_claims: list[str]


def test_parse_json_object_accepts_fences_and_surrounding_prose() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! Here it is: {"a": 2} Hope that helps.') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json_object("no json here")


def test_complete_json_retries_once_on_malformed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter(["not json", '{"unsupported_claims": ["10 years of Go"]}'])
    monkeypatch.setattr(ai_client.httpx, "post", lambda *_a, **_k: reply(next(replies)))

    result = complete_json(FakeDB(), [{"role": "user", "content": "x"}], Shape, providers=[provider("groq")])  # type: ignore[arg-type]

    assert result.unsupported_claims == ["10 years of Go"]


def test_complete_json_gives_up_after_two_bad_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_client.httpx, "post", lambda *_a, **_k: reply('{"wrong": true}'))

    with pytest.raises(AIUnavailableError, match="valid JSON"):
        complete_json(FakeDB(), [], Shape, providers=[provider("groq")])  # type: ignore[arg-type]


PROFILE = DraftProfile(
    full_name="Ada Example",
    headline="Backend developer focused on Python APIs.",
    skills=["Python", "FastAPI", "PostgreSQL", "Rust"],
    target_roles=["backend", "full-stack"],
    projects=[
        {"name": "Shop Sys", "description": "inventory app with live sync", "url": "https://example.com/shop"},
        {"name": "QueryLang", "description": "SQL-like query engine", "url": ""},
    ],
)
DESCRIPTION = "<p>We build APIs with <b>Python</b> and FastAPI on PostgreSQL.</p><ul><li>Docker</li></ul>"


def test_strip_html_gives_plain_text() -> None:
    text = strip_html(DESCRIPTION)
    assert "<" not in text
    assert "Python" in text and "Docker" in text
    assert strip_html(None) == ""


def test_template_draft_only_uses_profile_facts() -> None:
    draft = template_draft("Backend Engineer", "Acme", DESCRIPTION, PROFILE)

    assert draft.generated_by == "template"
    assert "Backend Engineer role at Acme" in draft.cover_letter
    assert "Python, FastAPI, PostgreSQL" in draft.cover_letter
    assert "Rust" not in draft.cover_letter  # skill is not in the job text
    assert "Shop Sys" in draft.cover_letter and "https://example.com/shop" in draft.cover_letter
    assert draft.cover_letter.rstrip().endswith("Ada Example")
    assert "relevant_experience" in draft.answers
    assert draft.warnings == []


def test_template_draft_warns_about_missing_profile_facts_and_does_not_invent() -> None:
    draft = template_draft("Backend Engineer", None, None, DraftProfile())

    assert draft.cover_letter.startswith("Dear Hiring Team,")
    assert "years" not in draft.cover_letter
    assert len(draft.warnings) == 3
    assert draft.answers == {}


def test_generate_draft_uses_the_template_when_ai_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.ai.drafting.complete", lambda *_a, **_k: (_ for _ in ()).throw(AIUnavailableError("none")))

    draft = generate_draft(FakeDB(), "Backend Engineer", "Acme", DESCRIPTION, PROFILE)  # type: ignore[arg-type]

    assert draft.generated_by == "template"


def test_generate_draft_flags_unsupported_claims_from_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai.client import AIResult

    monkeypatch.setattr(
        "app.ai.drafting.complete",
        lambda *_a, **_k: AIResult(text="Dear team, I have 10 years of Go.", provider="groq", model="m"),
    )
    monkeypatch.setattr(
        "app.ai.drafting.complete_json",
        lambda *_a, **_k: type("V", (), {"unsupported_claims": ["10 years of Go"]})(),
    )

    draft = generate_draft(FakeDB(), "Backend Engineer", "Acme", DESCRIPTION, PROFILE)  # type: ignore[arg-type]

    assert draft.generated_by == "groq:m"
    assert any("10 years of Go" in warning for warning in draft.warnings)
    assert "relevant_experience" in draft.answers  # fact-only answers still come from the template
