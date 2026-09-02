"""add bookings.user_id and saved_places.user_id — bookings and saved places get an owner

Revision ID: c7f1a9d4e6b2
Revises: a4d8e2c6b013
Create Date: 2026-09-02 10:00:00.000000

DESTRUCTIVE. Before this revision neither ``bookings`` nor ``saved_places`` had an
owner, so every existing row is ownerless by definition and there is nothing to
backfill from — nothing links these rows to a user. Following the decision that
shipped ``a4d8e2c6b013`` (#118) the rows are deleted rather than left under a
permanently-nullable column, which is what lets ``user_id`` be NOT NULL in a
single revision.

Deletes every row in ``bookings`` and ``saved_places`` (neither is referenced by
another table), then adds ``user_id`` NOT NULL with an index on each.

``downgrade()`` restores the schema, NOT the data. Take a backup before running
this anywhere the rows matter.
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7f1a9d4e6b2"
down_revision: str | Sequence[str] | None = "a4d8e2c6b013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Drop every ownerless booking and saved place, then add the NOT NULL owner column."""
    bind = op.get_bind()

    # Report before destroying: a migration that silently empties two tables is
    # not something an operator should have to diff the database to notice.
    counts = {
        table: bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        for table in ("bookings", "saved_places")
    }
    logger.warning(
        "review-a: deleting all ownerless booking and saved-place data — "
        "bookings=%s saved_places=%s",
        counts["bookings"],
        counts["saved_places"],
    )

    op.execute(sa.text("DELETE FROM bookings"))
    op.execute(sa.text("DELETE FROM saved_places"))

    # The tables are empty now, so NOT NULL needs no server_default and no second
    # pass — the whole reason the rows were deleted first.
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(), nullable=False))
        batch_op.create_index("ix_bookings_user_id", ["user_id"], unique=False)

    with op.batch_alter_table("saved_places", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(), nullable=False))
        batch_op.create_index("ix_saved_places_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    """Restore the schema. The deleted bookings and saved places are NOT restored."""
    with op.batch_alter_table("saved_places", schema=None) as batch_op:
        batch_op.drop_index("ix_saved_places_user_id")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index("ix_bookings_user_id")
        batch_op.drop_column("user_id")
