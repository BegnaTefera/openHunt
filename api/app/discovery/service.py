"""Find new company job boards and add the ones that hire backend/full-stack roles."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors.base import CollectorError, CollectorUnavailableError
from app.collectors.registry import get_collector
from app.collectors.url_detection import detect_ats_from_url
from app.core.config import settings
from app.discovery.commoncrawl import CommonCrawlSource
from app.discovery.errors import DiscoveryError, QuotaExhaustedError
from app.discovery.providers import SearchProvider, configured_search_providers
from app.discovery.queries import build_search_queries, rotate
from app.models.company import Company
from app.models.discovery import DiscoveryCandidate
from app.models.event import Event
from app.models.profile import Profile
from app.services.job_scorer import is_target_title
from app.services.usage import Budget, get_usage, record_usage, remaining

logger = logging.getLogger("openhunt.discovery")

SUPPORTED_ATS = {"greenhouse", "lever", "ashby"}
_RESERVED_SLUGS = {
    "embed", "jobs", "api", "v1", "static", "assets", "apply", "favicon.ico",
    "robots.txt", "sitemap.xml", "login", "careers", "about", "privacy", "terms",
}

REASON_NO_MATCH = "no matching backend/full-stack roles"
REASON_NOT_FOUND = "board not found"
_RETRY_NO_MATCH_AFTER = timedelta(days=30)
_RETRY_OTHER_AFTER = timedelta(days=90)


class UrlSource(Protocol):
    name: str
    errors: list[str]

    def fetch_urls(self, db: Session) -> list[str]: ...


class SearchSource:
    """Runs a few rotating ``site:`` queries within a free-tier budget."""

    def __init__(
        self,
        provider: SearchProvider,
        budget: Budget,
        queries: list[str],
        max_queries: int,
    ) -> None:
        self.provider = provider
        self.budget = budget
        self.queries = queries
        self.max_queries = max_queries
        self.name = provider.name
        self.errors: list[str] = []

    def fetch_urls(self, db: Session) -> list[str]:
        allowed = min(self.max_queries, remaining(db, self.name, self.budget))
        if allowed <= 0:
            self.errors.append(f"{self.name}: free-tier budget used up for now")
            return []
        cursor = get_usage(db, self.name).total
        urls: list[str] = []
        for query in rotate(self.queries, cursor, allowed):
            record_usage(db, self.name)  # count the attempt before calling out
            db.commit()
            try:
                urls.extend(self.provider.search(query))
            except QuotaExhaustedError as error:
                self.errors.append(str(error))
                break
            except DiscoveryError as error:
                self.errors.append(str(error))
        return urls


@dataclass
class BoardCheck:
    outcome: str  # ok | no_match | dead | transient | unsupported
    detail: str


def validate_board(ats_type: str, slug: str) -> BoardCheck:
    """Call the board's public jobs API once and look for backend/full-stack titles."""
    company = Company(name=slug, ats_type=ats_type, ats_slug=slug)
    try:
        collector = get_collector(ats_type)
    except CollectorUnavailableError as error:
        return BoardCheck("unsupported", str(error))
    try:
        payloads = collector.fetch(company)
    except CollectorError as error:
        cause = error.__cause__
        if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code in (404, 410):
            return BoardCheck("dead", REASON_NOT_FOUND)
        return BoardCheck("transient", str(error))

    titles: list[str] = []
    for payload in payloads:
        try:
            titles.append(collector.normalize(company, payload).title)
        except CollectorError:
            continue
    matching = [title for title in titles if is_target_title(title)]
    if not matching:
        return BoardCheck("no_match", REASON_NO_MATCH)
    return BoardCheck("ok", f"{len(matching)} of {len(titles)} jobs are backend/full-stack")


def extract_candidates(urls: Iterable[str]) -> dict[tuple[str, str], str]:
    """Map (ats_type, lowercase slug) to the slug as written, for supported ATSs."""
    found: dict[tuple[str, str], str] = {}
    for url in urls:
        slug = None
        detection = detect_ats_from_url(url)
        if detection.ats_type not in SUPPORTED_ATS:
            continue
        slug = detection.ats_slug
        if detection.ats_type == "greenhouse" and slug and slug.casefold() == "embed":
            values = parse_qs(urlsplit(url).query).get("for")
            slug = values[0] if values else None
        if not slug or slug.casefold() in _RESERVED_SLUGS:
            continue
        found.setdefault((detection.ats_type, slug.casefold()), slug)
    return found


def display_name(slug: str) -> str:
    words = slug.replace("_", " ").replace("-", " ").replace(".", " ").split()
    return " ".join(word.capitalize() for word in words) or slug


