from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.services.roles import matches_roles

_SENIORITY_RE = re.compile(r"\b(senior|staff|principal|lead)\b", re.I)
_COUNTRY_LIMIT_RE = re.compile(
    r"\b(?:only\s+(?:applicants?|candidates?|employees?|residents?)\s+"
    r"(?:located|based|residing)?\s*(?:in|from)|"
    r"(?:applicants?|candidates?|employees?)\s+(?:must\s+be\s+)?"
    r"(?:located|based|resident|residing)\s+in|"
    r"(?:must\s+be\s+)?(?:located|based|resident|reside)\s+in)"
    r"\s+([^.;\n]+)",
    re.I,
)
_COUNTRY_SUFFIX_RE = re.compile(
    r"\b((?-i:[A-Z]{2,3})|United States|United Kingdom|South Africa|"
    r"New Zealand|European Union|Europe|Canada|Australia|India|Ireland|"
    r"Nigeria|Kenya|Singapore|Japan|Brazil|Mexico|France|Germany|Spain|"
    r"Portugal|Netherlands)\s+only\b",
    re.I,
)
_TIMEZONE_LIMIT_RE = re.compile(
    r"\b(?:time[\s-]?zones?|timezone|working hours|business hours|overlap with)"
    r"\b[^.;\n]{0,50}",
    re.I,
)
_TIMEZONE_RE = re.compile(
    r"\b(?:UTC|GMT)\s*[+-]\s*\d{1,2}(?::?\d{2})?\b|"
    r"\b(?:PST|PDT|MST|MDT|CST|CDT|EST|EDT|AKST|AKDT|"
    r"HST|GMT|UTC|BST|CET|CEST|EET|EEST|IST|JST|"
    r"WAT|CAT|EAT|SAST|"
    r"AEST|AEDT|NZST|NZDT)\b",
    re.I,
)
_AUTH_LIMIT_RE = re.compile(
    r"\b(?:must\s+be\s+)?(?:legally\s+)?authorized\s+to\s+work\s+in\s+"
    r"([^.;\n]+)|"
    r"\bwork\s+authorization\s+(?:for|in)\s+([^.;\n]+)|"
    r"\bright\s+to\s+work\s+in\s+([^.;\n]+)|"
    r"\b(United States|United Kingdom|South Africa|New Zealand|Canada|"
    r"Australia|India|Ireland|Nigeria|Kenya|Singapore|Japan|Brazil|Mexico|"
    r"France|Germany|Spain|Portugal|Netherlands|USA|US|UK)\s+"
    r"(?:work\s+authorization|work\s+eligibility)\s+"
    r"(?:is\s+)?(?:required|needed|mandatory)\b",
    re.I,
)


def _field(job: object, name: str, default: Any = None) -> Any:
    """Read a job field whether the job is a dict (dashboard) or an object (parser, tests)."""
    if isinstance(job, Mapping):
        return job.get(name, default)
    return getattr(job, name, default)


@dataclass
class Profile:
    # Role family keys from app.services.roles. An empty list means every tech role.
    preferred_roles: list[str] = field(default_factory=lambda: ["backend", "full-stack"])
    custom_title_keywords: list[str] = field(default_factory=list)
    tech_stack: set[str] = field(
        default_factory=lambda: {"python", "fastapi", "postgresql", "typescript", "react"}
    )
    years_experience: int = 4
    remote_only: bool = True
    allowed_seniority: set[str] = field(default_factory=set)
    country: str | None = None
    timezones: set[str] = field(default_factory=set)
    work_authorizations: set[str] = field(default_factory=set)


def _normalized_values(values: set[str]) -> set[str]:
    return {re.sub(r"\s+", " ", value.strip().casefold()) for value in values if value.strip()}


def _contains_configured_value(text: str, values: set[str]) -> bool:
    normalized_text = re.sub(r"\s+", " ", text.casefold())
    return any(
        re.search(rf"(?<!\w){re.escape(value)}(?!\w)", normalized_text)
        for value in _normalized_values(values)
    )


