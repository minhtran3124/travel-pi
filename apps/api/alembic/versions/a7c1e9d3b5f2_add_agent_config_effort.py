"""add agent_config effort

Revision ID: a7c1e9d3b5f2
Revises: d4f7a2c9e1b3
Create Date: 2026-10-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c1e9d3b5f2"
down_revision: str | Sequence[str] | None = "d4f7a2c9e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("effort", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.drop_column("effort")
