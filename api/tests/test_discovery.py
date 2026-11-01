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
from app.discovery.providers import parse_brave_results, parse_serper_results
from app.discovery.queries import build_search_queries, rotate
from app.discovery.service import BoardCheck, display_name, extract_candidates, validate_board

FIXTURES = Path(__file__).parent / "fixtures"


def test_queries_use_site_operators_and_rotate() -> None:
    queries = build_search_queries(["backend", "full-stack"])

    assert 'site:jobs.lever.co "backend engineer" remote' in queries
    assert 'site:boards.greenhouse.io "full stack developer" junior remote' in queries
    assert len(queries) == len(set(queries))
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
    brave = {"web": {"results": [{"url": "https://jobs.lever.co/a"}, {"title": "no url"}]}}
    serper = {"organic": [{"link": "https://jobs.ashbyhq.com/b"}, {"title": "no link"}]}

    assert parse_brave_results(brave) == ["https://jobs.lever.co/a"]
    assert parse_serper_results(serper) == ["https://jobs.ashbyhq.com/b"]
    assert parse_brave_results({}) == []
    assert parse_serper_results(None) == []


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
        (["Account Executive", "Designer"], "no_match"),
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
