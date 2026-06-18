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

### Verify (to be filled at DONE)

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| New per-status + default tests | `.venv/bin/python -m pytest tests/ -k trip -q` | | each status creatable; default `pending` |
| Legacy-DB ALTER path (Phase A convention) | `.venv/bin/python -m pytest tests/ -k "migration or legacy" -q` | | `status` added to a pre-existing `trip_items` |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | | no regressions |
| Lint | `ruff check app && ruff format --check app` | | clean |
