from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedJob:
    title: str
    company: str
    location: str
    remote: bool = False
    source: str = "manual"
    url: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)


def parse_job_description(raw_text: str, source: str = "manual", url: str = "") -> ParsedJob:
    normalized = raw_text.strip()
    if not normalized:
        raise ValueError("raw_text cannot be empty")

    first_line = normalized.splitlines()[0].strip()
    title = _extract_title(first_line, normalized)
    company = _extract_company(normalized)
    location = _extract_location(normalized)
    remote = "remote" in normalized.lower() or "remote-first" in normalized.lower()
    description = normalized[:2000]
    skills = _extract_skills(normalized)

    return ParsedJob(
        title=title,
        company=company,
        location=location,
        remote=remote,
        source=source,
        url=url,
        description=description,
        skills=skills,
    )


def _extract_title(first_line: str, raw_text: str) -> str:
    patterns = [
        r"(?i)title\s*[:\-]\s*(.+)",
        r"(?i)senior\s+[a-z0-9\-\s]+(?:engineer|developer|software)",
        r"(?i)(?:full-stack|backend|full stack|frontend|software)\s+(?:engineer|developer|developer)"
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text)
        if match:
            candidate = match.group(1).strip() if match.lastindex else match.group(0).strip()
            if candidate:
                return candidate
    return first_line or "Unknown role"


def _extract_company(raw_text: str) -> str:
    match = re.search(r"(?i)company\s*[:\-]\s*([A-Za-z0-9 .&'-]+)", raw_text)
    if match:
        return match.group(1).strip()
    return "Unknown company"


def _extract_location(raw_text: str) -> str:
    text = raw_text.lower()
    if "remote" in text:
        return "Remote"
    if "hybrid" in text:
        return "Hybrid"
    match = re.search(r"(?i)location\s*[:\-]\s*([A-Za-z0-9 ,.-]+)", raw_text)
    if match:
        return match.group(1).strip()
    return "Unknown location"


def _extract_skills(raw_text: str) -> list[str]:
    skill_tokens = [
        "python",
        "fastapi",
        "sqlalchemy",
        "postgresql",
        "next.js",
        "typescript",
        "react",
        "docker",
        "kubernetes",
        "aws",
        "redis",
    ]
    found = [token for token in skill_tokens if token.lower() in raw_text.lower()]
    return found
