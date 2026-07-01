"""add agent_config

Revision ID: b4d8f1a3c6e2
Revises: a1f3e2c9b7d5
Create Date: 2026-07-01 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d8f1a3c6e2"
down_revision: str | Sequence[str] | None = "a1f3e2c9b7d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_config",
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.create_index("ix_agent_config_agent_name", ["agent_name"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_config_agent_name")

    op.drop_table("agent_config")
