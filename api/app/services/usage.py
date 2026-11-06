"""Request budgets for free-tier APIs (search providers and AI providers)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.api_usage import ApiUsage


@dataclass(frozen=True)
class UsageTotals:
    day: int
    month: int
    total: int


@dataclass(frozen=True)
class Budget:
    """Caps for one provider. ``None`` means that period is not limited."""

    daily: int | None = None
    monthly: int | None = None
    total: int | None = None


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def get_usage(db: Session, provider: str, today: date | None = None) -> UsageTotals:
    today = today or utc_today()
    month_start = today.replace(day=1)
    rows = db.execute(
        select(ApiUsage.day, ApiUsage.count).where(ApiUsage.provider == provider)
    ).all()
    return UsageTotals(
        day=sum(count for day, count in rows if day == today),
        month=sum(count for day, count in rows if month_start <= day <= today),
        total=sum(count for _day, count in rows),
    )


def remaining(db: Session, provider: str, budget: Budget, today: date | None = None) -> int:
    """How many more requests the provider may receive right now."""
    usage = get_usage(db, provider, today)
    limits: list[int] = []
    if budget.daily is not None:
        limits.append(budget.daily - usage.day)
    if budget.monthly is not None:
        limits.append(budget.monthly - usage.month)
    if budget.total is not None:
        limits.append(budget.total - usage.total)
    if not limits:
        return 10**9
    return max(0, min(limits))


def record_usage(db: Session, provider: str, amount: int = 1, today: date | None = None) -> None:
    """Add to today's counter. Counts attempts too: a failed call may still use quota."""
    statement = insert(ApiUsage).values(
        provider=provider, day=today or utc_today(), count=amount
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_api_usage_provider_day",
        set_={"count": ApiUsage.count + amount},
    )
    db.execute(statement)
    db.flush()


def reserve_request(db: Session, provider: str, budget: Budget) -> bool:
    """Atomically reserve one provider request before calling the external API."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(provider))))
    if remaining(db, provider, budget) <= 0:
        db.commit()
        return False
    record_usage(db, provider)
    db.commit()
    return True


def total_requests_today(db: Session, today: date | None = None) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(ApiUsage.count), 0)).where(
                ApiUsage.day == (today or utc_today())
            )
        )
        or 0
    )
