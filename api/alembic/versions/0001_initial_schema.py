"""Create the initial job-search schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

application_status = postgresql.ENUM(
    "new",
    "shortlisted",
    "drafted",
    "applied",
    "replied",
    "interview",
    "rejected",
    "offer",
    "skipped",
    name="application_status",
    create_type=False,
)


def upgrade() -> None:
    application_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("website", sa.String(length=2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("location_text", sa.String(length=500)),
        sa.Column("remote_scope", sa.String(length=50)),
        sa.Column("employment_type", sa.String(length=50)),
        sa.Column("seniority", sa.String(length=50)),
        sa.Column("salary_text", sa.String(length=500)),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("score_reason", sa.Text()),
        sa.UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False, unique=True),
        sa.Column("status", application_status, nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("cover_letter", sa.Text()),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
        ),
        sa.Column("from", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=1000)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classification", sa.String(length=50)),
        sa.Column("snippet", sa.Text()),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("skills", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("target_roles", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("seniority", sa.String(length=50)),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_profile_single_row"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_users_single_row"),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("profile")
    op.drop_table("events")
    op.drop_table("emails")
    op.drop_table("documents")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("companies")
    application_status.drop(op.get_bind(), checkfirst=True)
