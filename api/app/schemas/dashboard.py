from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from app.models.application import ApplicationStatus


class JobDashboardRead(BaseModel):
    id: int
    title: str
    source: str
    url: str
    company: str | None
    company_id: int | None
    location: str | None
    seniority: str | None
    description: str | None
    tags: list[str]
    posted_at: datetime | None
    first_seen_at: datetime
    score: int
    score_reasons: list[str]
    status: ApplicationStatus


class JobDetailRead(JobDashboardRead):
    employment_type: str | None
    salary_text: str | None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ProfileProject(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=600)
    url: str = Field(default="", max_length=2048)


class ProfileRead(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=100)
    # Role family keys (see GET /roles). An empty list means every tech role.
    target_roles: list[str] = Field(default_factory=list, max_length=30)
    seniority: str | None = None
    country: str | None = None
    timezones: list[str] = Field(default_factory=list, max_length=30)
    work_authorizations: list[str] = Field(default_factory=list, max_length=30)
    allowed_seniority: list[str] = Field(default_factory=list, max_length=10)
    # Extra title words (for example "recruiter") that should always count as a match.
    custom_title_keywords: list[str] = Field(default_factory=list, max_length=20)
    # Facts used when drafting cover letters. Only what you enter here is ever used.
    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=1200)
    projects: list[ProfileProject] = Field(default_factory=list, max_length=10)


class ProfileUpdate(ProfileRead):
    pass


class SourceStats(BaseModel):
    source: str
    jobs_found: int
    applied: int
    replies: int
    interviews: int


class DashboardStats(BaseModel):
    jobs_found: int
    applied: int
    replies: int
    interviews: int
    by_source: list[SourceStats]
