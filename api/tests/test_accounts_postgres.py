"""Account, session, CV and multi-user tests against a real Postgres database.

Skipped unless TEST_DATABASE_URL is set (see test_integration_postgres.py).
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to run")

PASSWORD = "a-long-test-password"
CLIENT = {"X-OpenHunt-Client": "web"}


@pytest.fixture()
def raw_client(db: Session):
    """The real authentication is used; only the database session is swapped."""
    from app.db.dependencies import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_cookie(client: TestClient, value: str | None) -> None:
    """Replace the session cookie, as another tab or a thief would present it."""
    client.cookies.clear()
    if value is not None:
        client.cookies.set("openhunt_refresh", value, domain="testserver.local", path="/")


def signup(client: TestClient, email: str = "ada@example.com", password: str = PASSWORD):
    return client.post("/auth/signup", json={"email": email, "password": password})


def bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_job(db: Session, title: str = "Backend Engineer", slug: str = "acme", ext: str = "1"):
    from app.models.company import Company
    from app.models.job import Job

    company = db.scalar(select(Company).where(Company.ats_slug == slug))
    if company is None:
        company = Company(name=slug.title(), ats_type="greenhouse", ats_slug=slug)
        db.add(company)
        db.flush()
    job = Job(
        source="greenhouse", external_id=ext, url=f"https://boards.greenhouse.io/{slug}/jobs/{ext}",
        title=title, company_id=company.id, description="<p>Build things.</p>", tags=[], raw_payload={},
    )
    db.add(job)
    db.commit()
    return job


def make_docx(text_value: str) -> bytes:
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text_value.splitlines())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{paragraphs}</w:body></w:document>')
    return buffer.getvalue()


CV = "Jane Example\nBackend engineer with Python, FastAPI, PostgreSQL and Docker experience.\njane@example.com\n"


# ---------------------------------------------------------------- sign up and login


def test_first_signup_is_not_admin_gets_a_session_and_an_empty_profile(raw_client: TestClient, db: Session) -> None:
    response = signup(raw_client)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "ada@example.com" and body["user"]["is_admin"] is False
    assert body["user"]["onboarding_completed"] is False and body["expires_in"] == 900
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert raw_client.get("/auth/me", headers=bearer(response)).json()["email"] == "ada@example.com"
    assert raw_client.get("/profile", headers=bearer(response)).json()["target_roles"] == []
    stored = db.execute(text("select password_hash from users")).scalar_one()
    assert stored.startswith("$argon2id$")


def test_second_user_is_not_admin_and_emails_are_case_insensitive(raw_client: TestClient) -> None:
    signup(raw_client)

    other = signup(raw_client, "grace@example.com")
    duplicate = signup(raw_client, "ADA@example.com")

    assert other.json()["user"]["is_admin"] is False
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    ("email", "password", "status"),
    [("not-an-email", PASSWORD, 422), ("a@example.com", "short", 422), ("a@example.com", "password123", 422)],
)
def test_invalid_signups_are_rejected(raw_client: TestClient, email: str, password: str, status: int) -> None:
    assert signup(raw_client, email, password).status_code == status


def test_login_errors_do_not_reveal_which_part_was_wrong(raw_client: TestClient) -> None:
    signup(raw_client)
    fresh = TestClient(raw_client.app)

    wrong = fresh.post("/auth/login", json={"email": "ada@example.com", "password": "wrong-password-1"})
    unknown = fresh.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    good = fresh.post("/auth/login", json={"email": "ADA@example.com", "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert good.status_code == 200


def test_repeated_failures_lock_the_account_for_a_while(raw_client: TestClient, db: Session) -> None:
    signup(raw_client)
    fresh = TestClient(raw_client.app)

    for _ in range(5):
        fresh.post("/auth/login", json={"email": "ada@example.com", "password": "wrong-password-1"})
    locked = fresh.post("/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    assert locked.status_code == 401

    db.execute(text("update users set locked_until = now() - interval '1 minute'"))
    db.commit()
    assert fresh.post("/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200


def test_legacy_scrypt_hash_is_upgraded_on_login(raw_client: TestClient, db: Session) -> None:
    import hashlib

    signup(raw_client)
    salt = b"0123456789abcdef"
    digest = hashlib.scrypt(PASSWORD.encode(), salt=salt, n=2**14, r=8, p=1)
    db.execute(text("update users set password_hash = :h"), {"h": f"scrypt${salt.hex()}${digest.hex()}"})
    db.commit()

    fresh = TestClient(raw_client.app)
    assert fresh.post("/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200
    assert db.execute(text("select password_hash from users")).scalar_one().startswith("$argon2id$")


# ---------------------------------------------------------------- sessions


def test_refresh_requires_the_client_header_and_rotates_the_token(raw_client: TestClient) -> None:
    signup(raw_client)
    first_cookie = raw_client.cookies.get("openhunt_refresh")

    assert raw_client.post("/auth/refresh").status_code == 403
    refreshed = raw_client.post("/auth/refresh", headers=CLIENT)

    assert refreshed.status_code == 200
    assert raw_client.cookies.get("openhunt_refresh") != first_cookie
    assert raw_client.get("/auth/me", headers=bearer(refreshed)).status_code == 200


def test_racing_refresh_is_tolerated_but_late_reuse_ends_the_session(raw_client: TestClient, db: Session) -> None:
    signup(raw_client)
    old_cookie = raw_client.cookies.get("openhunt_refresh")
    raw_client.post("/auth/refresh", headers=CLIENT)
    newest_cookie = raw_client.cookies.get("openhunt_refresh")

    # Two tabs racing: the stale token fails, but the session survives.
    use_cookie(raw_client, old_cookie)
    assert raw_client.post("/auth/refresh", headers=CLIENT).status_code == 401
    use_cookie(raw_client, newest_cookie)
    assert raw_client.post("/auth/refresh", headers=CLIENT).status_code == 200
    newest_cookie = raw_client.cookies.get("openhunt_refresh")

    # Reusing an old token long after rotation looks like theft: the whole family is revoked.
    db.execute(text("update refresh_tokens set revoked_at = now() - interval '1 hour' where revoked_at is not null"))
    db.commit()
    use_cookie(raw_client, old_cookie)
    assert raw_client.post("/auth/refresh", headers=CLIENT).status_code == 401
    use_cookie(raw_client, newest_cookie)
    assert raw_client.post("/auth/refresh", headers=CLIENT).status_code == 401


def test_logout_revokes_the_session(raw_client: TestClient) -> None:
    signup(raw_client)
    cookie = raw_client.cookies.get("openhunt_refresh")

    assert raw_client.post("/auth/logout", headers=CLIENT).status_code == 204
    use_cookie(raw_client, cookie)
    assert raw_client.post("/auth/refresh", headers=CLIENT).status_code == 401


def test_logout_everywhere_also_kills_unexpired_access_tokens(raw_client: TestClient) -> None:
    response = signup(raw_client)
    headers = bearer(response)

    assert raw_client.post("/auth/logout-all", headers=headers).status_code == 204
    assert raw_client.get("/auth/me", headers=headers).status_code == 401


def test_change_password_invalidates_every_other_session(raw_client: TestClient) -> None:
    response = signup(raw_client)
    old_headers = bearer(response)
    old_cookie = raw_client.cookies.get("openhunt_refresh")

    bad = raw_client.post("/auth/change-password", headers=old_headers,
                          json={"current_password": "not-my-password", "new_password": "another-long-password"})
    changed = raw_client.post("/auth/change-password", headers=old_headers,
                              json={"current_password": PASSWORD, "new_password": "another-long-password"})

    assert bad.status_code == 403 and changed.status_code == 200
    assert raw_client.get("/auth/me", headers=old_headers).status_code == 401
    assert raw_client.get("/auth/me", headers=bearer(changed)).status_code == 200
    stale = TestClient(raw_client.app)
    use_cookie(stale, old_cookie)
    assert stale.post("/auth/refresh", headers=CLIENT).status_code == 401
    assert stale.post("/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401
    assert stale.post("/auth/login", json={"email": "ada@example.com", "password": "another-long-password"}).status_code == 200


def test_deleting_an_account_removes_all_of_its_data(raw_client: TestClient, db: Session) -> None:
    response = signup(raw_client)
    headers = bearer(response)
    job = make_job(db)
    raw_client.patch(f"/jobs/{job.id}/status", headers=headers, json={"status": "shortlisted"})
    raw_client.put("/profile/cv", headers={**headers, "X-Filename": "cv.docx"}, content=make_docx(CV))

    assert raw_client.request("DELETE", "/auth/account", headers=headers, json={"password": "wrong-password-1"}).status_code == 403
    assert raw_client.request("DELETE", "/auth/account", headers=headers, json={"password": PASSWORD}).status_code == 204

    for table in ("users", "profile", "applications", "cv_documents", "refresh_tokens"):
        assert db.execute(text(f"select count(*) from {table}")).scalar_one() == 0, table
    assert db.execute(text("select count(*) from jobs")).scalar_one() == 1  # shared data stays


def test_onboarding_flag_is_saved(raw_client: TestClient) -> None:
    headers = bearer(signup(raw_client))

    assert raw_client.post("/auth/onboarding/complete", headers=headers).json()["onboarding_completed"] is True
    assert raw_client.get("/auth/me", headers=headers).json()["onboarding_completed"] is True


# ---------------------------------------------------------------- who may sign up


def test_signups_can_be_closed(raw_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "signup_enabled", False)

    assert signup(raw_client).status_code == 403


def test_invite_list_does_not_grant_admin_privileges(raw_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "allowed_signup_emails", "ben@example.com, friend@example.com")

    assert signup(raw_client, "stranger@example.com").status_code == 403
    friend = signup(raw_client, "friend@example.com")
    owner = signup(raw_client, "Ben@Example.com")

    assert friend.json()["user"]["is_admin"] is False
    assert owner.json()["user"]["is_admin"] is False


# ---------------------------------------------------------------- privacy between users


def test_users_never_see_each_others_applications_profiles_or_drafts(raw_client: TestClient, db: Session) -> None:
    a = bearer(signup(raw_client, "a@example.com"))
    b = bearer(signup(raw_client, "b@example.com"))
    job = make_job(db)

    raw_client.put("/profile", headers=a, json={"skills": ["python"], "target_roles": ["backend"], "full_name": "Ada A"})
    raw_client.patch(f"/jobs/{job.id}/status", headers=a, json={"status": "applied"})
    raw_client.post(f"/jobs/{job.id}/draft?use_ai=false", headers=a)

    assert raw_client.get(f"/jobs/{job.id}", headers=a).json()["status"] == "applied"
    assert raw_client.get(f"/jobs/{job.id}", headers=b).json()["status"] == "new"
    assert raw_client.get("/profile", headers=b).json()["full_name"] is None
    assert raw_client.get(f"/jobs/{job.id}/draft", headers=b).status_code == 404
    assert raw_client.get("/stats", headers=a).json()["applied"] == 1
    assert raw_client.get("/stats", headers=b).json()["applied"] == 0

    raw_client.patch(f"/jobs/{job.id}/status", headers=b, json={"status": "skipped"})
    assert raw_client.get(f"/jobs/{job.id}", headers=a).json()["status"] == "applied"


def test_only_admins_change_the_shared_company_list(raw_client: TestClient, db: Session) -> None:
    from app.models.user import User

    admin = bearer(signup(raw_client, "admin@example.com"))
    member = bearer(signup(raw_client, "member@example.com"))
    admin_user = db.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin_user is not None
    admin_user.is_admin = True
    db.commit()
    company = {"name": "Acme", "ats_type": "greenhouse", "ats_slug": "acme"}

    assert raw_client.post("/companies", headers=member, json=company).status_code == 403
    assert raw_client.post("/companies", headers=admin, json=company).status_code == 201
    assert raw_client.get("/companies", headers=member).status_code == 200


def test_data_endpoints_require_a_valid_session(raw_client: TestClient) -> None:
    for path in ("/jobs", "/profile", "/profile/cv", "/stats", "/roles", "/discovery", "/auth/me"):
        assert raw_client.get(path).status_code == 401, path


# ---------------------------------------------------------------- role types


def test_job_scores_follow_each_users_role_choices(raw_client: TestClient, db: Session) -> None:
    broad = bearer(signup(raw_client, "broad@example.com"))
    narrow = bearer(signup(raw_client, "narrow@example.com"))
    devops = make_job(db, "DevOps Engineer", ext="7")
    sales = make_job(db, "Account Executive", ext="8")

    raw_client.put("/profile", headers=narrow, json={"skills": [], "target_roles": ["backend"]})

    assert raw_client.get(f"/jobs/{devops.id}", headers=broad).json()["score"] > 0  # empty = every tech role
    assert raw_client.get(f"/jobs/{devops.id}", headers=narrow).json()["score"] == 0
    assert raw_client.get(f"/jobs/{sales.id}", headers=broad).json()["score"] == 0
    keys = [item["key"] for item in raw_client.get("/roles", headers=broad).json()]
    assert {"backend", "devops", "data", "design", "product"} <= set(keys)


def test_free_text_roles_from_older_profiles_become_keywords(raw_client: TestClient) -> None:
    headers = bearer(signup(raw_client))

    saved = raw_client.put("/profile", headers=headers, json={
        "skills": [], "target_roles": ["Backend", "wizard"], "custom_title_keywords": ["recruiter"]}).json()

    assert saved["target_roles"] == ["backend"]
    assert sorted(saved["custom_title_keywords"]) == ["recruiter", "wizard"]


# ---------------------------------------------------------------- CV


def test_cv_upload_download_replace_and_delete(raw_client: TestClient, db: Session) -> None:
    headers = bearer(signup(raw_client))
    other = bearer(signup(raw_client, "b@example.com"))
    assert raw_client.get("/profile/cv", headers=headers).json() is None

    uploaded = raw_client.put("/profile/cv", headers={**headers, "X-Filename": "My%20CV%20(final).docx"}, content=make_docx(CV))
    body = uploaded.json()
    assert uploaded.status_code == 200 and body["filename"] == "My CV _final_.docx"
    assert body["suggestions"]["full_name"] == "Jane Example"
    assert {"Python", "FastAPI", "PostgreSQL", "Docker"} <= set(body["suggestions"]["skills"])

    download = raw_client.get("/profile/cv/download", headers=headers)
    assert download.status_code == 200 and download.content == make_docx(CV)
    assert download.headers["x-content-type-options"] == "nosniff" and "attachment" in download.headers["content-disposition"]
    assert raw_client.get("/profile/cv/download", headers=other).status_code == 404

    raw_client.put("/profile/cv", headers={**headers, "X-Filename": "cv2.txt"}, content=CV.encode() * 3)
    assert db.execute(text("select count(*) from cv_documents")).scalar_one() == 1
    assert raw_client.get("/profile/cv", headers=headers).json()["filename"] == "cv2.txt"

    assert raw_client.delete("/profile/cv", headers=headers).status_code == 204
    assert raw_client.get("/profile/cv", headers=headers).json() is None


def test_cv_uploads_are_validated(raw_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    headers = {**bearer(signup(raw_client)), "X-Filename": "cv.pdf"}

    assert raw_client.put("/profile/cv", headers=headers, content=b"").status_code == 422
    assert raw_client.put("/profile/cv", headers=headers, content=b"\x89PNG\r\n\x1a\n\x00\x00binary").status_code == 422
    assert raw_client.put("/profile/cv", headers=headers, content=b"%PDF-1.4 definitely not a pdf").status_code == 422
    assert raw_client.put("/profile/cv", headers=headers, content=b"too short").status_code == 422
    monkeypatch.setattr(settings, "cv_max_bytes", 1000)
    assert raw_client.put("/profile/cv", headers=headers, content=b"x" * 2000).status_code == 413
    assert raw_client.put("/profile/cv", content=make_docx(CV)).status_code == 401


def test_cv_text_reaches_the_ai_prompt_without_contact_details(raw_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai.client import AIResult

    headers = bearer(signup(raw_client))
    raw_client.put("/profile/cv", headers={**headers, "X-Filename": "cv.docx"}, content=make_docx(CV))
    job = make_job(db)
    seen: dict[str, object] = {}

    def fake_complete(_db, messages, **kwargs):
        seen["prompt"] = messages[-1]["content"]
        seen["sensitive"] = kwargs.get("sensitive")
        return AIResult(text="Dear team, hello.", provider="groq", model="m")

    monkeypatch.setattr("app.ai.drafting.complete", fake_complete)
    monkeypatch.setattr("app.ai.drafting.complete_json", lambda *_a, **_k: type("V", (), {"unsupported_claims": []})())

    draft = raw_client.post(f"/jobs/{job.id}/draft", headers=headers).json()

    assert draft["generated_by"] == "groq:m"
    assert "FastAPI" in str(seen["prompt"]) and "jane@example.com" not in str(seen["prompt"])
    assert seen["sensitive"] is True


# ---------------------------------------------------------------- migration of an old single-user database


def test_upgrade_keeps_the_old_single_user_data(engine, alembic_cmd) -> None:
    alembic_cmd("downgrade", "0004_discovery_and_usage")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
        connection.execute(text("INSERT INTO users (id, username, password_hash) VALUES (1, 'Admin', 'scrypt$00$00')"))
        connection.execute(text(
            "INSERT INTO profile (id, skills, target_roles, preferences) "
            "VALUES (1, ARRAY['python'], ARRAY['backend'], '{\"country\": \"Kenya\"}')"))
        connection.execute(text("INSERT INTO companies (name, ats_type, ats_slug) VALUES ('Acme', 'greenhouse', 'acme')"))
        connection.execute(text(
            "INSERT INTO jobs (source, external_id, url, title, tags, is_active, raw_payload) "
            "VALUES ('greenhouse', '1', 'https://x.test/1', 'Backend Engineer', ARRAY[]::text[], true, '{}')"))
        connection.execute(text("INSERT INTO applications (job_id, status) VALUES (1, 'applied')"))

    alembic_cmd("upgrade", "head")

    with engine.begin() as connection:
        user = connection.execute(text("select id, email, is_admin, onboarding_completed from users")).one()
        assert tuple(user) == (1, "admin@legacy.invalid", True, True)
        assert connection.execute(text("select user_id, skills from profile")).one() == (1, ["python"])
        assert connection.execute(text("select user_id, status from applications")).one() == (1, "applied")
        # The sequences were moved past the old explicit ids, so new rows get fresh ids.
        connection.execute(text("INSERT INTO users (email, password_hash) VALUES ('new@example.com', 'x')"))
        assert connection.execute(text("select count(*) from users")).scalar_one() == 2
        connection.execute(text("TRUNCATE users, jobs, companies RESTART IDENTITY CASCADE"))


# ---------------------------------------------------------------- admin command


def test_set_credentials_creates_then_resets_a_user(raw_client: TestClient, db: Session, engine, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import cli
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(cli, "SessionLocal", sessionmaker(bind=engine))

    assert cli.set_credentials("owner@example.com", PASSWORD, make_admin=True) == "created"
    first = TestClient(raw_client.app)
    session = first.post("/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert session.status_code == 200 and session.json()["user"]["is_admin"] is True

    # Locked out and forgotten password: the command recovers the account.
    db.execute(text("update users set failed_login_attempts = 4, locked_until = now() + interval '1 hour'"))
    db.commit()
    assert cli.set_credentials("OWNER@example.com", "a-brand-new-password", make_admin=False) == "password reset"

    assert first.get("/auth/me", headers=bearer(session)).status_code == 401  # old sessions end
    again = TestClient(raw_client.app)
    assert again.post("/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 401
    assert again.post("/auth/login", json={"email": "owner@example.com", "password": "a-brand-new-password"}).status_code == 200


def test_set_credentials_rejects_weak_passwords(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import cli
    from app.services.accounts import AuthError

    with pytest.raises(AuthError):
        cli.set_credentials("owner@example.com", "short", make_admin=False)
