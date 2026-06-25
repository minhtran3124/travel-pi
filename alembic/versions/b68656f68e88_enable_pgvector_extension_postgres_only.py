"""enable pgvector extension (postgres only)

Revision ID: b68656f68e88
Revises: 0ab2cdadfc16
Create Date: 2026-06-25 23:31:30.050888

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b68656f68e88"
down_revision: str | Sequence[str] | None = "0ab2cdadfc16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable the pgvector extension so RAG tables can use the vector type.

    Postgres-only: SQLite (local/test) uses the in-memory vector store and has no
    such extension, so this is a no-op there. The langchain-postgres PGVector
    store creates its own collection/embedding tables on first use; this only
    guarantees the ``vector`` type exists.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """No-op: dropping the extension could break other consumers."""
    pass
