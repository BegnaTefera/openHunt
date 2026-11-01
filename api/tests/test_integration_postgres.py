"""Integration tests against a real, throwaway PostgreSQL database.

Skipped unless TEST_DATABASE_URL is set, because they DROP and recreate the public
schema. Example (PowerShell, using the Compose database):

    $env:TEST_DATABASE_URL = "postgresql+psycopg://openhunt:PASSWORD@localhost:5432/openhunt_test"
    py -3.12 -m pytest tests/test_integration_postgres.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

TEST_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="set TEST_DATABASE_URL to run")

API_DIR = Path(__file__).resolve().parents[1]


def alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": TEST_URL or ""}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, check=True, capture_output=True
    )


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(TEST_URL or "")
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic("upgrade", "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def db(engine) -> Session:
    with sessionmaker(bind=engine)() as session:
        yield session
        session.rollback()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE api_usage, discovery_candidates, documents, applications, jobs, "
                "companies, events, profile RESTART IDENTITY CASCADE"
            )
        )


def test_migration_0004_downgrades_and_upgrades_cleanly(engine) -> None:
    alembic("downgrade", "0003_unmatched_board_jobs")
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))}
    assert "api_usage" not in tables and "discovery_candidates" not in tables
    alembic("upgrade", "head")


def test_usage_budgets_count_per_day_month_and_total(db: Session) -> None:
    from app.services.usage import Budget, get_usage, record_usage, remaining

    today = datetime(2026, 10, 31).date()
    record_usage(db, "brave", 3, today=today)
    record_usage(db, "brave", 2, today=today)
    record_usage(db, "brave", 5, today=today - timedelta(days=5))  # same month
    record_usage(db, "brave", 7, today=today - timedelta(days=40))  # older month

    usage = get_usage(db, "brave", today)
    assert (usage.day, usage.month, usage.total) == (5, 10, 17)
    assert remaining(db, "brave", Budget(daily=20, monthly=12), today) == 2
    assert remaining(db, "brave", Budget(daily=20, total=17), today) == 0
    assert remaining(db, "other", Budget(daily=4), today) == 4
    assert remaining(db, "brave", Budget(), today) > 1_000_000


class FakeSource:
    def __init__(self, name: str, urls: list[str]) -> None:
        self.name = name
        self.urls = urls
        self.errors: list[str] = []

    def fetch_urls(self, _db: Session) -> list[str]:
        return self.urls


def test_discovery_adds_matching_boards_and_remembers_the_rest(db: Session) -> None:
    from app.discovery.service import BoardCheck, run_discovery
    from app.models.company import Company
    from app.models.discovery import DiscoveryCandidate

    db.add(Company(name="Existing Co", ats_type="lever", ats_slug="existing-co"))
    db.commit()

    outcomes = {
        "good-co": BoardCheck("ok", "2 of 9 jobs are backend/full-stack"),
        "sales-only": BoardCheck("no_match", "no matching backend/full-stack roles"),
        "gone": BoardCheck("dead", "board not found"),
        "flaky": BoardCheck("transient", "timeout"),
    }
    checked: list[str] = []

    def validator(_ats: str, slug: str) -> BoardCheck:
        checked.append(slug)
        return outcomes[slug]

    source = FakeSource(
        "commoncrawl",
        [f"https://jobs.lever.co/{slug}/1" for slug in ("existing-co", *outcomes)],
    )
    report = run_discovery(db, [source], validator=validator)

    assert report.added == 1 and report.added_companies == ["Good Co"]
    assert report.rejected == 2 and report.deferred == 1 and report.already_known == 1
    assert "existing-co" not in checked
    rows = {row.ats_slug: row for row in db.scalars(select(DiscoveryCandidate)).all()}
    assert set(rows) == {"good-co", "sales-only", "gone"}  # transient errors are not remembered
    assert rows["good-co"].status == "added" and rows["good-co"].company_id is not None
    assert rows["sales-only"].reason == "no matching backend/full-stack roles"

    # Second run: nothing is re-validated until the retry window passes.
    checked.clear()
    second = run_discovery(db, [source], validator=validator)
    assert checked == ["flaky"] and second.added == 0

    # After 31 days a "no matching roles" board is checked again, and may now qualify.
    outcomes["sales-only"] = BoardCheck("ok", "1 of 3 jobs are backend/full-stack")
    checked.clear()
    later = run_discovery(db, [source], validator=validator, now=datetime.now(timezone.utc) + timedelta(days=31))
    assert "sales-only" in checked and "good-co" not in checked
    assert later.added == 1
    db.expire_all()
    assert db.scalar(select(DiscoveryCandidate).where(DiscoveryCandidate.ats_slug == "sales-only")).status == "added"


def test_discovery_respects_the_validation_limit(db: Session) -> None:
    from app.discovery.service import BoardCheck, run_discovery

    source = FakeSource("brave", [f"https://jobs.ashbyhq.com/co{i}/x" for i in range(5)])
    report = run_discovery(
        db, [source], max_validations=2, validator=lambda *_: BoardCheck("ok", "match")
    )

    assert report.validated == 2 and report.added == 2 and report.deferred == 3


def test_search_source_stops_when_the_free_budget_is_used_up(db: Session) -> None:
    from app.discovery.errors import QuotaExhaustedError
    from app.discovery.service import SearchSource
    from app.services.usage import Budget, get_usage

    class Provider:
        name = "brave"

        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str) -> list[str]:
            self.queries.append(query)
            if len(self.queries) == 2:
                raise QuotaExhaustedError("brave rate limit or quota reached (HTTP 429)")
            return [f"https://jobs.lever.co/slug{len(self.queries)}/1"]

    provider = Provider()
    queries = [f"q{i}" for i in range(10)]
    source = SearchSource(provider, Budget(daily=3), queries, max_queries=5)  # type: ignore[arg-type]

    urls = source.fetch_urls(db)
    assert provider.queries == ["q0", "q1"] and urls == ["https://jobs.lever.co/slug1/1"]
    assert get_usage(db, "brave").day == 2  # attempts are counted, including the rejected one
    assert source.errors and "429" in source.errors[0]

    provider.queries.clear()
    source2 = SearchSource(provider, Budget(daily=3), queries, max_queries=5)  # type: ignore[arg-type]
    source2.fetch_urls(db)
    assert provider.queries == ["q2"]  # only one request of the daily budget remained
    assert source2.fetch_urls(db) == [] and "budget used up" in source2.errors[-1]


@pytest.fixture()
def client(db: Session):
    from app.core.auth import get_current_user
    from app.db.dependencies import get_db
    from app.main import app
    from app.models.user import User

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(id=1, username="admin", password_hash="x")
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_job(db: Session):
    from app.models.company import Company
    from app.models.job import Job

    company = Company(name="Acme", ats_type="greenhouse", ats_slug="acme")
    db.add(company)
    db.flush()
    job = Job(
        source="greenhouse", external_id="1", url="https://boards.greenhouse.io/acme/jobs/1",
        title="Backend Engineer", company_id=company.id,
        description="<p>Build APIs with Python and FastAPI.</p>", tags=[], raw_payload={},
    )
    db.add(job)
    db.commit()
    return job


def test_draft_flow_and_profile_facts(client: TestClient, db: Session) -> None:
    job = make_job(db)
    assert client.get(f"/jobs/{job.id}/draft").status_code == 404

    profile = {
        "skills": ["Python", "FastAPI"], "target_roles": ["backend"], "seniority": None,
        "full_name": "Ada Example", "summary": "I build reliable Python APIs.",
        "projects": [{"name": "Shop Sys", "description": "inventory app", "url": "https://example.com/s"}],
    }
    saved = client.put("/profile", json=profile)
    assert saved.status_code == 200 and saved.json()["projects"][0]["name"] == "Shop Sys"

    created = client.post(f"/jobs/{job.id}/draft?use_ai=false")
    assert created.status_code == 200
    body = created.json()
    assert body["generated_by"] == "template" and "Ada Example" in body["cover_letter"]
    assert "Python, FastAPI" in body["cover_letter"]
    assert client.get(f"/jobs/{job.id}").json()["status"] == "drafted"

    edited = client.put(f"/jobs/{job.id}/draft", json={"cover_letter": "My own words.", "answers": {"note": "x"}})
    assert edited.json()["generated_by"] == "edited"
    assert client.get(f"/jobs/{job.id}/draft").json()["cover_letter"] == "My own words."

    # An older client that does not send the new fields must not erase them.
    older = {"skills": ["Python"], "target_roles": ["backend"], "seniority": None}
    kept = client.put("/profile", json=older).json()
    assert kept["full_name"] == "Ada Example" and len(kept["projects"]) == 1


def test_drafting_does_not_downgrade_a_later_status(client: TestClient, db: Session) -> None:
    job = make_job(db)
    client.patch(f"/jobs/{job.id}/status", json={"status": "applied"})

    client.post(f"/jobs/{job.id}/draft?use_ai=false")

    assert client.get(f"/jobs/{job.id}").json()["status"] == "applied"


def test_discovery_status_endpoint(client: TestClient, db: Session) -> None:
    from app.discovery.service import BoardCheck, run_discovery

    run_discovery(
        db,
        [FakeSource("brave", ["https://jobs.lever.co/zed/1"])],
        validator=lambda *_: BoardCheck("ok", "1 of 1 jobs are backend/full-stack"),
    )

    body = client.get("/discovery").json()

    assert body["added_total"] == 1 and body["rejected_total"] == 0
    assert body["recent_candidates"][0]["ats_slug"] == "zed"
    assert body["last_run"]["added"] == 1
    assert {item["name"] for item in body["providers"]} == {"brave", "serper", "commoncrawl"}
