"""add bookings.trip_id — link a booking back to the trip it was made from

Revision ID: b8e4c1f7a305
Revises: a7c3e9f1b2d4
Create Date: 2026-09-08 00:00:00.000000

Additive. Adds a nullable, indexed ``trip_id`` column to ``bookings``,
matching ``trip_items.trip_id`` (plain String, no foreign key). No data
movement; ``downgrade`` drops the index and the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e4c1f7a305"
down_revision: str | Sequence[str] | None = "a7c3e9f1b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the trip_id column and its index to bookings."""
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.add_column(sa.Column("trip_id", sa.String(), nullable=True))
        batch_op.create_index("ix_bookings_trip_id", ["trip_id"], unique=False)


def downgrade() -> None:
    """Drop the trip_id index and column from bookings."""
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.drop_index("ix_bookings_trip_id")
        batch_op.drop_column("trip_id")
