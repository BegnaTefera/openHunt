from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApiUsage(Base):
    """Per-provider, per-day request counter used to stay inside free quotas."""

    __tablename__ = "api_usage"
    __table_args__ = (UniqueConstraint("provider", "day", name="uq_api_usage_provider_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
