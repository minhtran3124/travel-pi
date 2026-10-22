"""add agent_runs — per-turn token/cost/latency metrics record

Revision ID: e3b7c5d9a1f4
Revises: c7f1a9d4e6b2
Create Date: 2026-09-03 10:00:00.000000

Additive. Creates the ``agent_runs`` table (specs/agent-turn-metrics) with indexes
on ``user_id``, ``conversation_id`` and ``status``. No data movement; ``downgrade``
drops the indexes and the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b7c5d9a1f4"
down_revision: str | Sequence[str] | None = "c7f1a9d4e6b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the agent_runs table and its three indexes."""
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("trip_id", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_flow", sa.String(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=True),
        sa.Column("finished_at", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("llm_errors", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("by_model", sa.JSON(), nullable=True),
        sa.Column("by_node", sa.JSON(), nullable=True),
        sa.Column("background_llm_calls", sa.Integer(), nullable=False),
        sa.Column("background_tokens", sa.Integer(), nullable=False),
        sa.Column("background_ms", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"], unique=False)
    op.create_index(
        "ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"], unique=False
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"], unique=False)


def downgrade() -> None:
    """Drop the agent_runs indexes and table."""
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_conversation_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
    op.drop_table("agent_runs")
