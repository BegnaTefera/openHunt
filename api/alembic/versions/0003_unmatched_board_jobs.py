"""Allow public-board jobs without a configured ATS company.

Revision ID: 0003_unmatched_board_jobs
Revises: 0002_ats_collectors
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_unmatched_board_jobs"
down_revision = "0002_ats_collectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("jobs", "company_id", nullable=True)


def downgrade() -> None:
    has_unmatched_jobs = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM jobs WHERE company_id IS NULL)")
    ).scalar()
    if has_unmatched_jobs:
        raise RuntimeError(
            "Cannot make jobs.company_id non-null while unmatched board jobs "
            "exist; assign those jobs to companies or remove them before downgrade."
        )
    op.alter_column("jobs", "company_id", nullable=False)
