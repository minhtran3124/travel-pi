# Research Brief — docker-postgres-setup

> **Depth: Deep.** Triggers: data-store migration, new external integration
> (Postgres), new runtime deps (SQLAlchemy + psycopg), high-blast persistence
> tier, session/transaction-primitive change. Each is independently a Deep signal.
>
> ⚠️ **PROJECT.md is stale.** The xia2 `PROJECT.md` describes the upstream
> `harness-skills` meta-repo (hooks, `render_plan.py`, `settings.json`), not this
> FastAPI/SQLite backend. Its signal mappings were *not* used for classification —
> depth was set from universal signals. **Recommend re-running `/bootstrap-xia2`**
> to regenerate it for travel-pi before the next research cycle.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Adapt upstream** (canonical FastAPI + SQLAlchemy 2.0 sync pattern) + **use built-in** (compose `depends_on` healthcheck, `metadata.create_all`) |
| **Why this is the lightest credible path** | All four repos share one identical sqlite3 shape; an ORM makes the engine a single config URL, so dual-engine (SQLite default / Postgres in Docker) falls out for free without per-dialect SQL forks. |
| **Confidence** | 80% |
| **Next step** | `/writing-plans` — sequence the ORM rewrite (4 repos + lifespan + config + conftest), then Dockerfile/compose/Makefile/README, then the isolated test-compose. Resolve the two follow-up questions first. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Mock REST API (FastAPI) |
| Primary language + runtime | Python 3.10+ (`list[X]`, `X \| None`; CLAUDE.md) |
| Frameworks / platforms | FastAPI `>=0.110,<1.0`, Pydantic v2 `>=2.6,<3`, pydantic-settings `>=2.2,<3`, Uvicorn `>=0.27,<1.0` |
| Relevant packages | **stdlib `sqlite3`** is the entire persistence layer today — no SQLAlchemy, no ORM, no Alembic present |
| Detectable versions | `requirements.txt` (no lockfile; no `pyproject.toml` deps) |
| Important constraints | CLAUDE.md: "no ORM" (**being overridden by user**); "Async only for real network I/O" → **DB tier is sync, runs in FastAPI threadpool**; "Bookings are the only mutable state" but trips + saved_places + flight-index also persist; `total_price` computed server-side; deterministic IDs from MD5 seeds are **in-memory in services, DB-independent** |

---

## Feature Understanding and Assumptions

- **Requested feature:** Dockerize the app; add a Postgres service; move persistence to SQLAlchemy ORM (engine chosen by config URL); compose-first Makefile + startup scripts; isolated test-compose against Postgres; update README/guide.
- **What success appears to mean:** `make up` runs app+Postgres in Docker and serves `/docs`; `pytest` still runs locally on SQLite and stays green (594 tests); a separate compose runs the suite against a throwaway Postgres; README documents both paths.
- **Assumptions from the request (confirmed via escalation E1):**
  - Backend is **config-selected**; SQLite stays the **default** for local/CI; Postgres runs **only behind Docker**.
  - Driver = **SQLAlchemy ORM** (deliberate override of CLAUDE.md "no ORM"; CLAUDE.md must be updated + `/compound` decision recorded).
  - Sync, not async (matches the existing threadpool design).
- **Assumptions still needing confirmation:** migration tooling (Alembic vs `create_all`); whether `details` JSON should become Postgres `JSONB`. See Follow-Up.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | 4 repos (`booking`/`trip`/`saved_place`/`flight`) share one shape: `__init__(db_path)` → `_connect()` ctx-mgr over `sqlite3.connect(path)` (`row_factory=Row`, commit-on-exit, fresh conn per call) → `init_db()` with `CREATE TABLE IF NOT EXISTS` + idempotent `ALTER`/index migrations → `?`-placeholder SQL. ~81 sqlite-specific call sites across 6 files. |
| `Local` | `config.database_path: str = "travel.db"` is a **file path**, not a URL; `.env.example` exposes `DATABASE_PATH`. |
| `Local` | `lifespan.py` calls `get_*_service().init_db()` for booking/trip/saved_place + `init_flight_index()` on startup; wraps in try/except logging the resolved path. |
| `Local` | `conftest.py` builds services from a **temp SQLite file path** per session and overrides FastAPI deps; saved_place + flight repos are repointed via **module singletons** (`saved_place_service._saved_place_service`, `flight_service.set_index_repo`) — NOT pure DI. trip_service has the same singleton trap (see memory `trip-service-booking-singleton-test-isolation`). |
| `Local` | Idempotency relies on a **UNIQUE partial index** (`WHERE idempotency_key IS NOT NULL`) + catching `sqlite3.IntegrityError` on race. `_migrations.py` uses `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` (SQLite-only idioms). |
| `Docs` | SQLAlchemy 2.0 sync pattern: `DeclarativeBase`/`Mapped`/`mapped_column`; one `Engine` per URL via `create_engine`; `sessionmaker`; FastAPI dependency yields a `Session` and caches it within a request. Sync routes run in the anyio threadpool (default ~40 workers) — matches this codebase's sync design; **no asyncpg/async needed.** |
| `Docs` | psycopg **3** driver string is `postgresql+psycopg://user:pass@host:port/db` (psycopg2 would be `+psycopg2`). SQLAlchemy raises a unified `sqlalchemy.exc.IntegrityError` wrapping both sqlite3 and psycopg — replaces the `sqlite3.IntegrityError` catch. |
| `Docs` | Postgres official image has **no built-in HEALTHCHECK**; standard is `pg_isready` in compose `healthcheck` + `depends_on: condition: service_healthy`. PG **18** is now released (PGDATA path became version-specific in 18+); **17** is the proven, safe pin. |
| `Inference` | Partial unique indexes (`WHERE col IS NOT NULL`) and JSON columns are supported on **both** SQLite and Postgres, so the idempotency constraint and `details` column port cleanly via SQLAlchemy types. Postgres `JSONB` would be an opt-in upgrade, not required. |

