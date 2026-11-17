"""Store all selected time ranges in one booking."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b742c90e613a"
down_revision = "57a031a2f61c"
branch_labels = None
depends_on = None


# Apply this schema revision; Alembic tracks the revision order.
def upgrade() -> None:
    op.add_column(
        "bookings", sa.Column("time_ranges", postgresql.TSTZMULTIRANGE(), nullable=True)
    )
    op.execute("""
        UPDATE bookings
        SET time_ranges = tstzmultirange(tstzrange(starts_at, ends_at, '[)'))
    """)
    op.alter_column("bookings", "time_ranges", nullable=False)
    op.create_check_constraint(
        "ck_bookings_range_bounds",
        "bookings",
        "NOT isempty(time_ranges) AND NOT lower_inf(time_ranges) "
        "AND NOT upper_inf(time_ranges) AND lower(time_ranges) = starts_at "
        "AND upper(time_ranges) = ends_at",
    )
    op.drop_constraint("bookings_no_overlap", "bookings")
    op.execute("""
        ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            time_ranges WITH &&
        ) WHERE (status = 'confirmed')
    """)


# Reverse this revision; dropping schema objects may discard their stored data.
def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM bookings
                WHERE time_ranges <> tstzmultirange(tstzrange(starts_at, ends_at, '[)'))
            ) THEN
                RAISE EXCEPTION 'Split bookings with separated time ranges before downgrading';
            END IF;
        END $$
    """)
    op.drop_constraint("bookings_no_overlap", "bookings")
    op.execute("""
        ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        ) WHERE (status = 'confirmed')
    """)
    op.drop_constraint("ck_bookings_range_bounds", "bookings")
    op.drop_column("bookings", "time_ranges")
