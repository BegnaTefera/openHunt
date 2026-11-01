"""Give the test run safe defaults so it works without a local .env file."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://openhunt:test@localhost:5432/openhunt_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-checks")
os.environ.setdefault("DEFAULT_PASSWORD", "test-password-long-enough")
