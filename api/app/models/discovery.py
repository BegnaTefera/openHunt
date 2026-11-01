from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiscoveryCandidate(Base):
    """A company board found by discovery, with the outcome of validating it."""

    __tablename__ = "discovery_candidates"
    __table_args__ = (
        UniqueConstraint("ats_type", "ats_slug", name="uq_discovery_candidates_ats_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ats_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ats_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # added | rejected
    reason: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
