from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CvSuggestionsRead(BaseModel):
    full_name: str | None = None
    skills: list[str] = Field(default_factory=list)


class CvRead(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    text_characters: int
    suggestions: CvSuggestionsRead
