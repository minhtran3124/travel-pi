"""add trips.user_id (#118) — trips get an owner

Revision ID: a4d8e2c6b013
Revises: f3b7c9d1e5a2
Create Date: 2026-07-27 10:00:00.000000

DESTRUCTIVE. Before this revision no trip had an owner, so every existing row is
ownerless by definition and there is nothing to backfill from — the dev database
had 0 conversations pinned to a trip across 35 users, which was the only link
that could have supplied one. Per the decision recorded in
``specs/gh-118-trip-ownership/SUMMARY.md`` the rows are deleted rather than left
under a permanently-nullable column, which is what lets ``user_id`` be NOT NULL
in a single revision.

Deletes, in dependency order: ``expenses`` → ``trip_items`` → ``trips``, and
clears ``conversations.trip_id`` so no conversation points at a deleted trip.
``bookings`` and ``saved_places`` carry no ``trip_id`` and are untouched.

``downgrade()`` restores the schema, NOT the data. Take a backup before running
this anywhere the rows matter.
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d8e2c6b013"
down_revision: str | Sequence[str] | None = "f3b7c9d1e5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Drop every ownerless trip, then add the NOT NULL owner column."""
    bind = op.get_bind()

    # Report before destroying: a migration that silently empties three tables
    # is not something an operator should have to diff the database to notice.
    counts = {
        table: bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        for table in ("trips", "trip_items", "expenses")
    }
    logger.warning(
        "gh-118: deleting all ownerless trip data — trips=%s trip_items=%s expenses=%s",
        counts["trips"],
        counts["trip_items"],
        counts["expenses"],
    )

    # Children first: both reference a trip that is about to disappear.
    op.execute(sa.text("DELETE FROM expenses"))
    op.execute(sa.text("DELETE FROM trip_items"))
    op.execute(sa.text("DELETE FROM trip_place_link"))
    op.execute(sa.text("DELETE FROM trips"))
    # A conversation pinned to a deleted trip would resume into a dangling id.
    op.execute(sa.text("UPDATE conversations SET trip_id = NULL"))

    # The table is empty now, so NOT NULL needs no server_default and no second
    # pass — the whole reason the rows were deleted first.
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(), nullable=False))
        batch_op.create_index("ix_trips_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    """Restore the schema. The deleted trips, items and expenses are NOT restored."""
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_index("ix_trips_user_id")
        batch_op.drop_column("user_id")
