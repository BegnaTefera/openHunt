from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DraftRead(BaseModel):
    job_id: int
    cover_letter: str
    answers: dict[str, str] = Field(default_factory=dict)
    generated_by: str
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class DraftUpdate(BaseModel):
    cover_letter: str = Field(max_length=20000)
    answers: dict[str, str] = Field(default_factory=dict)
