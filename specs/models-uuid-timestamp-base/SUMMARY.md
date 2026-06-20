# SUMMARY — models-uuid-timestamp-base

**Lane:** high-risk (schema change across every model + seeder + data-access).
**Confidence:** high (design confirmed with user via 3 decisions; full suite green).

## What changed
Every ORM model now has a uniform **UUID `id` primary key** + **`created_at`/`updated_at`**
ISO-8601 timestamps, via two mixins in `app/db/base.py` (`UUIDMixin`, `TimestampMixin`).

- Reference tables (country/airline/airport/fxrate/country_currency/visa/country_summary/
  flight_index) keep their natural keys (`code`/`iata`/`country`/`flight_id`) as **`unique`
  columns** (FKs + lookups depend on them); the 2 FKs keep pointing at those unique columns.
- `city` (was int PK) and `fx_meta` (was int singleton) and `tip` (was positional string)
  now use the uuid PK.
- Reference ids are **deterministic UUID5** (`deterministic_uuid(*parts)`) over the natural
  key → `session.merge` stays idempotent (re-seed = no-op). Hotels/places keep their
  data-file uuids; runtime rows (booking/trip/saved_place/flight_index) get UUID4.
- 9 `session.get(Model, natural_key)` CRUD sites rewritten to query the demoted column.
- `FlightIndex.remember_many` sets explicit id/created_at/updated_at; `on_conflict` still
  targets the (now unique) `flight_id`.

## Rationale / Alternatives
- **UUID id DB-internal; API keyed on natural codes** (user decision) → no response-schema
  change, no FE codegen impact. Alternative (expose uuid in responses) rejected as a public
  contract break.
- **Deterministic UUID5** chosen over uuid4 to preserve the documented idempotent-merge
  invariant.

### Verify
| Check | Command | Exit | Notes |
|---|---|---|---|
| Lint | `ruff check app` | 0 | all checks passed |
| Migration drift | `alembic check` | 0 | "No new upgrade operations detected" |
| Migration applies | `rm -f travel.db && alembic upgrade head` | 0 | single migration `7b300c56abff` |
| Seed idempotency | `make seed && make seed` | 0 | counts identical across runs |
| Full suite | `make test` | 0 | 665 passed |

### Deviations
- Rule 1 — Updated 5 tests asserting the old design (tip positional-id format ×3,
  booking column set, `s.get(FxMeta, 1)` singleton lookup) to the new uuid/timestamp design.
- Rule 1 — Removed orphaned `_slug`/`prefix` in `seed.py` (made dead by the tip-id change).

### Rollback
- Revert code: `git checkout -- app/db app/crud tests && git stash` (changes unstaged).
- Regenerate prior migration: delete `alembic/versions/7b300c56abff_*.py`, restore models, `alembic revision --autogenerate`.

## Not verified
- Postgres parity (`make test-docker`) not yet run — local SQLite suite is fully green.
