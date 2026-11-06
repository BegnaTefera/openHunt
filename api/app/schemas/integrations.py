from __future__ import annotations

from pydantic import BaseModel, Field


class GmailStatus(BaseModel):
    connected: bool
    gmail_address: str | None
    tracked_threads: int
    oauth_configured: bool
    telegram_alerts_enabled: bool


class GmailThreadRead(BaseModel):
    thread_id: str
    subject: str
    last_message_at: int
    tracked: bool
    tracked_id: int | None
    application_id: int | None


class GmailApplicationRead(BaseModel):
    id: int
    job_id: int
    title: str
    company: str | None
    status: str


class TrackGmailThreadRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_-]+$")
    application_id: int = Field(gt=0)


class TrackedGmailThreadRead(BaseModel):
    id: int
    thread_id: str
    application_id: int
