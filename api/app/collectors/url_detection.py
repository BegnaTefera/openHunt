from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ATSDetection:
    ats_type: str | None
    ats_slug: str | None


def detect_ats_from_url(value: str) -> ATSDetection:
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").lower()
        path = [segment for segment in parsed.path.split("/") if segment]
    except ValueError:
        return ATSDetection(None, None)

    if hostname.endswith(".greenhouse.io") or hostname == "greenhouse.io":
        slug = _first_after(path, "boards", "job-boards")
        if slug is None and path:
            slug = path[0]
        return ATSDetection("greenhouse", slug)

    if hostname.endswith(".lever.co") or hostname == "lever.co":
        if hostname.startswith("jobs.") or hostname.startswith("api."):
            return ATSDetection("lever", path[0] if path else None)

    if hostname.endswith(".ashbyhq.com") or hostname == "ashbyhq.com":
        if hostname.startswith("jobs.") or hostname.startswith("api."):
            return ATSDetection("ashby", path[0] if path else None)

    if hostname.endswith(".workable.com") or hostname == "workable.com":
        if hostname.startswith("apply.") or hostname.startswith("www."):
            return ATSDetection("workable", path[0] if path else None)

    return ATSDetection(None, None)


def _first_after(path: list[str], *markers: str) -> str | None:
    for index, segment in enumerate(path[:-1]):
        if segment.lower() in markers:
            return path[index + 1]
    return None
