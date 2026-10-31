"""add agent_runs.instance_id

Revision ID: d4e8a2c6f1b3
Revises: c5a8e1d3f7b9
Create Date: 2026-10-31 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8a2c6f1b3"
down_revision: str | Sequence[str] | None = "c5a8e1d3f7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable instance_id; pre-existing rows stay NULL."""
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("instance_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("instance_id")
