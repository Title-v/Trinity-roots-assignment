"""Persist model audit logs on hosts without a durable writable filesystem."""

import sqlalchemy as sa
from alembic import op

revision = "d962e38b105f"
down_revision = "c851d27a904e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event IN ('request', 'response')", name="ck_assistant_audit_event"
        ),
    )
    op.create_index(
        "ix_assistant_audit_logs_request_id", "assistant_audit_logs", ["request_id"]
    )


def downgrade() -> None:
    op.drop_table("assistant_audit_logs")
