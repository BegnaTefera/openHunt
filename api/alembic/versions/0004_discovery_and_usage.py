"""Add API usage counters and discovery candidates.

Revision ID: 0004_discovery_and_usage
Revises: 0003_unmatched_board_jobs
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_discovery_and_usage"
down_revision = "0003_unmatched_board_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("provider", "day", name="uq_api_usage_provider_day"),
    )
    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ats_type", sa.String(length=32), nullable=False),
        sa.Column("ats_slug", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "found_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("ats_type", "ats_slug", name="uq_discovery_candidates_ats_slug"),
    )


def downgrade() -> None:
    op.drop_table("discovery_candidates")
    op.drop_table("api_usage")
