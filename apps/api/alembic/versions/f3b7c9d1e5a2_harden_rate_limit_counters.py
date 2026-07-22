"""harden rate_limit_counters policy identity and pruning

Revision ID: f3b7c9d1e5a2
Revises: e1a2b3c4d5f6
Create Date: 2026-07-22 12:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3b7c9d1e5a2"
down_revision: str | Sequence[str] | None = "e1a2b3c4d5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Version policy windows, make epochs 64-bit, and index row expiry."""
    with op.batch_alter_table("rate_limit_counters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("window_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prune_after", sa.BigInteger(), nullable=True))

    # The old schema did not retain enough information to infer its policy
    # window. Keep those counters isolated under identity 0 and immediately
    # prune-eligible; a positive-window policy can never reuse them.
    op.execute(
        sa.text(
            "UPDATE rate_limit_counters "
            "SET window_seconds = 0, prune_after = window_start"
        )
    )

    with op.batch_alter_table("rate_limit_counters", schema=None) as batch_op:
        batch_op.drop_index("ix_rate_limit_counters_window_start")
        batch_op.drop_constraint("uq_rate_limit_window", type_="unique")
        batch_op.alter_column(
            "window_start",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "window_seconds",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "prune_after",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_rate_limit_window",
            ["bucket", "subject", "window_seconds", "window_start"],
        )
        batch_op.create_index(
            "ix_rate_limit_counters_bucket_prune_after",
            ["bucket", "prune_after"],
            unique=False,
        )


def downgrade() -> None:
    """Restore the e1 schema, dropping transient counters before identity collapse.

    Multiple hardened rows may map to one legacy identity, and 64-bit epochs may
    not fit its Integer column. Rate-limit counters are transient operational
    data, so downgrade clears them before rebuilding the exact e1 table shape.
    """
    op.execute(sa.text("DELETE FROM rate_limit_counters"))
    with op.batch_alter_table("rate_limit_counters", schema=None) as batch_op:
        batch_op.drop_index("ix_rate_limit_counters_bucket_prune_after")
        batch_op.drop_constraint("uq_rate_limit_window", type_="unique")
        batch_op.alter_column(
            "window_start",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.drop_column("prune_after")
        batch_op.drop_column("window_seconds")
        batch_op.create_unique_constraint(
            "uq_rate_limit_window",
            ["bucket", "subject", "window_start"],
        )
        batch_op.create_index(
            "ix_rate_limit_counters_window_start",
            ["window_start"],
            unique=False,
        )
