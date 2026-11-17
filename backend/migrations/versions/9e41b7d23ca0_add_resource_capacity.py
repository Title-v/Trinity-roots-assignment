"""Add optional seating capacity to resources."""

import sqlalchemy as sa
from alembic import op

revision = "9e41b7d23ca0"
down_revision = "62232fda171c"
branch_labels = None
depends_on = None


# Apply this schema revision; Alembic tracks the revision order.
def upgrade() -> None:
    op.add_column("resources", sa.Column("capacity", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_resources_capacity_positive", "resources", "capacity > 0"
    )


# Reverse this revision; dropping schema objects may discard their stored data.
def downgrade() -> None:
    op.drop_constraint("ck_resources_capacity_positive", "resources", type_="check")
    op.drop_column("resources", "capacity")