---

## Local Findings

- **Relevant files:** `app/crud/{booking,trip,saved_place,flight}.py`, `app/crud/_migrations.py`, `app/core/lifespan.py`, `app/core/config.py`, `tests/conftest.py`; services `booking_service.py` (`_repo = BookingRepository(db_path)`, module singleton `_booking_service`), `trip_service.py`, `saved_place_service.py`, `flight_service.py`.
- **Existing abstractions / extension points:** every repo already isolates connection handling in one `_connect()` ctx-mgr and table setup in one `init_db()` — these are the **two seams** to swap for a SQLAlchemy `Session`/`sessionmaker` and `Base.metadata.create_all(engine)`. Repos already take a constructor arg, so swapping `db_path: str` → an engine/session-factory is a localized signature change.
- **Conventions worth preserving:** layering routers→services→crud (services raise domain exceptions, never DB errors); fresh-scope-per-call (maps to session-per-request); deterministic MD5 IDs (untouched — they live in services, not the DB); typed `response_model`s; the idempotency UNIQUE-partial-index + integrity-race pattern.
- **Reusable:** schema field lists already enumerated (`_COLUMNS`); `_row_to_booking` mapping logic transfers to ORM model construction; `confirmation_code` backfill logic.
- **Missing locally:** any ORM, any DB URL config, any migration framework, any Docker/compose/Makefile, any DB-engine abstraction.

---

## Upstream Findings

- **Pattern present upstream:** the "FastAPI + SQLAlchemy 2.0" sync pattern is well-established (chaoticengineer guide; oneuptime 2026 guide) — `engine = create_engine(url)`, `SessionLocal = sessionmaker(bind=engine)`, a `get_db()` dependency that yields and closes a session.
- **Match quality:** high for sync; most 2026 write-ups push **async** (asyncpg/AsyncSession) which would be a poor fit here — it contradicts the repo's deliberate "sync DB in threadpool" design and would force rewriting every sync endpoint. **Adapt the sync variant, ignore the async push.**
- **Upstream gap:** the dual-engine (SQLite-default / Postgres-in-Docker) split is project-specific; upstream guides assume a single DB. The seam is config: one `database_url` → one engine.

---

## Docs Findings

- **Sources checked:** SQLAlchemy 2.0 Engine Configuration docs; psycopg3 docs; Docker Hub `postgres` official image + docker-library healthcheck issue; FastAPI/SQLAlchemy 2026 pattern guides.
- **Version-matched status:** SQLAlchemy 2.0.x current major; psycopg3 current (`postgresql+psycopg`); Postgres 17 proven (18 available).
- **Built-in capabilities:** `Base.metadata.create_all(engine)` covers fresh-DB table creation (replaces `CREATE TABLE IF NOT EXISTS` across all repos) — Alembic only needed if real schema migrations must be versioned (the current `_migrations.py` ALTER guards are for legacy DBs and become moot for a fresh Postgres).
- **Caveats:** psycopg3 requires user/pass in the URL; the `sqlite3.IntegrityError` catch must become `sqlalchemy.exc.IntegrityError`; SQLite needs `connect_args={"check_same_thread": False}` if a connection is shared across threads (avoidable with session-per-request); Postgres image needs an explicit `pg_isready` healthcheck + `depends_on` gating so the app doesn't boot before the DB is ready.

---

## Recommendation

