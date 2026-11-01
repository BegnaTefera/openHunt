from __future__ import annotations

import time
from collections import deque
from threading import Lock
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings


class RateLimiter:
    def __init__(
        self, requests_per_minute: int, min_interval_seconds: float = 2.0
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be at least 1")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.requests_per_minute = requests_per_minute
        self.min_interval_seconds = min_interval_seconds
        self._timestamps: deque[float] = deque()
        self._last_request_at: float | None = None
        self._lock = Lock()

    def acquire(self) -> None:
        window_seconds = 60.0
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= window_seconds:
                    self._timestamps.popleft()
                interval_wait = (
                    max(0.0, self.min_interval_seconds - (now - self._last_request_at))
                    if self._last_request_at is not None
                    else 0.0
                )
                window_wait = (
                    max(0.0, window_seconds - (now - self._timestamps[0]))
                    if len(self._timestamps) >= self.requests_per_minute
                    else 0.0
                )
                wait_seconds = max(interval_wait, window_wait)
                if wait_seconds == 0:
                    self._timestamps.append(now)
                    self._last_request_at = now
                    return
            time.sleep(wait_seconds)


rate_limiter = RateLimiter(settings.requests_per_minute)


def can_fetch_url(url: str, user_agent: str | None = None) -> bool:
    agent = user_agent or settings.user_agent
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("url must be an absolute HTTP or HTTPS URL")
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    rate_limiter.acquire()
    response = httpx.get(
        robots_url,
        headers={"User-Agent": agent},
        timeout=settings.request_timeout_seconds,
        follow_redirects=False,
    )
    if response.status_code == 404:
        return True
    response.raise_for_status()

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(agent, url)
