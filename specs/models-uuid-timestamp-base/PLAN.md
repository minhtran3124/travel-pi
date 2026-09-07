---
slug: models-uuid-timestamp-base
status: shipped
owner: Minh Tran
created: 2026-06-19
---

# Uniform UUID id + timestamp base for every ORM model

## 1. Motivation
The `refactor/models-uuid-timestamp-base` branch name promises a uuid id +
timestamp base on every model, but reality diverged: reference tables still use
natural/int PKs, `Base` is an empty `DeclarativeBase`, and there is no
`updated_at` anywhere. Make every ORM model use a uuid `id` PK plus
`created_at`/`updated_at`.

## 2. Decisions (confirmed with user)
- **UUID5 deterministic** ids for reference data (keeps `session.merge` idempotent).
- **UUID id is DB-internal** — API stays keyed on natural codes (country code, IATA, …). No response-schema changes.
- **Scope:** uuid id + `created_at` + `updated_at` on ALL models.
- Natural keys (`code`/`iata`/`country`/`name`) are **kept as `unique` columns** (FKs + lookups depend on them); the two FKs (`city.country→countries.name`, `airport.country_code→countries.code`) keep pointing at those unique columns — no repointing.
- `created_at`/`updated_at` are **String ISO-8601** (matches existing `created_at` type → no serialization change for booking/trip/saved_place).

## 3. Success Criteria
- `alembic check` → no drift; single migration applies clean on empty DB.
- `make seed` idempotent (re-seed twice → same row counts, stable ids).
- `make test` green (minus the pre-existing, unrelated booking_service import bug, which is fixed as a Rule-3 blocker).

## 4. Tasks

```xml
<task id="1.1" wave="1">
  <files>app/db/base.py</files>
  <action>Add UUIDMixin (uuid4 default PK) + TimestampMixin (ISO created_at/updated_at) + new_uuid()/deterministic_uuid() helpers (UUID5 over a stable namespace).</action>
  <verify>python -c "from app.db.base import UUIDMixin, TimestampMixin, deterministic_uuid, new_uuid; print(deterministic_uuid('country','VN'))"</verify>
  <done>Mixins + helpers importable; deterministic_uuid stable.</done>
</task>
```

```xml
<task id="2.1" wave="2">
  <files>app/db/models/*.py</files>
  <action>Every model inherits (UUIDMixin, TimestampMixin, Base). Demote natural PKs (country.code, airline.code, airport.iata, fxrate.code, country_currency.country, visa.country, country_summary.country, flight_index.flight_id) to unique non-PK columns. Replace city int PK, fx_meta int PK, tip positional-string PK with the uuid id. Drop per-model created_at decls (now from mixin).</action>
  <verify>python -c "from app.db import models; from app.db.base import Base; print(len(Base.metadata.tables))"</verify>
  <done>All models import; every table has id/created_at/updated_at.</done>
</task>
```

```xml
<task id="3.1" wave="3">
  <files>app/db/seed.py</files>
  <action>Set id=deterministic_uuid(<entity>, <natural key>) for every reference entity (country/airline/airport/city/tip/country_summary/visa/fxrate/country_currency/fx_meta). Hotels/places keep their data-file uuids. City keeps natural-key upsert.</action>
  <verify>rm -f travel.db && alembic upgrade head && make seed && make seed && python -c "import sqlite3;c=sqlite3.connect('travel.db');print(c.execute('select count(*) from countries').fetchone())"</verify>
  <done>Re-seed is a no-op (stable counts), reference rows carry uuid ids.</done>
</task>
```

```xml
<task id="4.1" wave="3">
  <files>app/crud/country.py, app/crud/airline.py, app/crud/airport.py, app/crud/fx.py, app/crud/visa.py, app/crud/tip.py, app/crud/flight.py</files>
  <action>Rewrite the 9 `session.get(Model, natural_key)` sites to query the demoted natural column (`.where(col == val)`); fx_meta → select().limit(1). FlightIndex.lookup by flight_id; remember_many sets explicit id/created_at/updated_at per row.</action>
  <verify>ruff check app/crud</verify>
  <done>No `session.get` against a natural key remains; lint clean.</done>
</task>
```

```xml
<task id="5.1" wave="4">
  <files>alembic/versions/*.py, tests/**</files>
  <action>Regenerate the single initial migration. Update tests asserting the old tip-id format (tip_country_...) to accept uuid ids. Fix pre-existing booking_service confirmation_code_for import (Rule-3 blocker).</action>
  <verify>make test</verify>
  <done>alembic check clean; full suite green.</done>
</task>
```

## 5. Risks
- Tip API `id` value format changes (positional → uuid5). Documented opaque/stable; tests updated.
- `session.get` PK lookups silently break if any are missed → caught by suite.

## 6. Status Log
- 2026-06-19: plan created; executing.
- 2026-06-19: shipped. All 18 models on uuid id + timestamps; migration `7b300c56abff` drift-clean; seed idempotent; `make test` 665 passed. See SUMMARY.md. Postgres parity (`make test-docker`) not yet run.

- 2026-09-03 — status corrected to `shipped`. Verified by artifact on `main`, not by the log:
  this plan's deliverables are present in the shipped code. It had been left `active`, which made
  `hooks/lib/lane.sh` resolve it as the plan under work for unrelated commits.
