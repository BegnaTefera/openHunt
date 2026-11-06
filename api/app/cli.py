"""Admin helpers for the hosted database.

    python -m app.cli set-credentials you@example.com            # create or reset a user
    python -m app.cli set-credentials you@example.com --admin    # ...and make them admin

Run it with DATABASE_URL pointing at the database you want to change. There is no
password reset by email, so this is how a forgotten password is recovered.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.profile import Profile
from app.models.user import User
from app.services import accounts


def set_credentials(email: str, password: str, make_admin: bool) -> str:
    normalized = accounts.validate_email(email)
    accounts.validate_password(password, normalized)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == normalized))
        if user is None:
            user = accounts.create_user(db, normalized, password, check_signup_rules=False)
            outcome = "created"
        else:
            user.password_hash = hash_password(password)
            user.failed_login_attempts = 0
            user.locked_until = None
            accounts.revoke_all_sessions(db, user)
            outcome = "password reset"
        if make_admin:
            user.is_admin = True
        if db.scalar(select(Profile).where(Profile.user_id == user.id)) is None:
            db.add(Profile(user_id=user.id, skills=[], target_roles=[], preferences={}))
        db.commit()
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="openHunt admin helpers")
    commands = parser.add_subparsers(dest="command", required=True)
    creds = commands.add_parser("set-credentials", help="create a user or reset their password")
    creds.add_argument("email")
    creds.add_argument("--admin", action="store_true", help="also make this user an admin")
    arguments = parser.parse_args(argv)

    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat password: "):
        print("The passwords do not match.", file=sys.stderr)
        return 1
    try:
        print(f"{arguments.email}: {set_credentials(arguments.email, password, arguments.admin)}")
    except accounts.AuthError as error:
        print(error.detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
