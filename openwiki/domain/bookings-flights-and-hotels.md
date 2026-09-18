---
type: "Reference"
title: "Bookings, flights and hotels"
openwiki_generated: true
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-a5adc42be2756996fccf803d
    resource: repo://apps/api/app/db/models/booking.py
  - id: openwiki-source-a88871f848e3cf5d85b29577
    resource: repo://apps/api/app/db/models/flight_index.py
  - id: openwiki-source-317f9c0d55a27936830e7380
    resource: repo://apps/api/app/exceptions.py
  - id: openwiki-source-6ad33679598c8cf3dd97ff88
    resource: repo://apps/api/app/repositories/booking.py
  - id: openwiki-source-ce11f205406b62705b4be062
    resource: repo://apps/api/app/repositories/flight.py
  - id: openwiki-source-70c0c0e827a77385ba90791d
    resource: repo://apps/api/app/routers/bookings.py
  - id: openwiki-source-fc1d96b9ff665fbf4704c239
    resource: repo://apps/api/app/routers/flights.py
  - id: openwiki-source-578304a8aa1e84630ba3f292
    resource: repo://apps/api/app/routers/hotels.py
  - id: openwiki-source-24d3b626d89909750a677184
    resource: repo://apps/api/app/schemas/booking.py
  - id: openwiki-source-2bebe8877415ffcf8e1536cc
    resource: repo://apps/api/app/services/booking_service.py
  - id: openwiki-source-578c62a6e778819da223f4c9
    resource: repo://apps/api/app/services/flight_service.py
  - id: openwiki-source-237fdd81477817e51b89166f
    resource: repo://apps/api/app/services/hotel_service.py
  - id: openwiki-source-193522ababf3cd1783b29503
    resource: repo://apps/api/app/tools/_idempotency.py
  - id: openwiki-source-8b6b11d9a840e7139ff3c56c
    resource: repo://apps/api/app/tools/_ranking.py
  - id: openwiki-source-fbd9573b3a515ae531651926
    resource: repo://apps/api/app/tools/hotel_tools.py
  - id: openwiki-source-39802d3bf042bbb929aaa701
    resource: repo://apps/api/tests/api/booking/test_booking_ownership.py
  - id: openwiki-source-e64db8d9a4a12bad43dd189f
    resource: repo://apps/api/tests/api/booking/test_booking_trip_link.py
  - id: openwiki-source-9b6c36c8a640a97118390cf3
    resource: repo://apps/api/tests/api/booking/test_premium_gate.py
  - id: openwiki-source-cc0cda8e59a22607091c74b4
    resource: repo://apps/api/tests/api/hotel/test_hotel_availability.py
  - id: openwiki-source-3e0d313ad6cf7f8f3357a1b9
    resource: repo://apps/api/tests/test_flight_index.py
  - id: openwiki-source-6b4a140ffb7b011b3a0261e4
    resource: repo://apps/api/tests/tools/test_booking_duplicate_tools.py
  - id: openwiki-source-6f54491d9ec7bfb93adeb180
    resource: repo://apps/api/tests/tools/test_booking_idempotency_tools.py
  - id: openwiki-source-a2a23a764d4745867a521fec
    resource: repo://apps/api/tests/tools/test_tool_registry.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---


# Bookings, flights and hotels

Travel inventory is **synthetic on purpose**: there is no external provider and no money moves. Flights and hotel availability are generated deterministically from seed data so the same query always returns the same answer across restarts and across SQLite and Postgres, while bookings created against that inventory are real persisted rows owned by the traveller. The services live in `apps/api/app/services/flight_service.py`, `hotel_service.py` and `booking_service.py`; routers in `routers/flights.py`, `routers/hotels.py` and `routers/bookings.py`; the agent's `flight_tools.py`, `hotel_tools.py` and `booking_tools.py` wrap the same services.

## Flights: generated, never stored

