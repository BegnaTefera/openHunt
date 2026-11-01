from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

from app.collectors.base import NormalizedJob, infer_remote_scope


@dataclass(frozen=True)
class BoardSnapshot:
    jobs: list[NormalizedJob]
    complete: bool


class BoardCollector(Protocol):
    def collect(self) -> BoardSnapshot: ...


@dataclass(frozen=True)
class Link:
    href: str
    text: str


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append(Link(self._href, " ".join(" ".join(self._text).split())))
            self._href = None
            self._text = []


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self._title_depth = 0
        self._h1_depth = 0
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "meta":
            key = values.get("property") or values.get("name")
            content = values.get("content")
            if key and content:
                self.metadata[key.lower()] = content
        elif tag.lower() == "title":
            self._title_depth += 1
        elif tag.lower() == "h1":
            self._h1_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title" and self._title_depth:
            self._title_depth -= 1
        elif tag.lower() == "h1" and self._h1_depth:
            self._h1_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_parts.append(data)
        if self._h1_depth:
            self.h1_parts.append(data)


def extract_links(html: str) -> list[Link]:
    parser = _LinkParser()
    parser.feed(html)
    return parser.links


def extract_metadata(html: str) -> tuple[dict[str, str], str | None, str | None]:
    parser = _MetadataParser()
    parser.feed(html)
    title = " ".join(" ".join(parser.title_parts).split()) or None
    heading = " ".join(" ".join(parser.h1_parts).split()) or None
    return parser.metadata, title, heading


def normalize_url(value: str, base_url: str, hostname: str) -> str | None:
    absolute = urljoin(base_url, value.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or parts.hostname != hostname:
        return None
    return absolute


def external_http_url(value: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, value.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    return absolute


def source_slug(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1]


def make_normalized_job(
    *,
    source: str,
    url: str,
    title: str,
    description: str | None,
    location_text: str | None,
    employment_type: str | None,
    tags: list[str],
    posted_at: datetime | None,
    raw_payload: dict[str, Any],
) -> NormalizedJob:
    return NormalizedJob(
        source=source,
        external_id=source_slug(url),
        url=url,
        title=title,
        description=description,
        location_text=location_text,
        remote_scope=infer_remote_scope(location_text, title),
        employment_type=employment_type,
        seniority=None,
        salary_text=None,
        tags=tags,
        posted_at=posted_at,
        raw_payload=raw_payload,
    )
