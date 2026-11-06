"""Multi-user accounts, rotating sessions, per-user profiles/applications, and CV storage.

Revision ID: 0005_accounts_and_cv
Revises: 0004_discovery_and_usage
Create Date: 2026-11-02

The single-user account (if one exists) is kept: it becomes an admin with an
email derived from its old username. Because it had no email, sign in again with
``python -m app.cli set-credentials you@example.com --admin`` to create or
promote an account with the desired email.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_accounts_and_cv"
down_revision = "0004_discovery_and_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- users ----
    op.drop_constraint("ck_users_single_row", "users", type_="check")
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE users SET "
        "email = CASE WHEN position('@' in username) > 0 THEN lower(username) "
        "ELSE lower(username) || '@legacy.invalid' END, "
        "is_admin = true, onboarding_completed = true"
    )
    op.alter_column("users", "email", nullable=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.drop_column("users", "username")
    # The old row was inserted with an explicit id, so move the sequence past it.
    op.execute(
        "SELECT setval(pg_get_serial_sequence('users', 'id'), "
        "GREATEST((SELECT COALESCE(MAX(id), 1) FROM users), 1))"
    )

    # ---- sessions ----
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    # ---- profile: one per user ----
    op.drop_constraint("ck_profile_single_row", "profile", type_="check")
    op.add_column("profile", sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute("UPDATE profile SET user_id = (SELECT MIN(id) FROM users)")
    op.execute("DELETE FROM profile WHERE user_id IS NULL")
    op.alter_column("profile", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_profile_user_id", "profile", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint("uq_profile_user_id", "profile", ["user_id"])
    op.execute(
        "SELECT setval(pg_get_serial_sequence('profile', 'id'), "
        "GREATEST((SELECT COALESCE(MAX(id), 1) FROM profile), 1))"
    )

    # ---- applications: one per user and job ----
    op.add_column("applications", sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute("UPDATE applications SET user_id = (SELECT MIN(id) FROM users)")
    op.execute("DELETE FROM applications WHERE user_id IS NULL")
    op.alter_column("applications", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_applications_user_id", "applications", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_constraint("applications_job_id_key", "applications", type_="unique")
    op.create_unique_constraint("uq_applications_user_job", "applications", ["user_id", "job_id"])
    op.create_index("ix_applications_user_id", "applications", ["user_id"])

    # ---- CV storage ----
    op.create_table(
        "cv_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM users")).scalar_one() > 1:
        raise RuntimeError("Cannot downgrade to the single-user schema while several users exist.")

    op.drop_table("cv_documents")

    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_constraint("uq_applications_user_job", "applications", type_="unique")
    op.create_unique_constraint("applications_job_id_key", "applications", ["job_id"])
    op.drop_constraint("fk_applications_user_id", "applications", type_="foreignkey")
    op.drop_column("applications", "user_id")

    op.drop_constraint("uq_profile_user_id", "profile", type_="unique")
    op.drop_constraint("fk_profile_user_id", "profile", type_="foreignkey")
    op.drop_column("profile", "user_id")
    op.execute("UPDATE profile SET id = 1")
    op.create_check_constraint("ck_profile_single_row", "profile", "id = 1")

    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.execute("UPDATE users SET username = left(email, 64)")
    op.alter_column("users", "username", nullable=False)
    op.create_unique_constraint("users_username_key", "users", ["username"])
    op.drop_constraint("uq_users_email", "users", type_="unique")
    for column in (
        "password_changed_at", "created_at", "locked_until", "failed_login_attempts",
        "token_version", "onboarding_completed", "is_active", "is_admin", "email",
    ):
        op.drop_column("users", column)
    op.execute("UPDATE users SET id = 1")
    op.create_check_constraint("ck_users_single_row", "users", "id = 1")
