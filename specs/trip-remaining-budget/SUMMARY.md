<!--
  Header block is machine-read by .claude/hooks/risk-corroboration.sh (Lane:) and the
  trust-metrics ledger.
-->

# trip-remaining-budget — Summary

Lane: normal
Confidence: high
Reason: 1 additive-contract flag — a new optional `remaining_budget` field on the `TripDetail` response. No new endpoint, no migration, no ORM/DB-schema change; reuses the budget-cap storage + rollup shipped in #12 (`specs/trip-budget`). No hard gate tripped (no new route, no `ensure_column`).
Flags: public-contract (additive, non-breaking)
Affects: trips detail contract — `app/schemas/trip.py` (`TripDetail` gains `remaining_budget`), `app/services/trip_service.py` (`get_trip_detail` populates it from `get_budget_caps`)
Input-type: change request (final slice of #1 in `AGENT_IMPROVEMENTS.md`)
Route: normal — feature branch off v3, direct implement + test, this record
Escalate: no

> `Lane` drives ceremony; `Confidence` drives interruption. Direction had a single
> plausible interpretation (surface `TripBudget.total_remaining` on `TripDetail`), so
> high confidence → no human gate.

### Intent

> "the strongest next item is #1 `remaining_budget` rollup now that #12 unblocked it" — user
> confirmed with "ok" to implement.

From `AGENT_IMPROVEMENTS.md` #1: the trip value-layer is complete except a `remaining_budget`
rollup on `TripDetail`. The per-category budget caps it depended on shipped in #12; the value
`total_remaining` (= summed caps − total_spent) already exists on `GET /trips/{id}/budget`.
This surfaces the same number on `GET /trips/{id}` so an agent gets it in one call instead of
two.

### Design

- `remaining_budget: float | None` on `TripDetail` (`app/schemas/trip.py`). Null when no cap
  is set anywhere; negative when over budget — same semantics as `TripBudget.total_remaining`.
- `get_trip_detail` fetches `self._repo.get_budget_caps(trip_id)` and computes
  `sum(caps.values()) - total_spent`, reusing the already-computed `total_spent` so the two
  fields stay mutually consistent on the same response. `caps == {}` → `None`.
- Computed fresh per call, nothing extra stored.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Lint | `ruff check app/schemas/trip.py app/services/trip_service.py` | 0 | All checks passed |
| Budget tests | `python -m pytest tests/api/trip/test_trip_budget.py -q` | 0 | 15 passed (12 prior + 3 new) |
| Trip suite | `python -m pytest tests/api/trip/ -q` | 0 | 88 passed — no regression in `get_trip_detail` |

New tests (`tests/api/trip/test_trip_budget.py`): `remaining_budget` is null without caps;
equals summed cap when unspent; nets linked booking spend and matches `/budget`'s
`total_remaining`.

### Rollback

- Revert code: `git revert <sha>` (additive field + one service block; no migration, no data).

### Deviations

- None (Rule 1–3). Note: `.claude/hooks/blast-radius-check.sh` warned all four edited files
  were outside the *stale* active-plan pointer (`specs/models-uuid-timestamp-base/PLAN.md`,
  an unrelated finished feature). False positive — this is a separate, intentional feature
  with its own spec dir; not scope creep.