- **Primary:** **Adapt the canonical sync FastAPI + SQLAlchemy 2.0 pattern** and drive the engine from a single `database_url` config value (`sqlite:///travel.db` default; `postgresql+psycopg://…` injected by Docker). Replace each repo's `_connect()`/`init_db()` seam with a shared `Session`/`sessionmaker` + `Base.metadata.create_all`. Use compose `pg_isready` healthcheck + `depends_on: service_healthy`. Tests keep SQLite by passing the SQLite URL; the test-compose passes a Postgres URL to the same code.
- **Why lightest credible path:** the four repos are structurally identical, so the rewrite is one pattern applied four times; the ORM collapses the ~81 dialect-specific call sites into engine-agnostic models, making dual-engine support a config value rather than a forked SQL maze.
- **Why next-best lost:** *raw psycopg + dialect shim* (my original recommendation) honors "no ORM" with a smaller dep but keeps two hand-maintained SQL dialects forever and a brittle placeholder shim — the user explicitly chose ORM, which also gives cleaner dual-engine. *Full replacement (drop SQLite)* loses the fast zero-config test path the user wants to keep.
- **What would change this:** if real, versioned schema migrations are required (not just fresh-DB creation), add **Alembic** — escalates effort and adds a migrations dir.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - **Test-isolation singletons:** conftest repoints `saved_place_service` / `flight_service` / `trip_service` via module globals, not pure DI (see project memory). The ORM rewrite must preserve a way to inject a test engine/session per session-scoped fixture or tests silently hit the wrong store.
  - **Behavior parity:** 594 tests are the safety net — the ORM models must reproduce exact column semantics (`total_price` REAL→Float, ISO `created_at` stored as TEXT/timestamptz, `details` JSON round-trip, partial-unique idempotency, confirmation_code index).
  - **Sync session lifecycle** under the threadpool: must close sessions per request to avoid leaking connections (the FastAPI discussion #15353 flags pool-exhaustion timeouts when sessions aren't scoped correctly).
  - **CLAUDE.md contract:** "no ORM" rule is now false — must be updated or the project-standards reviewer and future intake will flag every ORM import.
- **Evidence gaps:** exact pinned versions (no lockfile) — will pin at implementation. Whether `apps/` stale monorepo copy needs the same treatment (CLAUDE.md says ignore it — confirm it stays untouched).
- **Version uncertainties:** Postgres 17 vs 18 (recommend 17-alpine pin); SQLAlchemy exact 2.0.x patch.
- **Follow-up questions for the user (max 2):**
  1. ~~Migrations~~ → **RESOLVED: add Alembic** (versioned migrations; `alembic/` dir + env wired to `database_url`; initial revision creates all tables; `lifespan` no longer hand-creates tables — or runs `alembic upgrade head`/`create_all` for the SQLite test path. Confirm at planning how tests bootstrap schema: simplest is `Base.metadata.create_all` in the test fixture, Alembic for the Docker/Postgres path).
  2. ~~JSON storage~~ → **RESOLVED: portable `JSON`** (SQLAlchemy generic `JSON` type; same model on SQLite + Postgres; no `JSONB`).

---

## Source Pack

- **Local files read:** `app/crud/booking.py`, `app/crud/_migrations.py`, `app/crud/{trip,saved_place,flight}.py` (signatures), `app/core/config.py`, `app/core/lifespan.py`, `tests/conftest.py`, `requirements.txt`, `app/services/booking_service.py`, `CLAUDE.md`, `specs/docker-postgres-setup/{SUMMARY,ESCALATIONS}.md`.
- **Upstream/docs checked:**
  - https://docs.sqlalchemy.org/en/20/core/engines.html
  - https://chaoticengineer.hashnode.dev/fastapi-sqlalchemy
  - https://oneuptime.com/blog/post/2026-01-27-sqlalchemy-fastapi/view
  - https://github.com/fastapi/fastapi/discussions/15353
  - https://www.psycopg.org/psycopg3/docs/api/connections.html
  - https://hub.docker.com/_/postgres/
  - https://github.com/docker-library/postgres/issues/1237

---

## Evidence Boundary

> **Confirmed from artifacts:** the 4-repo sqlite3 shape and the two swap seams; `database_path` is a file path; lifespan init sequence; conftest's singleton-based test isolation; idempotency partial-unique-index + IntegrityError pattern; no ORM/Docker/migration tooling present; sync DB design.
>
> **Inferred from patterns/docs:** SQLAlchemy 2.0 sync session-per-request is the right fit; partial-unique-index + JSON port cleanly to both engines; `create_all` suffices without Alembic; psycopg3 driver string.
>
> **Not checked:** exact installed patch versions (no lockfile); whether any dashboard/Jinja path reads the DB directly; behavior of the stale `apps/` copy (CLAUDE.md says ignore); live Postgres run of the suite (no Postgres available in this research env).
