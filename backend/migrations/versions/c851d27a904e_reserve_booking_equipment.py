"""Reserve equipment units alongside room bookings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c851d27a904e"
down_revision = "b742c90e613a"
branch_labels = None
depends_on = None


# Apply this schema revision; Alembic tracks the revision order.
def upgrade() -> None:
    op.create_table(
        "booking_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id", sa.Integer(), sa.ForeignKey("resources.id"), nullable=False
        ),
        sa.Column("time_ranges", postgresql.TSTZMULTIRANGE(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.UniqueConstraint(
            "booking_id", "resource_id", name="uq_booking_equipment_unit"
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'completed')",
            name="ck_booking_equipment_status",
        ),
        sa.CheckConstraint(
            "NOT isempty(time_ranges) AND NOT lower_inf(time_ranges) AND NOT upper_inf(time_ranges)",
            name="ck_booking_equipment_ranges",
        ),
        postgresql.ExcludeConstraint(
            ("resource_id", "="),
            ("time_ranges", "&&"),
            where=sa.text("status = 'confirmed'"),
            using="gist",
            name="booking_equipment_no_overlap",
        ),
    )


# Reverse this revision; dropping schema objects may discard their stored data.
def downgrade() -> None:
    op.drop_table("booking_equipment")
