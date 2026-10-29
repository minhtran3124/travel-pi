"""add bot_heartbeats

Revision ID: c5a8e1d3f7b9
Revises: a7c1e9d3b5f2
Create Date: 2026-10-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5a8e1d3f7b9"
down_revision: str | Sequence[str] | None = "a7c1e9d3b5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create bot_heartbeats: one row per (instance, process) with a JSON snapshot."""
    op.create_table(
        "bot_heartbeats",
        sa.Column("instance_id", sa.String(), nullable=False),
        sa.Column("pid", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("last_seen", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("instance_id", "pid"),
    )
    op.create_index(
        "ix_bot_heartbeats_last_seen", "bot_heartbeats", ["last_seen"], unique=False
    )


def downgrade() -> None:
    """Drop bot_heartbeats."""
    op.drop_index("ix_bot_heartbeats_last_seen", table_name="bot_heartbeats")
    op.drop_table("bot_heartbeats")
