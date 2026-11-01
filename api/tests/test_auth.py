from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.auth import login
from app.core.security import decode_access_token, hash_password
from app.models.user import User
from app.schemas.user import UserLogin


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def scalar(self, _statement: object) -> User | None:
        return self.user


def test_login_returns_token_for_matching_password() -> None:
    user = User(id=1, username="admin", password_hash=hash_password("correct-password"))

    response = login(
        UserLogin(username="admin", password="correct-password"),
        FakeSession(user),
    )

    assert decode_access_token(response.access_token)["sub"] == "1"


def test_login_rejects_invalid_password() -> None:
    user = User(id=1, username="admin", password_hash=hash_password("correct-password"))

    with pytest.raises(HTTPException) as error:
        login(UserLogin(username="admin", password="incorrect-password"), FakeSession(user))

    assert error.value.status_code == 401
