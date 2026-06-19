# ESCALATIONS — seed-data-orm-models

Default: deny-on-no-response (no DB-migration/seed code until E1 is resolved).

## E1 — Persistence approach forks (open)

**Trigger:** Hard gate (seed data → DB migration) + low confidence on approach.

**Questions (to resolve in /brainstorming):**
- Seeding strategy: startup upsert · Alembic data migration · seed script.
- Read-path: in-memory cache hydrated from DB (preserve fast fuzzy-match) vs per-request DB queries.
- Fate of `app/data/*.py`: keep as seed source vs delete.
- Schema refactor extent (public-contract bound).
- Branch base: build on `feat/docker-postgres-setup` (PR #11, unmerged) vs wait for v2 merge.

**Status:** RESOLVED (2026-06-19, brainstorming) — see design.md "Decisions" table.
- Read-path: **per-request DB queries** (data live/editable).
- Fuzzy/JSON-list filters: **kept in Python** (portable; preserves core/text.py behavior).
- Seeding: **idempotent startup upsert** + `make seed` + test fixture.
- `app/data/*`: **kept as seed source** (guards intact).
- Schemas: public response contract **unchanged**.
- Write side: **read-only now** (no write endpoints).
- Branch: stack on `feat/docker-postgres-setup` as `feat/seed-data-orm-models`, Alembic `0002`.
