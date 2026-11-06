"""Give the test run safe defaults so it works without a local .env file."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://openhunt:test@localhost:5432/openhunt_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-checks")


# ---- real-Postgres fixtures (used by the *_postgres tests; skipped without TEST_DATABASE_URL) ----
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

TEST_URL = os.environ.get("TEST_DATABASE_URL")
API_DIR = Path(__file__).resolve().parents[1]


def alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": TEST_URL or ""}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, check=True, capture_output=True
    )


@pytest.fixture(scope="session")
def alembic_cmd():
    return alembic


@pytest.fixture(scope="session")
def engine():
    if not TEST_URL:
        pytest.skip("set TEST_DATABASE_URL to run the Postgres tests")
    engine = create_engine(TEST_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic("upgrade", "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def db(engine) -> Session:
    with sessionmaker(bind=engine)() as session:
        yield session
        session.rollback()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE api_usage, discovery_candidates, documents, emails, applications, jobs, "
                "companies, events, notification_outbox, tracked_gmail_threads, gmail_connections, "
                "profile, refresh_tokens, cv_documents, users RESTART IDENTITY CASCADE"
            )
        )
