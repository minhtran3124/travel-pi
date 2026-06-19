<!--
  Header block is machine-read by hooks/risk-corroboration.sh (Lane:) and the
  trust-metrics ledger.
-->

# trip-budget — Summary

Lane: normal
Confidence: high (low at intake → escalated → resolved 2026-06-19)
Reason: 3 flags (data-model, public-contract, existing-behavior). The data-loss/migration hard gate is mechanically tripped by new stored budget-cap columns, but it is an additive, idempotent `ensure_column` migration — the standing A0 convention ("every subsequent Phase A item MUST use ensure_column + add a legacy-DB test") applies by analogy and keeps the lane at normal as A3 did. Intake confidence was **low** on a design-shape axis; escalated and resolved by the user (per-category caps · reuse `estimate_trip` for planned · hard 409 at item-add) → now unblocked.
Flags: data-model, public-contract, existing-behavior
Affects: trips budget/itinerary contract — `app/schemas/trip.py` (new `TripBudget*` models; per-category caps; `TripDetail` may gain a budget rollup), `app/crud/trip.py` (`trips` DDL + `ensure_column` migration + column list for the per-category caps storage), `app/services/trip_service.py` (budget rollup-by-category reusing `estimate_trip` for "planned" + per-category 409-on-exceed gate in `add_trip_item`), `app/routers/trips.py` (new `GET`/`POST /trips/{id}/budget`)
Input-type: spec slice
Route: normal — /using-git-worktrees → /writing-plans → /subagent-driven-development (PLAN.md triggered: ~4 files > 2). Phase A migration convention: add a legacy-DB ALTER-path test. **Unblocked** — escalation resolved (see ESCALATIONS.md).
Escalate: resolved — design-shape fork confirmed by user (per-category caps · reuse `estimate_trip` breakdown for "planned" · hard 409 at `POST /trips/{id}/items`).

> `Lane` drives **ceremony**. `Confidence` drives **interruption**. The migration hard gate
> is waived to **normal** by the standing A0 `ensure_column` convention (additive/idempotent);
> the **low confidence** is a separate axis and is what triggers the human gate here.

### Intent

> '12. ⬜ Budget endpoints" from @AGENT_IMPROVEMENTS.md

Item #12 (verbatim from `AGENT_IMPROVEMENTS.md`):

> ### 12. ⬜ Budget endpoints
>
> - `GET /trips/{id}/budget` — by category (flights/hotels/activities/buffer), planned vs. spent
> - `POST /trips/{id}/budget` — set a target; bookings that would exceed it return a 409 with a `hint`

