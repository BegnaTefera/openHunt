from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.dependencies import get_db
from app.models.application import Application, ApplicationStatus
from app.models.company import Company
from app.models.job import Job
from app.models.profile import Profile
from app.models.user import User
from app.schemas.dashboard import (
    ApplicationStatusUpdate,
    DashboardStats,
    JobDashboardRead,
    JobDetailRead,
    ProfileRead,
    ProfileUpdate,
    SourceStats,
)
from app.services.job_scorer import Profile as ScoringProfile
from app.services.job_scorer import score_job

router = APIRouter(tags=["dashboard"])


def _profile_record(db: Session) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.id == 1))


def _profile_response(record: Profile | None) -> ProfileRead:
    preferences: dict[str, Any] = record.preferences if record else {}
    return ProfileRead(
        skills=record.skills if record else [],
        target_roles=record.target_roles if record else [],
        seniority=record.seniority if record else None,
        country=preferences.get("country"),
        timezones=preferences.get("timezones", []),
        work_authorizations=preferences.get("work_authorizations", []),
        allowed_seniority=preferences.get("allowed_seniority", []),
        full_name=preferences.get("full_name"),
        headline=preferences.get("headline"),
        summary=preferences.get("summary"),
        projects=preferences.get("projects", []),
    )


def _scoring_profile(record: Profile | None) -> ScoringProfile:
    preferences = record.preferences if record else {}
    return ScoringProfile(
        preferred_roles=record.target_roles or ["backend", "full-stack"] if record else [
            "backend",
            "full-stack",
        ],
        tech_stack={skill.casefold() for skill in record.skills} if record else set(),
        allowed_seniority=set(preferences.get("allowed_seniority", [])),
        country=preferences.get("country"),
        timezones=set(preferences.get("timezones", [])),
        work_authorizations=set(preferences.get("work_authorizations", [])),
    )


def _job_response(
    job: Job,
    company_name: str | None,
    status: ApplicationStatus,
    profile: ScoringProfile,
    detail: bool = False,
) -> JobDashboardRead | JobDetailRead:
    scoring_job = {
        "title": job.title,
        "description": job.description or "",
        "location_text": job.location_text or "",
        "seniority": job.seniority,
        "skills": job.tags or [],
    }
    score, reasons = score_job(scoring_job, profile)
    values: dict[str, Any] = {
        "id": job.id,
        "title": job.title,
        "source": job.source,
        "url": job.url,
        "company": company_name,
        "company_id": job.company_id,
        "location": job.location_text,
        "seniority": job.seniority,
        "description": job.description,
        "tags": job.tags,
        "posted_at": job.posted_at,
        "first_seen_at": job.first_seen_at,
        "score": score,
        "score_reasons": reasons,
        "status": status,
    }
    if detail:
        values.update(employment_type=job.employment_type, salary_text=job.salary_text)
        return JobDetailRead(**values)
    return JobDashboardRead(**values)


