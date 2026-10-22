---
type: domain
title: Trips, itinerary and budget
description: The trip aggregate and its business rules — owner-scoped trips with soft delete and per-owner idempotency, day-numbered itinerary items with status and budget enforcement, the place shortlist, the computed trip detail (spend rollup, remaining budget, coverage gaps) and day plan, per-category budget caps versus booked spend, the expense ledger with FX normalization, saved places with proximity de-duplication, and how the planner and budget specialists reach the same services through tools.
tags: [trips, itinerary, budget, expenses, shortlist, saved-places, idempotency, ownership, domain]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-376b2cbcfa274a01852a15f2
    resource: repo://apps/api/app/db/models/expense.py
  - id: openwiki-source-12f5abb44efbbd30f3f69adf
    resource: repo://apps/api/app/db/models/trip.py
  - id: openwiki-source-27bf76fad4ad63694bd62a67
    resource: repo://apps/api/app/routers/trips.py
  - id: openwiki-source-e54adad3405cff6b39dc0dde
    resource: repo://apps/api/app/services/expense_service.py
  - id: openwiki-source-6a6a8f7cfae95c4f204d1da3
    resource: repo://apps/api/app/services/saved_place_service.py
  - id: openwiki-source-e52f22dd7dfd7d00a70046ae
    resource: repo://apps/api/app/services/trip_service.py
  - id: openwiki-source-97b1fd4b365c73190c64c4c1
    resource: repo://apps/api/app/tools/registry.py
  - id: openwiki-source-3b89cfbd1d5116099ae2bca0
    resource: repo://apps/api/app/tools/trip_tools.py
  - id: openwiki-source-85cbb4b03400811c55895673
    resource: repo://apps/api/tests/api/trip/test_trip_budget.py
  - id: openwiki-source-ccc57f1047e187cddc5acd83
    resource: repo://apps/api/tests/api/trip/test_trip_ownership.py
  - id: openwiki-source-ab9e1d3aab0785e5c9dcd65a
    resource: repo://apps/api/tests/api/trip/test_trips.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Trips, itinerary and budget

A **trip** is the aggregate everything else hangs off: itinerary items, a place shortlist, bookings linked to items, budget caps, and an expense ledger. All of it is real, persisted user data (see [Monorepo overview](../architecture/monorepo-overview.md) for the product boundary). The business rules live in `apps/api/app/services/trip_service.py`, `expense_service.py` and `saved_place_service.py`; routers in `routers/trips.py` and `routers/expenses.py` expose them, and the planner and budget specialists reach the very same services through tools (see [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md)).

## Ownership and the service boundary

`TripService(session, user_id)` is constructed per request by `get_trip_service`, which binds it to the request session and the verified caller (see [Authentication and user tiers](../concepts/auth-and-tiers.md)). Every read and mutation funnels through `get_trip`, which queries by `(trip_id, user_id)` and raises `NotFoundError` for a missing **or foreign** trip, so a probe cannot confirm a guessed id. `tests/api/trip/test_trip_ownership.py` checks that another user's trip is not listed, reads as 404, cannot be modified or deleted, and cannot receive or list expenses. The `trips` table stores `user_id` as `NOT NULL` so no trip is ownerless.

## Trips and idempotent creation

`POST /trips` accepts an optional `Idempotency-Key` header. The key is **unique per owner** (a partial unique index over `(user_id, idempotency_key)`), so two users reusing the same key never collide, and a replay returns the original trip instead of creating a second one. The web client mints these keys automatically for trip and item creation (see [Web app shell, routing and auth](../frontend/app-shell-and-routing.md)). Trips carry title, optional city and dates, `travelers`, notes, and JSON `budget_caps`; validation rejects blank titles, zero travelers and an end date before the start date. Deletion is a **soft delete** (`deleted_at`), and a repeat delete is a 404.

## Itinerary items

Items belong to a trip day (`day ≥ 1`) with a `sort_order`, a `kind` (`place`, `activity`, `meal`, `transport`, `note`), a `status` (`pending`, `booked`, `constraint`, `optional`; default `pending`), optional `place_id`, `booking_id`, `start_time` and notes. `POST /trips/{id}/items` also takes an `Idempotency-Key`, but item keys are **globally unique**: reusing a key on a different trip is a `409` rather than a silent wrong-item replay. Update and delete verify the item belongs to the named trip.

