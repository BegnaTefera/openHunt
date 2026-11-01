"""Enumerate ATS board URLs from Common Crawl's free public URL index."""

from __future__ import annotations

import json
import string

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.discovery.errors import DiscoveryError
from app.discovery.queries import ATS_SEARCH_HOSTS
from app.services.robots import rate_limiter
from app.services.usage import get_usage, record_usage

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
_PREFIX_ALPHABET = string.ascii_lowercase + string.digits


def parse_collinfo(payload: object) -> str:
    """Return the CDX endpoint of the newest crawl (the first collinfo entry)."""
    if not isinstance(payload, list) or not payload:
        raise DiscoveryError("Common Crawl collinfo.json had no crawls")
    endpoint = payload[0].get("cdx-api") if isinstance(payload[0], dict) else None
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise DiscoveryError("Common Crawl collinfo.json had no cdx-api endpoint")
    return endpoint


def parse_cdx_lines(body: str) -> list[str]:
    """Parse ``output=json`` CDX responses: one JSON object per line."""
    urls: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and isinstance(record.get("url"), str):
            urls.append(record["url"])
    return urls


class CommonCrawlSource:
    """Queries one slug-prefix slice per host per run, rotating through a-z, 0-9.

    A CDX prefix query returns URLs in alphabetical order, so a single capped query
    would always return the same companies. Rotating the first slug character
    explores a different slice of the index on each run.
    """

    name = "commoncrawl"

    def __init__(self, hosts: tuple[str, ...] = ATS_SEARCH_HOSTS) -> None:
        self.hosts = hosts
        self.errors: list[str] = []

    def fetch_urls(self, db: Session) -> list[str]:
        cursor = get_usage(db, self.name).total
        character = _PREFIX_ALPHABET[(cursor // max(1, len(self.hosts))) % len(_PREFIX_ALPHABET)]
        try:
            endpoint = self._latest_endpoint()
        except DiscoveryError as error:
            self.errors.append(str(error))
            return []

        urls: list[str] = []
        for host in self.hosts:
            record_usage(db, self.name)
            db.commit()
            try:
                urls.extend(self._query(endpoint, f"{host}/{character}*"))
            except DiscoveryError as error:
                self.errors.append(str(error))
        return urls

    def _latest_endpoint(self) -> str:
        rate_limiter.acquire()
        try:
            response = httpx.get(
                COLLINFO_URL,
                headers={"User-Agent": settings.user_agent},
                timeout=settings.api_timeout_seconds,
            )
            response.raise_for_status()
            return parse_collinfo(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise DiscoveryError("Could not read Common Crawl collinfo.json") from error

    def _query(self, endpoint: str, url_pattern: str) -> list[str]:
        rate_limiter.acquire()
        try:
            response = httpx.get(
                endpoint,
                params={
                    "url": url_pattern,
                    "output": "json",
                    "fl": "url",
                    "filter": "=status:200",
                    "limit": settings.commoncrawl_max_urls_per_host,
                },
                headers={"User-Agent": settings.user_agent},
                timeout=settings.api_timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise DiscoveryError(f"Common Crawl request failed for {url_pattern}") from error
        if response.status_code == 404:
            return []  # the index reports "no captures" as 404
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise DiscoveryError(
                f"Common Crawl returned HTTP {response.status_code} for {url_pattern}"
            ) from error
        return parse_cdx_lines(response.text)