@router.get("/jobs", response_model=list[JobDashboardRead])
def list_dashboard_jobs(
    source: str | None = None,
    company_id: int | None = None,
    seniority: str | None = None,
    new_today: bool = False,
    status: ApplicationStatus | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[JobDashboardRead]:
    query = (
        select(Job, Company.name, Application.status)
        .outerjoin(Company, Job.company_id == Company.id)
        .outerjoin(Application, Application.job_id == Job.id)
        .where(Job.is_active.is_(True))
    )
    if source:
        query = query.where(Job.source == source)
    if company_id is not None:
        query = query.where(Job.company_id == company_id)
    if seniority:
        query = query.where(func.lower(func.coalesce(Job.seniority, "")) == seniority.casefold())
    if new_today:
        today = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
        query = query.where(Job.first_seen_at >= today)
    if status is not None:
        query = query.where(Application.status == status)

    rows = db.execute(query).all()
    profile = _scoring_profile(_profile_record(db))
    jobs = [
        _job_response(job, company_name, app_status or ApplicationStatus.NEW, profile)
        for job, company_name, app_status in rows
    ]
    return sorted(jobs, key=lambda item: (-item.score, -item.first_seen_at.timestamp()))


@router.get("/jobs/{job_id}", response_model=JobDetailRead)
def get_dashboard_job(
    job_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> JobDetailRead:
    row = db.execute(
        select(Job, Company.name, Application.status)
        .outerjoin(Company, Job.company_id == Company.id)
        .outerjoin(Application, Application.job_id == Job.id)
        .where(Job.id == job_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job, company_name, status = row
    profile = _scoring_profile(_profile_record(db))
    return _job_response(
        job,
        company_name,
        status or ApplicationStatus.NEW,
        profile,
        detail=True,
    )


@router.patch("/jobs/{job_id}/status", response_model=JobDashboardRead)
def update_job_status(
    job_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> JobDashboardRead:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    application = db.scalar(select(Application).where(Application.job_id == job.id))
    if application is None:
        application = Application(job_id=job.id, status=payload.status)
        db.add(application)
    else:
        application.status = payload.status
    if payload.status == ApplicationStatus.APPLIED and application.applied_at is None:
        application.applied_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(application)
    return _job_response(
        job,
        db.scalar(select(Company.name).where(Company.id == job.company_id))
        if job.company_id is not None
        else None,
        application.status,
        _scoring_profile(_profile_record(db)),
    )


@router.get("/profile", response_model=ProfileRead)
def read_profile(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ProfileRead:
    return _profile_response(_profile_record(db))


@router.put("/profile", response_model=ProfileRead)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ProfileRead:
    record = _profile_record(db)
    if record is None:
        record = Profile(id=1, skills=[], target_roles=[], preferences={})
        db.add(record)
    record.skills = payload.skills
    record.target_roles = payload.target_roles
    record.seniority = payload.seniority
    preferences = dict(record.preferences or {})
    preferences.update(
        country=payload.country,
        timezones=payload.timezones,
        work_authorizations=payload.work_authorizations,
        allowed_seniority=payload.allowed_seniority,
    )
    # Drafting facts are only changed when the client sends them, so older clients
    # that do not know these fields cannot erase them.
    for key in ("full_name", "headline", "summary"):
        if key in payload.model_fields_set:
            preferences[key] = getattr(payload, key)
    if "projects" in payload.model_fields_set:
        preferences["projects"] = [project.model_dump() for project in payload.projects]
    record.preferences = preferences
    db.commit()
    db.refresh(record)
    return _profile_response(record)


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardStats:
    applied_count = func.sum(
        case(
            (Application.status.in_([ApplicationStatus.APPLIED, ApplicationStatus.REPLIED,
                                     ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER]), 1),
            else_=0,
        )
    )
    replies_count = func.sum(
        case(
            (Application.status.in_([ApplicationStatus.REPLIED, ApplicationStatus.INTERVIEW,
                                     ApplicationStatus.OFFER]), 1),
            else_=0,
        )
    )
    interviews_count = func.sum(
        case(
            (Application.status.in_([ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER]), 1),
            else_=0,
        )
    )
    rows = db.execute(
        select(
            Job.source,
            func.count(Job.id),
            func.coalesce(applied_count, 0),
            func.coalesce(replies_count, 0),
            func.coalesce(interviews_count, 0),
        )
        .outerjoin(Application, Application.job_id == Job.id)
        .where(Job.is_active.is_(True))
        .group_by(Job.source)
        .order_by(Job.source)
    ).all()
    sources = [
        SourceStats(
            source=source,
            jobs_found=jobs_found,
            applied=int(applied or 0),
            replies=int(replies or 0),
            interviews=int(interviews or 0),
        )
        for source, jobs_found, applied, replies, interviews in rows
    ]
    return DashboardStats(
        jobs_found=sum(item.jobs_found for item in sources),
        applied=sum(item.applied for item in sources),
        replies=sum(item.replies for item in sources),
        interviews=sum(item.interviews for item in sources),
        by_source=sources,
    )