@dataclass
class DiscoveryReport:
    urls_seen: int = 0
    candidates: int = 0
    already_known: int = 0
    validated: int = 0
    added: int = 0
    rejected: int = 0
    deferred: int = 0
    sources: dict[str, int] = field(default_factory=dict)
    added_companies: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_retryable(row: DiscoveryCandidate, now: datetime) -> bool:
    if row.status == "added":
        return False
    age = now - row.found_at
    if row.reason == REASON_NO_MATCH:
        return age > _RETRY_NO_MATCH_AFTER
    return age > _RETRY_OTHER_AFTER


def _create_company(db: Session, ats_type: str, slug: str) -> Company | None:
    base = display_name(slug)
    for name in (base, f"{base} ({ats_type})"):
        try:
            with db.begin_nested():
                company = Company(name=name, ats_type=ats_type, ats_slug=slug)
                db.add(company)
                db.flush()
            return company
        except IntegrityError:
            continue
    return None


def default_sources(db: Session) -> list[UrlSource]:
    profile = db.scalar(select(Profile).where(Profile.id == 1))
    queries = build_search_queries(list(profile.target_roles) if profile else None)
    sources: list[UrlSource] = [
        SearchSource(provider, budget, queries, settings.discovery_max_queries_per_run)
        for provider, budget in configured_search_providers()
    ]
    if settings.commoncrawl_enabled:
        sources.append(CommonCrawlSource())
    return sources


def run_discovery(
    db: Session,
    sources: list[UrlSource] | None = None,
    *,
    max_validations: int | None = None,
    validator: Callable[[str, str], BoardCheck] = validate_board,
    now: datetime | None = None,
) -> DiscoveryReport:
    now = now or datetime.now(timezone.utc)
    limit = settings.discovery_max_validations_per_run if max_validations is None else max_validations
    sources = default_sources(db) if sources is None else sources
    report = DiscoveryReport()

    urls_by_source: list[tuple[str, list[str]]] = []
    for source in sources:
        try:
            urls = source.fetch_urls(db)
        except DiscoveryError as error:
            report.errors.append(str(error))
            continue
        report.errors.extend(source.errors)
        report.sources[source.name] = len(urls)
        report.urls_seen += len(urls)
        urls_by_source.append((source.name, urls))

    ordered: list[tuple[str, str, str, str]] = []  # source, ats_type, key slug, slug
    seen: set[tuple[str, str]] = set()
    for source_name, urls in urls_by_source:
        for (ats_type, key), slug in extract_candidates(urls).items():
            if (ats_type, key) not in seen:
                seen.add((ats_type, key))
                ordered.append((source_name, ats_type, key, slug))
    report.candidates = len(ordered)

    known_companies = {
        (company.ats_type, company.ats_slug.casefold())
        for company in db.scalars(select(Company)).all()
    }
    rows = {
        (row.ats_type, row.ats_slug.casefold()): row
        for row in db.scalars(select(DiscoveryCandidate)).all()
    }

    for source_name, ats_type, key, slug in ordered:
        if (ats_type, key) in known_companies:
            report.already_known += 1
            continue
        row = rows.get((ats_type, key))
        if row is not None and not _is_retryable(row, now):
            report.already_known += 1
            continue
        if report.validated >= limit:
            report.deferred += 1
            continue

        report.validated += 1
        check = validator(ats_type, slug)
        if check.outcome == "transient":
            report.deferred += 1
            report.errors.append(f"{ats_type}/{slug}: {check.detail}")
            continue

        company = None
        if check.outcome == "ok":
            company = _create_company(db, ats_type, slug)
        status = "added" if company is not None else "rejected"
        reason = check.detail if company is not None or check.outcome != "ok" else "name already in use"

        if row is None:
            row = DiscoveryCandidate(ats_type=ats_type, ats_slug=slug, source=source_name)
            db.add(row)
            rows[(ats_type, key)] = row
        row.status = status
        row.reason = reason
        row.source = source_name
        row.company_id = company.id if company is not None else None
        row.found_at = now
        if company is not None:
            report.added += 1
            report.added_companies.append(company.name)
            known_companies.add((ats_type, key))
        else:
            report.rejected += 1
        db.commit()

    db.add(
        Event(
            entity_type="discovery",
            entity_id=None,
            action="run_completed",
            details=asdict(report),
        )
    )
    db.commit()
    logger.info(
        "Discovery: %s URLs, %s candidates, %s validated, %s added, %s rejected, %s deferred",
        report.urls_seen, report.candidates, report.validated,
        report.added, report.rejected, report.deferred,
    )
    return report
