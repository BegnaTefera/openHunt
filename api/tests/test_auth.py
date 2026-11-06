from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import get_current_user, require_admin
from app.core.security import create_access_token
from app.models.user import User


class FakeDB:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def get(self, _model: object, _identifier: int) -> User | None:
        return self.user


def make_user(**overrides: object) -> User:
    values = dict(
        id=5, email="ada@example.com", password_hash="x", is_admin=False,
        is_active=True, onboarding_completed=True, token_version=2,
    )
    values.update(overrides)
    return User(**values)


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_valid_token_returns_the_user() -> None:
    user = make_user()

    result = get_current_user(credentials(create_access_token("5", token_version=2)), FakeDB(user))

    assert result is user


@pytest.mark.parametrize(
    ("token", "user"),
    [
        (None, make_user()),
        ("garbage", make_user()),
        (create_access_token("5", token_version=1), make_user()),  # password changed since
        (create_access_token("5", token_version=2), make_user(is_active=False)),
        (create_access_token("5", token_version=2), None),
    ],
)
def test_bad_tokens_and_inactive_users_are_rejected(token: str | None, user: User | None) -> None:
    with pytest.raises(HTTPException) as error:
        get_current_user(credentials(token) if token else None, FakeDB(user))  # type: ignore[arg-type]

    assert error.value.status_code == 401


def test_admin_only_dependency() -> None:
    assert require_admin(make_user(is_admin=True)).is_admin
    with pytest.raises(HTTPException) as error:
        require_admin(make_user())
    assert error.value.status_code == 403
