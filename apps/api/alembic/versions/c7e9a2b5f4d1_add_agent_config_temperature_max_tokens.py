"""add agent_config temperature + max_tokens

Revision ID: c7e9a2b5f4d1
Revises: b4d8f1a3c6e2
Create Date: 2026-07-02 15:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e9a2b5f4d1"
down_revision: str | Sequence[str] | None = "b4d8f1a3c6e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("temperature", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.drop_column("max_tokens")
        batch_op.drop_column("temperature")
