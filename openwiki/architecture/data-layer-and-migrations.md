---
type: architecture
title: Data layer and migrations
description: How persistence is organized — SQLAlchemy 2.0 ORM models with UUID string keys and ISO timestamps, one engine per DATABASE_URL, SQLite self-created schema versus Alembic-managed Postgres, the idempotent seeder that turns app/data reference literals into rows with deterministic ids and seed-order positions, the startup invariants, and the portability rules (portable JSON, partial unique indexes, ordered reads) that keep both engines byte-equal.
tags: [sqlalchemy, alembic, postgres, sqlite, seeding, migrations, orm, determinism, pgvector]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-58284531dd21a357cc3f0e42
    resource: repo://apps/api/alembic/env.py
  - id: openwiki-source-d3d300e4d60ee9147a87fa4b
    resource: repo://apps/api/alembic/versions/b68656f68e88_enable_pgvector_extension_postgres_only.py
  - id: openwiki-source-f18f564b85852ec3a8a054dc
    resource: repo://apps/api/app/core/lifespan.py
  - id: openwiki-source-1d0fda0c72faeba77b0eb5e5
    resource: repo://apps/api/app/db/base.py
  - id: openwiki-source-9967de0445cdfe2a1cd416b6
    resource: repo://apps/api/app/db/engine.py
  - id: openwiki-source-1ddade7dd015e249d1d14c53
    resource: repo://apps/api/app/db/locks.py
  - id: openwiki-source-b0de2358ac11ef7a3e3b6f37
    resource: repo://apps/api/app/db/models/__init__.py
  - id: openwiki-source-a5adc42be2756996fccf803d
    resource: repo://apps/api/app/db/models/booking.py
  - id: openwiki-source-dd51ce6041b0216bb8b46bef
    resource: repo://apps/api/app/db/seed.py
  - id: openwiki-source-6ad33679598c8cf3dd97ff88
    resource: repo://apps/api/app/repositories/booking.py
  - id: openwiki-source-a74ad515a45edaaee7c4752c
    resource: repo://apps/api/app/repositories/hotel_ref.py
  - id: openwiki-source-b842553da9494f6fbfc62431
    resource: repo://apps/api/app/research/service.py
  - id: openwiki-source-c67fada0a467b1fb8d2dec3a
    resource: repo://apps/api/docker/entrypoint.sh
  - id: openwiki-source-594b0ff08df95de64ae23701
    resource: repo://apps/api/tests/db/test_agent_run_steps_migration.py
  - id: openwiki-source-cd018494e0914c5c825348bb
    resource: repo://apps/api/tests/db/test_agent_runs_migration.py
  - id: openwiki-source-c8e2c8fca8c5be100bba161b
    resource: repo://apps/api/tests/db/test_determinism.py
  - id: openwiki-source-6ebc3a2e1311ab3ccf640e83
    resource: repo://apps/api/tests/db/test_seed.py
  - id: openwiki-source-f136ab6c061754fa8c7a4861
    resource: repo://apps/api/tests/test_db_engine.py
  - id: openwiki-source-8d92358cee745defd23d6c98
    resource: repo://apps/api/tests/test_db_models.py
  - id: openwiki-source-7d039b665ea4e834caec0e08
    resource: repo://docs/decisions/0001-orm-and-postgres.md
  - id: openwiki-source-2b608be26f3a5affa7ff2940
    resource: repo://docs/decisions/0002-reference-data-in-db.md
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
---

# Data layer and migrations

The backend runs the same code on two engines: a zero-config SQLite file for local development and the unit-test suite, and Postgres (with pgvector) in Docker and deployments. The choice is a single connection string, `DATABASE_URL` (see [Configuration and environments](configuration-and-environments.md)). Two architecture decision records explain the shape: [0001](../../docs/decisions/0001-orm-and-postgres.md) adopted SQLAlchemy 2.0 ORM plus Alembic over hand-written SQL so a backend swap is a URL change rather than a per-dialect shim, and [0002](../../docs/decisions/0002-reference-data-in-db.md) moved the reference catalog from in-memory Python dicts into first-class ORM entities read per request.

## Models

All models live in the `apps/api/app/db/models/` package, one file per entity, and are re-exported from `app/db/models/__init__.py`; importing the package registers every table on `Base.metadata`, which is what Alembic's `env.py` and `create_all` rely on. ORM classes carry plain names (`Hotel`, `Trip`) and are disambiguated from the identically named Pydantic response schemas in `app/schemas/` by the `models.` namespace; the ORM never leaks past repositories (see [Backend request lifecycle](backend-request-lifecycle.md)).

`app/db/base.py` provides the shared base: `UUIDBase` gives every runtime table a random UUID4 string primary key plus ISO-8601 string `created_at`/`updated_at` (updated automatically). `deterministic_uuid(*parts)` produces a UUID5 under a fixed namespace from a natural key, so seeded reference rows get **the same id on every machine and every run**. Importing the base has no database side effects.

Tables today: reference catalog (`countries`, `airlines`, `airports`, `cities`, `hotels`, `places`, `tips`, `country_summaries`, `visa`, FX rates and metadata, `content_translations`), user data (`users`, `trips`, `trip_items`, `trip_place_links`, `saved_places`, `bookings`, `expenses`, `flight_index`), and agent tables (`conversations`, `messages`, `agent_runs`, `agent_run_steps`, `agent_config`, `feedback_events`, `rate_limit_counters`, `jobs`). `tests/test_db_models.py` asserts the registered table set and the columns of the agent tables.

