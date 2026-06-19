# 0001 — Adopt SQLAlchemy ORM + Postgres (override the "no ORM" rule)

- **Status:** Accepted
- **Date:** 2026-06-19
- **Supersedes:** the prior "no ORM" convention in `CLAUDE.md` / `mock-api-spec.md` §1

## Context

The mock backend's original minimalism rule banned an ORM: persistence was
hand-written `sqlite3` raw SQL in `app/crud/`. We needed the same app to run on
**Postgres in Docker** (for a more production-like deployment) while keeping the
**fast, zero-config SQLite path** for local development and CI tests.

The raw-SQL approach made a backend swap expensive: supporting a second dialect
would mean a hand-maintained per-dialect SQL shim (placeholder styles, type
affinities, upserts, JSON handling) across every crud module — easy to drift,
hard to keep in parity, and untested on the dialect you don't run locally.

## Decision

- Override the prior **"no ORM"** rule and adopt **SQLAlchemy 2.0 ORM (sync)**.
- Select the engine by a single **`DATABASE_URL`** connection string:
  - **SQLite** (`sqlite:///travel.db`) by default — local development and CI tests.
  - **Postgres** (`postgresql+psycopg://travel:travel@db:5432/travel`) behind
    Docker, injected by the compose files.
- Use **Alembic** for schema migrations (`alembic upgrade head`, revision
  `0001_initial`); the Docker entrypoint runs it automatically before the app boots.
- Use a **portable `JSON`** column type (not Postgres-specific `JSONB`) so the
  same models work on both engines.
- **Confine the ORM to the crud tier (`app/crud/`)**; services, schemas, and
  routers stay ORM-free, preserving the existing layering.

## Consequences

- A backend swap is now a single connection-URL change rather than a per-dialect
  raw-SQL shim. The fast zero-config SQLite test path is preserved, and Postgres
  parity is real: the **617-test** suite is green on **both** SQLite and Postgres
  (`make test` and `make test-docker`).
- The legacy on-disk migration machinery was removed, since fresh ORM tables make
  it moot:
  - The `init_db` `confirmation_code` backfill and the `_migrations.py`
    PRAGMA/ALTER helpers are gone.
  - The **7 legacy on-disk-migration tests were deleted** accordingly.
  - If backfilling a pre-existing `travel.db` ever becomes necessary, do it as an
    **Alembic data migration**, not ad-hoc startup code.
- **`fastapi<0.137` pin in `requirements.txt` is load-bearing.** FastAPI 0.137
  refactored `router.routes` into a tree with intermediate non-`APIRoute`
  objects, which breaks `tests/infra/test_operation_ids.py` (it introspects the
  public `app.routes` + `APIRoute` pattern). The pin reproduces the validated
  baseline; to loosen it later, adjust that test for the new route tree. (The
  accompanying `starlette<1.3` cap is redundant — the root cause is FastAPI
  0.137, not Starlette.)
- **Test isolation** uses session-scoped fixtures plus module singletons that
  must be repointed (`saved_place_service._saved_place_service`,
  `flight_service.set_index_repo`); a `TEST_DATABASE_URL` env gate in
  `conftest.py` routes the suite to Postgres under the test-compose.

## References

- `specs/docker-postgres-setup/SUMMARY.md` — task summary and lane
- `specs/docker-postgres-setup/research-brief.md` — research and options weighed
- `specs/docker-postgres-setup/PLAN.md` — implementation plan
