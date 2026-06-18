<!--
  Header block is machine-read by hooks/risk-corroboration.sh (Lane:) and the
  trust-metrics ledger.
-->

# migration-helper — Summary

Lane: normal
Confidence: high
Reason: Touches SQLite migration code (relocates existing `ALTER TABLE ADD COLUMN` statements into a shared helper) → mechanically trips the `data-loss/migration` hard gate, but introduces NO new or destructive migration — it is a behavior-preserving DRY refactor of three already-shipped, additive, idempotent column migrations. 3 flags.
Flags: data-model, existing-behavior, weak-proof
Affects: crud/ persistence layer — `app/crud/trip.py` (booking_id, idempotency_key, deleted_at migrations) + `app/crud/booking.py` (unique-index migration); new `app/crud/_migrations.py`
Input-type: maintenance

> `Lane` drives **ceremony**. `Confidence` drives **interruption**. A hard gate forces
> `high-risk` unless a human narrows/authorizes. This task trips a hard gate → escalated.

### Intent

> A0 — Migration discipline: extract the repeated SQLite PRAGMA table_info + ALTER TABLE ADD COLUMN pattern (used for booking_id, idempotency_key, deleted_at) into a shared reusable helper in crud/, so every Phase A schema change uses one consistent, tested migration path. See specs/agent-platform-roadmap/CHECKLIST.md A0.

## What changed

New `app/crud/_migrations.py` with `ensure_column()` (PRAGMA-guarded `ALTER TABLE ADD COLUMN`,
returns True iff added) and `ensure_unique_partial_index()` (idempotent UNIQUE partial index).
`crud/trip.py` (booking_id, idempotency_key×2 + indexes, deleted_at) and `crud/booking.py`
(idempotency_key, confirmation_code + backfill, unique index) `init_db()` now call them instead of
inline PRAGMA/ALTER. Behavior-identical — verified across all 4 column-presence DB states by the
correctness review, plus the full suite green. +3 helper unit tests (incl. legacy-DB ALTER path).

### Rationale

The three column migrations (`booking_id`, `idempotency_key`, `deleted_at`) each re-implement the
same `PRAGMA table_info` → `ALTER TABLE ADD COLUMN` guard inline. Extracting `ensure_column()` (+
`ensure_unique_partial_index()`) into `app/crud/_migrations.py` removes the duplication and gives
every Phase A schema change one tested path. The refactor must be **behavior-identical** — same
columns, same idempotency, verified on both a fresh DB (CREATE TABLE path) and a legacy DB
(ALTER path).

### Alternatives considered

- Base-class method on a shared repository — rejected for now: the two repos don't share a base; a
  small module-level helper is lighter (YAGNI).
- Adopt Alembic — rejected: out of scope and over-heavy for a mock backend with raw `sqlite3`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Helper unit tests | `.venv/bin/python -m pytest tests/test_migrations.py -v` | 0 | 3 passed (incl. legacy-DB ALTER) |
| Full suite (behavior-identical proof) | `.venv/bin/python -m pytest tests/ -q` | 0 | 573 passed (was 570; +3) |
| Lint (touched) | `ruff check app/crud tests/test_migrations.py` | 0 | clean (flight.py drift is pre-existing, untouched) |

### Review gates

- Combined spec + quality + **behavior-identity correctness** review (sonnet) ✅ — all 4
  column-presence DB states traced; confirmation_code backfill condition preserved exactly.
- Intent == spec (extract migration pattern into a tested shared helper, behavior-identical) — met.

### Deviations

- none

### Rollback

- `git revert <sha>` — pure refactor, additive helper; reverting restores the inline migrations.
