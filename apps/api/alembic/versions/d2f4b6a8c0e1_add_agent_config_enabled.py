"""add agent_config enabled

Revision ID: d2f4b6a8c0e1
Revises: c7e9a2b5f4d1
Create Date: 2026-07-04 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f4b6a8c0e1"
down_revision: str | Sequence[str] | None = "c7e9a2b5f4d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.drop_column("enabled")
