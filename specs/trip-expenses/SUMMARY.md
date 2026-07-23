# Trip Expenses — Intake Summary

**Lane:** normal
**Confidence:** high
**Reason:** Greenfield child-resource of Trip, follows the established `SavedPlace` stack
template (model → repo → service → router) end-to-end. Design forks resolved with the user
(A + A below). The only elevated-risk surfaces are *additive only*: new endpoints
(public-contract hard gate) and a new table (migration hard gate) — both reversible.

## Goal

Backend API/service layer so a traveller can record on-the-ground spending during a trip
(e.g. "breakfast 50,000 VND"), categorised, in any currency, and see totals vs. the trip
budget. This is the data layer the future travel-assistant/chatbot will call; **NLU parsing
of free text ("breakfast 50k" → amount/category) is out of scope here** — that's the agent
layer, built later on top of these endpoints.

## Resolved design decisions (with user)

- **Budget link → A: separate ledger + actual-vs-planned view.** New `expenses` table and
  endpoints, fully independent of the existing booking-based `/budget`. The expense summary
  endpoint *reads* existing budget caps + booked spend and adds expense actuals to give one
  planned-vs-actual rollup at the trip-total level. The existing `/budget` contract is
  **not modified** (booking categories flights/hotels/activities/buffer ≠ expense categories,
  so only a trip-total comparison is meaningful).
- **Currency → A: original + normalize to base (USD).** Each expense stores its original
  `amount` + `currency` (e.g. 50000 VND) AND a normalized `amount_usd` + the `fx_rate` used
  (snapshot, via existing `FxRepository`). Summaries aggregate in USD and keep a per-currency
  breakdown. USD is the base because the budget is USD.

## Rationale

Folding expenses into `/budget` (option B) would couple two different taxonomies/currencies
and risk regressing 685 tests + the `/budget` public contract. A fully independent ledger
(option C) loses the "how much of my budget have I spent" answer the assistant needs most.
Option A gives clean separation with the one comparison that matters, all additive.

## Alternatives considered

- **B (fold into budget):** rejected — couples planning caps with on-trip actuals; high
  regression risk on a hard-gated contract.
- **C (independent, no link):** rejected — drops the budget comparison.
- **Single trip currency** (currency option B): rejected — cannot record the literal "50,000
  VND on a USD-budget trip" example without manual conversion.

## Hard gates acknowledged

- **Public contract** (new endpoints): per [[public-contract-hard-gate]] memory, the
  risk-corroboration hook blocks new-endpoint commits at `normal` lane; authorize the commit
  with `RISK_WARN_CATEGORIES="public-contract"`. Additive only — no existing route changes.
- **Migration** (new `expenses` table): additive `create_table`, reversible via `downgrade`.

### Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| Migration applies | `.venv/bin/alembic upgrade head` | 0 | wave 1 |
| Full suite (SQLite) | `make test` | 0 | 750 passed |
| Cross-engine (Postgres) | `make test-docker` | 0 | 750 passed |
| Lint | `ruff check app && ruff format --check app` | — | run before PR |

### Deviations

- Rule 2 — Added `app/routers/tags.py` (new `expenses` tag). Not listed in task 4.1 `<files>` but required for every router group. Wave 4.
- Rule 2 — Updated `tests/test_db_models.py` (added `"expenses"` to the hardcoded table set). Required to keep the suite green after new table. Wave 5.

### Rollback

- Revert code: `git revert <sha>` (or drop the feature branch before merge).
- Revert migration: `.venv/bin/alembic downgrade -1` (drops `expenses` table).
- Rebuild dev DB after downgrade: `rm travel.db && make seed` (per
  [[stale-travel-db-breaks-suite-on-schema-change]]).
