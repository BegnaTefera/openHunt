"""Add Gmail tracking and Telegram notification outbox.

Revision ID: 0006_gmail_tracking
Revises: 0005_accounts_and_cv
Create Date: 2026-11-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_gmail_tracking"
down_revision = "0005_accounts_and_cv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("emails_gmail_message_id_key", "emails", type_="unique")
    op.add_column("emails", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("emails", sa.Column("gmail_thread_id", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        "fk_emails_user_id", "emails", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_emails_user_id", "emails", ["user_id"])
    op.create_unique_constraint(
        "uq_emails_user_gmail_message", "emails", ["user_id", "gmail_message_id"]
    )

    op.create_table(
        "gmail_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("gmail_address", sa.String(length=320), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("oauth_state_hash", sa.String(length=64), nullable=True),
        sa.Column("oauth_state_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "tracked_gmail_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("last_seen_internal_date", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "thread_id", name="uq_tracked_gmail_user_thread"),
    )
    op.create_index("ix_tracked_gmail_threads_user_id", "tracked_gmail_threads", ["user_id"])
    op.create_index(
        "ix_tracked_gmail_threads_application_id", "tracked_gmail_threads", ["application_id"]
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_outbox_user_id", "notification_outbox", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_user_id", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index(
        "ix_tracked_gmail_threads_application_id", table_name="tracked_gmail_threads"
    )
    op.drop_index("ix_tracked_gmail_threads_user_id", table_name="tracked_gmail_threads")
    op.drop_table("tracked_gmail_threads")
    op.drop_table("gmail_connections")
    op.drop_constraint("uq_emails_user_gmail_message", "emails", type_="unique")
    op.drop_index("ix_emails_user_id", table_name="emails")
    op.drop_constraint("fk_emails_user_id", "emails", type_="foreignkey")
    op.drop_column("emails", "gmail_thread_id")
    op.drop_column("emails", "user_id")
    op.create_unique_constraint(
        "emails_gmail_message_id_key", "emails", ["gmail_message_id"]
    )
