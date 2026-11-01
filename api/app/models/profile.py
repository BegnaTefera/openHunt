from __future__ import annotations

from typing import Any

from sqlalchemy import ARRAY, CheckConstraint, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Profile(Base):
    __tablename__ = "profile"
    __table_args__ = (CheckConstraint("id = 1", name="ck_profile_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    seniority: Mapped[str | None] = mapped_column(String(50))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
