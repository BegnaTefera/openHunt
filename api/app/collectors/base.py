from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.job import Job
from app.services.notifications import enqueue_new_matching_jobs
from app.services.robots import can_fetch_url, rate_limiter
from app.collectors.url_detection import detect_ats_from_url

_TEXT_CACHE_TTL_SECONDS = 15 * 60
_TEXT_CACHE_LIMIT = 2048
_text_cache: dict[str, tuple[float, str]] = {}
_text_cache_lock = Lock()


@dataclass(frozen=True)
class NormalizedJob:
    source: str
    external_id: str
    url: str
    title: str
    description: str | None
    location_text: str | None
    remote_scope: str | None
    employment_type: str | None
    seniority: str | None
    salary_text: str | None
    tags: list[str]
    posted_at: datetime | None
    raw_payload: dict[str, Any]


class Collector(Protocol):
    ats_type: str

    def fetch(self, company: Company) -> list[dict[str, Any]]: ...

    def normalize(
        self, company: Company, payload: dict[str, Any]
    ) -> NormalizedJob: ...

    def collect(self, company: Company) -> list[NormalizedJob]: ...


class CollectorError(RuntimeError):
    """Raised when an ATS response is invalid or cannot be fetched."""


class CollectorUnavailableError(CollectorError):
    """Raised when no supported public collector exists for an ATS."""


def fetch_json(url: str) -> Any:
    try:
        allowed = can_fetch_url(url, settings.user_agent)
    except httpx.HTTPError as error:
        raise CollectorError(f"robots.txt request failed for {url}") from error
    if not allowed:
        raise CollectorError(f"robots.txt disallows collector request: {url}")

    rate_limiter.acquire()
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            timeout=settings.api_timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as error:
        raise CollectorError(f"ATS request failed for {url}") from error
    except ValueError as error:
        raise CollectorError(f"ATS returned invalid JSON: {url}") from error


def fetch_text(url: str, accept: str = "text/html,application/xml,text/plain") -> str:
    try:
        allowed = can_fetch_url(url, settings.user_agent)
    except httpx.HTTPError as error:
        raise CollectorError(f"robots.txt request failed for {url}") from error
    if not allowed:
        raise CollectorError(f"robots.txt disallows collector request: {url}")

    now = time.monotonic()
    with _text_cache_lock:
        cached = _text_cache.get(url)
        if cached and now - cached[0] < _TEXT_CACHE_TTL_SECONDS:
            return cached[1]
        expired_urls = [
            cached_url
            for cached_url, (cached_at, _body) in _text_cache.items()
            if now - cached_at >= _TEXT_CACHE_TTL_SECONDS
        ]
        for cached_url in expired_urls:
            del _text_cache[cached_url]

    rate_limiter.acquire()
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": settings.user_agent, "Accept": accept},
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()
        body = response.text
        with _text_cache_lock:
            if len(_text_cache) >= _TEXT_CACHE_LIMIT:
                oldest_url = min(_text_cache, key=lambda cached_url: _text_cache[cached_url][0])
                del _text_cache[oldest_url]
            _text_cache[url] = (time.monotonic(), body)
        return body
    except httpx.HTTPError as error:
        raise CollectorError(f"Public-board request failed for {url}") from error


class PublicCollector:
    ats_type: str

    def fetch(self, company: Company) -> list[dict[str, Any]]:
        raise NotImplementedError

    def normalize(
        self, company: Company, payload: dict[str, Any]
    ) -> NormalizedJob:
        raise NotImplementedError

    def collect(self, company: Company) -> list[NormalizedJob]:
        payloads = self.fetch(company)
        return [self.normalize(company, payload) for payload in payloads]


