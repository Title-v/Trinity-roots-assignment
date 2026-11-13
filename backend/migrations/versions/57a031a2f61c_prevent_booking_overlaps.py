"""Prevent overlapping confirmed bookings for the same resource."""

from alembic import op

revision = "57a031a2f61c"
down_revision = "9e41b7d23ca0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
        ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        ) WHERE (status = 'confirmed')
    """)


def downgrade() -> None:
    op.drop_constraint("bookings_no_overlap", "bookings")
