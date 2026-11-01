from __future__ import annotations

from fastapi import APIRouter

from app.schemas.job import JobScoreRequest, JobScoreResponse
from app.services.job_scorer import Profile, score_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/score", response_model=JobScoreResponse)
def score_job_endpoint(payload: JobScoreRequest) -> JobScoreResponse:
    profile = Profile(
        preferred_roles=payload.preferred_roles or ["backend", "full-stack"],
        tech_stack=set(payload.profile_tech_stack),
        allowed_seniority=set(payload.allowed_seniority),
        country=payload.profile_country,
        timezones=set(payload.profile_timezones),
        work_authorizations=set(payload.profile_work_authorizations),
    )
    raw_score, reasons = score_job(payload.job, profile)
    return JobScoreResponse(score=raw_score, reasons=reasons)
