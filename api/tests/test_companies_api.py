from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.auth import get_current_user, require_admin
from app.db.dependencies import get_db
from app.main import app
from app.models.company import Company
from app.models.user import User


class FakeResult:
    def __init__(self, companies: list[Company]) -> None:
        self.companies = companies

    def all(self) -> list[Company]:
        return self.companies


class FakeSession:
    def __init__(self) -> None:
        self.companies: list[Company] = []

    def scalars(self, _statement: object) -> FakeResult:
        return FakeResult(self.companies)

    def add(self, company: Company) -> None:
        company.id = len(self.companies) + 1
        self.companies.append(company)

    def commit(self) -> None:
        return None

    def refresh(self, _company: Company) -> None:
        return None


def test_company_setup_requires_login_and_supports_add_and_list() -> None:
    db = FakeSession()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        unauthenticated = client.get("/companies")
        assert unauthenticated.status_code == 401

        admin = User(
            id=1, email="admin@example.com", password_hash="unused", is_admin=True,
            is_active=True, onboarding_completed=True, token_version=0,
        )
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[require_admin] = lambda: admin

        created = client.post(
            "/companies",
            json={
                "name": "Acme",
                "ats_type": "greenhouse",
                "ats_slug": "acme",
                "website": "https://acme.example",
            },
        )
        assert created.status_code == 201
        assert created.json()["ats_slug"] == "acme"

        listed = client.get("/companies")
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == "Acme"
    finally:
        app.dependency_overrides.clear()
