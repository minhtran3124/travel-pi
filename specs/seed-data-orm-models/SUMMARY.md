# SUMMARY — seed-data-orm-models

Lane: high-risk
Confidence: low (approach forks open — see ESCALATIONS E1)
Reason: Hard gate (data migration — seed data → DB tables) + 5 flags (data-model, public-contracts, existing-behavior, weak-proof, multi-domain).
Flags: data-model, public-contracts, existing-behavior, weak-proof, multi-domain
Affects: `app/db/models.py` (→ package), `app/schemas/*` (FE-codegen response contracts), `app/data/*` (9 seed entities + import-time guards), `app/core/invariants.py`, `core/text.py` consumers, ~15 services/routers, Alembic migrations. Deterministic-seed invariants (flights/hotel availability MD5; stable hotel/place UUIDs).
Input-type: New initiative (multi-entity persistence + model restructure + schema refactor)
Route: high-risk full chain — /brainstorming → /xia2 → /writing-plans → /using-git-worktrees → /subagent-driven-development (record decision via /compound). Brainstorming resolves the open approach forks (escalation E1).
Escalate: yes (hard gate + low confidence on approach)

### Intent

User request, verbatim (across turns):

- "review the @app/data/, we have a lot of data for entities. I want to create multiple models to match for each entity. And update related code too"
- (Model type chosen) "SQLAlchemy ORM models (persist to DB)"
- (Placement chosen) "no, create models folder, and create indiviual file for each model, ex: models/airports.py, models/hotels.py, etc ... Check the app/schemas/ too, if we need to refactor, let do it. Dont be scare"

### Rationale

Today `app/data/*` is read-only, in-memory Python (typed loosely as `list[dict]`/`dict`), with
import-time consistency guards (everything validates against `countries.py`, failing loudly at
startup). It's consumed directly as dicts by ~15 services/routers, and `core/text.py` fuzzy-matches
in-memory over those lists. The user wants these 9 entities persisted to the DB via SQLAlchemy ORM,
the single `app/db/models.py` split into a `models/` package (one file per entity, incl. the
existing booking/trip/saved_place/flight migration entities), and `app/schemas/` refactored where
it helps. This rides on the unmerged ORM/Postgres + Alembic work (branch `feat/docker-postgres-setup`,
PR #11).

### Alternatives / open approach forks (why confidence is low → resolve in brainstorming)

1. **Seeding strategy:** idempotent upsert on startup (lifespan) · Alembic data migration · standalone
   seed script (`make seed`). Affects reproducibility + test setup.
2. **Read-path strategy (the big one):** (a) query the DB per request, or (b) load DB rows into an
   in-memory cache at startup and keep the current fast in-memory `core/text.py` fuzzy-matching.
   (b) preserves behavior/perf with least churn; (a) is "truly DB-backed" but changes perf and every
   consumer. Materially different blast radius.
3. **Fate of `app/data/*.py`:** keep as the seed *source* that populates the DB (recommended — preserves
   the countries.py source-of-truth + guards) vs delete and make the DB authoritative.
4. **Import-time guards:** where validation moves (seed-time vs retained at import) — must not weaken
   (hard-gate sensitive).
5. **Deterministic invariants:** flights/hotel-availability are generated from MD5 of seed values and
   hotel/place UUIDs are stable — these MUST be preserved byte-for-byte regardless of storage.
6. **Schema refactor extent:** "don't be scared," but `app/schemas/` are the FE's TS-codegen contract —
   bound the public-contract changes.
7. **Branch base:** depends on PR #11 (unmerged) — build on `feat/docker-postgres-setup` vs wait for v2 merge.

### Verify (high-risk lane evidence)

Implemented via subagent-driven-development (6 chunks A–F + a correctness-fix pass); spec + quality review per chunk, then final correctness + intent gates. BASE `f0b5062` → HEAD (20 commits, ~60 files).

- **SQLite suite:** `pytest tests/ -q` → **665 passed** (621 baseline + seed/repo/determinism tests; minus the obsolete docker-postgres legacy-migration tests already removed on the parent branch).
- **Cross-engine parity:** `make test-docker` → **665 passed on real Postgres 17 / Python 3.12** after every read-path chunk.
- **Determinism (the hardest invariant):** golden fixtures captured on the clean pre-migration tree (`tests/db/fixtures/golden_{flights,hotel_availability}.json`); `tests/db/test_determinism.py` asserts the DB-backed endpoints **byte-equal** them on both engines. Airline + airport + hotel/place ordering pinned by `position` columns; flight `rng.choice` and board `Random.sample` reproduce pre-migration output exactly.
- **Seeder idempotent** on a non-empty Postgres (3× re-seed → stable counts; City via `(name,country)` natural-key upsert; tip ids byte-identical to the old `tip_service`; short-code collision guard moved to seed time).
- **Alembic:** `0002_seed_entities` (12 tables + FKs `airports.country_code→countries.code`, `cities.country→countries.name` + unique indexes); up/down/up round-trip + `alembic check` no-drift on Postgres.
- **Sweep:** `grep -rn "from app.data" app/` → only `app/db/seed.py` (app/data kept as the guarded source; its import-time guards run at seed time).
- **Public contract unchanged:** `app/schemas/*` zero diff; operationIds + API tests green.
- **Final correctness review** (adversarial, blind to plan): 2 P1 + 1 P2 (PG pagination/board/tie-order instability from the every-boot `merge()` relocating heap tuples) → **fixed `83a2914`** (seed-order `position` on Airport/Hotel/Place + `ORDER BY position`; regression tests fail-without/pass-with).
- **Final intent review** (blind to plan, oracle = the verbatim request): all 6 clauses satisfied; no gap/drift; one low-severity justified excess (determinism-guard harness).

### Deviations

- Rule 1 — Golden-fixture capture used the real route `GET /hotels/availability?city=…` (the plan's illustrative `/hotels/{id}/availability` doesn't exist). `tests/db/_capture_golden.py`.
- Rule 1 — Fixed a latent Python-3.12-vs-3.14 annotation bug (`list` builtin shadow) with `from __future__ import annotations` in `app/crud/country.py` (surfaced only in the Docker 3.12 container).
- Rule 1 — Corrected a determinism regression introduced mid-build: `airport_repo.list()` ordering changed the board sample → added `position` columns to restore exact pre-migration order. Commit `83a2914`.

### Status

Implementation complete; all gates green (665 SQLite + Postgres). Ready for `finishing-a-development-branch`. Branch stacks on `feat/docker-postgres-setup` (PR #11, unmerged).
