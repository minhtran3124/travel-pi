"""add rate_limit_counters

Revision ID: e1a2b3c4d5f6
Revises: d2f4b6a8c0e1
Create Date: 2026-07-21 17:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a2b3c4d5f6"
down_revision: str | Sequence[str] | None = "d2f4b6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rate_limit_counters",
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket", "subject", "window_start", name="uq_rate_limit_window"
        ),
    )
    with op.batch_alter_table("rate_limit_counters", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_rate_limit_counters_window_start"),
            ["window_start"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("rate_limit_counters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rate_limit_counters_window_start"))

    op.drop_table("rate_limit_counters")