def _eligibility_reasons(job: object, profile: Profile) -> list[str]:
    title = _field(job, "title", "") or ""
    description = _field(job, "description", "") or ""
    location = _field(job, "location", "") or _field(job, "location_text", "") or ""
    text = f"{title}\n{location}\n{description}"
    reasons: list[str] = []

    if not matches_roles(title, profile.preferred_roles, profile.custom_title_keywords):
        reasons.append("excluded: title does not match your selected role types")

    allowed_seniority = _normalized_values(profile.allowed_seniority)
    title_levels = {match.casefold() for match in _SENIORITY_RE.findall(title)}
    job_seniority = (_field(job, "seniority", None) or "").strip().casefold()
    if job_seniority in {"senior", "staff", "principal", "lead"}:
        title_levels.add(job_seniority)
    disallowed_levels = title_levels - allowed_seniority
    if disallowed_levels:
        reasons.append(
            "excluded: seniority not allowed ("
            + ", ".join(sorted(disallowed_levels))
            + ")"
        )

    if profile.country:
        country_clauses = [
            match.group(1)
            for match in _COUNTRY_LIMIT_RE.finditer(text)
        ]
        country_clauses.extend(
            match.group(1) for match in _COUNTRY_SUFFIX_RE.finditer(text)
        )
        if country_clauses and not _contains_configured_value(
            " ".join(country_clauses), {profile.country}
        ):
            reasons.append("excluded: country restriction does not include your country")

    if profile.timezones:
        for clause in _TIMEZONE_LIMIT_RE.findall(text):
            configured_zones = _normalized_values(profile.timezones)
            mentioned_zones = {
                match.group(0).casefold() for match in _TIMEZONE_RE.finditer(clause)
            }
            mentioned_zones.update(
                zone
                for zone in configured_zones
                if re.search(rf"(?<!\w){re.escape(zone)}(?!\w)", clause, re.I)
            )
            if mentioned_zones and not mentioned_zones.intersection(configured_zones):
                reasons.append("excluded: timezone restriction does not match your timezones")
                break

    if profile.work_authorizations:
        configured_authorizations = _normalized_values(profile.work_authorizations)
        for match in _AUTH_LIMIT_RE.finditer(text):
            required_region = next((value for value in match.groups() if value), "")
            if required_region and not _contains_configured_value(
                required_region, configured_authorizations
            ):
                reasons.append(
                    "excluded: work-authorization requirement is not in your profile"
                )
                break

    return reasons


def score_job(job: object, profile: Profile) -> tuple[int, list[str]]:
    eligibility_reasons = _eligibility_reasons(job, profile)
    if eligibility_reasons:
        return 0, eligibility_reasons

    title = (_field(job, "title", "") or "").lower()
    description = (_field(job, "description", "") or "").lower()
    location = (
        _field(job, "location", "")
        or _field(job, "location_text", "")
        or ""
    ).lower()
    remote = bool(_field(job, "remote", False))
    skills = {skill.lower() for skill in _field(job, "skills", [])}

    score = 0
    reasons: list[str] = []

    if matches_roles(title, profile.preferred_roles, profile.custom_title_keywords):
        score += 35
        reasons.append("role match")

    overlap = sorted(profile.tech_stack & skills)
    if overlap:
        score += min(30, 10 * len(overlap))
        reasons.append(f"tech overlap: {', '.join(overlap)}")

    if profile.remote_only and (remote or "remote" in location):
        score += 15
        reasons.append("remote-friendly")

    # Small bonus for each of the user's own skills that the description mentions.
    mentioned = [skill for skill in sorted(profile.tech_stack) if skill and skill in description]
    score += min(10, 2 * len(mentioned))

    score = max(0, min(100, score))
    return score, reasons
