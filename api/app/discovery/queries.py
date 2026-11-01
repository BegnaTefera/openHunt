"""Google-style site: queries for finding ATS-hosted job boards."""

from __future__ import annotations

ATS_SEARCH_HOSTS = (
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
)

_MODIFIERS = ("remote", "junior remote")


def _role_phrases(role: str) -> list[str]:
    normalized = role.casefold().replace("-", " ").strip()
    if not normalized:
        return []
    if "full" in normalized:
        return ["full stack engineer", "full stack developer"]
    if "back" in normalized:
        return ["backend engineer", "backend developer"]
    return [normalized]


def build_search_queries(target_roles: list[str] | None) -> list[str]:
    """Return one ``site:`` query per host, role phrase, and modifier.

    One host per query keeps each query simple for any search engine, and the
    caller rotates through the list so a small daily quota still covers all of it.
    """
    roles = target_roles or ["backend", "full-stack"]
    phrases: list[str] = []
    for role in roles:
        for phrase in _role_phrases(role):
            if phrase not in phrases:
                phrases.append(phrase)
    return [
        f'site:{host} "{phrase}" {modifier}'
        for phrase in phrases
        for modifier in _MODIFIERS
        for host in ATS_SEARCH_HOSTS
    ]


def rotate(items: list[str], cursor: int, count: int) -> list[str]:
    """Pick ``count`` items starting at ``cursor`` and wrapping around."""
    if not items or count <= 0:
        return []
    count = min(count, len(items))
    return [items[(cursor + offset) % len(items)] for offset in range(count)]