`FlightService.generate_flights(origin, destination, date)` seeds a `random.Random` with an MD5 of the search parameters (not Python's per-process `hash()`), then draws five flights: airline (chosen from the seeded airline list in `position` order), departure hour and quarter-hour, duration, price, seats and stops (75 % direct). Each flight's id is a UUID5 of a slug built from route, date and index, so **the order of the RNG calls is contractual**: reordering them reissues every flight id. Search applies airline, max-price and max-stops filters and one of six sort keys, falling back to departure-ascending for an unknown key. Flights are never persisted.

Because a booking must later resolve a flight id that was issued in an earlier request or before a restart, the service keeps a **flight index**: a process-wide write-through cache plus the `flight_index` table mapping `flight_id → (origin, destination, departure_date)`. New ids are recorded with a dialect-aware `ON CONFLICT DO NOTHING` so two concurrent searches for the same route cannot race, and `find_flight_by_id` re-runs the generator from the stored parameters. `tests/test_flight_index.py` covers concurrent and overlapping batches, and `tests/db/test_determinism.py` pins the generated output against golden fixtures on both engines (see [Data layer and migrations](../architecture/data-layer-and-migrations.md)).

## Hotels: stable rooms and availability

Hotels themselves are seeded catalog rows (see [Destinations, places and travel information](destinations-places-and-travel-info.md)). Capacity is derived, not stored: `total_rooms(hotel)` is a `Random(hotel.id)` draw between 20 and 200, `max_occupancy` grows with star rating (2 to 3 guests per room), and `available_rooms(hotel, check_in, check_out)` is a draw from 0 to `total_rooms` seeded by an MD5 of hotel id and dates, so some hotel-and-date combinations are genuinely sold out. `is_available` requires enough free rooms **and** that the requested rooms can physically hold the party. `count_nights` raises when check-out is not strictly after check-in; an earlier clamp-to-one-night silently booked a paid stay. `GET /hotels/availability` returns every matching hotel annotated with availability, free rooms, occupancy, nights and `total_price = price_per_night × nights × rooms`, and returns `nights` even when nothing matches. City names are fuzzy-resolved to the seeded canonical names.

## The booking service

`BookingService` (`booking_service.py`) is the only writer of the `bookings` table. Its invariants:

- **Owner scoping.** `get`, `list_all`, `query` and `cancel` take a `user_id`; a booking owned by someone else raises the same `NotFoundError` as a missing one, and lookups accept either the UUID or the 6-character confirmation code. `tests/api/booking/test_booking_ownership.py` covers reads, listing, cancellation and both lookup forms.
- **Confirmation codes.** Each booking id is minted so that its derived PNR-style code (`confirmation_code_for`, a deterministic short code of the UUID) is unused; the uniqueness check is unscoped because the unique index spans all owners, and minting gives up after eight attempts. Both `idempotency_key` and `confirmation_code` are partial unique indexes (unique only when present).
- **Replay by idempotency key.** With a key, a prior booking by the same owner is returned unchanged before anything else happens, even if the replayed request names a different trip.
- **Trip linking.** An optional `trip_id` is verified to belong to the caller (a foreign or missing trip is a 404, never an existence oracle) and stored on the booking so budgets can roll it up (see [Trips, itinerary and budget](trips-itinerary-and-budget.md)).
- **Flight booking** resolves the flight by id or by flight number plus route and date (404 with a hint to re-run the search when an old id no longer resolves), prices it as `price × passengers`, and stores the flight details and passenger contact in the JSON `details`.
- **Hotel booking** resolves the hotel by id or `HTL-` short code, raises a `409` when the hotel cannot take the rooms and party on those dates, and prices the stay per night, night count and rooms.
- **Duplicate detection is opt-in** (`check_duplicate=True`). It runs after the sold-out check, takes a **per-owner transaction-scoped advisory lock** on Postgres (`pg_advisory_xact_lock`; a no-op on SQLite, and it requires a caller-owned live session), re-runs the replay under the lock so a concurrent same-key request receives the original booking rather than a duplicate error, and then raises `DuplicateBookingError` (a `ConflictError`) if an active booking exists for the same flight and passenger count, or the same hotel and exact dates. The error's detail always carries a machine-readable `[possible-duplicate:<id>]` marker and lists every matching booking.
- **Cancellation is idempotent** and keeps the row: cancelling an already-cancelled booking returns it unchanged, and cancelling **releases the idempotency key** so a cancelled booking is never a replay target (rebooking in the same turn creates a new row).

## The REST surface

`GET /flights/search`, `GET /flights/{id}`, `GET /hotels`, `GET /hotels/search`, `GET /hotels/availability` and `GET /hotels/{id}` are read-only. `POST /flights/book` and `POST /hotels/book` are **premium-only** through `Depends(require_premium)` (a free caller gets 403; see [Authentication and user tiers](../concepts/auth-and-tiers.md)) and accept an `Idempotency-Key` header. `GET /bookings` lists the caller's bookings in a paginated envelope with an optional trip filter, `GET /bookings/{id}` reads by UUID or code, and `POST /bookings/{id}/cancel` cancels.

## The agent's booking tools

Only the booking specialist, which sits behind the plan-approval interrupt, is bound to `book_flight`, `book_hotel`, `cancel_flight` and `cancel_hotel` (see [Guardrails](../agent/guardrails-pii-and-hitl.md) and [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md)). Hotel search is split so the concierge can browse without dates and the planner can check availability without booking. Two mechanisms make the tools safe under the agent's reflection re-runs:

- **Turn-scoped idempotency.** `turn_idempotency_key` (`tools/_idempotency.py`) hashes owner, thread id, the id of the last human message, the tool name and the model-visible arguments (injected `user_id`, `trip_id`, `messages` and `config` are stripped), so a reflection revise that re-runs the same call replays the existing booking, while a new traveller message is a genuinely new request. With no thread id or human message (direct or MCP callers) the tool books without a key. `tests/tools/test_booking_idempotency_tools.py` covers replay within a turn, rebooking after a cancel, and a new turn creating a second row.
- **Duplicate warnings and the override guard.** The tools call the service with `check_duplicate=not allow_duplicate`, so a duplicate surfaces to the model as a tool error carrying the marker and a hint to tell the traveller and ask. Because a blocked duplicate leaves no row to replay, `allow_duplicate=True` is honoured **only if the traveller has spoken since the warning**: `duplicate_warned_ids_this_turn` scans error `ToolMessage`s since the last human message for the marker, and an override that targets any booking flagged this turn (or a malformed marker, which acts as a wildcard) is refused with `OVERRIDE_REFUSED_HINT`. When the override stands, the tool re-books on the same session so the advisory lock is still held. `tests/tools/test_booking_duplicate_tools.py` covers both the refusal and the accepted override after a new message.

Results from the search tools are re-ranked by the traveller's stored preferences in a **boost-only, stable** way (word-boundary keyword matches of at least three characters, ties keep search order) so the same query and preferences always yield the same order.
