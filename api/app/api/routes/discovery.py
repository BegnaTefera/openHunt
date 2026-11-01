from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.dependencies import get_db
from app.models.discovery import DiscoveryCandidate
from app.models.event import Event
from app.models.user import User
from app.schemas.discovery import CandidateRead, DiscoveryStatus, ProviderBudgetRead
from app.services.usage import Budget, get_usage, remaining

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _provider_budget(db: Session, name: str, configured: bool, budget: Budget) -> ProviderBudgetRead:
    usage = get_usage(db, name)
    unlimited = budget.daily is None and budget.monthly is None and budget.total is None
    return ProviderBudgetRead(
        name=name,
        configured=configured,
        used_today=usage.day,
        daily_cap=budget.daily,
        used_this_month=usage.month,
        monthly_cap=budget.monthly,
        used_total=usage.total,
        total_cap=budget.total,
        remaining_now=None if unlimited else remaining(db, name, budget),
    )


@router.get("", response_model=DiscoveryStatus)
def discovery_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DiscoveryStatus:
    providers = [
        _provider_budget(
            db,
            "brave",
            bool(settings.brave_api_key),
            Budget(daily=settings.brave_daily_cap, monthly=settings.brave_monthly_cap),
        ),
        _provider_budget(
            db,
            "serper",
            bool(settings.serper_api_key),
            Budget(daily=settings.serper_daily_cap, total=settings.serper_total_cap),
        ),
        _provider_budget(db, "commoncrawl", settings.commoncrawl_enabled, Budget()),
    ]
    added_total = db.scalar(
        select(func.count()).select_from(DiscoveryCandidate).where(DiscoveryCandidate.status == "added")
    )
    rejected_total = db.scalar(
        select(func.count()).select_from(DiscoveryCandidate).where(DiscoveryCandidate.status == "rejected")
    )
    last_event = db.scalar(
        select(Event)
        .where(Event.entity_type == "discovery", Event.action == "run_completed")
        .order_by(Event.occurred_at.desc())
        .limit(1)
    )
    candidates = db.scalars(
        select(DiscoveryCandidate).order_by(DiscoveryCandidate.found_at.desc()).limit(50)
    ).all()
    return DiscoveryStatus(
        providers=providers,
        added_total=int(added_total or 0),
        rejected_total=int(rejected_total or 0),
        last_run_at=last_event.occurred_at if last_event else None,
        last_run=last_event.details if last_event else None,
        recent_candidates=[
            CandidateRead(
                ats_type=item.ats_type,
                ats_slug=item.ats_slug,
                source=item.source,
                status=item.status,
                reason=item.reason,
                company_id=item.company_id,
                found_at=item.found_at,
            )
            for item in candidates
        ],
    )
