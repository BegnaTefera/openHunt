from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.collectors.ashby import AshbyCollector
from app.collectors.dynamitejobs import (
    parse_dynamitejobs_detail,
    parse_dynamitejobs_sitemap,
)
from app.collectors.remotiko import parse_remotiko_job, parse_remotiko_listing
from app.collectors.trulyremotework import (
    parse_trulyremotework_corpus,
    parse_trulyremotework_job,
)
from app.collectors import base as collector_base
from app.collectors.base import (
    CollectorUnavailableError,
    NormalizedJob,
    dedupe_snapshot,
    sync_board_jobs,
    sync_company_jobs,
)
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.registry import get_collector
from app.collectors.url_detection import detect_ats_from_url
from app.models.company import Company
from app.models.job import Job
from app.services.robots import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_company(ats_type: str, slug: str) -> Company:
    return Company(id=1, name="Acme", ats_type=ats_type, ats_slug=slug)


@pytest.mark.parametrize(
    ("collector_type", "fixture_name", "ats_type"),
    [
        (GreenhouseCollector, "greenhouse_jobs.json", "greenhouse"),
        (LeverCollector, "lever_jobs.json", "lever"),
        (AshbyCollector, "ashby_jobs.json", "ashby"),
    ],
)
def test_collectors_normalize_saved_response_fixtures(
    monkeypatch: pytest.MonkeyPatch,
    collector_type: type[Any],
    fixture_name: str,
    ats_type: str,
) -> None:
    fixture = load_fixture(fixture_name)
    company = make_company(ats_type, "acme")
    if isinstance(fixture, list):
        records = fixture
    else:
        records = fixture["jobs"]

    monkeypatch.setattr(
        f"app.collectors.{ats_type}.fetch_json",
        lambda _url: fixture,
    )

    normalized = collector_type().collect(company)

    assert len(normalized) == 1
    job = normalized[0]
    assert job.source == ats_type
    assert job.external_id
    assert job.title
    assert job.url.startswith("https://")
    assert job.raw_payload == records[0]


@pytest.mark.parametrize(
    ("url", "expected_type", "expected_slug"),
    [
        ("https://boards.greenhouse.io/acme/jobs/42", "greenhouse", "acme"),
        ("https://jobs.lever.co/acme/abc123/apply", "lever", "acme"),
        ("https://jobs.eu.lever.co/acme/abc123", "lever", "acme"),
        ("https://jobs.ashbyhq.com/acme/role/apply", "ashby", "acme"),
        ("https://apply.workable.com/acme/j/abc123", "workable", "acme"),
        ("https://example.org/jobs/42", None, None),
    ],
)
def test_detect_ats_from_apply_url(
    url: str, expected_type: str | None, expected_slug: str | None
) -> None:
    result = detect_ats_from_url(url)

    assert result.ats_type == expected_type
    assert result.ats_slug == expected_slug


def test_workable_collector_is_explicitly_unavailable() -> None:
    with pytest.raises(CollectorUnavailableError, match="No public collector"):
        get_collector("workable")


def make_normalized(url: str, external_id: str) -> NormalizedJob:
    return NormalizedJob(
        source="greenhouse",
        external_id=external_id,
        url=url,
        title="Backend Engineer",
        description="Build APIs",
        location_text="Remote",
        remote_scope="remote",
        employment_type=None,
        seniority=None,
        salary_text=None,
        tags=["Engineering"],
        posted_at=None,
        raw_payload={"id": external_id},
    )


class FakeResult:
    def __init__(self, items: list[Job]) -> None:
        self.items = items

    def all(self) -> list[Job]:
        return self.items


class FakeSession:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def scalars(self, _statement: object) -> FakeResult:
        return FakeResult(self.jobs)

    def scalar(self, _statement: object) -> None:
        return None

    def add(self, job: Job) -> None:
        self.jobs.append(job)

    def flush(self) -> None:
        return None


def test_sync_dedupes_urls_persists_raw_payload_and_deactivates_missing_jobs() -> None:
    company = make_company("greenhouse", "acme")
    still_live = Job(
        id=10,
        source="greenhouse",
        external_id="old-id",
        url="https://boards.greenhouse.io/acme/jobs/10",
        title="Old title",
        company_id=company.id,
        tags=[],
        is_active=True,
        raw_payload={},
    )
    disappeared = Job(
        id=11,
        source="greenhouse",
        external_id="gone",
        url="https://boards.greenhouse.io/acme/jobs/11",
        title="Disappeared",
        company_id=company.id,
        tags=[],
        is_active=True,
        raw_payload={},
    )
    session = FakeSession([still_live, disappeared])
    duplicate_feed = make_normalized(still_live.url, "new-id")

    inserted = sync_company_jobs(
        session,
        company,
        [duplicate_feed, duplicate_feed],
    )

    assert inserted == 0
    assert still_live.external_id == "new-id"
    assert still_live.raw_payload == {"id": "new-id"}
    assert still_live.is_active is True
    assert disappeared.is_active is False


def test_snapshot_dedupes_repeated_url() -> None:
    job = make_normalized("https://jobs.example/1", "1")

    assert dedupe_snapshot([job, job]) == [job]


