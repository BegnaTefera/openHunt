from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlsplit

from app.collectors.base import CollectorError, fetch_text
from app.collectors.board_common import (
    BoardSnapshot,
    extract_links,
    extract_metadata,
    make_normalized_job,
)
from app.core.config import settings

SOURCE = "dynamitejobs"
SITEMAP_URL = (
    "https://dynamitejobs.com/sitemap/jobs-of-category.xml?category=development"
)
HOST = "dynamitejobs.com"
SITEMAP_NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def parse_dynamitejobs_sitemap(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise CollectorError("Dynamite Jobs returned invalid category XML") from error
    urls = []
    for location in root.iter(f"{SITEMAP_NAMESPACE}loc"):
        url = location.text or ""
        path = urlsplit(url).path
        if (
            urlsplit(url).hostname == HOST
            and "/company/" in path
            and "/remote-job/" in path
        ):
            urls.append(url)
    return list(dict.fromkeys(urls))


def parse_dynamitejobs_detail(html: str, url: str) -> dict[str, Any]:
    metadata, page_title, heading = extract_metadata(html)
    title = (
        heading
        or metadata.get("og:title")
        or page_title
        or source_slug(url).replace("-", " ").title()
    )
    for suffix in (" | Dynamite Jobs", " - Dynamite Jobs", " — Dynamite Jobs"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    description = metadata.get("og:description") or metadata.get("description")
    apply_links = [
        link.href
        for link in extract_links(html)
        if "apply" in link.text.casefold()
        and urlsplit(link.href).hostname != HOST
        and urlsplit(link.href).scheme in {"http", "https"}
    ]
    company_slug = urlsplit(url).path.split("/")[2]
    return {
        "title": title,
        "description": description,
        "company_slug": company_slug,
        "apply_url": apply_links[0] if apply_links else None,
    }


class DynamiteJobsCollector:
    def collect(self) -> BoardSnapshot:
        urls = parse_dynamitejobs_sitemap(fetch_text(SITEMAP_URL, accept="application/xml"))
        if not urls:
            raise CollectorError("Dynamite Jobs development sitemap contained no job URLs")
        complete = len(urls) <= settings.max_jobs_per_run
        jobs = []
        for url in urls[: settings.max_jobs_per_run]:
            html = fetch_text(url)
            parsed = parse_dynamitejobs_detail(html, url)
            raw_payload = {
                "category": "Developer / Engineer",
                "job_url": url,
                "company_slug": parsed["company_slug"],
                "title": parsed["title"],
                "description": parsed["description"],
            }
            if parsed["apply_url"]:
                raw_payload["apply_url"] = parsed["apply_url"]
            jobs.append(
                make_normalized_job(
                    source=SOURCE,
                    url=url,
                    title=parsed["title"],
                    description=parsed["description"],
                    location_text="Remote",
                    employment_type=None,
                    tags=["Developer / Engineer"],
                    posted_at=None,
                    raw_payload=raw_payload,
                )
            )
        return BoardSnapshot(jobs=jobs, complete=complete)
