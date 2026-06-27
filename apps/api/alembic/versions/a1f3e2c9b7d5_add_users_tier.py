"""add users table with tier column

Revision ID: a1f3e2c9b7d5
Revises: b68656f68e88
Create Date: 2026-06-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f3e2c9b7d5"
down_revision: str | Sequence[str] | None = "b68656f68e88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the users table (user_id PK string, tier, timestamps)."""
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False, server_default="free"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Drop the users table."""
    op.drop_table("users")
