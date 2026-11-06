from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.application import ApplicationStatus
from app.models.company import Company
from app.models.integrations import NotificationOutbox
from app.models.job import Job
from app.models.profile import Profile
from app.services.roles import matches_roles

logger = logging.getLogger("openhunt.notifications")


def telegram_enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _enqueue(
    db: Session, user_id: int, event_type: str, payload: dict[str, Any]
) -> None:
    if telegram_enabled():
        db.add(NotificationOutbox(user_id=user_id, event_type=event_type, payload=payload))


def enqueue_status_change(
    db: Session,
    user_id: int,
    job: Job,
    company: str | None,
    old_status: ApplicationStatus | None,
    new_status: ApplicationStatus,
) -> None:
    if old_status == new_status:
        return
    _enqueue(
        db,
        user_id,
        "application_status",
        {
            "title": job.title,
            "company": company or "Company",
            "url": job.url,
            "old_status": old_status.value if old_status else "not tracked",
            "new_status": new_status.value,
        },
    )


def enqueue_reply(
    db: Session,
    user_id: int,
    job: Job,
    company: str | None,
) -> None:
    _enqueue(
        db,
        user_id,
        "application_reply",
        {
            "title": job.title,
            "company": company or "Company",
            "url": job.url,
        },
    )


def _plain(value: Any) -> str:
    return " ".join(str(value).split())


def enqueue_new_matching_jobs(db: Session, jobs: list[Job]) -> None:
    if not jobs or not telegram_enabled():
        return
    profiles = db.execute(select(Profile.user_id, Profile.target_roles, Profile.preferences)).all()
    for profile in profiles:
        preferences = profile.preferences or {}
        keywords = preferences.get("custom_title_keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        for job in jobs:
            if matches_roles(job.title, profile.target_roles, [str(value) for value in keywords]):
                company = db.get(Company, job.company_id) if job.company_id else None
                _enqueue(
                    db,
                    profile.user_id,
                    "new_matching_job",
                    {
                        "title": job.title,
                        "company": company.name if company else "New job",
                        "url": job.url,
                    },
                )


def _message(item: NotificationOutbox) -> str:
    payload = item.payload
    if item.event_type == "application_reply":
        return (
            f"New Gmail reply for {_plain(payload['title'])} at {_plain(payload['company'])}\n"
            f"{_plain(payload['url'])}"
        )
    if item.event_type == "application_status":
        return (
            f"Application status: {_plain(payload['title'])} at {_plain(payload['company'])}\n"
            f"{_plain(payload['old_status'])} -> {_plain(payload['new_status'])}\n"
            f"{_plain(payload['url'])}"
        )
    if item.event_type == "new_matching_job":
        return f"New matching job: {_plain(payload['title'])}\n{_plain(payload['url'])}"
    raise ValueError(f"Unknown Telegram notification type: {item.event_type}")


def dispatch_telegram_notifications(db: Session, *, limit: int = 50) -> int:
    if not telegram_enabled():
        return 0

    now = datetime.now(timezone.utc)
    item_ids = db.scalars(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.delivered_at.is_(None),
            NotificationOutbox.next_attempt_at <= now,
        )
        .order_by(NotificationOutbox.id)
        .limit(limit)
        .with_only_columns(NotificationOutbox.id)
    ).all()
    sent = 0
    for item_id in item_ids:
        item = db.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id == item_id,
                NotificationOutbox.delivered_at.is_(None),
                NotificationOutbox.next_attempt_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        if item is None:
            continue
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": _message(item)},
                timeout=settings.api_timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise RuntimeError("Telegram rejected the message")
            item.delivered_at = now
            item.last_error = None
            sent += 1
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            item.attempt_count += 1
            item.last_error = type(error).__name__
            retry_minutes = min(2 ** min(item.attempt_count, 6), 60)
            item.next_attempt_at = now + timedelta(minutes=retry_minutes)
            logger.warning(
                "Telegram delivery failed for notification %s (%s)",
                item.id,
                type(error).__name__,
            )
        db.commit()
    return sent
