from __future__ import annotations

from typing import Any

from sqlalchemy import ARRAY, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Profile(Base):
    """One profile per user."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    seniority: Mapped[str | None] = mapped_column(String(50))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
