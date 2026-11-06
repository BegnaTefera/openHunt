from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.user import User
from app.services.accounts import AuthError, create_user, normalize_email, validate_email, validate_password


class FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    def flush(self) -> None:
        for instance in self.added:
            if isinstance(instance, User):
                instance.id = 1

    def commit(self) -> None:
        pass

    def refresh(self, _instance: object) -> None:
        pass


def test_signup_allowlisted_email_does_not_get_admin_privileges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "signup_enabled", True)
    monkeypatch.setattr(settings, "allowed_signup_emails", "admin@example.com")

    user = create_user(FakeDB(), "admin@example.com", "a-strong-test-password")

    assert user.is_admin is False


def test_emails_are_trimmed_lowercased_and_checked() -> None:
    assert validate_email("  Ada@Example.COM ") == "ada@example.com"
    assert normalize_email("A@B.co") == "a@b.co"
    for bad in ("", "nope", "a@b", "a b@c.de", "@example.com"):
        with pytest.raises(AuthError) as error:
            validate_email(bad)
        assert error.value.status_code == 422


@pytest.mark.parametrize(
    "password",
    ["short", "a" * 129, "password123", "1234567890", "aaaaaaaaaaaa", "ada.lovelace-1"],
)
def test_weak_passwords_are_rejected(password: str) -> None:
    with pytest.raises(AuthError):
        validate_password(password, "ada.lovelace@example.com")


def test_reasonable_passphrases_are_accepted() -> None:
    validate_password("correct horse battery staple", "ada@example.com")
    validate_password("Tr0ub4dor&3-and-more", "")
