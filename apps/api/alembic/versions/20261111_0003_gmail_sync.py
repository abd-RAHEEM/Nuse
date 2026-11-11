"""Add read-only Gmail sync state and matched-message review records.

Revision ID: 20261111_0003
Revises: 20261107_0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261111_0003"
down_revision = "20261107_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "integration_connections_provider_check",
        "integration_connections",
        type_="check",
    )
    op.create_check_constraint(
        "integration_connections_provider_check",
        "integration_connections",
        "provider IN ('notion', 'google_calendar', 'gmail')",
    )
    op.create_table(
        "gmail_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("after_date", sa.Date(), nullable=True),
        sa.Column("page_token", sa.Text(), nullable=True),
        sa.Column("history_page_token", sa.Text(), nullable=True),
        sa.Column(
            "pending_message_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("start_history_id", sa.String(128), nullable=True),
        sa.Column("latest_history_id", sa.String(128), nullable=True),
        sa.Column("messages_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_queued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_discarded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('initial', 'incremental')",
            name="gmail_sync_runs_mode_check",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="gmail_sync_runs_status_check",
        ),
    )
    op.create_index(
        "gmail_sync_runs_one_active_connection_idx",
        "gmail_sync_runs",
        ["connection_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "gmail_processed_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sender", sa.String(500), nullable=True),
        sa.Column("subject", sa.String(1000), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suggested_status", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "message_id",
            name="uq_gmail_processed_user_message",
        ),
        sa.CheckConstraint(
            "status IN ('needs_review', 'processed', 'ignored')",
            name="gmail_processed_messages_status_check",
        ),
    )
    op.create_index(
        "gmail_processed_messages_user_status_idx",
        "gmail_processed_messages",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "gmail_processed_messages_user_status_idx",
        table_name="gmail_processed_messages",
    )
    op.drop_table("gmail_processed_messages")
    op.drop_index(
        "gmail_sync_runs_one_active_connection_idx",
        table_name="gmail_sync_runs",
    )
    op.drop_table("gmail_sync_runs")
    op.drop_constraint(
        "integration_connections_provider_check",
        "integration_connections",
        type_="check",
    )
    op.create_check_constraint(
        "integration_connections_provider_check",
        "integration_connections",
        "provider IN ('notion', 'google_calendar')",
    )
