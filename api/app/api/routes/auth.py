from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.security import verify_password
from app.db.dependencies import get_db
from app.models.user import User
from app.schemas.user import (
    AuthResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    SignupRequest,
    UserRead,
)
from app.services import accounts
from app.services.accounts import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])

CLIENT_HEADER = "x-openhunt-client"


def _fail(error: AuthError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        raw_token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def _require_client_header(request: Request) -> None:
    """Cookie-authenticated endpoints must come from our own page (CSRF defence)."""
    if request.headers.get(CLIENT_HEADER) != "web":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing client header")


def _respond(response: Response, user: User, session: accounts.Session_) -> AuthResponse:
    _set_refresh_cookie(response, session.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=UserRead.model_validate(user),
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    try:
        user = accounts.create_user(db, payload.email, payload.password)
    except AuthError as error:
        raise _fail(error) from error
    return _respond(response, user, accounts.start_session(db, user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    try:
        user = accounts.authenticate(db, payload.email, payload.password)
    except AuthError as error:
        raise _fail(error) from error
    return _respond(response, user, accounts.start_session(db, user))


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    _require_client_header(request)
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    try:
        user, session = accounts.rotate_session(db, raw)
    except AuthError as error:
        # The cookie is deliberately left alone: in a two-tab race the stale request must
        # not delete the fresh cookie the other tab just received. The page signs out via
        # /auth/logout, which clears it.
        raise _fail(error) from error
    return _respond(response, user, session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    _require_client_header(request)
    accounts.revoke_by_raw_token(db, request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    accounts.revoke_all_sessions(db, user)
    db.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/onboarding/complete", response_model=UserRead)
def complete_onboarding(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    user.onboarding_completed = True
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password", response_model=AuthResponse)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthResponse:
    try:
        accounts.change_password(db, user, payload.current_password, payload.new_password)
    except AuthError as error:
        raise _fail(error) from error
    db.refresh(user)
    return _respond(response, user, accounts.start_session(db, user))


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your password is not correct.")
    db.delete(user)
    db.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
