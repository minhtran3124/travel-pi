---
slug: symmetric-booking-inputs
status: shipped
owner: Minh Tran
created: 2026-06-20
lane: normal
---

# Symmetric booking inputs — accept `flight_id` on `POST /flights/book`

## 1. Motivation

`POST /hotels/book` takes a single `hotel_id`; `POST /flights/book` requires
`flight_number + origin + destination + departure_date`. An agent holding a
search-result `id` must unpack it to book. Accept `flight_id` as an alternative
so the agent can do `search → pick id → book`. The resolver already exists
(`flight_service.find_flight_by_id`, `app/services/flight_service.py:216`).

## 2. Non-goals

- No new endpoint; `POST /flights/book` keeps its path/method.
- No change to `POST /hotels/book`.
- No change to the legacy `flight_number + route + date` path for existing callers.
- No quote/hold flow (#2, separate item).

## 3. Success Criteria

- `POST /flights/book` accepts `{flight_id, passenger_*}` and books the same
  flight the legacy quad would.
- Legacy quad path is byte-for-byte unchanged (existing tests stay green).
- Sending **both** `flight_id` and the quad → 422. Sending **neither** complete
  identifier → 422. Unknown/expired `flight_id` → 404 with a search hint.
- `make test` green; `ruff check app` clean.

## 4. Tasks

### Task 1.1 — Schema: optional `flight_id` + exactly-one-identifier validator

```xml
<task id="1.1" wave="1">
  <files>app/schemas/flight.py</files>
  <action>On FlightBookingRequest: add `flight_id: str | None = Field(default=None, ...)`. Make flight_number/origin/destination/departure_date `str | None` with `default=None` (keep their descriptions/examples). Guard the existing departure_date field_validator to return None untouched when value is None. Add a `@model_validator(mode="after")` enforcing exactly one identifier mode: has_id XOR full-quad-present — error if both supplied, error if neither complete identifier present (partial quad without flight_id is "neither"). Update the docstring + json_schema_extra to show the flight_id path. Keep price out of the request (unchanged).</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && ruff check app/schemas/flight.py && python -c "from app.schemas.flight import FlightBookingRequest as F; import pydantic; F(flight_id='x', passenger_name='a', passenger_email='a@b.co', passenger_phone='1'); 
import sys
for bad in [dict(passenger_name='a',passenger_email='a@b.co',passenger_phone='1'), dict(flight_id='x',flight_number='VN1',origin='DAD',destination='SGN',departure_date='2026-06-01',passenger_name='a',passenger_email='a@b.co',passenger_phone='1')]:
    try: F(**bad); sys.exit('should have raised: '+str(bad))
    except pydantic.ValidationError: pass
print('ok')"</verify>
  <done>flight_id-only and full-quad-only validate; both-supplied and neither-supplied raise ValidationError</done>
</task>
```

### Task 1.2 — Service: resolve by `flight_id` when present

```xml
<task id="1.2" wave="1">
  <files>app/services/booking_service.py</files>
  <action>In book_flight, branch resolution: if request.flight_id is set, `flight = flight_service.find_flight_by_id(request.flight_id)` and on None raise NotFoundError(f"Flight {request.flight_id!r} not found", hint="Run GET /flights/search and use the `id` from a result, or expired ids re-search for a fresh one."); else keep the existing find_flight_by_number path + its 404. Everything after resolution (Booking/FlightBookingDetails construction) is unchanged — it already reads from `flight`, not the request route fields. Guard the .upper() calls so they only run on the legacy path (origin/destination may now be None).</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && ruff check app/services/booking_service.py</verify>
  <done>book_flight resolves via flight_id when present, falls back to the quad, no AttributeError on None route fields</done>
</task>
```

### Task 1.3 — Tests: flight_id booking path + cross-field validation

```xml
<task id="1.3" wave="2">
  <files>tests/api/flight/test_flights.py</files>
  <action>Add tests: (a) book by flight_id (use get_first_flight_id helper) → 200, type flight, reference_id equals that id; (b) book by flight_id yields same flight as the legacy quad for the same search-result; (c) both flight_id + quad → 422; (d) unknown flight_id (random uuid) → 404. Reuse VALID_ORIGIN/DESTINATION/DATE + get_first_flight_id from conftest. Do not weaken the existing test_book_flight_missing_fields_returns_422 (flight_number-only stays 422).</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && python -m pytest tests/api/flight/test_flights.py -q</verify>
  <done>new tests pass; all pre-existing flight tests still green</done>
</task>
```

## 5. Risks

- **Weakening validation** — mitigated: the model_validator preserves "exactly
  one complete flight identity", so net validation strength is unchanged
  (intake hard-gate analysis in SUMMARY.md).
- **`.upper()` on None** — origin/destination now nullable; the service guard
  keeps `.upper()` on the legacy branch only.
- **OpenAPI example drift** — update `json_schema_extra` so `/docs` shows both
  modes.

## 6. Status Log

- 2026-06-20 — plan drafted from intake (lane=normal). Waves: 1 (schema+service,
  disjoint files, parallel-safe) → 2 (tests). Executing in main thread (small).
- 2026-06-20 — shipped. 1.1/1.2/1.3 done; `ruff check app` clean; full suite
  671 passed (+4). flight_id booking path live on `feat/symmetric-booking-inputs`.
