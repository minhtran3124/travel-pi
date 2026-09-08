"""Alembic round-trip coverage for the bookings.trip_id migration."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
TABLE = "bookings"
COLUMN = "trip_id"
INDEX = "ix_bookings_trip_id"
REVISION = "b8e4c1f7a305"
DOWN_REVISION = "a7c3e9f1b2d4"


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'bookings_trip_id_migration.db'}", (lambda: None)

    schema = f"test_bookings_trip_id_{uuid4().hex}"
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


def test_bookings_trip_id_migration_round_trip(tmp_db, tmp_path, monkeypatch):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(API_ROOT / "alembic.ini"))
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, DOWN_REVISION)
        inspector = inspect(engine)
        assert inspector.has_table(TABLE) is True
        assert COLUMN not in {col["name"] for col in inspector.get_columns(TABLE)}
        assert INDEX not in {ix["name"] for ix in inspector.get_indexes(TABLE)}

        command.upgrade(config, REVISION)
        inspector = inspect(engine)
        assert COLUMN in {col["name"] for col in inspector.get_columns(TABLE)}
        assert INDEX in {ix["name"] for ix in inspector.get_indexes(TABLE)}

        command.downgrade(config, DOWN_REVISION)
        inspector = inspect(engine)
        assert COLUMN not in {col["name"] for col in inspector.get_columns(TABLE)}
        assert INDEX not in {ix["name"] for ix in inspector.get_indexes(TABLE)}

        command.upgrade(config, REVISION)
        inspector = inspect(engine)
        assert COLUMN in {col["name"] for col in inspector.get_columns(TABLE)}
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()
