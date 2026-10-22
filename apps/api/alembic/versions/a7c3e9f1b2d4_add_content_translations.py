"""add content_translations — language-keyed catalog text

Revision ID: a7c3e9f1b2d4
Revises: b2d9f4a7c1e8
Create Date: 2026-09-05 06:30:00.000000

Additive. Creates the ``content_translations`` table (specs/catalog-content-i18n)
with a unique key on (entity_type, entity_id, field, language) and an index on
(entity_type, language). No data movement; ``downgrade`` drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9f1b2d4"
down_revision: str | Sequence[str] | None = "b2d9f4a7c1e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the content_translations table, its unique key and index."""
    op.create_table(
        "content_translations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "field",
            "language",
            name="uq_content_translations_key",
        ),
    )
    op.create_index(
        "ix_content_translations_type_language",
        "content_translations",
        ["entity_type", "language"],
    )


def downgrade() -> None:
    """Drop the index and the table."""
    op.drop_index(
        "ix_content_translations_type_language", table_name="content_translations"
    )
    op.drop_table("content_translations")
