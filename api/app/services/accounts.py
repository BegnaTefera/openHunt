"""Account rules: sign-up checks, login lockout, and rotating refresh sessions."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.profile import Profile
from app.models.refresh_token import RefreshToken
from app.models.user import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
# Reusing a token this soon after rotation is almost always two tabs racing.
REUSE_GRACE_SECONDS = 10

_COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "passw0rd123", "1234567890",
    "12345678910", "123456789012", "qwertyuiop", "qwerty123456", "iloveyou123",
    "letmein1234", "welcome1234", "admin12345", "administrator", "changeme123",
    "abcdefghij", "0123456789", "1q2w3e4r5t", "openhunt123",
}


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if len(normalized) > 254 or not _EMAIL_RE.match(normalized):
        raise AuthError(422, "Enter a valid email address.")
    return normalized


def validate_password(password: str, email: str = "") -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(422, f"Use a password with at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(422, f"Use a password with at most {MAX_PASSWORD_LENGTH} characters.")
    lowered = password.casefold()
    if lowered in _COMMON_PASSWORDS or len(set(lowered)) < 4:
        raise AuthError(422, "That password is too common. Pick something less guessable.")
    local = email.split("@", 1)[0]
    if len(local) >= 4 and local in lowered:
        raise AuthError(422, "The password should not contain your email name.")


def create_user(db: Session, email: str, password: str, *, check_signup_rules: bool = True) -> User:
    normalized = validate_email(email)
    validate_password(password, normalized)
    if check_signup_rules:
        if not settings.signup_enabled:
            raise AuthError(403, "Sign-ups are closed on this server.")
        allowed = settings.allowed_signup_email_set
        if allowed and normalized not in allowed:
            raise AuthError(403, "This email address is not on the invite list.")

    user = User(
        email=normalized,
        password_hash=hash_password(password),
        is_admin=False,
        is_active=True,
        onboarding_completed=False,
        token_version=0,
        failed_login_attempts=0,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise AuthError(409, "An account with this email already exists.") from error
    db.add(Profile(user_id=user.id, skills=[], target_roles=[], preferences={}))
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for valid credentials, or raise one generic error."""
    generic = AuthError(401, "Invalid email or password, or the account is temporarily locked.")
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not user.is_active:
        burn_password_check(password)
        raise generic

    now = _now()
    if user.locked_until is not None and user.locked_until > now:
        burn_password_check(password)
        raise generic

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_attempts = 0
        db.commit()
        raise generic

    user.failed_login_attempts = 0
    user.locked_until = None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    db.commit()
    return user


@dataclass
class Session_:
    access_token: str
    refresh_token: str
    expires_in: int


def _issue_refresh(db: Session, user: User, family_id: str) -> str:
    raw, hashed = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashed,
            family_id=family_id,
            expires_at=_now() + timedelta(days=settings.refresh_token_days),
        )
    )
    return raw


def start_session(db: Session, user: User) -> Session_:
    refresh = _issue_refresh(db, user, str(uuid.uuid4()))
    db.commit()
    return Session_(
        access_token=create_access_token(str(user.id), token_version=user.token_version),
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def rotate_session(db: Session, raw_token: str) -> tuple[User, Session_]:
    """Exchange a refresh token for a new pair. Reuse of an old token ends the session family."""
    invalid = AuthError(401, "Your session has expired. Please sign in again.")
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if record is None:
        raise invalid
    now = _now()

    if record.revoked_at is not None:
        if (now - record.revoked_at).total_seconds() > REUSE_GRACE_SECONDS:
            revoke_family(db, record.family_id)
            db.commit()
        raise invalid
    if record.expires_at <= now:
        raise invalid

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise invalid

    record.revoked_at = now
    refresh = _issue_refresh(db, user, record.family_id)
    db.commit()
    return user, Session_(
        access_token=create_access_token(str(user.id), token_version=user.token_version),
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def revoke_family(db: Session, family_id: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_by_raw_token(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if record is not None:
        revoke_family(db, record.family_id)
        db.commit()


def revoke_all_sessions(db: Session, user: User) -> None:
    """Sign the user out everywhere, including access tokens that are still unexpired."""
    user.token_version += 1
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AuthError(403, "Your current password is not correct.")
    validate_password(new_password, user.email)
    if current_password == new_password:
        raise AuthError(422, "Choose a password you have not used for this account just now.")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = _now()
    revoke_all_sessions(db, user)
    db.commit()
