from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ats_type: Literal["greenhouse", "lever", "ashby", "workable"]
    ats_slug: str = Field(pattern=r"^[A-Za-z0-9._-]{1,255}$")
    website: str | None = Field(default=None, max_length=2048)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ats_type: str
    ats_slug: str
    website: str | None
