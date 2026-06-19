---
slug: docker-postgres-setup
status: shipped
lane: high-risk
---

## Status Log

- 2026-06-19 — shipped via `feat/docker-postgres-setup` (PR #11)

# Docker + Postgres + SQLAlchemy ORM Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Containerize the FastAPI mock backend, move its persistence tier from raw `sqlite3` to SQLAlchemy 2.0 ORM (engine chosen by a single `database_url`), run Postgres behind Docker while keeping SQLite as the default for local/CI tests, add Alembic migrations, a compose-first Makefile, an isolated test-compose, and updated docs.

**Architecture:** ORM stays **confined to the `app/crud/` tier** — repos keep returning Pydantic models, so `app/services/`, `app/schemas/`, and `app/routers/` are untouched. A new `app/db/` package owns the `DeclarativeBase`, ORM models, and a URL-keyed engine/session-factory cache. The DB tier stays **sync** (FastAPI threadpool design preserved — no async/asyncpg). The engine is selected purely by `settings.database_url`: `sqlite:///travel.db` by default, `postgresql+psycopg://…` injected in Docker. Test isolation is preserved because each distinct URL (the per-session temp SQLite path) gets its own cached engine.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, **SQLAlchemy 2.0 (sync)**, **psycopg 3** (`postgresql+psycopg`), **Alembic**, Postgres 17 (Docker), SQLite (stdlib, local/test), Docker + Docker Compose, Make.

**Parity gate:** The existing suite runs on SQLite and MUST stay green after every task — it is the behavioral oracle for the migration. **Baseline = 617 collected tests** (verify at execution start: `.venv/bin/python -m pytest tests/ --collect-only -q | tail -1`); this plan adds 7 (`test_db_engine.py` ×4, `test_db_models.py` ×3) → **624 total**. Run `.venv/bin/python -m pytest tests/ -q` after each phase and require the full collected count to pass — do not hardcode a number, re-baseline if collection changes.

**Decisions locked (see `ESCALATIONS.md`):** runtime-Postgres / tests-stay-SQLite · SQLAlchemy **ORM** (deliberate override of CLAUDE.md "no ORM") · **Alembic** for migrations · **portable `JSON`** for JSON columns (no JSONB) · compose-first Makefile.

---

## File Structure

**New files:**
- `app/db/__init__.py` — package marker
- `app/db/base.py` — `Base(DeclarativeBase)`
- `app/db/engine.py` — URL-keyed `get_engine(url)` / `get_session_factory(url)` (sqlite connect_args, pooling)
- `app/db/models.py` — 6 ORM models + indexes
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`
- `Dockerfile`
- `docker-compose.yml` — app + postgres
- `docker-compose.test.yml` — test runner + isolated postgres
- `docker/entrypoint.sh` — `alembic upgrade head` → uvicorn
- `Makefile`
- `scripts/start.sh`, `scripts/test-docker.sh` (thin wrappers used by Make)
- `tests/test_db_engine.py` — engine/dual-URL unit tests
- `docs/decisions/0001-orm-and-postgres.md` — `/compound` decision record

**Modified files:**
- `requirements.txt` — add sqlalchemy, psycopg[binary], alembic
- `app/core/config.py` — `database_url` (replaces `database_path`)
- `app/crud/booking.py`, `app/crud/flight.py`, `app/crud/saved_place.py`, `app/crud/trip.py` — ORM rewrite
- `app/core/lifespan.py` — engine init, sqlite `create_all`, log URL
- `app/services/booking_service.py`, `trip_service.py`, `saved_place_service.py`, `flight_service.py` — accept `database_url`, build session factory. **`trip_service.py` additionally** swaps its `import sqlite3` + `except sqlite3.IntegrityError` (line 10, 251) for `from sqlalchemy.exc import IntegrityError` — the shortlist 409 path. (This is the one service-layer line the ORM migration forces; "ORM confined to crud" holds otherwise — only the exception *type* crosses the boundary, and `sqlalchemy.exc.IntegrityError` is the engine-agnostic one.)
- `tests/conftest.py` — temp SQLite **URL**, repoint singletons to test session factory
- `.env.example` — `DATABASE_URL`
- `README.md` — Docker/local/test guide
- `CLAUDE.md` — amend "no ORM" rule; note dual-engine + Alembic

**Deleted files:**
- `app/crud/_migrations.py` — `PRAGMA`/`ALTER` legacy guards become moot (Alembic owns Postgres schema; `create_all` owns the fresh SQLite/test schema)

---

## Chunk 1: DB foundation (ORM core + config + deps)

### Task 1: Add runtime dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the three deps** under the main block (keep the pinned-upper-bound style):

```
sqlalchemy>=2.0.0,<2.1.0
psycopg[binary]>=3.1.0,<4.0.0   # psycopg 3 driver: postgresql+psycopg://
alembic>=1.13.0,<2.0.0
```

- [ ] **Step 2: Install** — Run: `uv pip install -r requirements.txt`
  Expected: SQLAlchemy, psycopg, alembic resolve and install with no conflict.

- [ ] **Step 3: Smoke import** — Run: `.venv/bin/python -c "import sqlalchemy, psycopg, alembic; print(sqlalchemy.__version__)"`
  Expected: prints a `2.0.x` version.

---

### Task 2: Config — `database_url` replaces `database_path`

**Files:**
- Modify: `app/core/config.py:62-64`
- Modify: `.env.example`

- [ ] **Step 1: Replace the storage setting.** Swap the `database_path` block for:

```python
    # Storage — SQLAlchemy connection URL. SQLite (a file) is the zero-config
    # default for local dev and the test suite; Docker injects a Postgres URL
    # (e.g. postgresql+psycopg://travel:travel@db:5432/travel). The engine is
    # selected entirely from this value — see app/db/engine.py.
    database_url: str = "sqlite:///travel.db"
```

- [ ] **Step 2: Update `.env.example`** — replace `DATABASE_PATH=travel.db` with:

```
DATABASE_URL=sqlite:///travel.db
```

- [ ] **Step 3: Verify settings load** — Run: `.venv/bin/python -c "from app.core.config import get_settings; print(get_settings().database_url)"`
  Expected: `sqlite:///travel.db`

> **Note:** `database_path` is referenced in `lifespan.py` and services/conftest; those are updated in later tasks. The suite is expected red from Task 2 until **Task 9 Step 4** (when services + conftest + the `trip_service` catch are all migrated) — that's the migration window. Do not ship mid-window.

---

### Task 3: `app/db` package — Base + engine/session factory

**Files:**
- Create: `app/db/__init__.py` (empty)
- Create: `app/db/base.py`
- Create: `app/db/engine.py`
- Test: `tests/test_db_engine.py`

- [ ] **Step 1: Write the failing test** (`tests/test_db_engine.py`):

```python
"""Engine/session-factory behavior: dual-URL selection + isolation."""

import pytest
from sqlalchemy import text
from app.db.engine import get_engine, get_session_factory


def test_sqlite_url_builds_sqlite_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine = get_engine(url)
    assert engine.dialect.name == "sqlite"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_same_url_returns_same_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    assert get_engine(url) is get_engine(url)  # cached


def test_distinct_urls_isolate(tmp_path):
    e1 = get_engine(f"sqlite:///{tmp_path / 'c.db'}")
    e2 = get_engine(f"sqlite:///{tmp_path / 'd.db'}")
    assert e1 is not e2


def test_session_factory_yields_working_session(tmp_path):
    sf = get_session_factory(f"sqlite:///{tmp_path / 'e.db'}")
    with sf() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 2: Run it, expect failure** — Run: `.venv/bin/python -m pytest tests/test_db_engine.py -q`
  Expected: FAIL (`ModuleNotFoundError: app.db.engine`).

- [ ] **Step 3: Write `app/db/base.py`:**

```python
"""SQLAlchemy declarative base — the registry every ORM model attaches to.

Importing this module has no DB side effects (no engine, no connection); it
only defines the metadata that Alembic autogenerate and create_all read.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models in app.db.models."""
```

- [ ] **Step 4: Write `app/db/engine.py`:**

```python
"""Engine + session-factory construction, keyed by connection URL.

The whole point of the DB rewrite: the backend is chosen by the URL, nothing
else. ``get_engine`` is cached per URL so all services/repos share one engine
(and one pool) per database. Tests pass a distinct temp-SQLite URL, which gets
its own cached engine — that is what keeps test data isolated from travel.db.

Sync only: the codebase runs DB work in FastAPI's threadpool (CLAUDE.md
"async only for real network I/O"). No async engine here.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _connect_args(url: str) -> dict:
    # SQLite hands a connection to whichever threadpool worker runs the
    # request; allow cross-thread use. Postgres needs no such flag.
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=None)
def get_engine(url: str) -> Engine:
    """Return a process-wide Engine for ``url`` (one per distinct URL)."""
    return create_engine(
        url,
        connect_args=_connect_args(url),
        pool_pre_ping=True,  # drop dead Postgres connections instead of erroring
        future=True,
    )


@lru_cache(maxsize=None)
def get_session_factory(url: str) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the (cached) engine for ``url``."""
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)
```

- [ ] **Step 5: Run the test, expect pass** — Run: `.venv/bin/python -m pytest tests/test_db_engine.py -q`
  Expected: 4 passed.

---

### Task 4: ORM models — all 6 tables

**Files:**
- Create: `app/db/models.py`
- Test: `tests/test_db_models.py`

> **Source of truth:** the existing `CREATE TABLE` statements in `crud/*.py`. Preserve column names, nullability, defaults, and indexes **exactly**. Timestamps/dates stay **String** (the code stores `.isoformat()` text and compares strings — converting to `DateTime` would break parity). Bool-as-int columns (`favorite`, `visited`) become `Boolean` (SQLAlchemy maps to INTEGER on SQLite, BOOLEAN on PG — round-trips Python bools, matching the current `bool()/int()` shims). JSON columns (`details`, `links`, `budget_caps`) become portable `JSON` (replaces manual `json.dumps/loads`).

- [ ] **Step 1: Write the failing test** (`tests/test_db_models.py`):

```python
from sqlalchemy import inspect
from app.db.base import Base
from app.db import models  # noqa: F401  (registers models on Base)


def test_all_tables_registered():
    assert set(Base.metadata.tables) == {
        "bookings", "trips", "trip_items", "trip_place_link",
        "saved_places", "flight_index",
    }


def test_booking_columns():
    cols = {c.name for c in Base.metadata.tables["bookings"].columns}
    assert cols == {
        "id", "type", "reference_id", "customer_name", "customer_email",
        "total_price", "currency", "status", "created_at", "details",
        "notes", "idempotency_key", "confirmation_code",
    }


def test_partial_unique_index_on_idempotency():
    idx = {i.name for i in Base.metadata.tables["bookings"].indexes}
    assert "ix_bookings_idempotency_key" in idx
```

- [ ] **Step 2: Run it, expect failure** — Run: `.venv/bin/python -m pytest tests/test_db_models.py -q`
  Expected: FAIL (`app.db.models` not found).

- [ ] **Step 3: Write `app/db/models.py`.** Full content:

```python
"""ORM models — the SQLAlchemy mapping of every persisted table.

Mirrors the legacy raw-SQL schemas in crud/*.py one-for-one. ORM lives only
in this tier; repos translate these rows to/from Pydantic models, so services
and schemas never see SQLAlchemy. Partial unique indexes (idempotency keys)
use sqlite_where + postgresql_where so the constraint exists on both engines.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BookingRow(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    reference_id: Mapped[str] = mapped_column(String, nullable=False)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    customer_email: Mapped[str] = mapped_column(String, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO text
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmation_code: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "ix_bookings_idempotency_key",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_bookings_confirmation_code", "confirmation_code"),
    )


class TripRow(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    travelers: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)
    budget_caps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index(
            "ix_trips_idempotency_key",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class TripItemRow(Base):
    __tablename__ = "trip_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trip_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    place_id: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )

    __table_args__ = (
        Index(
            "ix_trip_items_idempotency_key",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class TripPlaceLinkRow(Base):
    __tablename__ = "trip_place_link"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trip_id: Mapped[str] = mapped_column(String, nullable=False)
    place_id: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    added_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index(
            "ix_trip_place_link_unique",
            "trip_id", "place_id", "source",
            unique=True,
        ),
    )


class SavedPlaceRow(Base):
    __tablename__ = "saved_places"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    favorite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    visited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)


class FlightIndexRow(Base):
    __tablename__ = "flight_index"

    flight_id: Mapped[str] = mapped_column(String, primary_key=True)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    departure_date: Mapped[str] = mapped_column(String, nullable=False)
```

> **Caveat for `favorite`/`visited`:** use `server_default=text("false")` — Postgres rejects `DEFAULT 0` on a `BOOLEAN` column (`cannot cast type integer to boolean`), while SQLite accepts `false`. Keep models and the Alembic revision consistent (`sa.false()` is the equivalent autogenerate emits).

- [ ] **Step 4: Run the test, expect pass** — Run: `.venv/bin/python -m pytest tests/test_db_models.py -q`
  Expected: 3 passed.

---

## Chunk 2: Repo migration (one repo per task; ORM confined to crud)

> **Cross-cutting rules for every repo task in this chunk:**
> - Constructor changes from `__init__(self, db_path: str)` to `__init__(self, session_factory)`. The repo holds a `sessionmaker`; each method opens `with self._session_factory() as session:` and commits via `session.commit()` (write methods) — mirroring the old fresh-connection-per-call contract.
> - `init_db()` becomes `Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)` (get the bound engine via the documented `Session.get_bind()` — **not** `sessionmaker.kw["bind"]`, which is brittle). This is the SQLite/test path; Postgres uses Alembic (Chunk 4).
> - `_row_to_*` helpers read **attributes** off ORM rows (`row.id`) instead of dict keys (`row["id"]`), and no longer `json.loads` (the `JSON` column already returns dict/list).
> - The idempotency race handler catches **`sqlalchemy.exc.IntegrityError`** instead of `sqlite3.IntegrityError`. On catch, the failed session's `with` block has already rolled back on exception exit; re-query in a fresh session.
> - **Never touch ORM attributes after the session closes.** Convert rows to Pydantic models (or plain dicts/tuples) *inside* the `with self._sf() as s:` block. Returning detached ORM rows works only by luck with `expire_on_commit=False` — don't rely on it.
> - Return Pydantic models (or plain dicts for link rows) exactly as before — **service/schema layers must not change** (the sole exception is the `trip_service.py` IntegrityError import, Task 9).

### Task 5: BookingRepository → ORM

**Files:**
- Modify: `app/crud/booking.py` (full rewrite of the class; keep module docstring intent)

- [ ] **Step 1: Confirm coverage exists** — Run: `.venv/bin/python -m pytest tests/test_bookings.py -q`
  Expected: PASS on current SQLite code (baseline before the rewrite).

- [ ] **Step 2: Rewrite `app/crud/booking.py`.** Replace the file body with:

```python
"""Data-access layer for bookings — SQLAlchemy ORM persistence, nothing else.

Business rules live in services/booking_service.py. This tier maps BookingRow
ORM rows to/from the Booking Pydantic model and nothing more.
"""

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models import BookingRow
from app.schemas.booking import Booking, confirmation_code_for


def _row_to_booking(row: BookingRow) -> Booking:
    details = dict(row.details) if isinstance(row.details, dict) else row.details
    if isinstance(details, dict) and "kind" not in details:
        details["kind"] = row.type
    return Booking(
        id=row.id,
        type=row.type,
        reference_id=row.reference_id,
        customer_name=row.customer_name,
        customer_email=row.customer_email,
        total_price=row.total_price,
        currency=row.currency,
        status=row.status,
        created_at=row.created_at,
        details=details,
        notes=row.notes,
    )


class BookingRepository:
    """SQLAlchemy-backed store of booking rows."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def ping(self) -> bool:
        # Cheap reachability check that does NOT require the table to exist
        # (parity with the old bare "SELECT 1").
        with self._sf() as s:
            s.execute(text("SELECT 1"))
        return True

    def get(self, booking_id: str) -> Booking | None:
        with self._sf() as s:
            row = s.get(BookingRow, booking_id)
            return _row_to_booking(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> Booking | None:
        with self._sf() as s:
            row = s.scalars(
                select(BookingRow).where(BookingRow.idempotency_key == key)
            ).first()
            return _row_to_booking(row) if row is not None else None

    def get_by_confirmation_code(self, code: str) -> Booking | None:
        with self._sf() as s:
            row = s.scalars(
                select(BookingRow).where(
                    BookingRow.confirmation_code == code.strip().upper()
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def list_all(self) -> list[Booking]:
        with self._sf() as s:
            rows = s.scalars(
                select(BookingRow).order_by(BookingRow.created_at.desc())
            ).all()
            return [_row_to_booking(r) for r in rows]

    def update_status(self, booking_id: str, status: str) -> bool:
        with self._sf() as s:
            row = s.get(BookingRow, booking_id)
            if row is None:
                return False
            row.status = status
            s.commit()
            return True

    def add(self, booking: Booking, idempotency_key: str | None = None) -> Booking:
        row = BookingRow(
            id=booking.id,
            type=booking.type.value,
            reference_id=booking.reference_id,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            total_price=booking.total_price,
            currency=booking.currency,
            status=booking.status.value,
            created_at=booking.created_at.isoformat(),
            details=booking.details.model_dump(mode="json"),
            notes=booking.notes,
            idempotency_key=idempotency_key,
            confirmation_code=booking.confirmation_code,
        )
        try:
            with self._sf() as s:
                s.add(row)
                s.commit()
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return booking
```

> Note: the legacy `init_db` confirmation_code **backfill** is dropped — it only mattered for SQLite files predating that column. Fresh ORM tables always have it. (If preserving backfill for an existing `travel.db` is required, raise it at review — Alembic data migration would be the home for it, not `init_db`.)

- [ ] **Step 3: Defer running** — booking_service still passes a `db_path` string; it is fixed in Task 9. Do not run `test_bookings.py` until conftest + services are migrated (Task 8–9). Proceed to Task 6.

---

### Task 6: FlightIndexRepository → ORM (portable insert-ignore)

**Files:**
- Modify: `app/crud/flight.py`

- [ ] **Step 1: Rewrite the class.** `INSERT OR IGNORE` is SQLite-only; use a **portable pre-filter** (select existing PKs in the batch, insert only the missing). Full body:

```python
"""Data-access layer for the flight lookup index — SQLAlchemy ORM only."""

from sqlalchemy import select

from app.db.base import Base
from app.db.models import FlightIndexRow


class FlightIndexRepository:
    """ORM-backed map of flight ID -> the search params that generated it."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def remember_many(self, rows: list[tuple[str, str, str, str]]) -> None:
        """Idempotently record (flight_id, origin, destination, departure_date).

        Portable insert-or-ignore: skip IDs already present, insert the rest.
        """
        if not rows:
            return
        ids = [r[0] for r in rows]
        with self._sf() as s:
            existing = set(
                s.scalars(
                    select(FlightIndexRow.flight_id).where(
                        FlightIndexRow.flight_id.in_(ids)
                    )
                ).all()
            )
            new_rows = [
                FlightIndexRow(
                    flight_id=fid, origin=o, destination=d, departure_date=dep
                )
                for (fid, o, d, dep) in rows
                if fid not in existing
            ]
            if new_rows:
                s.add_all(new_rows)
                s.commit()

    def lookup(self, flight_id: str) -> tuple[str, str, str] | None:
        with self._sf() as s:
            row = s.get(FlightIndexRow, flight_id)
            if row is None:
                return None
            return (row.origin, row.destination, row.departure_date)
```

> **Concurrency note:** the pre-filter has a tiny TOCTOU window two workers could both insert the same new ID. The PK makes the loser raise `IntegrityError`. If `test_flights.py` exercises concurrent identical lookups, wrap the `add_all`/`commit` in a `try/except IntegrityError: s.rollback()` (the row is already there — safe to ignore). Add this guard only if a test surfaces it.

- [ ] **Step 2: Defer running** until conftest/services migrated. Proceed to Task 7.

---

### Task 7: SavedPlaceRepository → ORM

**Files:**
- Modify: `app/crud/saved_place.py`

- [ ] **Step 1: Rewrite the class.** Preserve: short-code Python scan, `LOWER()` filters (→ `func.lower`), bool flags (now native `Boolean`), `links` JSON (now native), soft-delete filter, dup detection. Full body:

```python
"""Data-access layer for saved places — SQLAlchemy ORM persistence only."""

from sqlalchemy import func, select

from app.core.geo import haversine_km
from app.db.base import Base
from app.db.models import SavedPlaceRow
from app.schemas.saved_place import SavedPlace

_SET_FLAG_FIELDS = {"favorite", "visited"}


def _row_to_saved_place(row: SavedPlaceRow) -> SavedPlace:
    return SavedPlace(
        id=row.id,
        name=row.name,
        city=row.city,
        country=row.country,
        category=row.category,
        address=row.address,
        latitude=row.latitude,
        longitude=row.longitude,
        price_level=row.price_level,
        notes=row.notes,
        favorite=bool(row.favorite),
        visited=bool(row.visited),
        links=row.links,
        duration=row.duration,
        created_at=row.created_at,
    )


class SavedPlaceRepository:
    """ORM-backed store of saved_places rows."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def add(self, sp: SavedPlace) -> SavedPlace:
        row = SavedPlaceRow(
            id=sp.id, name=sp.name, city=sp.city, country=sp.country,
            category=sp.category, address=sp.address, latitude=sp.latitude,
            longitude=sp.longitude, price_level=sp.price_level, notes=sp.notes,
            favorite=bool(sp.favorite), visited=bool(sp.visited),
            links=sp.links, duration=sp.duration, created_at=sp.created_at,
        )
        with self._sf() as s:
            s.add(row)
            s.commit()
        return sp

    def get(self, id_: str) -> SavedPlace | None:
        with self._sf() as s:
            row = s.scalars(
                select(SavedPlaceRow).where(
                    SavedPlaceRow.id == id_, SavedPlaceRow.deleted_at.is_(None)
                )
            ).first()
            if row is not None:
                return _row_to_saved_place(row)
            rows = s.scalars(
                select(SavedPlaceRow).where(SavedPlaceRow.deleted_at.is_(None))
            ).all()
            wanted = id_.upper()
            for r in rows:
                sp = _row_to_saved_place(r)
                if sp.short_code.upper() == wanted:
                    return sp
        return None

    def list(
        self, *, city=None, category=None, favorite=None, visited=None
    ) -> list[SavedPlace]:
        stmt = select(SavedPlaceRow).where(SavedPlaceRow.deleted_at.is_(None))
        if city is not None:
            stmt = stmt.where(func.lower(SavedPlaceRow.city) == func.lower(city))
        if category is not None:
            stmt = stmt.where(
                func.lower(SavedPlaceRow.category) == func.lower(category)
            )
        if favorite is not None:
            stmt = stmt.where(SavedPlaceRow.favorite == bool(favorite))
        if visited is not None:
            stmt = stmt.where(SavedPlaceRow.visited == bool(visited))
        stmt = stmt.order_by(
            SavedPlaceRow.created_at.desc(), SavedPlaceRow.id.desc()
        )
        with self._sf() as s:
            return [_row_to_saved_place(r) for r in s.scalars(stmt).all()]

    def soft_delete(self, id_: str, *, when: str) -> bool:
        with self._sf() as s:
            row = s.scalars(
                select(SavedPlaceRow).where(
                    SavedPlaceRow.id == id_, SavedPlaceRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return False
            row.deleted_at = when
            s.commit()
            return True

    def set_flag(self, id_: str, field: str, value: bool) -> bool:
        if field not in _SET_FLAG_FIELDS:
            raise ValueError(f"Unsupported flag field: {field!r}")
        with self._sf() as s:
            row = s.scalars(
                select(SavedPlaceRow).where(
                    SavedPlaceRow.id == id_, SavedPlaceRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return False
            setattr(row, field, bool(value))
            s.commit()
            return True

    def find_duplicate(
        self, *, name, city, lat, lng, radius_km
    ) -> SavedPlace | None:
        with self._sf() as s:
            # Materialize to Pydantic INSIDE the session — never iterate ORM
            # rows after the block closes (detached-instance hazard).
            cands = [
                _row_to_saved_place(r)
                for r in s.scalars(
                    select(SavedPlaceRow).where(
                        SavedPlaceRow.deleted_at.is_(None),
                        func.lower(SavedPlaceRow.name) == func.lower(name),
                    )
                ).all()
            ]
        for cand in cands:
            both = (
                lat is not None and lng is not None
                and cand.latitude is not None and cand.longitude is not None
            )
            if both:
                if haversine_km(lat, lng, cand.latitude, cand.longitude) <= radius_km:
                    return cand
            elif cand.city == city:
                return cand
        return None
```

- [ ] **Step 2: Defer running.** Proceed to Task 8.

---

### Task 8: TripRepository → ORM + conftest migration (suite goes green)

**Files:**
- Modify: `app/crud/trip.py`
- Modify: `tests/conftest.py`

> This task migrates the last + most complex repo (3 tables, a transactional create) **and** flips conftest to URLs, so the suite can run green again. `list_trip_places`/`get_trip_place` returned raw `sqlite3.Row`; the service reads them by key (`row["place_id"]`, `row["source"]`, `row["id"]` at `trip_service.py:265,269`). To keep the service untouched **and** not leak ORM rows past the session, these two repo methods return **plain dicts** (`dict` supports `row["col"]` exactly like `sqlite3.Row`).

- [ ] **Step 1: Confirm the link-row call sites** — Run: `grep -n "list_trip_places\|get_trip_place\|row\[" app/services/trip_service.py app/routers/trips.py`
  Expected: only `list_trip_places` (trip_service.py:264-269) reads link rows, all by key (`["place_id"]`, `["source"]`, `["id"]`). `get_trip_place` has **no by-key caller**; `delete_trip_place` returns bool. → returning dicts means **zero service changes** for link rows.

- [ ] **Step 2: Rewrite `app/crud/trip.py`** following the same pattern as Tasks 5–7. Enumerate and port **every** method (≈16) — do not skip any:
  - **Helpers:** `_row_to_item(row)` / `_row_to_trip(row, item_rows)` read attributes; keep `sorted(..., key=lambda i: (i.day, i.sort_order))`. Drop `_iso` only if the schema already yields ISO strings; otherwise keep it for `start_date`/`end_date`/`created_at`.
  - `init_db()` → `Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)`.
  - `create_trip` (transactional): one session, `s.add(trip_row)`, `s.add_all(item_rows)`, single `s.commit()`; `try/except IntegrityError` → `get_trip_by_idempotency_key` replay (the `with` block already rolled back on the exception).
  - `get_trip` / `list_trips`: filter `TripRow.deleted_at.is_(None)`; build Pydantic **inside** the session; preserve newest-first ordering and the items-by-trip grouping.
  - `update_trip` (bool): `s.get` live row → set the 6 columns → commit → `return True`; `return False` if missing. Preserves the old `rowcount > 0` contract.
  - `get_budget_caps` → `return row.budget_caps or {}` (native JSON, no `json.loads`); `set_budget_caps` assigns the dict directly (no `json.dumps`), guarded `deleted_at IS NULL`.
  - `delete_trip` (bool): set `deleted_at` + `idempotency_key = None`, guarded by `deleted_at IS NULL` on a live row.
  - `add_item` (returns item): `try/except IntegrityError` → `get_item_by_idempotency_key` replay.
  - `get_item` / `get_item_by_idempotency_key` / `get_trip_by_idempotency_key`: build Pydantic inside the session.
  - `update_item` (bool) / `delete_item` (**hard** `DELETE` → `s.delete(row)`, bool): preserve `rowcount > 0` semantics.
  - **Link methods:** `add_trip_place` → `s.add(TripPlaceLinkRow(...))` + commit; let `IntegrityError` propagate (the `with` block rolls back on exception; service maps to 409). `list_trip_places(trip_id)` → return `list[dict]` ordered by `added_at` (`[{"id":..,"trip_id":..,"place_id":..,"source":..,"added_at":..}, ...]`, built inside the session). `get_trip_place(link_id)` → return a `dict` or `None`. `delete_trip_place(trip_id, link_id)` → bool, scoped to its trip.

- [ ] **Step 3: Migrate `tests/conftest.py`.** Replace path-based construction with URL-based. The temp DB fixture returns a SQLite **URL**:

```python
@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Return a SQLite URL for an isolated per-session test database."""
    db_file = tmp_path_factory.mktemp("data") / "test_travel.db"
    return f"sqlite:///{db_file}"
```

Then update the `client` fixture: services now take the URL; the flight repo takes a **session factory**:

```python
from app.db.engine import get_session_factory
from app.crud.flight import FlightIndexRepository
# ...
    svc = BookingService(tmp_db)
    svc.init_db()
    flight_service.set_index_repo(FlightIndexRepository(get_session_factory(tmp_db)))
    trip_svc = TripService(tmp_db)
    trip_svc.init_db()
    sp_svc = SavedPlaceService(tmp_db)
    sp_svc.init_db()
    saved_place_service._saved_place_service = sp_svc
```

And the standalone `booking_service` fixture builds `BookingService(tmp_db)` (now a URL) — no other change.

> **Singleton seam preserved:** the three module-singleton repoints (`saved_place_service._saved_place_service`, `flight_service.set_index_repo`, and the trip/booking DI overrides) stay exactly as before — they just carry a URL/session-factory instead of a path. This is the test-isolation trap from project memory; do not remove these.

- [ ] **Step 4:** Proceed to Task 9 (services) before running — services still reference `database_path`.

---

## Chunk 3: Service wiring + lifespan + cleanup

### Task 9: Services accept `database_url`, build session factory

**Files:**
- Modify: `app/services/booking_service.py` (`__init__`, module singleton line ~292)
- Modify: `app/services/trip_service.py`
- Modify: `app/services/saved_place_service.py`
- Modify: `app/services/flight_service.py`

- [ ] **Step 1: For each service `__init__(self, db_path: str)`**, change to build a session factory and pass it to the repo:

```python
from app.db.engine import get_session_factory
# ...
    def __init__(self, database_url: str) -> None:
        self._repo = BookingRepository(get_session_factory(database_url))
```

  Apply the analogous change to `TripService`, `SavedPlaceService`. For `flight_service`, wherever it builds `FlightIndexRepository(...)` from a path/settings, build `FlightIndexRepository(get_session_factory(get_settings().database_url))` (and `set_index_repo` already accepts a repo — unchanged).

- [ ] **Step 2: Update each module singleton** that read `get_settings().database_path` to `get_settings().database_url` (e.g. `booking_service.py:292` `_booking_service = BookingService(get_settings().database_url)`). Grep to be exhaustive: `grep -rn "database_path" app/`.
  Expected after edits: `grep -rn "database_path" app/` returns nothing.

- [ ] **Step 3: Fix the `trip_service.py` exception catch** (the one forced service-layer change). Replace `import sqlite3` (line 10) with `from sqlalchemy.exc import IntegrityError`, and `except sqlite3.IntegrityError:` (line ~251) with `except IntegrityError:`. Verify: `grep -rn "sqlite3" app/` → no matches anywhere in `app/`.

- [ ] **Step 4: Run the full suite** — Run: `.venv/bin/python -m pytest tests/ -q`
  Expected: the full collected count (624 with the 2 new test files) passes — this is the parity gate; the ORM rewrite is behavior-preserving. Fix regressions before continuing. Common culprits: a missed `row["x"]`→`row.x`, a missing `s.commit()`, a JSON column still being `json.dumps`'d, ORM attributes read after the session closed, or the `trip_service` 409 catch (Step 3).

---

### Task 10: Lifespan — engine init + sqlite create_all + cleanup

**Files:**
- Modify: `app/core/lifespan.py`
- Delete: `app/crud/_migrations.py`

- [ ] **Step 1: Update `lifespan.py`.** Replace the `database_path` resolve/log with URL logging, and gate auto-create on SQLite (Postgres schema is owned by Alembic):

```python
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine
# ...
    settings = get_settings()
    logger.info("Database URL: %s", settings.database_url)
    engine = get_engine(settings.database_url)
    # SQLite (local/dev/test) self-creates its schema; Postgres schema is
    # managed by Alembic (alembic upgrade head, run by the container entrypoint).
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine, checkfirst=True)
    check_city_coverage()
    try:
        get_booking_service().init_db()
        get_trip_service().init_db()
        get_saved_place_service().init_db()
        init_flight_index()
    except Exception:
        logger.exception("Could not initialise database at %s", settings.database_url)
        raise
```

> The per-service `init_db()` calls (also `create_all`, idempotent) are kept for the SQLite path so each service can be constructed/inited independently in tests. On Postgres they are effectively no-ops after Alembic has run (`checkfirst=True`).

- [ ] **Step 2: Delete `app/crud/_migrations.py`** and remove its imports from `booking.py`/`trip.py` (already gone after the rewrites — verify): Run: `grep -rn "_migrations\|ensure_column\|ensure_unique_partial_index" app/`
  Expected: no matches.

- [ ] **Step 3: Re-run the suite + lint** — Run: `.venv/bin/python -m pytest tests/ -q && ruff check app scripts && ruff format --check app scripts`
  Expected: 594 pass, lint clean.

---

## Chunk 4: Alembic

### Task 11: Initialize + configure Alembic

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`

- [ ] **Step 1: Scaffold** — Run: `.venv/bin/alembic init alembic`
  Expected: creates `alembic.ini` + `alembic/`.

- [ ] **Step 2: Point `alembic/env.py` at the app.** Set `target_metadata` and read the URL from settings (so one source of truth):

```python
from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401  (register tables on Base.metadata)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

  Set `render_as_batch=True` in both `run_migrations_offline`/`online` `context.configure(...)` calls so SQLite ALTERs work if Alembic is ever run against SQLite.

- [ ] **Step 3: Verify config loads** — Run: `.venv/bin/alembic current`
  Expected: connects (no revision yet) without error.

---

### Task 12: Initial migration

**Files:**
- Create: `alembic/versions/0001_initial.py`

- [ ] **Step 1: Autogenerate against a scratch Postgres** (preferred, captures dialect-correct DDL). With a throwaway PG running (e.g. `docker run --rm -e POSTGRES_PASSWORD=x -p 5432:5432 postgres:17`), Run:
  `DATABASE_URL=postgresql+psycopg://postgres:x@localhost:5432/postgres .venv/bin/alembic revision --autogenerate -m "initial schema"`
  Expected: a revision creating all 6 tables + the partial-unique / composite-unique / plain indexes.

- [ ] **Step 2: Review the generated revision.** Confirm: all 6 tables; partial unique indexes carry `postgresql_where=...`; `trip_place_link` composite unique; `ix_trip_items_trip_id`; `ix_bookings_confirmation_code`. Hand-fix anything autogenerate dropped (partial-index `where` is the usual miss).

- [ ] **Step 3: Apply + verify round-trip** — Run: `alembic upgrade head` then `alembic downgrade base` then `alembic upgrade head` against the scratch PG.
  Expected: clean up/down/up with no errors.

> If no scratch PG is available at plan-execution time, hand-write `0001_initial.py` from `app/db/models.py` (it is the schema source of truth) — every column, type, nullability, and the four indexes above.

---

## Chunk 5: Docker + tooling

### Task 13: Dockerfile + entrypoint

**Files:**
- Create: `Dockerfile`, `docker/entrypoint.sh`

- [ ] **Step 1: Write `Dockerfile`:**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# psycopg[binary] ships its own libpq, so no apt postgresql-client needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `docker/entrypoint.sh`:**

```bash
#!/usr/bin/env sh
set -e
# Postgres path: bring the schema to head before serving. (No-op tables already
# at head.) SQLite/dev path self-creates in lifespan, so this is still safe.
echo "Running migrations: alembic upgrade head"
alembic upgrade head
exec "$@"
```

- [ ] **Step 3: Lint the Dockerfile build locally** — Run: `docker build -t travel-pi:dev .`
  Expected: image builds.

---

### Task 14: docker-compose.yml (app + Postgres)

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write it** (Postgres 17 + `pg_isready` healthcheck + `depends_on: service_healthy`):

```yaml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: travel
      POSTGRES_PASSWORD: travel
      POSTGRES_DB: travel
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U travel -d travel"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build: .
    environment:
      DATABASE_URL: postgresql+psycopg://travel:travel@db:5432/travel
      ENVIRONMENT: development
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 2: Bring it up** — Run: `docker compose up --build -d`
  Expected: `db` healthy, `api` starts, migrations run.

- [ ] **Step 3: Smoke test** — Run: `curl -s localhost:8000/healthz || curl -s localhost:8000/docs -o /dev/null -w "%{http_code}\n"`
  Expected: app responds (HTTP 200 on `/docs`). Then `docker compose down`.

> Confirm the real health/readiness path during execution (`grep -rn "healthz\|/health\|@router.get(\"/\"" app/routers`); use whatever exists.

---

### Task 15: docker-compose.test.yml (isolated Postgres test run)

**Files:**
- Create: `docker-compose.test.yml`

- [ ] **Step 1: Write it** — a throwaway PG + a one-shot test container that runs pytest against it. **This is the one place tests run on Postgres**, proving cross-engine parity:

```yaml
services:
  test-db:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: test
    tmpfs:
      - /var/lib/postgresql/data   # ephemeral; no volume, wiped on teardown
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d test"]
      interval: 3s
      timeout: 3s
      retries: 15

  tests:
    build: .
    environment:
      DATABASE_URL: postgresql+psycopg://test:test@test-db:5432/test
    depends_on:
      test-db:
        condition: service_healthy
    entrypoint: ["sh", "-c", "alembic upgrade head && python -m pytest tests/ -q"]
```

> **Caveat:** `conftest.py` overrides the DB to a **temp SQLite URL** regardless of `DATABASE_URL` — so by default the suite always runs on SQLite even in this container. To make the test-compose genuinely exercise Postgres, gate the conftest URL on an env var: `tmp_db` returns `os.environ.get("TEST_DATABASE_URL")` when set, else the SQLite temp URL. Add `TEST_DATABASE_URL` (= the PG URL) to the `tests` service env. Decide at execution: keep SQLite-only (simplest; the compose just runs the suite in a container) or wire the env override (true PG parity). **Recommend the env override** — it is the stated goal ("run unittest with isolated db" against Postgres).

- [ ] **Step 2: Run it** — Run: `docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests`
  Expected: suite passes inside the container; `docker compose -f docker-compose.test.yml down -v` cleans up.

---

### Task 16: Makefile + scripts

**Files:**
- Create: `Makefile`, `scripts/start.sh`, `scripts/test-docker.sh`

- [ ] **Step 1: Write `Makefile`** (compose-first, plus local non-Docker targets):

```makefile
.PHONY: help install dev up down logs migrate test test-docker fmt lint

help:           ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:        ## Create venv + install deps (local)
	uv venv && uv pip install -r requirements.txt

dev:            ## Run the app locally on SQLite (no Docker)
	.venv/bin/uvicorn app.main:app --reload --port 8000

up:             ## Build + start app + Postgres in Docker
	docker compose up --build -d

down:           ## Stop the Docker stack
	docker compose down

logs:           ## Tail Docker logs
	docker compose logs -f

migrate:        ## Run Alembic migrations against the configured DATABASE_URL
	.venv/bin/alembic upgrade head

test:           ## Run the suite locally on SQLite
	.venv/bin/python -m pytest tests/ -q

test-docker:    ## Run the suite in Docker against isolated Postgres
	docker compose -f docker-compose.test.yml up --build \
	  --abort-on-container-exit --exit-code-from tests; \
	  docker compose -f docker-compose.test.yml down -v

fmt:            ## Format
	.venv/bin/ruff format app scripts

lint:           ## Lint
	.venv/bin/ruff check app scripts
```

- [ ] **Step 2: Write thin scripts** (so non-Make users have an entry point). `scripts/start.sh`: `#!/usr/bin/env sh` + `exec docker compose up --build "$@"`. `scripts/test-docker.sh`: the `test-docker` body. `chmod +x scripts/*.sh`.

- [ ] **Step 3: Verify** — Run: `make help` then `make test`
  Expected: targets listed; 594 pass.

---

## Chunk 6: Docs + decision record

### Task 17: README / guide

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add/replace the run section** with three paths: (a) **local SQLite** (`make install && make dev`, `make test`), (b) **Docker + Postgres** (`make up`, `/docs` at :8000, `make down`), (c) **tests on isolated Postgres** (`make test-docker`). Document `DATABASE_URL` (default `sqlite:///travel.db`; Docker uses `postgresql+psycopg://…`) and the Alembic flow (`make migrate`). Keep the existing `uv` instructions as the local path.

- [ ] **Step 2: Verify** the commands you documented actually run as written (copy-paste check `make install`, `make test`).

---

### Task 18: Amend CLAUDE.md "no ORM" rule

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Conventions bullet** "Keep it minimal — no auth, ORM, pagination, or rate limiting" → remove "ORM" and add a sentence: persistence uses **SQLAlchemy 2.0 ORM** (sync), engine chosen by `DATABASE_URL` (SQLite default, Postgres in Docker), schema versioned by **Alembic**; ORM is confined to `app/crud/` (services/schemas unchanged).

- [ ] **Step 2: Update the architecture/"Run it" sections** to mention `make up` / `make test-docker` and the dual-engine model. Update the stale "336 tests" to the real count.

---

### Task 19: Record the decision (`/compound`)

**Files:**
- Create: `docs/decisions/0001-orm-and-postgres.md` (or wherever `/compound` writes)

- [ ] **Step 1: Invoke `/compound`** to capture: *why* the "no ORM" constraint was overridden (clean dual-engine via a single URL beats a hand-maintained per-dialect raw-SQL shim), the runtime-PG / tests-SQLite split, Alembic choice, the "ORM confined to crud tier" boundary, and the **dropped `init_db` confirmation_code backfill** (safe for fresh tables; the only data lost is auto-backfill for a pre-existing `travel.db` — acceptable for a mock backend, and recoverable via an Alembic data migration if ever needed). Link `specs/docker-postgres-setup/`.

---

## Final Verification (Definition of Done)

- [ ] `.venv/bin/python -m pytest tests/ -q` → full collected count (**624**) passes on SQLite.
- [ ] `make test-docker` → suite passes against isolated Postgres (**cross-engine parity proven** — this is the only run that exercises PG; required before declaring done).
- [ ] `alembic check` (1.13+) → no pending model-vs-migration diff (catches drift between `models.py` and `0001_initial.py`, e.g. partial-index `where`, boolean default, composite unique).
- [ ] `make up` → `db` healthy, `api` serves `/docs` (HTTP 200) after `alembic upgrade head`.
- [ ] `ruff check app scripts && ruff format --check app scripts` → clean.
- [ ] `grep -rn "sqlite3\|database_path\|_migrations" app/` → no matches (full migration, incl. the `trip_service` catch).
- [ ] `alembic upgrade head` / `downgrade base` / `upgrade head` round-trips on Postgres.
- [ ] CLAUDE.md "no ORM" amended; `/compound` decision recorded.
- [ ] `SUMMARY.md` `### Verify` section filled with the above evidence (high-risk lane requires it).
```