Adding an item that links a booking runs `_enforce_budget` **after** the replay check (a replay is not a new charge) and before the insert: if caps are set and the booking's category cap would be exceeded, the service raises a `409` with the projected overspend and a hint to raise the cap or link a cheaper booking. Spending exactly up to the cap is allowed, a cancelled or unpriceable booking never blocks, and items without a booking are never blocked (`tests/api/trip/test_trip_budget.py`).

## Shortlist

`add_place_to_trip` links a catalog place or one of the caller's saved places to a trip (`source` must be `catalog` or `saved`; anything else is 422). The saved-place resolution is scoped to the caller, so a foreign saved place can never be shortlisted or echoed back. A unique index over `(trip_id, place_id, source)` turns a duplicate into a `409`. Listing resolves each entry and silently drops entries whose place no longer resolves.

## Computed views

`GET /trips/{id}` returns `TripDetail`, computed fresh each call: every linked booking is resolved once (missing ones are skipped, cancelled ones excluded), `total_spent` sums booking prices per item, `remaining_budget` is the sum of set caps minus that spend (null when no cap exists anywhere), and `gaps` lists, for each day between the trip's start and end dates, days with no planned items and days without a hotel booking. **Optional items do not count as planning a day**, so a day holding only optional items still reports a gap (`test_gap_detection_treats_optional_as_unplanned`). The shortlist rides along.

`GET /trips/{id}/day-plan?date=` returns that date's items in order with travel-time annotations between stops from the routing service; it is a `409` when the trip has no start date (the day number cannot be derived), and routing failures leave the travel fields null rather than failing the plan (see [Destinations, places and travel information](destinations-places-and-travel-info.md)).

## Budget caps versus booked spend

`GET /trips/{id}/budget` reports per category (`BudgetCategory`: flights, accommodation, and so on) the cap, the spend and the remaining amount, plus totals and an `over_budget` flag. `POST /trips/{id}/budget` **replaces** the caps wholesale with whichever categories are supplied, and rejects negatives. Two spend figures coexist deliberately:

- `total_spent` counts booked spend **per itinerary item link**, mapping a booking's type to a category; a booking linked from two items counts twice, matching the detail view.
- `booked_total` counts every non-cancelled booking that carries this `trip_id` **once**, by existence, whether or not an item references it.

Money is rounded half-up to two decimals through `Decimal`, avoiding banker's rounding. `POST /trips/estimate` is a pure function that produces a line-item estimate (flights, accommodation, meals by style, activities by level, local transport, plus a buffer) with the assumptions spelled out; nothing is stored. The agent uses the same estimate to propose caps, and a `$0` estimate leaves a category uncapped.

## Expense ledger

`ExpenseService(session, user_id)` validates trip ownership on every call. Each expense records `amount` and `currency` plus a normalized `amount_usd` and the `fx_rate` used, computed from the seeded FX snapshot (an unknown currency is a 404 listing the valid codes). Updating the amount or currency recomputes both derived fields. Deletes are soft, the live-rows index is scoped to non-deleted expenses, and `summary` totals USD spend and groups it by category. Routes: `POST/GET /trips/{id}/expenses`, `GET .../summary`, `GET/PATCH/DELETE .../{expense_id}`. The budget specialist's `add_expense`, `list_expenses` and `expense_summary` tools wrap these methods.

## Saved places

`SavedPlaceService` creates user-owned places with a **proximity de-duplication rule**: a place with the same name in the same city within roughly 50 metres of an existing one is a `409` whose hint names the existing short code to reuse. Saved places can then be shortlisted onto trips with `source="saved"`.

## The agent's view of trips

Trip-scoped tools (`get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`, `add_itinerary_item`, `set_trip_budget`, `estimate_trip_budget`, `list_trips`) receive `user_id` and `trip_id` through injected state, never from the model. Called with no active trip on the agent path they are stopped by the specialist's trip guard before executing; called directly (for example over MCP) they return a plain `no_active_trip` guidance dict rather than raising. `create_trip` is bound to the planner only, returns a `Command` that sets the new trip as the active `trip_id` for the rest of the turn, and its docstring encodes the product rule that the planner **searches first and creates a trip only when the traveller wants to keep a result**. The supervisor's extracted trip facts (destination, dates, counts, budget) are what let these tools be called without re-asking (see [Agent state, runtime context and reply language](../agent/state-context-and-language.md)).
