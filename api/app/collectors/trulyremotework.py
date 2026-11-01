from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from app.collectors.base import CollectorError, fetch_text
from app.collectors.board_common import BoardSnapshot, make_normalized_job, source_slug
from app.core.config import settings

SOURCE = "trulyremotework"
CORPUS_URL = "https://trulyremotework.com/llms-full.txt"
HOST = "trulyremotework.com"


def parse_trulyremotework_corpus(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for block in re.split(r"(?m)^## ", text):
        heading, separator, body = block.partition("\n")
        if not separator:
            continue
        values = {
            key.lower(): value.strip()
            for key, value in re.findall(
                r"(?m)^-\s*([A-Za-z]+):\s*(.+?)\s*$", body
            )
        }
        url = values.get("url", "")
        category = values.get("category", "").casefold()
        if (
            category not in {"engineering", "development"}
            or not url.startswith("https://trulyremotework.com/jobs/")
        ):
            continue
        records.append(
            {
                "title": heading.strip(),
                "url": url,
                "category": values["category"],
                "location": values.get("location", ""),
            }
        )
    return records


def parse_trulyremotework_job(
    markdown: str, expected_url: str
) -> dict[str, Any]:
    fields = {
        key.lower(): value.strip()
        for key, value in re.findall(
            r"(?m)^\*\*([A-Za-z]+):\*\*\s*(.+?)\s*$", markdown
        )
    }
    apply_url = fields.get("apply")
    if (
        not apply_url
        or urlsplit(apply_url).scheme not in {"http", "https"}
        or urlsplit(apply_url).hostname == HOST
    ):
        raise CollectorError(f"TrulyRemoteWork Markdown has no Apply URL: {expected_url}")
    location = fields.get("location")
    job_type = fields.get("type")
    posted = fields.get("posted")
    posted_at: datetime | None = None
    if posted:
        try:
            posted_at = datetime.strptime(posted, "%a %b %d %Y").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            posted_at = None
    description = ""
    if "## Description" in markdown:
        description = markdown.split("## Description", 1)[1].strip()
        description = description.split("\n## ", 1)[0].strip()
    tags = [tag.strip() for tag in fields.get("tags", "").split(",") if tag.strip()]
    return {
        "title": markdown.partition("\n")[0].removeprefix("# ").strip(),
        "apply_url": apply_url,
        "location": location,
        "employment_type": job_type,
        "posted_at": posted_at,
        "tags": tags,
        "description": description or None,
        "raw_payload": {"markdown": markdown, "apply_url": apply_url},
    }


class TrulyRemoteWorkCollector:
    def collect(self) -> BoardSnapshot:
        corpus = fetch_text(CORPUS_URL, accept="text/plain")
        records = parse_trulyremotework_corpus(corpus)
        if not records:
            raise CollectorError("TrulyRemoteWork corpus contained no engineering jobs")

        jobs = []
        complete = len(records) <= settings.max_jobs_per_run
        for record in records[: settings.max_jobs_per_run]:
            url = record["url"]
            parts = urlsplit(url)
            if parts.hostname != HOST:
                raise CollectorError(f"Unexpected TrulyRemoteWork job URL: {url}")
            markdown_url = f"{url.rstrip('/')}.md"
            markdown = fetch_text(markdown_url, accept="text/markdown,text/plain")
            parsed = parse_trulyremotework_job(markdown, url)
            title = parsed["title"] or record["title"]
            payload = {
                **parsed["raw_payload"],
                "corpus_url": CORPUS_URL,
                "category": record["category"],
                "location": parsed["location"] or record["location"],
            }
            jobs.append(
                make_normalized_job(
                    source=SOURCE,
                    url=url,
                    title=title,
                    description=parsed["description"],
                    location_text=parsed["location"] or record["location"],
                    employment_type=parsed["employment_type"],
                    tags=parsed["tags"] or [record["category"]],
                    posted_at=parsed["posted_at"],
                    raw_payload=payload,
                )
            )
        return BoardSnapshot(jobs=jobs, complete=complete)
