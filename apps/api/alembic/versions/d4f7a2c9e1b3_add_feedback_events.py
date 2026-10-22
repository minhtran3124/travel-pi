"""add feedback_events + messages.agent_run_id — per-message thumbs feedback

Revision ID: d4f7a2c9e1b3
Revises: b8e4c1f7a305
Create Date: 2026-09-12 00:00:00.000000

Additive (specs/user-feedback-v1 §11). Adds a nullable, indexed ``agent_run_id``
to ``messages`` (plain String, no foreign key — links an assistant reply to the
``agent_runs`` row that produced it) and creates the append-only
``feedback_events`` table with its unique key, rating CHECK and indexes.
``agent_runs`` / ``agent_run_steps`` are not touched. No data movement;
``downgrade`` drops ``feedback_events`` first, then the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7a2c9e1b3"
down_revision: str | Sequence[str] | None = "b8e4c1f7a305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add messages.agent_run_id, then create feedback_events."""
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("agent_run_id", sa.String(), nullable=True))
        batch_op.create_index(
            "ix_messages_agent_run_id", ["agent_run_id"], unique=False
        )

    op.create_table(
        "feedback_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("assistant_message_id", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(), nullable=True),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=True),
        sa.Column("client_event_id", sa.String(), nullable=False),
        sa.Column("request_fingerprint", sa.String(), nullable=False),
        sa.Column("supersedes_event_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "client_event_id", name="uq_feedback_events_user_client_event"
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating IN (-1, 1)", name="ck_feedback_events_rating"
        ),
    )
    with op.batch_alter_table("feedback_events") as batch_op:
        batch_op.create_index("ix_feedback_events_user_id", ["user_id"], unique=False)
        batch_op.create_index(
            "ix_feedback_events_conversation_id", ["conversation_id"], unique=False
        )
        batch_op.create_index(
            "ix_feedback_events_assistant_message_id",
            ["assistant_message_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_feedback_events_agent_run_id", ["agent_run_id"], unique=False
        )
        batch_op.create_index(
            "ix_feedback_events_assistant_message_id_created_at_id",
            ["assistant_message_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_feedback_events_user_id_created_at",
            ["user_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_feedback_events_rating_created_at",
            ["rating", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop feedback_events, then the messages.agent_run_id index and column."""
    op.drop_table("feedback_events")
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_agent_run_id")
        batch_op.drop_column("agent_run_id")
