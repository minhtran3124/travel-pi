"""Alembic round-trip coverage for the rate-limit counter migration."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import BigInteger, create_engine, inspect, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REVISION = "f3b7c9d1e5a2"
LEGACY_REVISION = "e1a2b3c4d5f6"


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'rate_limit_migration.db'}", lambda: None

    schema = f"test_rate_limit_migration_{uuid4().hex}"
    admin_engine = create_engine(tmp_db, future=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    # Keep libpq ``options`` raw: render_as_string() percent-encodes ``=``/``,``, which Alembic's ConfigParser reads as ``%`` interpolation and fails.
    separator = "&" if "?" in tmp_db else "?"
    # Isolated schema only: including ``public`` would let inspector lookups see already-migrated shared tables (false positive).
    isolated = f"{tmp_db}{separator}options=-csearch_path={schema}"

    def cleanup() -> None:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()

    return isolated, cleanup


def _alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def _assert_hardened_schema(engine) -> None:
    inspector = inspect(engine)
    assert inspector.has_table("rate_limit_counters") is True

    columns = {
        column["name"]: column
        for column in inspector.get_columns("rate_limit_counters")
    }
    assert {
        "bucket",
        "subject",
        "window_seconds",
        "window_start",
        "prune_after",
        "count",
        "id",
        "created_at",
        "updated_at",
    } == set(columns)
    assert isinstance(columns["window_start"]["type"], BigInteger)
    assert isinstance(columns["prune_after"]["type"], BigInteger)
    assert columns["window_seconds"]["nullable"] is False
    assert columns["prune_after"]["nullable"] is False

    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("rate_limit_counters")
    }
    assert unique_constraints["uq_rate_limit_window"] == (
        "bucket",
        "subject",
        "window_seconds",
        "window_start",
    )
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("rate_limit_counters")
        if not index.get("duplicates_constraint")
    }
    assert indexes == {
        "ix_rate_limit_counters_bucket_prune_after": ("bucket", "prune_after")
    }


def _assert_legacy_schema(engine) -> None:
    inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("rate_limit_counters")
    }
    assert "window_seconds" not in columns
    assert "prune_after" not in columns
    assert not isinstance(columns["window_start"]["type"], BigInteger)
    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("rate_limit_counters")
    }
    assert unique_constraints["uq_rate_limit_window"] == (
        "bucket",
        "subject",
        "window_start",
    )
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("rate_limit_counters")
        if not index.get("duplicates_constraint")
    }
    assert indexes == {"ix_rate_limit_counters_window_start": ("window_start",)}


def test_rate_limit_migration_upgrade_downgrade_round_trip(
    tmp_db, tmp_path, monkeypatch
):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, LEGACY_REVISION)
        _assert_legacy_schema(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO rate_limit_counters "
                    "(bucket, subject, window_start, count, id, created_at, updated_at) "
                    "VALUES (:bucket, :subject, :window_start, :count, :id, :ts, :ts)"
                ),
                {
                    "bucket": "feedback",
                    "subject": "legacy-user",
                    "window_start": 100,
                    "count": 2,
                    "id": "legacy-counter",
                    "ts": "2026-07-22T00:00:00+00:00",
                },
            )

        command.upgrade(config, REVISION)
        _assert_hardened_schema(engine)
        with engine.connect() as connection:
            legacy = connection.execute(
                text(
                    "SELECT window_seconds, window_start, prune_after, count "
                    "FROM rate_limit_counters WHERE id = :id"
                ),
                {"id": "legacy-counter"},
            ).one()
        assert legacy == (0, 100, 100, 2)

        command.downgrade(config, LEGACY_REVISION)
        _assert_legacy_schema(engine)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM rate_limit_counters")
                ).scalar_one()
                == 0
            )

        command.upgrade(config, REVISION)
        _assert_hardened_schema(engine)
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()
