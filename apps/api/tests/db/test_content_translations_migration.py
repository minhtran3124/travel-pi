"""Alembic round-trip coverage for the content_translations migration."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
TABLE = "content_translations"
REVISION = "a7c3e9f1b2d4"
DOWN_REVISION = "f3b7c9d1e5a2"


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'content_translations_migration.db'}", (
            lambda: None
        )

    schema = f"test_content_translations_{uuid4().hex}"
    admin_engine = create_engine(tmp_db, future=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    separator = "&" if "?" in tmp_db else "?"
    isolated = f"{tmp_db}{separator}options=-csearch_path={schema}"

    def cleanup() -> None:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()

    return isolated, cleanup


def test_content_translations_migration_round_trip(tmp_db, tmp_path, monkeypatch):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(API_ROOT / "alembic.ini"))
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table(TABLE) is False

        command.upgrade(config, REVISION)
        inspector = inspect(engine)
        assert inspector.has_table(TABLE) is True
        assert "ix_content_translations_type_language" in {
            ix["name"] for ix in inspector.get_indexes(TABLE)
        }
        unique_cols = [
            tuple(uc["column_names"]) for uc in inspector.get_unique_constraints(TABLE)
        ]
        assert ("entity_type", "entity_id", "field", "language") in unique_cols

        command.downgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table(TABLE) is False

        command.upgrade(config, REVISION)
        assert inspect(engine).has_table(TABLE) is True
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()
