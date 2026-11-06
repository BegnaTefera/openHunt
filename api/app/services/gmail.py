from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.application import Application, ApplicationStatus
from app.models.company import Company
from app.models.email import Email
from app.models.integrations import GmailConnection, TrackedGmailThread
from app.models.job import Job
from app.models.user import User
from app.services.notifications import enqueue_reply

logger = logging.getLogger("openhunt.gmail")

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
STATE_TTL = timedelta(minutes=10)


class GmailError(RuntimeError):
    pass


class GmailValidationError(GmailError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise GmailError("Stored Gmail credentials cannot be decrypted; check SECRET_KEY.") from error


def _ensure_oauth_configured() -> None:
    if not all((settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_redirect_uri)):
        raise GmailError("Gmail OAuth is not configured on this server.")


def start_oauth(db: Session, user: User) -> str:
    _ensure_oauth_configured()
    state = secrets.token_urlsafe(32)
    connection = db.scalar(select(GmailConnection).where(GmailConnection.user_id == user.id))
    if connection is None:
        connection = GmailConnection(
            user_id=user.id,
            gmail_address="pending",
            access_token_encrypted="pending",
            refresh_token_encrypted="pending",
            access_token_expires_at=_now(),
        )
        db.add(connection)
    connection.oauth_state_hash = hashlib.sha256(state.encode()).hexdigest()
    connection.oauth_state_expires_at = _now() + STATE_TTL
    db.commit()
    params = {
        "client_id": settings.gmail_client_id,
        "redirect_uri": settings.gmail_redirect_uri,
        "response_type": "code",
        "scope": f"openid email {GMAIL_SCOPE}",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def _post_token(data: dict[str, str]) -> dict[str, Any]:
    try:
        response = httpx.post(GOOGLE_TOKEN_URL, data=data, timeout=settings.api_timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise GmailError("Google OAuth request failed.") from error
    if not isinstance(payload, dict) or payload.get("error"):
        raise GmailError("Google OAuth returned an invalid token response.")
    return payload


def finish_oauth(db: Session, state: str, code: str) -> None:
    _ensure_oauth_configured()
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    connection = db.scalar(
        select(GmailConnection).where(GmailConnection.oauth_state_hash == state_hash)
    )
    if (
        connection is None
        or connection.oauth_state_expires_at is None
        or connection.oauth_state_expires_at < _now()
    ):
        raise GmailError("Gmail authorization expired; please try again.")

    connection.oauth_state_hash = None
    connection.oauth_state_expires_at = None
    db.commit()

    tokens = _post_token(
        {
            "code": code,
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "redirect_uri": settings.gmail_redirect_uri,
            "grant_type": "authorization_code",
        }
    )
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise GmailError("Google OAuth did not return an access token.")
    if not isinstance(refresh_token, str) or not refresh_token:
        try:
            refresh_token = _decrypt(connection.refresh_token_encrypted)
        except GmailError:
            raise GmailError("Google did not provide a refresh token; authorize Gmail again.")

    try:
        response = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.api_timeout_seconds,
        )
        response.raise_for_status()
        identity = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise GmailError("Could not verify the connected Google account.") from error
    gmail_address = identity.get("email") if isinstance(identity, dict) else None
    if (
        not isinstance(gmail_address, str)
        or identity.get("email_verified") is not True
        or "@" not in gmail_address
    ):
        raise GmailError("Google did not verify the connected Gmail address.")

    if connection.gmail_address not in ("pending", gmail_address.casefold()):
        db.execute(
            delete(TrackedGmailThread).where(
                TrackedGmailThread.user_id == connection.user_id
            )
        )
        db.execute(delete(Email).where(Email.user_id == connection.user_id))
    connection.gmail_address = gmail_address.casefold()
    connection.access_token_encrypted = _encrypt(access_token)
    connection.refresh_token_encrypted = _encrypt(refresh_token)
    connection.access_token_expires_at = _now() + timedelta(
        seconds=max(60, int(tokens.get("expires_in", 3600)))
    )
    db.commit()


def _access_token(db: Session, connection: GmailConnection, *, force_refresh: bool = False) -> str:
    _ensure_oauth_configured()
    if not force_refresh and connection.access_token_expires_at > _now() + timedelta(seconds=60):
        return _decrypt(connection.access_token_encrypted)
    tokens = _post_token(
        {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "refresh_token": _decrypt(connection.refresh_token_encrypted),
            "grant_type": "refresh_token",
        }
    )
    token = tokens.get("access_token")
    if not isinstance(token, str) or not token:
        raise GmailError("Google did not return a refreshed access token.")
    connection.access_token_encrypted = _encrypt(token)
    if isinstance(tokens.get("refresh_token"), str):
        connection.refresh_token_encrypted = _encrypt(tokens["refresh_token"])
    connection.access_token_expires_at = _now() + timedelta(
        seconds=max(60, int(tokens.get("expires_in", 3600)))
    )
    db.flush()
    return token


def _gmail_request(
    db: Session,
    connection: GmailConnection,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for attempt in range(2):
        token = _access_token(db, connection, force_refresh=bool(attempt))
        try:
            response = httpx.get(
                f"{GMAIL_API}/{path.lstrip('/')}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=settings.api_timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise GmailError("Gmail API request failed.") from error
        if response.status_code == 401 and attempt == 0:
            continue
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GmailError(f"Gmail API returned HTTP {response.status_code}.") from error
        if not isinstance(payload, dict):
            raise GmailError("Gmail API returned an invalid response.")
        return payload
    raise GmailError("Gmail authorization expired; reconnect the account.")


def _thread(db: Session, connection: GmailConnection, thread_id: str) -> dict[str, Any]:
    payload = _gmail_request(
        db,
        connection,
        f"threads/{thread_id}",
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"],
        },
    )
    if not isinstance(payload.get("messages"), list):
        raise GmailError("Gmail returned a thread without messages.")
    return payload


def _headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload")
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    return {
        str(item.get("name", "")).casefold(): str(item.get("value", ""))
        for item in headers
        if isinstance(item, dict)
    }


def _sender(message: dict[str, Any]) -> str:
    return parseaddr(_headers(message).get("from", ""))[1].casefold()


def _internal_date(message: dict[str, Any]) -> int:
    try:
        return int(message.get("internalDate", 0))
    except (TypeError, ValueError):
        return 0


def _sent_by_user(thread: dict[str, Any], gmail_address: str) -> bool:
    return any(
        gmail_address == _sender(message)
        and isinstance(message.get("labelIds"), list)
        and "SENT" in message["labelIds"]
        for message in thread["messages"]
    )


def recent_sent_threads(db: Session, connection: GmailConnection, limit: int = 25) -> list[dict[str, Any]]:
    # Gmail's metadata-only scope forbids the q parameter; request SENT-labeled
    # threads directly and still verify the sender before offering them to users.
    response = _gmail_request(
        db,
        connection,
        "threads",
        params={"labelIds": "SENT", "maxResults": min(max(limit, 1), 50)},
    )
    found_threads = response.get("threads", [])
    thread_ids = [
        item["id"]
        for item in (found_threads if isinstance(found_threads, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].isalnum()
    ]
    tracked_rows = db.scalars(
        select(TrackedGmailThread).where(
            TrackedGmailThread.user_id == connection.user_id
        )
    ).all()
    tracked_by_thread = {item.thread_id: item for item in tracked_rows}
    results: list[dict[str, Any]] = []
    for thread_id in thread_ids:
        thread = _thread(db, connection, thread_id)
        if not _sent_by_user(thread, connection.gmail_address):
            continue
        messages = sorted(thread["messages"], key=_internal_date)
        headers = _headers(messages[-1])
        results.append(
            {
                "thread_id": thread_id,
                "subject": headers.get("subject") or "(No subject)",
                "last_message_at": _internal_date(messages[-1]),
                "tracked": thread_id in tracked_by_thread,
                "tracked_id": (
                    tracked_by_thread[thread_id].id if thread_id in tracked_by_thread else None
                ),
                "application_id": (
                    tracked_by_thread[thread_id].application_id
                    if thread_id in tracked_by_thread
                    else None
                ),
            }
        )
    db.commit()
    return results


def track_thread(
    db: Session,
    connection: GmailConnection,
    user_id: int,
    application_id: int,
    thread_id: str,
) -> TrackedGmailThread:
    application = db.scalar(
        select(Application).where(
            Application.id == application_id, Application.user_id == user_id
        )
    )
    if application is None:
        raise GmailValidationError("Application not found for this account.")
    existing = db.scalar(
        select(TrackedGmailThread).where(
            TrackedGmailThread.user_id == user_id,
            TrackedGmailThread.thread_id == thread_id,
        )
    )
    if existing is not None:
        existing.application_id = application.id
        db.commit()
        return existing
    thread = _thread(db, connection, thread_id)
    if not _sent_by_user(thread, connection.gmail_address):
        raise GmailValidationError(
            "Only a thread containing mail sent from this Gmail account can be tracked."
        )
    last_seen = max((_internal_date(message) for message in thread["messages"]), default=0)
    tracked = TrackedGmailThread(
        user_id=user_id,
        application_id=application.id,
        thread_id=thread_id,
        last_seen_internal_date=last_seen,
    )
    db.add(tracked)
    db.commit()
    db.refresh(tracked)
    return tracked


def poll_gmail_replies(db: Session) -> int:
    connections = db.scalars(select(GmailConnection)).all()
    found = 0
    for connection in connections:
        if connection.gmail_address == "pending":
            continue
        tracked_ids = db.scalars(
            select(TrackedGmailThread.id).where(
                TrackedGmailThread.user_id == connection.user_id
            )
        ).all()
        for tracked_id in tracked_ids:
            tracked = db.scalar(
                select(TrackedGmailThread)
                .where(
                    TrackedGmailThread.id == tracked_id,
                    TrackedGmailThread.user_id == connection.user_id,
                )
                .with_for_update(skip_locked=True)
            )
            if tracked is None:
                continue
            try:
                thread = _thread(db, connection, tracked.thread_id)
                if not _sent_by_user(thread, connection.gmail_address):
                    logger.warning("Tracked Gmail thread no longer contains a sent message.")
                    continue
                application = db.get(Application, tracked.application_id)
                job = db.get(Job, application.job_id) if application else None
                company = db.get(Company, job.company_id) if job and job.company_id else None
                if application is None or job is None:
                    continue
                current_max = tracked.last_seen_internal_date
                messages = sorted(thread["messages"], key=_internal_date)
                for message in messages:
                    internal_date = _internal_date(message)
                    if internal_date <= tracked.last_seen_internal_date:
                        continue
                    current_max = max(current_max, internal_date)
                    sender = _sender(message)
                    message_id = message.get("id")
                    if (
                        sender == connection.gmail_address
                        or not isinstance(message_id, str)
                        or db.scalar(
                            select(Email.id).where(
                                Email.user_id == connection.user_id,
                                Email.gmail_message_id == message_id,
                            )
                        )
                        is not None
                    ):
                        continue
                    headers = _headers(message)
                    received_at = datetime.fromtimestamp(internal_date / 1000, tz=timezone.utc)
                    db.add(
                        Email(
                            gmail_message_id=message_id,
                            gmail_thread_id=tracked.thread_id,
                            user_id=connection.user_id,
                            application_id=application.id,
                            from_address=sender,
                            subject=headers.get("subject"),
                            received_at=received_at,
                            classification="application_reply",
                            snippet=None,
                        )
                    )
                    if application.status not in (
                        ApplicationStatus.REPLIED,
                        ApplicationStatus.INTERVIEW,
                        ApplicationStatus.REJECTED,
                        ApplicationStatus.OFFER,
                    ):
                        application.status = ApplicationStatus.REPLIED
                    enqueue_reply(db, connection.user_id, job, company.name if company else None)
                    db.flush()
                    found += 1
                tracked.last_seen_internal_date = current_max
                db.commit()
            except GmailError as error:
                db.rollback()
                logger.warning(
                    "Gmail polling failed for tracked thread %s (%s)",
                    tracked.id,
                    str(error),
                )
            except Exception:
                db.rollback()
                logger.exception("Unexpected Gmail polling failure for tracked thread %s", tracked.id)
    return found
