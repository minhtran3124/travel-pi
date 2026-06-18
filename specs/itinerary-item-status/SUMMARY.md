<!--
  Header block is machine-read by hooks/risk-corroboration.sh (Lane:) and the
  trust-metrics ledger.
-->

# itinerary-item-status — Summary

Lane: normal
Confidence: high
Reason: 3 flags (data-model, public-contract, existing-behavior). The data-loss/migration hard gate is mechanically tripped by the new `status` column, but it is an additive, idempotent, non-destructive `ensure_column` migration with a `pending` default — the standing Phase A convention (CHECKLIST A0: "every subsequent Phase A item MUST use ensure_column + add a legacy-DB test") pre-authorizes exactly this boundary, so it stays normal as A0 did.
Flags: data-model, public-contract, existing-behavior
Affects: trips itinerary contract — `app/enums.py` (new `TripItemStatus`), `app/schemas/trip.py` (`TripItem*` gains `status`), `app/crud/trip.py` (`trip_items` DDL + `_ITEM_COLUMNS` + INSERT/UPDATE + `init_db` migration), `app/services/trip_service.py` (gap-detection + `get_day_plan`)
Input-type: spec slice
Route: normal — /using-git-worktrees → /writing-plans → /subagent-driven-development (PLAN.md triggered: ~4 files > 2). Phase A migration convention: add a legacy-DB ALTER-path test.
Escalate: no — migration boundary pre-authorized by the standing Phase A `ensure_column` convention; direction unambiguous (enum values + default spelled out in the checklist).

> `Lane` drives **ceremony**. `Confidence` drives **interruption**. A hard gate forces
> `high-risk` unless a human narrows/authorizes. Here the human-authored CHECKLIST A0
> convention is the standing authorization for additive `ensure_column` migrations → normal.

### Intent

> for A3 in agent-platform-roadmap/CHECKLIST.md

A3 (verbatim from `specs/agent-platform-roadmap/CHECKLIST.md`):

> ### A3. ⬜ Enum `status` cho itinerary item (`pending | booked | constraint | optional`) [#1]
> > Một trường — agent diễn đạt được phần kế hoạch mềm vs cứng và ràng buộc bắt buộc.
> - [ ] Thêm `TripItemStatus` enum vào `app/enums.py`.
> - [ ] Thêm field `status` vào `TripItem` schema + cột `status` + migration.
> - [ ] Cập nhật day-plan: hiển thị status; gap-detection có thể bỏ qua `optional`.
> - [ ] Test: tạo item với từng status, default = `pending`.
> - *Phụ thuộc:* A0. *Công sức:* Thấp. *Giá trị:* Cao (ngữ nghĩa lập kế hoạch cho agent).

### Risk checklist (10 flags)

| # | Flag | Fires? | Why |
|---|---|---|---|
| 1 | Auth | no | — |
| 2 | Authorization | no | — |
| 3 | Data model | **yes** | new `status` column on `trip_items` + idempotent column migration |
| 4 | Audit/security | no | — |
| 5 | External systems | no | — |
| 6 | Public contracts | **yes** | `TripItem` response_model gains a `status` field (FE codegen TS types change) — additive / non-breaking |
| 7 | Cross-platform | no | — |
| 8 | Existing behavior | **yes** | gap-detection + `get_day_plan` change (skip `optional`); `TripItemCreate/Update` gain a field — test-covered itinerary behavior |
| 9 | Weak proof | no | itinerary + day-plan paths are well test-covered; spec adds per-status tests |
| 10 | Multi-domain | no | single domain (trips) |

3 flags → **normal**.

### Hard-gate check

- **Data loss / migration:** mechanically tripped (new column migration). **Waived to normal** — additive, idempotent (`ensure_column`), non-destructive, `pending` default backfill; pre-authorized by the standing Phase A convention (A0). Phase A obligation carried forward: **add a legacy-DB ALTER-path test**.
- **Public contract:** the `status` field is additive/non-breaking on an existing model — no new/changed endpoint. (Per [[public-contract-hard-gate]], if the local corroboration hook flags it, authorize with `RISK_WARN_CATEGORIES="public-contract"` at commit; no hook is currently present in this repo.)
- All other hard gates: not hit.

### Rationale

One field, four states (`pending | booked | constraint | optional`), lets the agent express soft vs hard plan and hard constraints. The additive `ensure_column` path keeps existing trip-item IDs/rows intact (default `pending`). `status` belongs on `TripItemCreate` (settable at create, default `pending`) so it flows through create/update/read uniformly.

### Alternatives considered

- Free-text `status` string — rejected: loses the single-source-of-truth enum + JSON-transparent `str, Enum` convention in `app/enums.py`.
- Separate boolean flags (`is_optional`, `is_booked`) — rejected: not mutually exclusive, harder for the agent to reason about than one closed enum.

### Open assumptions (confidence high)

- gap-detection ("Day N has no planned items") will **exclude `optional` items** when deciding emptiness (checklist "có thể bỏ qua" → treated as yes; it is the feature's value).
- Enum value `booked` is the itinerary-item planning state, independent of `BookingStatus` / `booking_id` (which remain the transactional booking lifecycle).

### Verify (DONE)

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Trip suite (per-status, default, gap, day-plan) | `.venv/bin/python -m pytest tests/test_trips.py tests/test_trip_value_layer_api.py -q` | 0 | 65 passed; each status creatable, default `pending`, gap-detection both polarities |
| Legacy-DB ALTER path (Phase A convention) | `.venv/bin/python -m pytest tests/test_trips.py::test_init_db_adds_status_to_legacy_trip_items -q` | 0 | `status` added to a pre-existing `trip_items`, old rows backfill to `pending` |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | 0 | **604 passed** (was 594; +10) |
| Lint (touched) | `ruff check app tests` | 0 | clean (pre-existing `flight.py` drift untouched) |

### Review gates

- Per-task **spec review** (oracle: PLAN) ✅ — all 4 A3 sub-tasks present, no scope creep, `status` survives create/update via `model_dump()`.
- Per-task **quality review** (maintainability) ✅ — one P3 docstring nit fixed in `7f42faa`; `_ITEM_COLUMNS`/`_item_values` append-only invariant preserved.
- Final **`/correctness-review`** (sonnet, blind to plan) ✅ — zero runtime bugs; traced enum coercion, `NOT NULL DEFAULT` legacy ALTER backfill, 12-col positional alignment, idempotency replay, nested-enum serialization.
- Final **`/intent-review`** (sonnet, blind to plan; oracle: this `### Intent`) ✅ — no gap / drift / behavioral excess; every A3 clause delivered.

### Deviations

- Rule 1 — Added `created_at=datetime.now(timezone.utc)` to the two test `Trip(...)` constructions (the plan's snippet omitted the required field; matches the existing `_make_trip` helper). Test-only; implementation untouched. `tests/test_trips.py`. Commit `bf06237`.
