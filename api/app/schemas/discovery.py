from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProviderBudgetRead(BaseModel):
    name: str
    configured: bool
    used_today: int
    daily_cap: int | None
    used_this_month: int
    monthly_cap: int | None
    used_total: int
    total_cap: int | None
    remaining_now: int | None


class CandidateRead(BaseModel):
    ats_type: str
    ats_slug: str
    source: str
    status: str
    reason: str | None
    company_id: int | None
    found_at: datetime


class DiscoveryStatus(BaseModel):
    providers: list[ProviderBudgetRead]
    added_total: int
    rejected_total: int
    last_run_at: datetime | None
    last_run: dict[str, Any] | None
    recent_candidates: list[CandidateRead]
