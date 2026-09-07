"""add agent_run_steps — per-step call chain for an agent turn

Revision ID: b2d9f4a7c1e8
Revises: e3b7c5d9a1f4
Create Date: 2026-09-03 12:00:00.000000

Additive. Creates the ``agent_run_steps`` table (specs/agent-run-trace-detail) with
an index on ``run_id``, and adds the nullable ``agent_runs.prompt_versions`` JSON
column. No data movement; ``downgrade`` drops the column, the index and the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d9f4a7c1e8"
down_revision: str | Sequence[str] | None = "e3b7c5d9a1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent_run_steps + its run_id index and add agent_runs.prompt_versions."""
    op.create_table(
        "agent_run_steps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("node", sa.String(), nullable=True),
        sa.Column("ns", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompts", sa.JSON(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("offset_ms", sa.Integer(), nullable=False),
        sa.Column("ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"], unique=False
    )
    op.add_column("agent_runs", sa.Column("prompt_versions", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop agent_runs.prompt_versions, the index and the agent_run_steps table."""
    op.drop_column("agent_runs", "prompt_versions")
    op.drop_index("ix_agent_run_steps_run_id", table_name="agent_run_steps")
    op.drop_table("agent_run_steps")
