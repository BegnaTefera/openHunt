"""Add ATS configuration and raw job payloads.

Revision ID: 0002_ats_collectors
Revises: 0001_initial_schema
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_ats_collectors"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("ats_type", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("ats_slug", sa.String(length=255), nullable=True))
    op.execute(
        "UPDATE companies SET ats_type = 'unsupported', "
        "ats_slug = 'legacy-' || id::text "
        "WHERE ats_type IS NULL OR ats_slug IS NULL"
    )
    op.alter_column("companies", "ats_type", nullable=False)
    op.alter_column("companies", "ats_slug", nullable=False)
    op.create_unique_constraint(
        "uq_companies_ats_type_slug", "companies", ["ats_type", "ats_slug"]
    )

    op.create_index("ix_jobs_company_id", "jobs", ["company_id"])
    op.drop_constraint("uq_jobs_source_external_id", "jobs", type_="unique")
    op.add_column(
        "jobs",
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("jobs", "raw_payload", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "raw_payload")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.create_unique_constraint(
        "uq_jobs_source_external_id", "jobs", ["source", "external_id"]
    )
    op.drop_constraint("uq_companies_ats_type_slug", "companies", type_="unique")
    op.drop_column("companies", "ats_slug")
    op.drop_column("companies", "ats_type")
