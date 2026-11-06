from __future__ import annotations

from app.core.config import settings
from app.models.integrations import NotificationOutbox
from app.services.gmail import _decrypt, _encrypt, _headers, _internal_date, _sender, _sent_by_user
from app.services.notifications import _message


def test_gmail_metadata_helpers_read_headers_without_message_bodies() -> None:
    message = {
        "id": "message-id",
        "internalDate": "1793800000000",
        "labelIds": ["INBOX", "SENT"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Hiring Team <Recruiter@Example.com>"},
                {"name": "Subject", "value": "Application received"},
            ]
        },
    }

    assert _headers(message)["subject"] == "Application received"
    assert _sender(message) == "recruiter@example.com"
    assert _internal_date(message) == 1793800000000
    assert _sent_by_user({"messages": [message]}, "recruiter@example.com")
    assert not _sent_by_user({"messages": [message]}, "other@example.com")
    assert "body" not in _headers(message)


def test_telegram_alert_formats_only_application_metadata() -> None:
    notification = NotificationOutbox(
        user_id=1,
        event_type="application_reply",
        payload={
            "title": "Backend Engineer",
            "company": "Acme",
            "url": "https://example.com/job/1",
        },
    )

    message = _message(notification)

    assert "New Gmail reply for Backend Engineer at Acme" in message
    assert "Subject:" not in message
    assert "https://example.com/job/1" in message


def test_gmail_tokens_are_encrypted_and_secret_key_scoped(monkeypatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-secret-key")

    encrypted = _encrypt("refresh-token")

    assert encrypted != "refresh-token"
    assert _decrypt(encrypted) == "refresh-token"
