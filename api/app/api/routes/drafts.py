from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.drafting import Draft, DraftProfile, generate_draft
from app.core.auth import get_current_user
from app.db.dependencies import get_db
from app.models.application import Application, ApplicationStatus
from app.models.company import Company
from app.models.document import Document
from app.models.job import Job
from app.models.profile import Profile
from app.models.user import User
from app.schemas.draft import DraftRead, DraftUpdate

router = APIRouter(tags=["drafts"])


def _draft_profile(record: Profile | None) -> DraftProfile:
    if record is None:
        return DraftProfile()
    preferences: dict[str, Any] = record.preferences or {}
    projects = [
        {
            "name": str(item.get("name", "")),
            "description": str(item.get("description", "")),
            "url": str(item.get("url", "")),
        }
        for item in preferences.get("projects", [])
        if isinstance(item, dict) and item.get("name")
    ]
    return DraftProfile(
        full_name=preferences.get("full_name") or None,
        headline=preferences.get("headline") or None,
        summary=preferences.get("summary") or None,
        skills=list(record.skills or []),
        target_roles=list(record.target_roles or []),
        projects=projects,
    )


def _job_and_company(db: Session, job_id: int) -> tuple[Job, str | None]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    company = db.get(Company, job.company_id) if job.company_id is not None else None
    return job, company.name if company else None


def _application(db: Session, job: Job) -> Application:
    application = db.scalar(select(Application).where(Application.job_id == job.id))
    if application is None:
        application = Application(job_id=job.id, status=ApplicationStatus.NEW)
        db.add(application)
        db.flush()
    return application


def _document(db: Session, application: Application) -> Document | None:
    return db.scalar(select(Document).where(Document.application_id == application.id))


def _read(job_id: int, document: Document) -> DraftRead:
    stored: dict[str, Any] = document.answers or {}
    return DraftRead(
        job_id=job_id,
        cover_letter=document.cover_letter or "",
        answers={str(key): str(value) for key, value in (stored.get("items") or {}).items()},
        generated_by=str(stored.get("generated_by", "unknown")),
        warnings=[str(item) for item in stored.get("warnings", [])],
    )


def _store(document: Document, draft: Draft) -> None:
    document.cover_letter = draft.cover_letter
    document.answers = {
        "items": draft.answers,
        "generated_by": draft.generated_by,
        "warnings": draft.warnings,
    }


@router.get("/jobs/{job_id}/draft", response_model=DraftRead)
def get_draft(
    job_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DraftRead:
    job, _company = _job_and_company(db, job_id)
    application = db.scalar(select(Application).where(Application.job_id == job.id))
    document = _document(db, application) if application else None
    if document is None:
        raise HTTPException(status_code=404, detail="No draft yet for this job")
    return _read(job_id, document)


@router.post("/jobs/{job_id}/draft", response_model=DraftRead)
def create_draft(
    job_id: int,
    use_ai: bool = True,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DraftRead:
    job, company_name = _job_and_company(db, job_id)
    profile = _draft_profile(db.scalar(select(Profile).where(Profile.id == 1)))
    draft = generate_draft(db, job.title, company_name, job.description, profile, use_ai=use_ai)

    application = _application(db, job)
    if application.status in (ApplicationStatus.NEW, ApplicationStatus.SHORTLISTED):
        application.status = ApplicationStatus.DRAFTED
    document = _document(db, application)
    if document is None:
        document = Document(application_id=application.id, answers={})
        db.add(document)
    _store(document, draft)
    db.commit()
    db.refresh(document)
    return _read(job_id, document)


@router.put("/jobs/{job_id}/draft", response_model=DraftRead)
def save_draft(
    job_id: int,
    payload: DraftUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DraftRead:
    job, _company = _job_and_company(db, job_id)
    application = _application(db, job)
    document = _document(db, application)
    if document is None:
        document = Document(application_id=application.id, answers={})
        db.add(document)
    previous: dict[str, Any] = document.answers or {}
    _store(
        document,
        Draft(
            cover_letter=payload.cover_letter,
            answers=payload.answers,
            generated_by="edited",
            warnings=[str(item) for item in previous.get("warnings", [])],
        ),
    )
    db.commit()
    db.refresh(document)
    return _read(job_id, document)
