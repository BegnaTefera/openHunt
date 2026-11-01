from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class JobPost(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    company: str
    location: str
    remote: bool = False
    source: str
    url: str
    description: str
    skills: list[str] = []
    seniority: str | None = None


class JobScoreRequest(BaseModel):
    job: JobPost
    profile_tech_stack: list[str]
    preferred_roles: list[str] = []
    allowed_seniority: list[str] = []
    profile_country: str | None = None
    profile_timezones: list[str] = []
    profile_work_authorizations: list[str] = []


class JobScoreResponse(BaseModel):
    score: int
    reasons: list[str] = []
