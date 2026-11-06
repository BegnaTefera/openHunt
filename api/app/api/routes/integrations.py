from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.dependencies import get_db
from app.models.application import Application, ApplicationStatus
from app.models.company import Company
from app.models.email import Email
from app.models.integrations import GmailConnection, TrackedGmailThread
from app.models.job import Job
from app.models.user import User
from app.schemas.integrations import (
    GmailApplicationRead,
    GmailStatus,
    GmailThreadRead,
    TrackGmailThreadRequest,
    TrackedGmailThreadRead,
)
from app.services import gmail
from app.services.notifications import telegram_enabled

logger = logging.getLogger("openhunt.integrations")
router = APIRouter(prefix="/integrations", tags=["integrations"])


def _connection(db: Session, user: User) -> GmailConnection:
    connection = db.scalar(
        select(GmailConnection).where(
            GmailConnection.user_id == user.id,
            GmailConnection.gmail_address != "pending",
        )
    )
    if connection is None:
        raise HTTPException(status_code=409, detail="Connect a Gmail account first.")
    return connection


@router.get("/gmail", response_model=GmailStatus)
def gmail_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GmailStatus:
    connection = db.scalar(
        select(GmailConnection).where(
            GmailConnection.user_id == user.id,
            GmailConnection.gmail_address != "pending",
        )
    )
    tracked_count = db.scalar(
        select(func.count()).select_from(TrackedGmailThread).where(
            TrackedGmailThread.user_id == user.id
        )
    )
    return GmailStatus(
        connected=connection is not None,
        gmail_address=connection.gmail_address if connection else None,
        tracked_threads=int(tracked_count or 0),
        oauth_configured=bool(
            settings.gmail_client_id
            and settings.gmail_client_secret
            and settings.gmail_redirect_uri
        ),
        telegram_alerts_enabled=telegram_enabled(),
    )


@router.get("/gmail/connect")
def connect_gmail(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    try:
        return {"authorization_url": gmail.start_oauth(db, user)}
    except gmail.GmailError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/gmail/callback")
def gmail_callback(
    state: str | None = Query(default=None, max_length=200),
    code: str | None = Query(default=None, max_length=4096),
    error: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    success = False
    if state and code and not error:
        try:
            gmail.finish_oauth(db, state, code)
            success = True
        except gmail.GmailError as cause:
            logger.warning("Gmail OAuth callback failed (%s)", str(cause))
    destination = f"{settings.web_app_url.rstrip('/')}/account?{urlencode({'gmail': 'connected' if success else 'error'})}"
    return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/gmail/threads", response_model=list[GmailThreadRead])
def list_gmail_threads(
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GmailThreadRead]:
    connection = _connection(db, user)
    try:
        return [GmailThreadRead(**item) for item in gmail.recent_sent_threads(db, connection, limit)]
    except gmail.GmailError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/gmail/applications", response_model=list[GmailApplicationRead])
def list_trackable_applications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GmailApplicationRead]:
    rows = db.execute(
        select(Application, Job, Company.name)
        .join(Job, Job.id == Application.job_id)
        .outerjoin(Company, Company.id == Job.company_id)
        .where(
            Application.user_id == user.id,
            Application.status.in_(
                [
                    ApplicationStatus.APPLIED,
                    ApplicationStatus.REPLIED,
                    ApplicationStatus.INTERVIEW,
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.OFFER,
                ]
            ),
        )
        .order_by(Application.applied_at.desc().nullslast(), Job.title)
        .limit(200)
    ).all()
    return [
        GmailApplicationRead(
            id=application.id,
            job_id=job.id,
            title=job.title,
            company=company,
            status=application.status.value,
        )
        for application, job, company in rows
    ]


@router.post("/gmail/threads", response_model=TrackedGmailThreadRead, status_code=201)
def track_gmail_thread(
    payload: TrackGmailThreadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrackedGmailThreadRead:
    connection = _connection(db, user)
    try:
        tracked = gmail.track_thread(
            db, connection, user.id, payload.application_id, payload.thread_id
        )
    except gmail.GmailValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except gmail.GmailError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return TrackedGmailThreadRead(
        id=tracked.id,
        thread_id=tracked.thread_id,
        application_id=tracked.application_id,
    )


@router.delete("/gmail/threads/{tracked_id}", status_code=204)
def untrack_gmail_thread(
    tracked_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    tracked = db.scalar(
        select(TrackedGmailThread).where(
            TrackedGmailThread.id == tracked_id,
            TrackedGmailThread.user_id == user.id,
        )
    )
    if tracked is None:
        raise HTTPException(status_code=404, detail="Tracked Gmail thread not found.")
    db.delete(tracked)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/gmail", status_code=204)
def disconnect_gmail(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    db.execute(delete(Email).where(Email.user_id == user.id))
    db.execute(delete(TrackedGmailThread).where(TrackedGmailThread.user_id == user.id))
    db.execute(delete(GmailConnection).where(GmailConnection.user_id == user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