Portability rules the models follow so one definition works on both engines:

- **Portable `JSON`**, never Postgres-specific `JSONB`, for `details`, `tool_calls`, `by_model` and similar columns.
- **Partial unique indexes** declared with both `sqlite_where` and `postgresql_where`, for example bookings' `idempotency_key` and `confirmation_code`, which must be unique only when present.
- **Batch-mode Alembic operations** for column changes, because SQLite cannot alter columns in place.

## Engine and sessions

`app/db/engine.py` caches one `Engine` and one `sessionmaker` per URL with `lru_cache`, so every caller of the same URL shares a pool; Postgres connections use `pool_pre_ping` and SQLite connections allow cross-thread use. `get_session` yields the request-scoped unit of work and repositories accept either that session or a factory (details on the request-lifecycle page). `tests/db/test_session.py` pins commit-on-success, rollback-on-exception and close-always.

### Serializing a check-then-write: advisory locks

`app/db/locks.py` is the one mechanism for making a duplicate check and its insert atomic against a concurrent request for the same subject. `advisory_xact_lock(session, name)` takes a Postgres `pg_advisory_xact_lock` on the caller's current transaction, so the caller must own that transaction. The lock is released automatically on commit or rollback. `advisory_lock_key(name)` hashes the subject name with blake2b into a signed int64. It does not use the salted built-in `hash()`, so every process derives the same key. The helper is a no-op on SQLite, where the unit suite runs sequentially. Two paths use it: the per-owner booking lock (`booking:{user_id}`, see [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md)) and the per-trip research start lock (`research_start:{user_id}:{trip_id}`, see [Trip-research deep agent](../agent/trip-research-deep-agent.md)).

## Schema management: SQLite creates, Postgres migrates

On startup the lifespan calls `Base.metadata.create_all` **only when the engine dialect is SQLite**. On Postgres the schema is owned by Alembic: the Docker entrypoint runs `alembic upgrade head` before serving, `make migrate` does the same locally, and `alembic/env.py` takes its URL from the app settings so there is a single source of truth. Nineteen revisions exist under `alembic/versions/`, from the initial schema through agent tables, users and tiers, ownership columns on trips, bookings and saved places, agent runs and steps, agent config and its later columns, feedback events, rate-limit counters and their hardening, content translations, and the pgvector extension.

Two migration behaviours are worth knowing:

- The **pgvector migration is Postgres-only and tolerant**: it probes `pg_available_extensions` first and only then runs `CREATE EXTENSION IF NOT EXISTS vector`; on a stock image without the extension it logs a warning instead of failing the chain, because RAG is opt-in and a failed migration would break the cross-engine test image. Its downgrade is a no-op. The `langchain-postgres` store creates its own tables on first use.
- The **rate-limit hardening migration** versions policy windows, widens epoch columns to 64-bit and indexes row expiry, isolating pre-existing counters under a sentinel identity so a new policy can never reuse them.

Migration tests in `tests/db/` run upgrade/downgrade round trips for the agent-run, feedback, rate-limit and content-translation revisions. When the ORM schema changes, a stale local `travel.db` will break the suite until it is rebuilt, since SQLite is created rather than migrated.

## Seeding reference data

`app/data/*.py` remains the source of truth for the catalog (countries, airlines, airports, cities, hotels, places, tips and summaries, visa rules, FX snapshot), plus `content_translations.<lang>.json` for checked-in catalog translations. `seed_all(session_factory)` in `app/db/seed.py` upserts all of it in one transaction and is run on every startup, by `make seed`, and by the test fixture, so it must be **idempotent**:

- Most entities are `session.merge()`d under a `deterministic_uuid` derived from their natural key (country code, hotel slug, and so on), so re-runs update in place.
- `City` has an autoincrement integer key, so it is upserted by the `(name, country)` natural key instead; merging would duplicate it.
- `agent_config` rows are created by name only when absent, leaving operator edits untouched. The two trip-research rows are created the same way, but with concrete values mirrored from a sibling row rather than NULLs (see [LLM providers and per-agent configuration](../agent/llm-providers-and-agent-config.md)).
- Translation files are validated against the supported-language list and upserted with `source="seed"`.
- After flushing, `_check_short_code_collisions` raises if two hotels or two places hash to the same short code, and the lifespan then runs `check_city_coverage` to enforce at least three hotels and three places per city.

`tests/db/test_seed.py` re-runs the seeder and asserts identical counts, no duplicate cities, stable tip ids and known totals.

### Determinism is order-sensitive

Synthetic flights and hotel availability are generated from seeded random number generators keyed on stable ids (see [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md)). Moving the catalog from Python-literal order to database rows therefore required **seed-order `position` columns** on airlines, countries, airports, hotels and places, and every repository list read orders by `position`. An unordered `SELECT` silently drifts on Postgres, because the every-boot `merge()` updates relocate heap tuples; this caused real pagination bugs, so **any new list read of a reference entity must use a deterministic `ORDER BY`**. `tests/db/test_determinism.py` compares flight and hotel-availability output against golden fixtures so both engines stay byte-equal.

## Operational notes

- Reference data is editable in the database and reflected per request, but there are no write endpoints for it; edit `app/data` and re-seed.
- Because the seeder only merges, a changed **default** in `app/data` is invisible on an existing database when the row is keyed by an unchanged natural key and the changed column is not part of the merge; verify seed changes on a fresh database.
- The Docker test stack runs the whole pytest suite against Postgres after migrating, which is the parity proof for anything touching models or queries (see [Backend test strategy](../testing/backend-test-strategy.md)).