def test_fetch_json_checks_robots_rate_limit_and_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"ok": "yes"}

    observed: dict[str, Any] = {}
    monkeypatch.setattr(collector_base, "can_fetch_url", lambda *_args: True)
    monkeypatch.setattr(
        collector_base.rate_limiter,
        "acquire",
        lambda: observed.update(rate_limited=True),
    )

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        observed["url"] = url
        observed.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(collector_base.httpx, "get", fake_get)

    assert collector_base.fetch_json("https://api.example/jobs") == {"ok": "yes"}
    assert observed["rate_limited"] is True
    assert observed["headers"]["User-Agent"]
    assert observed["timeout"] > 0


def test_fetch_text_caches_response_after_robots_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        text = "cached response"

        def raise_for_status(self) -> None:
            return None

    calls = {"robots": 0, "target": 0}
    monkeypatch.setattr(
        collector_base,
        "can_fetch_url",
        lambda *_args: calls.__setitem__("robots", calls["robots"] + 1) or True,
    )
    monkeypatch.setattr(
        collector_base.rate_limiter,
        "acquire",
        lambda: None,
    )

    def fake_get(url: str, **_kwargs: Any) -> FakeResponse:
        calls["target"] += 1
        return FakeResponse()

    monkeypatch.setattr(collector_base.httpx, "get", fake_get)
    collector_base._text_cache.pop("https://example.test/jobs", None)

    assert collector_base.fetch_text("https://example.test/jobs") == "cached response"
    assert collector_base.fetch_text("https://example.test/jobs") == "cached response"
    assert calls == {"robots": 2, "target": 1}


def test_rate_limiter_enforces_two_second_spacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.robots as robots

    clock = [0.0]
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(robots.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(robots.time, "sleep", sleep)

    limiter = RateLimiter(requests_per_minute=30, min_interval_seconds=2.0)
    limiter.acquire()
    limiter.acquire()

    assert waits == [2.0]


def test_public_board_parsers_read_saved_fixtures() -> None:
    remotiko_html = (FIXTURES / "remotiko_listing.html").read_text(encoding="utf-8")
    remotiko_job = (FIXTURES / "remotiko_job.html").read_text(encoding="utf-8")
    trw_corpus = (FIXTURES / "trulyremotework_corpus.md").read_text(encoding="utf-8")
    trw_job = (FIXTURES / "trulyremotework_job.md").read_text(encoding="utf-8")
    dynamite_sitemap = (FIXTURES / "dynamitejobs_development.xml").read_text(
        encoding="utf-8"
    )
    dynamite_job = (FIXTURES / "dynamitejobs_job.html").read_text(encoding="utf-8")

    remotiko_records, has_next_page = parse_remotiko_listing(remotiko_html)
    assert remotiko_records == [("/job/backend-engineer/", "Backend Engineer")]
    assert has_next_page is True
    assert parse_remotiko_job(
        remotiko_job,
        "https://remotiko.com/job/backend-engineer/",
        "Backend Engineer",
    ) == (
        "Backend Engineer",
        "https://boards.greenhouse.io/acme/jobs/42",
        "Build backend services.",
    )

    trw_records = parse_trulyremotework_corpus(trw_corpus)
    assert [record["url"] for record in trw_records] == [
        "https://trulyremotework.com/jobs/backend-engineer-acme"
    ]
    trw_detail = parse_trulyremotework_job(
        trw_job, "https://trulyremotework.com/jobs/backend-engineer-acme"
    )
    assert trw_detail["apply_url"] == "https://jobs.ashbyhq.com/acme/42"
    assert trw_detail["title"] == "Backend Engineer"

    assert parse_dynamitejobs_sitemap(dynamite_sitemap) == [
        "https://dynamitejobs.com/company/acme/remote-job/backend-engineer"
    ]
    dynamite_detail = parse_dynamitejobs_detail(
        dynamite_job,
        "https://dynamitejobs.com/company/acme/remote-job/backend-engineer",
    )
    assert dynamite_detail["title"] == "Backend Engineer"
    assert dynamite_detail["description"] == "Build backend services."


def test_sync_board_jobs_matches_apply_url_and_only_deactivates_complete_snapshots() -> None:
    company = make_company("greenhouse", "acme")
    still_live = Job(
        id=10,
        source="remotiko",
        external_id="backend-engineer",
        url="https://remotiko.com/job/backend-engineer/",
        title="Old title",
        company_id=None,
        tags=[],
        is_active=True,
        raw_payload={},
    )
    disappeared = Job(
        id=11,
        source="remotiko",
        external_id="disappeared",
        url="https://remotiko.com/job/disappeared/",
        title="Disappeared",
        company_id=None,
        tags=[],
        is_active=True,
        raw_payload={},
    )

    class BoardSession(FakeSession):
        def __init__(self) -> None:
            super().__init__([still_live, disappeared])
            self.responses = [[company], [still_live, disappeared]]

        def scalars(self, _statement: object) -> FakeResult:
            return FakeResult(self.responses.pop(0))

    session = BoardSession()
    normalized = make_normalized(still_live.url, "backend-engineer")
    normalized = NormalizedJob(
        **{
            **normalized.__dict__,
            "source": "remotiko",
            "raw_payload": {
                "apply_url": "https://boards.greenhouse.io/acme/jobs/42"
            },
        }
    )

    sync_board_jobs(session, "remotiko", [normalized], complete_snapshot=False)

    assert still_live.company_id == company.id
    assert still_live.is_active is True
    assert disappeared.is_active is True

    session = BoardSession()
    sync_board_jobs(session, "remotiko", [normalized], complete_snapshot=True)
    assert disappeared.is_active is False
