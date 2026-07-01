---
slug: search-tool-hardening
status: shipped
owner: Minh Tran
created: 2026-07-01
---

# Search-tool hardening (flights + hotels)

Give the agent an explicit "no matches" signal instead of a bare `[]`, so the LLM answers the
user clearly ("no flights/hotels match X") instead of guessing or lightly hallucinating. The
tool-**failure** path (`ToolException` → `_tool_error_to_message`) is already sound — this plan
verifies it with a test and does not change it. No service change: the tool layer already has
everything it needs (`resolve_city` distinguishes an unknown city for hotels).

## 1. Motivation

`search_flights` / `search_hotels` return `dump(results)`; when filters (or an unknown city for
hotels) eliminate everything, that's a bare `[]`. The LLM has no cue why → weak-proof gap +
hallucination risk. Fix: on empty, return a small dict with a human `message`, the applied
filters, and (hotels) a `reason` code. Non-empty return is unchanged.

## 2. Non-goals

- No side panel (workstream B → `/brainstorming`, extend `specs/agent-side-panel/`).
- No change to `book_hotel` (guarded mutation, out of scope).
- No change to the non-empty return shape, the services, or the DB.
- No change to the existing `ToolException` failure path (only add a test asserting it).

## 3. Success Criteria

- Empty flight search → `{"results": [], "reason": "no_match", "message": "...applied filters..."}`.
- Empty hotel search → same shape; `reason` is `unknown_city` when `resolve_city` returns `None`,
  else `no_match`; `message` reflects which.
- Non-empty search → unchanged bare list (existing tests still green).
- Tool failure (bad date) → still raises `ToolException`; a test asserts it.
- `ruff` clean; full `test_booking_tools.py` green.

## 4. Tasks

### Task 1.1 — Flight empty-result signal

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/tools/flight_tools.py</files>
  <action>In search_flights, after computing results: if empty, return a dict {"results": [], "reason": "no_match", "message": f"No flights from {origin} to {destination} on {departure_date} match your filters"} echoing the non-None filters (airline / max_price / max_stops). Keep the non-empty path returning dump(results) unchanged. Keep both ToolException branches as-is.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x -k flight && ruff check app/tools/flight_tools.py</verify>
  <done>Empty flight search returns the dict with message+reason; non-empty unchanged; lint clean.</done>
</task>
```

### Task 1.2 — Hotel empty-result signal (unknown_city vs no_match)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/tools/hotel_tools.py</files>
  <action>In search_hotels, reuse one HotelService instance (svc = HotelService(s)). After check_availability returns empty results: reason = "unknown_city" if svc.resolve_city(city) is None else "no_match"; build a message that says "city not recognized" vs "no hotels in {resolved} match your filters" echoing min_stars/max_price/amenities. Return {"results": [], "reason": reason, "message": message}. Non-empty path returns dump(results) unchanged. Leave book_hotel untouched.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x -k hotel && ruff check app/tools/hotel_tools.py</verify>
  <done>Empty hotel search returns dict; reason distinguishes unknown city from filtered-out; non-empty unchanged; lint clean.</done>
</task>
```

### Task 2.1 — Regression tests (empty + failure, both tools)

```xml
<task id="2.1" wave="2">
  <files>apps/api/tests/tools/test_booking_tools.py</files>
  <action>Add tests: (a) flight search whose filters eliminate all → asserts dict with results==[] and a non-empty message; (b) hotel search for an unknown city → reason=="unknown_city"; (c) hotel search with impossible filter → reason=="no_match"; (d) a search with a bad date raises ToolException (via tool .invoke). Reuse existing fixtures/patterns in the file.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x</verify>
  <done>All new + existing booking-tool tests pass.</done>
</task>
```

## 5. Risks

- **LLM-facing contract:** the empty shape changes from `[]` to a dict — but only on the empty
  branch, and the agent prompts already tell the model to ground answers in tool results, so a
  richer empty payload only helps. Reversible (`git revert`).
- **Hotel double call:** `resolve_city` runs only on the empty branch (cheap; in-memory fuzzy
  match over distinct cities) — no extra cost on the hot path.

## 6. Status Log

- 2026-07-01 — plan proposed after `/feature-intake` (normal lane, high confidence).
- 2026-07-01 — implemented on `feat/search-tool-hardening`: empty-result dict signal for
  `search_flights` + `search_hotels` (hotels distinguish `unknown_city`/`no_match`), docstrings
  updated, 4 new tests + 1 updated. `test_booking_tools.py` 10 passed; ruff clean.
