"""Google-style site: queries for finding ATS-hosted job boards."""

from __future__ import annotations

from app.services.roles import search_phrases_for

ATS_SEARCH_HOSTS = (
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
)

_MODIFIERS = ("remote", "junior remote")


def build_search_queries(target_roles: list[str] | None) -> list[str]:
    """Return one ``site:`` query per host, role phrase, and modifier.

    ``target_roles`` are role family keys (see ``app.services.roles``); an empty
    list means every tech family. One host per query keeps each query simple for any
    search engine, and the caller rotates through the list so a small daily quota
    still covers all of it.
    """
    phrases = search_phrases_for(target_roles)
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
