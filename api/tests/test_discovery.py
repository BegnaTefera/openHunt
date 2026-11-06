from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.collectors.base import CollectorError
from app.discovery import service
from app.discovery.commoncrawl import parse_cdx_lines, parse_collinfo
from app.discovery.errors import DiscoveryError
from app.discovery.providers import (
    SerpApiSearchProvider,
    configured_search_providers,
    parse_serpapi_results,
    parse_serper_results,
)
from app.discovery.queries import build_search_queries, rotate
from app.discovery.service import BoardCheck, display_name, extract_candidates, validate_board

FIXTURES = Path(__file__).parent / "fixtures"


def test_queries_use_site_operators_and_rotate() -> None:
    queries = build_search_queries(["backend", "full-stack"])

    assert 'site:jobs.lever.co "backend engineer" remote' in queries
    assert 'site:boards.greenhouse.io "full stack developer" junior remote' in queries
    assert not any("devops" in query for query in queries)
    assert len(queries) == len(set(queries))

    everything = build_search_queries([])
    assert any("site reliability engineer" in query for query in everything)
    assert any("data analyst" in query for query in everything)
    assert len(everything) > len(queries)
    assert rotate(queries, cursor=len(queries) - 1, count=2) == [queries[-1], queries[0]]
    assert rotate([], 0, 3) == []


def test_extract_candidates_handles_each_ats_and_skips_noise() -> None:
    urls = [
        "https://jobs.lever.co/acme-labs/1111",
        "https://jobs.lever.co/acme-labs/2222/apply",
        "https://boards.greenhouse.io/embed/job_board?for=WidgetCo",
        "https://boards.greenhouse.io/embed/job_app",
        "https://job-boards.greenhouse.io/Gadget-Inc/jobs/42",
        "https://jobs.ashbyhq.com/Orbit/abc",
        "https://apply.workable.com/some-co/",
        "https://example.com/jobs",
    ]

    found = extract_candidates(urls)

    assert found == {
        ("lever", "acme-labs"): "acme-labs",
        ("greenhouse", "widgetco"): "WidgetCo",
        ("greenhouse", "gadget-inc"): "Gadget-Inc",
        ("ashby", "orbit"): "Orbit",
    }


def test_display_name_from_slug() -> None:
    assert display_name("acme-labs") == "Acme Labs"
    assert display_name("big_co.io") == "Big Co Io"


def test_search_result_parsers() -> None:
    serpapi = {"organic_results": [{"link": "https://jobs.lever.co/a"}, {"title": "no link"}]}
    serper = {"organic": [{"link": "https://jobs.ashbyhq.com/b"}, {"title": "no link"}]}

    assert parse_serpapi_results(serpapi) == ["https://jobs.lever.co/a"]
    assert parse_serper_results(serper) == ["https://jobs.ashbyhq.com/b"]
    assert parse_serpapi_results({}) == []
    assert parse_serper_results(None) == []


def test_serpapi_search_uses_google_engine_and_parses_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"organic_results": [{"link": "https://jobs.lever.co/acme"}]}

    def fake_get(_url: str, *, params: dict[str, Any], headers: dict[str, str], timeout: int) -> Response:
        seen.update(params=params, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr("app.discovery.providers.httpx.get", fake_get)
    monkeypatch.setattr("app.discovery.providers.rate_limiter.acquire", lambda: None)

    results = SerpApiSearchProvider("test-key").search("site:jobs.lever.co backend")

    assert results == ["https://jobs.lever.co/acme"]
    assert seen["params"] == {
        "engine": "google",
        "q": "site:jobs.lever.co backend",
        "api_key": "test-key",
        "num": 20,
    }


def test_configured_search_providers_include_serpapi_and_keep_optional_serper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "serpapi_api_key", "serp-key")
    monkeypatch.setattr(settings, "serpapi_monthly_cap", 250)
    monkeypatch.setattr(settings, "serper_api_key", "serper-key")

    providers = configured_search_providers()

    assert [provider.name for provider, _budget in providers] == ["serpapi", "serper"]
    assert providers[0][1].monthly == 250 and providers[0][1].daily is None


def test_common_crawl_parsers_use_saved_fixtures() -> None:
    collinfo = json.loads((FIXTURES / "commoncrawl_collinfo.json").read_text(encoding="utf-8"))
    assert parse_collinfo(collinfo) == "https://index.commoncrawl.org/CC-MAIN-2026-30-index"
    with pytest.raises(DiscoveryError):
        parse_collinfo([])

    urls = parse_cdx_lines((FIXTURES / "commoncrawl_cdx.ndjson").read_text(encoding="utf-8"))
    assert len(urls) == 7
    assert set(extract_candidates(urls)) == {
        ("lever", "acme-labs"),
        ("lever", "zeta"),
        ("greenhouse", "widgetco"),
        ("greenhouse", "gadget-inc"),
        ("ashby", "orbit"),
    }


class _FakeCollector:
    def __init__(self, titles: list[str] | Exception) -> None:
        self.titles = titles

    def fetch(self, _company: Any) -> list[dict[str, str]]:
        if isinstance(self.titles, Exception):
            raise self.titles
        return [{"title": title} for title in self.titles]

    def normalize(self, _company: Any, payload: dict[str, str]) -> Any:
        return type("Job", (), {"title": payload["title"]})()


def _status_error(code: int) -> CollectorError:
    request = httpx.Request("GET", "https://example.test")
    cause = httpx.HTTPStatusError("x", request=request, response=httpx.Response(code, request=request))
    error = CollectorError("ATS request failed")
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("titles", "outcome"),
    [
        (["Senior Backend Engineer", "Designer"], "ok"),
        (["Full-Stack Developer"], "ok"),
        (["Senior Data Engineer", "Sales Manager"], "ok"),
        (["Account Executive", "Marketing Manager"], "no_match"),
        ([], "no_match"),
        (_status_error(404), "dead"),
        (CollectorError("timeout"), "transient"),
        (_status_error(503), "transient"),
    ],
)
def test_validate_board_outcomes(monkeypatch: pytest.MonkeyPatch, titles: Any, outcome: str) -> None:
    monkeypatch.setattr(service, "get_collector", lambda _ats: _FakeCollector(titles))

    assert validate_board("lever", "acme").outcome == outcome


def test_validate_board_reports_unsupported_ats() -> None:
    assert validate_board("workable", "acme").outcome == "unsupported"


def test_board_check_dataclass() -> None:
    assert BoardCheck("ok", "x").detail == "x"
