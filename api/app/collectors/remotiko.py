from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

from app.collectors.base import CollectorError, fetch_text
from app.collectors.board_common import (
    BoardSnapshot,
    extract_links,
    extract_metadata,
    external_http_url,
    make_normalized_job,
    normalize_url,
    source_slug,
)
from app.core.config import settings

SOURCE = "remotiko"
HOST = "remotiko.com"
LISTING_URL = "https://remotiko.com/job-listings/"


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jobs: dict[str, str] = {}
        self._href: str | None = None
        self._parts: list[str] = []
        self._in_job_link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        href = values.get("href")
        if tag.lower() == "a" and href and urlsplit(href).path.startswith("/job/"):
            self._href = href
            self._parts = []
            self._in_job_link = True

    def handle_data(self, data: str) -> None:
        if self._in_job_link:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._in_job_link and self._href:
            title = " ".join(" ".join(self._parts).split())
            if title:
                self.jobs[self._href] = title
            self._href = None
            self._parts = []
            self._in_job_link = False


def parse_remotiko_listing(html: str) -> tuple[list[tuple[str, str]], bool]:
    parser = _ListingParser()
    parser.feed(html)
    jobs = list(parser.jobs.items())
    has_next_page = any(
        link.text.strip().lower().startswith("next")
        for link in extract_links(html)
    )
    return jobs, has_next_page


def parse_remotiko_job(
    html: str, url: str, listing_title: str
) -> tuple[str, str, str | None]:
    metadata, page_title, heading = extract_metadata(html)
    title = heading or listing_title
    description = metadata.get("description") or metadata.get("og:description")
    apply_links = []
    for link in extract_links(html):
        if link.text.casefold() not in {"apply", "apply now", "apply for this job"}:
            continue
        external_url = external_http_url(link.href, url)
        if external_url and urlsplit(external_url).hostname != HOST:
            apply_links.append(external_url)
    apply_url = next((link for link in reversed(apply_links) if link), None)
    if not apply_url:
        raise CollectorError(f"Remotiko job has no external Apply URL: {url}")
    if page_title and title == listing_title:
        title = page_title.split(" - ", 1)[0].strip() or listing_title
    return title, apply_url, description


class RemotikoCollector:
    def collect(self) -> BoardSnapshot:
        jobs = []
        seen_urls: set[str] = set()
        page = 1
        complete = False
        while len(jobs) < settings.max_jobs_per_run:
            query = {"remotiko_region": "africa_inclusive"}
            if page > 1:
                query["paged"] = str(page)
            listing_url = f"{LISTING_URL}?{urlencode(query)}"
            listing_html = fetch_text(listing_url)
            listings, has_next_page = parse_remotiko_listing(listing_html)
            if not listings:
                raise CollectorError(f"Remotiko listing contained no jobs: {listing_url}")

            for detail_path, listing_title in listings:
                detail_url = normalize_url(detail_path, LISTING_URL, HOST)
                if detail_url is None or detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)
                detail_html = fetch_text(detail_url)
                title, apply_url, description = parse_remotiko_job(
                    detail_html, detail_url, listing_title
                )
                jobs.append(
                    make_normalized_job(
                        source=SOURCE,
                        url=detail_url,
                        title=title,
                        description=description,
                        location_text="Africa-inclusive remote",
                        employment_type=None,
                        tags=["Africa inclusive"],
                        posted_at=None,
                        raw_payload={
                            "listing_url": listing_url,
                            "job_url": detail_url,
                            "apply_url": apply_url,
                            "title": title,
                        },
                    )
                )
                if len(jobs) >= settings.max_jobs_per_run:
                    break

            if len(jobs) >= settings.max_jobs_per_run:
                break
            if not has_next_page:
                complete = True
                break
            page += 1

        return BoardSnapshot(jobs=jobs, complete=complete)