Cross-reference (`AGENT_IMPROVEMENTS.md` #1): "no `remaining_budget` field yet (no per-trip
budget target is stored — see #12; `POST /trips/estimate` exists as a stateless estimator)."

### Risk checklist (10 flags)

| # | Flag | Fires? | Why |
|---|---|---|---|
| 1 | Auth | no | — |
| 2 | Authorization | no | — |
| 3 | Data model | **yes** | a stored per-trip budget target must persist → new `trips.budget_target` column + idempotent `ensure_column` migration |
| 4 | Audit/security | no | — |
| 5 | External systems | no | — |
| 6 | Public contracts | **yes** | two **new** endpoints (`GET`/`POST /trips/{id}/budget`) + new `response_model`s; `TripDetail` likely gains `remaining_budget` (FE codegen TS changes) |
| 7 | Cross-platform | no | — |
| 8 | Existing behavior | **yes** | the 409-on-exceed gate changes an existing mutating path (`POST /trips/{id}/items` when a linked booking would push spend past target) — test-covered itinerary behavior gains a constraint |
| 9 | Weak proof | no | trip value-layer / estimate paths are well test-covered; the spec adds budget + legacy-DB tests |
| 10 | Multi-domain | no | single domain (trips) |

3 flags → **normal**.

### Hard-gate check

- **Data loss / migration:** mechanically tripped (new `budget_target` column). **Waived to normal** — additive, idempotent (`ensure_column`), non-destructive, nullable (no backfill needed; absent target = no budget set). A0 convention applies **by analogy** (budget endpoints are not a formal A-numbered item but are data-normalization in spirit). Obligation carried forward: **add a legacy-DB ALTER-path test**.
- **Removing/weakening validation:** not hit — the 409 *adds* a constraint, it does not weaken one.
- **Public contract:** two new endpoints. Per [[public-contract-hard-gate]], the local `risk-corroboration.sh` would block new-endpoint commits at `normal` and require `RISK_WARN_CATEGORIES="public-contract"` to authorize — but **no `.claude/hooks/` is present in this repo**, so there is no mechanical block today. Still recorded as a flag.
- All other hard gates: not hit.

### Rationale

A stored target is the missing primitive behind `remaining_budget` (#1) and the agent's
"am I within budget?" question. `total_spent` (booked rollup) and `estimate_trip`
(category breakdown: flights/hotels/activities/buffer) already exist, so the GET rollup can
largely **compose existing parts** rather than introduce new computation. The fork is
*shape*, not *feasibility* — hence low confidence, not a high lane.

### Alternatives considered

- **Single total** target — *rejected by user*; chose **per-category caps**
  (`{flights, hotels, activities, buffer}`, each a separate cap).
- **Enforce 409 at the raw `/flights/book` · `/hotels/book`** — rejected on its face: bookings
  are decoupled from trips (linked only via `trip_item.booking_id`), so they cannot know a
  trip's budget. The only place that knows both is `POST /trips/{id}/items` — *confirmed*.
- **Per-item `planned_cost` field** as the source of "planned" — *rejected by user* in favor of
  **reusing `estimate_trip`'s category breakdown**, avoiding a second data-model change.

### Resolved decisions (escalation closed 2026-06-19 — see ESCALATIONS.md)

1. **Target shape:** **per-category caps** — flights / hotels / activities / buffer, each an
   independent cap. Storage shape (4 nullable columns vs one JSON `budget_caps` column via
   `ensure_column`) is a PLAN-level detail; lean toward a single JSON column to keep the
   migration additive and the cap set extensible.
2. **"planned" source:** **the per-category cap IS "planned"** (clarified 2026-06-19 after reading
   `estimate_trip`: it is a stateless calculator needing inputs the stored trip lacks, and its
   categories don't map to the budget categories). GET returns per category `{cap, spent, remaining}`;
   "spent" rolls up linked, non-cancelled bookings grouped by `BookingType`. `estimate_trip` stays the
   separate `/trips/estimate` what-if tool — **not** used by `/budget`. Note: `BookingType` is only
   `FLIGHT | HOTEL` today, so activities/buffer `spent` = 0 until activity booking (#15) ships.
3. **Enforcement:** **hard 409** in `add_trip_item` when a linked, booked item would push that
   **category's** spent past that category's cap; envelope carries a `hint` naming the category,
   the overage, and the cap. Categories with no cap set are unconstrained.

### Implementation (shipped on `feat/trip-budget`)

Storage chose the **single JSON `budget_caps` column** option (additive `ensure_column`), as the
decision-1 lean predicted. Three commits off `v2` (`77dc281`):

- `af6362e` — `BudgetCategory` enum + `CategoryBudget`/`BudgetCategories`/`TripBudget`/`TripBudgetSet`
  schemas + `budget_caps` column + `get_budget_caps`/`set_budget_caps` + legacy-DB ALTER test.
- `afff1b3` — `_resolve_bookings` (extracted, behavior-preserving) + `_spend_by_category` +
  `get_trip_budget`/`set_trip_budget`/`_build_budget` + `_enforce_budget` (409) wired into
  `add_item`; `GET`/`POST /trips/{id}/budget` routes; `add_item` route `→ error_responses(404,409,422)`.
- `922c2ef` — `APIS.md` documentation.

### Verify (DONE)

| Check | Command | Result |
| --- | --- | --- |
| Budget suite | `.venv/bin/python -m pytest tests/test_trip_budget.py -q` | 14 passed (enum/schema/no-cap/set/replace/422/404/spend/409 boundary + no-cap/no-booking) |
| Trip regression (refactor safety) | `pytest tests/test_trips.py tests/test_trip_value_layer_api.py tests/test_trip_value_layer_service.py` | green — `total_spent`/gaps unchanged |
| Legacy-DB ALTER (A0 obligation) | `tests/test_trips.py::test_init_db_adds_budget_caps_to_legacy_trips` | passed — `budget_caps` added, old rows read `{}` |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | **615 passed**, 2 pre-existing baseline failures only (`test_meta::test_root_endpoints_is_list`, `test_operation_ids` — Starlette 1.2 route-introspection drift, unrelated) |
| Lint | `ruff check app tests` | clean on touched files |

### Review gates

- Per-chunk **spec review** (oracle: PLAN) ✅ ×2 — all Task 1–6 requirements present, no scope creep.
- Per-chunk **quality review** (maintainability) ✅ ×2 — fixed: `init_db` docstring migration
  inventory; test-isolation teardown for the booking singleton (yield-fixture restore).
- Final **`/correctness-review`** (blind to plan, capable model) ✅ — zero runtime bugs; traced
  JSON NULL→`{}`, replay-before-enforce ordering, strict `>` boundary, `cap=0` enforced (not
  falsy), `_resolve_bookings` extraction preserving `total_spent`/gaps, all-4-categories contract.
- Final **`/intent-review`** (blind to plan; oracle: this `### Intent` + Resolved decisions) ✅ —
  no gap/drift/excess; both endpoint bullets + all four decisions delivered, 409 hint populated.

### Deviations

- Rule 1 — `{c: 0.0 for c in BudgetCategory}` → `dict.fromkeys(BudgetCategory, 0.0)` (ruff `C420`; behaviour-identical). `app/services/trip_service.py`. Commit `afff1b3`.
- Rule 2 — Test infra: `_flight_booking` fixture repoints the module-level `_booking_service` singleton at the client's isolated store (the trip service resolves bookings via the singleton, not FastAPI DI, so a conftest-overridden booking was invisible). Yield-fixture restores the original in `finally`. `tests/test_trip_budget.py`. Commit `afff1b3`.
- Rule 3 — ruff `I001` import reorder in the new test file. `tests/test_trip_budget.py`. Commit `afff1b3`.