def parse_datetime(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def infer_remote_scope(*values: object) -> str | None:
    text = " ".join(str(value) for value in values if value).lower()
    if "hybrid" in text:
        return "hybrid"
    if any(term in text for term in ("remote", "distributed", "work from home")):
        return "remote"
    if text:
        return "onsite"
    return None


def dedupe_snapshot(jobs: list[NormalizedJob]) -> list[NormalizedJob]:
    by_url: dict[str, NormalizedJob] = {}
    for job in jobs:
        if not job.url:
            raise CollectorError("collector normalized a job without a URL")
        by_url.setdefault(job.url, job)
    return list(by_url.values())


def sync_company_jobs(
    db: Session, company: Company, jobs: list[NormalizedJob]
) -> int:
    snapshot = dedupe_snapshot(jobs)
    seen_at = datetime.now(timezone.utc)
    existing = {
        job.url: job
        for job in db.scalars(select(Job).where(Job.company_id == company.id)).all()
    }
    new_count = 0
    new_jobs: list[Job] = []

    for normalized in snapshot:
        row = existing.get(normalized.url)
        values = {
            "source": normalized.source,
            "external_id": normalized.external_id,
            "url": normalized.url,
            "title": normalized.title,
            "company_id": company.id,
            "description": normalized.description,
            "location_text": normalized.location_text,
            "remote_scope": normalized.remote_scope,
            "employment_type": normalized.employment_type,
            "seniority": normalized.seniority,
            "salary_text": normalized.salary_text,
            "tags": normalized.tags,
            "posted_at": normalized.posted_at,
            "last_seen_at": seen_at,
            "is_active": True,
            "raw_payload": normalized.raw_payload,
        }
        if row is None:
            row = db.scalar(select(Job).where(Job.url == normalized.url))
            if row is not None and row.company_id != company.id:
                raise CollectorError(
                    f"job URL is already assigned to a different company: {normalized.url}"
                )
        if row is None:
            row = Job(**values)
            db.add(row)
            new_jobs.append(row)
            new_count += 1
        else:
            for field, value in values.items():
                setattr(row, field, value)

    seen_urls = {job.url for job in snapshot}
    for row in existing.values():
        if row.url not in seen_urls:
            row.is_active = False

    db.flush()
    enqueue_new_matching_jobs(db, new_jobs)
    return new_count


def sync_board_jobs(
    db: Session,
    source: str,
    jobs: list[NormalizedJob],
    complete_snapshot: bool,
) -> int:
    snapshot = dedupe_snapshot(jobs)
    seen_at = datetime.now(timezone.utc)
    companies = db.scalars(select(Company)).all()
    existing = {
        job.url: job
        for job in db.scalars(select(Job).where(Job.source == source)).all()
    }
    new_count = 0
    new_jobs: list[Job] = []

    for normalized in snapshot:
        raw_apply_url = normalized.raw_payload.get("apply_url")
        matched_company = None
        if isinstance(raw_apply_url, str):
            detection = detect_ats_from_url(raw_apply_url)
            if detection.ats_type and detection.ats_slug:
                matched_company = next(
                    (
                        company
                        for company in companies
                        if company.ats_type == detection.ats_type
                        and company.ats_slug.casefold() == detection.ats_slug.casefold()
                    ),
                    None,
                )

        row = existing.get(normalized.url)
        values = {
            "source": source,
            "external_id": normalized.external_id,
            "url": normalized.url,
            "title": normalized.title,
            "company_id": matched_company.id if matched_company else None,
            "description": normalized.description,
            "location_text": normalized.location_text,
            "remote_scope": normalized.remote_scope,
            "employment_type": normalized.employment_type,
            "seniority": normalized.seniority,
            "salary_text": normalized.salary_text,
            "tags": normalized.tags,
            "posted_at": normalized.posted_at,
            "last_seen_at": seen_at,
            "is_active": True,
            "raw_payload": normalized.raw_payload,
        }
        if row is None:
            row = db.scalar(select(Job).where(Job.url == normalized.url))
            if row is not None and row.source != source:
                raise CollectorError(
                    f"job URL is already assigned to a different source: {normalized.url}"
                )
        if row is None:
            row = Job(**values)
            db.add(row)
            new_jobs.append(row)
            new_count += 1
        else:
            for field, value in values.items():
                setattr(row, field, value)

    if complete_snapshot:
        seen_urls = {job.url for job in snapshot}
        for row in existing.values():
            if row.url not in seen_urls:
                row.is_active = False

    db.flush()
    enqueue_new_matching_jobs(db, new_jobs)
    return new_count
