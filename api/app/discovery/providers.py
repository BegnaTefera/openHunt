"""Free-tier web search providers that understand ``site:`` queries."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.discovery.errors import DiscoveryError, QuotaExhaustedError
from app.services.robots import rate_limiter
from app.services.usage import Budget


class SearchProvider(Protocol):
    name: str

    def search(self, query: str) -> list[str]:
        """Return result URLs for the query."""


def _raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.status_code == 429:
        raise QuotaExhaustedError(f"{provider} rate limit or quota reached (HTTP 429)")
    if response.status_code in (401, 402, 403):
        raise QuotaExhaustedError(
            f"{provider} rejected the request (HTTP {response.status_code}); "
            "check the API key and remaining credit"
        )
    try:
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise DiscoveryError(f"{provider} request failed: HTTP {response.status_code}") from error


class SerpApiSearchProvider:
    name = "serpapi"
    endpoint = "https://serpapi.com/search.json"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str) -> list[str]:
        rate_limiter.acquire()
        try:
            response = httpx.get(
                self.endpoint,
                params={"engine": "google", "q": query, "api_key": self.api_key, "num": 20},
                headers={"Accept": "application/json", "User-Agent": settings.user_agent},
                timeout=settings.api_timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise DiscoveryError("SerpApi request failed") from error
        _raise_for_status(response, "SerpApi")
        payload = _json(response, "SerpApi")
        if isinstance(payload, dict) and payload.get("error"):
            raise DiscoveryError("SerpApi returned an error")
        return parse_serpapi_results(payload)


class SerperSearchProvider:
    name = "serper"
    endpoint = "https://google.serper.dev/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str) -> list[str]:
        rate_limiter.acquire()
        try:
            response = httpx.post(
                self.endpoint,
                json={"q": query, "num": 20},
                headers={"X-API-KEY": self.api_key, "User-Agent": settings.user_agent},
                timeout=settings.api_timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise DiscoveryError("Serper request failed") from error
        _raise_for_status(response, "Serper")
        return parse_serper_results(_json(response, "Serper"))


def _json(response: httpx.Response, provider: str) -> Any:
    try:
        return response.json()
    except ValueError as error:
        raise DiscoveryError(f"{provider} returned invalid JSON") from error


def parse_serpapi_results(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    results = (payload or {}).get("organic_results") or []
    return [item["link"] for item in results if isinstance(item, dict) and item.get("link")]


def parse_serper_results(payload: Any) -> list[str]:
    results = (payload or {}).get("organic") or []
    return [item["link"] for item in results if isinstance(item, dict) and item.get("link")]


def configured_search_providers() -> list[tuple[SearchProvider, Budget]]:
    """Providers with an API key, each with its free-tier budget from settings."""
    providers: list[tuple[SearchProvider, Budget]] = []
    if settings.serpapi_api_key:
        providers.append(
            (
                SerpApiSearchProvider(settings.serpapi_api_key),
                Budget(monthly=settings.serpapi_monthly_cap),
            )
        )
    if settings.serper_api_key:
        providers.append(
            (
                SerperSearchProvider(settings.serper_api_key),
                Budget(daily=settings.serper_daily_cap, total=settings.serper_total_cap),
            )
        )
    return providers
