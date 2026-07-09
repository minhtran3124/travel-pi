---
slug: min-42-implement-mcp-tool
status: shipped
owner: Minh Tran
created: 2026-07-09
---

# Implement MCP tool — book_flight / cancel_flight / cancel_hotel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Expose flight/hotel **book & cancel** as three new agent tools (`book_flight`, `cancel_flight`, `cancel_hotel`) so they are callable over MCP by external clients, alongside the existing search/book tools.

**Architecture:** The tools are thin adapters over the already-existing, already-tested `BookingService` (`book_flight`, `get`, `cancel`) — no new business logic. MCP exposure is automatic: `app/mcp/server.py::build_mcp_server()` iterates `ALL_TOOLS` from the registry and maps `_DESTRUCTIVE`/`_WRITE` membership to `destructiveHint`/`readOnlyHint` + a " Cannot be undone." description suffix. So the work is: clone the `book_hotel` tool pattern, register the three names, add tests. `app/mcp/server.py` is **not** touched.

**Tech Stack:** FastAPI, LangChain `@tool` (`langchain_core.tools`), Pydantic v2 `args_schema`, `mcp` python SDK (`ToolAnnotations`), pytest on temp SQLite (`agent_db` fixture).

---

## 1. Motivation

Linear MIN-42. Agents (and external MCP clients like Claude Desktop / Agent SDK) can currently `search_flights`, `search_hotels`, and `book_hotel`, but cannot **book a flight** or **cancel** either kind of booking over the tool/MCP surface — even though the backing `BookingService` methods already exist. This closes that gap.

## 2. Non-goals

- No change to `app/mcp/server.py` (exposure is registry-driven).
- No change to `BookingService` / repositories / schemas (all backing methods and request schemas already exist).
- No new business logic, no DB schema change, no new dependency.
- Not a generic `cancel_booking` tool — the issue resolved on two type-specific cancel tools.

## 3. Success Criteria

- `book_flight`, `cancel_flight`, `cancel_hotel` are discoverable + callable over MCP with `destructiveHint=True` and "Cannot be undone." in the description.
- Valid input books/cancels the correct `Booking`; invalid input (unknown id, missing `confirm`, wrong booking type) raises a graceful `ToolException`.
- `make test` passes.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `app/tools/flight_tools.py` | Modify | Add `BookFlightArgs` + `book_flight` tool; append to `FLIGHT_TOOLS`. |
| `app/tools/booking_tools.py` | **Create** | `CancelBookingArgs` + `cancel_flight` + `cancel_hotel` + `BOOKING_TOOLS`; type-guarded cancels. |
| `app/tools/registry.py` | Modify | Import `BOOKING_TOOLS`; add to `booking` domain; add 3 names to `_WRITE` **and** `_DESTRUCTIVE`. |
| `tests/tools/test_flight_booking_tool.py` | **Create** | `book_flight`: happy path, missing-confirm guard, unknown-flight error. |
| `tests/tools/test_cancel_tools.py` | **Create** | cancels: happy path, unknown id, missing confirm, wrong-type guard. |
| `tests/mcp/test_mcp_server.py` | Modify | Assert the 3 new tools are exposed with `destructiveHint=True` + "Cannot be undone.". |

## Design notes (read before coding)

- **Template is `book_hotel`** (`app/tools/hotel_tools.py:325-381`): `@tool(args_schema=…)` → `log_tool_call` → `if not confirm: raise ToolException(...)` → `with session_scope() as s:` → build request → `BookingService(s).<method>(request)` → `return dump(result)` → `except AppError` then `except ValueError` → `ToolException`.
- **No injected params** in these tools (no `InjectedState`/`InjectedStore`), so the known `args_schema`+ToolNode-injection bug does not apply — mirror `book_hotel` exactly. (`explicit-args-schema-breaks-langgraph-injection`.)
- **`FlightBookingRequest`** (`app/schemas/flight.py:136`) already accepts `flight_id` **XOR** `flight_number`+`origin`+`destination`+`departure_date`; its `@model_validator` raises `ValueError` (→ `ToolException`) on a bad/partial identifier. Pass args straight through — do not re-validate in the tool.
- **`BookingService`** (`app/services/booking_service.py`): `get(booking_id)` resolves UUID **or** 6-char `confirmation_code` (`:96`, raises `NotFoundError`); `cancel(booking_id)` is idempotent and returns the cancelled `Booking` (`:129`). Both are **type-agnostic** → the wrong-type guard lives in the tool.
- **`booking.type`** is `BookingType` str-enum (`app/enums.py:11`, values `"flight"`/`"hotel"`); `dump()` → `model_dump(mode="json")` yields `type`/`status` as strings and the computed `confirmation_code`.
- **Registry**: `book_flight` reaches the `booking` domain automatically via `FLIGHT_TOOLS`; the cancels reach it via the new `BOOKING_TOOLS`. `book_hotel` is in both `_WRITE` and `_DESTRUCTIVE` — mirror that for all three new tools.
- **Tests** use the `agent_db` fixture (`tests/tools/conftest.py`) — real temp SQLite, no FakeLLM. Invoke a tool with `tool.invoke({...args...})`. Guard assertions use `pytest.raises(ToolException, match=...)`.

---

## 4. Tasks

### Task 1.1 — `book_flight` tool

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/tools/flight_tools.py, apps/api/tests/tools/test_flight_booking_tool.py</files>
  <action>Add BookFlightArgs + the book_flight tool to flight_tools.py mirroring book_hotel; append book_flight to FLIGHT_TOOLS. Write the test file first (TDD). See code blocks below.</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -x -q</verify>
  <done>3 book_flight tests pass; book_flight in FLIGHT_TOOLS; ruff clean.</done>
</task>
```

- [ ] **Step 1 — Write the failing test** — Create `apps/api/tests/tools/test_flight_booking_tool.py`:

```python
"""Tests for the book_flight agent tool (MIN-42)."""

import pytest
from langchain_core.tools import ToolException


def test_book_flight_guard_raises_without_confirm(agent_db):
    from app.tools.flight_tools import book_flight

    with pytest.raises(ToolException, match="confirm=true"):
        book_flight.invoke(
            {
                "flight_number": "VN123",
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "2027-03-15",
                "passenger_name": "Test User",
                "passenger_email": "test@example.com",
                "passenger_phone": "+1 555 000 0000",
            }
        )


def test_book_flight_unknown_flight_raises(agent_db):
    from app.tools.flight_tools import book_flight

    with pytest.raises(ToolException):
        book_flight.invoke(
            {
                "flight_id": "00000000-0000-0000-0000-000000000000",
                "passenger_name": "Test User",
                "passenger_email": "test@example.com",
                "passenger_phone": "+1 555 000 0000",
                "confirm": True,
            }
        )


def test_book_flight_happy_path_returns_booking(agent_db):
    from app.db.engine import get_session_factory
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    # Deterministic seed: HAN->SGN on this date returns >=1 flight.
    with get_session_factory(agent_db)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        flight_number = flight.flight_number

    result = book_flight.invoke(
        {
            "flight_number": flight_number,
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
            "passenger_name": "Test User",
            "passenger_email": "test@example.com",
            "passenger_phone": "+1 555 000 0000",
            "confirm": True,
        }
    )
    assert result["type"] == "flight"
    assert result["status"] == "confirmed"
    assert result["confirmation_code"]
```

- [ ] **Step 2 — Run test, verify it fails** — `cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -x -q` → FAIL (`ImportError: cannot import name 'book_flight'`). (The `DATABASE_URL` pin only guards import time — the `agent_db` fixture repoints it at a temp file DB per test.)

- [ ] **Step 3 — Implement** — In `apps/api/app/tools/flight_tools.py`: add imports (with usage, so `ruff-on-edit` won't strip them) and the tool. Add to the existing import section:

```python
from app.exceptions import AppError  # already imported — keep
from app.schemas.flight import FlightBookingRequest
from app.services.booking_service import BookingService
from app.tools._base import dump, log_tool_call, panel_result, session_scope  # add `dump`
```

Insert `BookFlightArgs` near `SearchFlightsArgs`, and the tool just before the `FLIGHT_TOOLS = [...]` line:

```python
class BookFlightArgs(AppBaseModel):
    flight_id: str | None = Field(
        None,
        description=(
            "The `id` of a flight from a search_flights result. Provide this "
            "OR flight_number+origin+destination+departure_date, not both."
        ),
    )
    flight_number: str | None = Field(
        None,
        description=(
            "Carrier code + number, e.g. 'VN123'. Required (with "
            "origin+destination+departure_date) when flight_id is not given."
        ),
    )
    origin: str | None = Field(
        None, description="3-letter IATA origin code, e.g. 'HAN'."
    )
    destination: str | None = Field(
        None, description="3-letter IATA destination code, e.g. 'SGN'."
    )
    departure_date: str | None = Field(
        None, description="Departure date, YYYY-MM-DD."
    )
    passenger_name: str = Field(
        ..., description="Full name as printed on the passenger's ID/passport."
    )
    passenger_email: str = Field(
        ..., description="Contact email for the itinerary and e-ticket."
    )
    passenger_phone: str = Field(
        ..., description="Contact phone for airline notifications (delays, gate)."
    )
    notes: str | None = Field(
        None, description="Optional note for the airline (seat/meal preference)."
    )
    confirm: bool = Field(
        False,
        description=(
            "Must be set to True to execute the booking — prevents accidental "
            "reservations. Leaving it False (the default) will not book anything."
        ),
    )


@tool(args_schema=BookFlightArgs)
def book_flight(
    passenger_name: str,
    passenger_email: str,
    passenger_phone: str,
    flight_id: str | None = None,
    flight_number: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    departure_date: str | None = None,
    notes: str | None = None,
    confirm: bool = False,
) -> dict:
    """Book a flight. You MUST pass confirm=True to create the reservation.

    Identify the flight EITHER by ``flight_id`` (from a search_flights result)
    OR by ``flight_number`` + ``origin`` + ``destination`` + ``departure_date``
    — provide one, not both. Raises ``ToolException`` if the flight is not found
    or the identifier is invalid/incomplete.

    :param passenger_name: Full name as printed on the passenger's ID/passport.
    :param passenger_email: Contact email for the itinerary and e-ticket.
    :param passenger_phone: Contact phone for airline notifications.
    :param flight_id: The `id` from a search_flights result (mode A).
    :param flight_number: Carrier code + number, e.g. 'VN123' (mode B).
    :param origin: 3-letter IATA origin code (mode B).
    :param destination: 3-letter IATA destination code (mode B).
    :param departure_date: Departure date YYYY-MM-DD (mode B).
    :param notes: Optional note for the airline.
    :param confirm: Must be True to execute the booking; left False, nothing books.
    :return: The confirmed Booking with id, confirmation_code, status, total_price.
    """
    log_tool_call("book_flight", locals())
    if not confirm:
        raise ToolException(
            "set confirm=true to book — this action creates a real reservation"
        )
    with session_scope() as s:
        try:
            request = FlightBookingRequest(
                flight_id=flight_id,
                flight_number=flight_number,
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                passenger_name=passenger_name,
                passenger_email=passenger_email,
                passenger_phone=passenger_phone,
                notes=notes,
            )
            result = BookingService(s).book_flight(request)
            return dump(result)
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e
```

Then change the group line:

```python
FLIGHT_TOOLS = [search_flights, book_flight]
```

- [ ] **Step 4 — Run tests, verify pass** — `cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -x -q` → 3 passed. Then `ruff check app/tools/flight_tools.py && ruff format --check app/tools/flight_tools.py`.

---

### Task 1.2 — `cancel_flight` + `cancel_hotel` tools

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/tools/booking_tools.py, apps/api/tests/tools/test_cancel_tools.py</files>
  <action>Create booking_tools.py with CancelBookingArgs, cancel_flight, cancel_hotel (each: confirm guard → BookingService.get → booking.type guard → cancel → dump), and BOOKING_TOOLS. Write the test file first (TDD). See code blocks below. Do NOT touch registry.py (that is Task 2.1).</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/tools/test_cancel_tools.py -x -q</verify>
  <done>All cancel tests pass (happy, unknown id, missing confirm, wrong-type guard); ruff clean.</done>
</task>
```

- [ ] **Step 1 — Write the failing test** — Create `apps/api/tests/tools/test_cancel_tools.py`:

```python
"""Tests for cancel_flight / cancel_hotel agent tools (MIN-42)."""

import pytest
from langchain_core.tools import ToolException


def _book_a_flight(url: str) -> str:
    """Arrange a real flight booking; return its confirmation_code."""
    from app.db.engine import get_session_factory
    from app.schemas.flight import FlightBookingRequest
    from app.services.booking_service import BookingService
    from app.services.flight_service import FlightService

    with get_session_factory(url)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        booking = BookingService(s).book_flight(
            FlightBookingRequest(
                flight_number=flight.flight_number,
                origin="HAN",
                destination="SGN",
                departure_date="2027-03-15",
                passenger_name="Test User",
                passenger_email="test@example.com",
                passenger_phone="+1 555 000 0000",
            )
        )
        s.commit()
        return booking.confirmation_code


def _book_a_hotel(url: str) -> str:
    """Arrange a real hotel booking; return its confirmation_code."""
    from app.db.engine import get_session_factory
    from app.schemas.hotel import HotelBookingRequest
    from app.services.booking_service import BookingService
    from app.services.hotel_service import HotelService

    with get_session_factory(url)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        hotel = next((h for h in results if h.available), None)
        assert hotel is not None, "no available Da Nang hotel to arrange the test"
        booking = BookingService(s).book_hotel(
            HotelBookingRequest(
                hotel_id=hotel.id,
                check_in="2027-04-10",
                check_out="2027-04-14",
                rooms=1,
                adults=2,
                children=0,
                guest_name="Test User",
                guest_email="test@example.com",
                guest_phone="+1 555 000 0000",
            )
        )
        s.commit()
        return booking.confirmation_code


def test_cancel_flight_happy_path(agent_db):
    from app.tools.booking_tools import cancel_flight

    code = _book_a_flight(agent_db)
    result = cancel_flight.invoke({"booking_id": code, "confirm": True})
    assert result["type"] == "flight"
    assert result["status"] == "cancelled"


def test_cancel_hotel_happy_path(agent_db):
    from app.tools.booking_tools import cancel_hotel

    code = _book_a_hotel(agent_db)
    result = cancel_hotel.invoke({"booking_id": code, "confirm": True})
    assert result["type"] == "hotel"
    assert result["status"] == "cancelled"


def test_cancel_flight_missing_confirm_raises(agent_db):
    from app.tools.booking_tools import cancel_flight

    code = _book_a_flight(agent_db)
    with pytest.raises(ToolException, match="confirm=true"):
        cancel_flight.invoke({"booking_id": code})


def test_cancel_flight_unknown_id_raises(agent_db):
    from app.tools.booking_tools import cancel_flight

    with pytest.raises(ToolException, match="not found"):
        cancel_flight.invoke({"booking_id": "ZZ9999", "confirm": True})


def test_cancel_flight_on_hotel_booking_raises_wrong_type(agent_db):
    from app.tools.booking_tools import cancel_flight

    hotel_code = _book_a_hotel(agent_db)
    with pytest.raises(ToolException, match="not a flight booking"):
        cancel_flight.invoke({"booking_id": hotel_code, "confirm": True})
```

- [ ] **Step 2 — Run test, verify it fails** — `cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/tools/test_cancel_tools.py -x -q` → FAIL (`ModuleNotFoundError: app.tools.booking_tools`).

- [ ] **Step 3 — Implement** — Create `apps/api/app/tools/booking_tools.py`:

```python
"""Booking lifecycle tools — cancel a flight or hotel booking (MIN-42).

Thin wrappers over ``BookingService.cancel``. Cancellation is irreversible, so
each tool requires ``confirm=True`` and is annotated destructive in the registry.
Two type-specific tools (not one generic) give an explicit MCP surface; each
loads the booking first via ``BookingService.get`` and refuses a booking of the
other type. Mirrors the ``book_hotel`` error-mapping pattern.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.enums import BookingType
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.booking_service import BookingService
from app.tools._base import dump, log_tool_call, session_scope


class CancelBookingArgs(AppBaseModel):
    booking_id: str = Field(
        ...,
        description=(
            "The booking UUID or 6-character confirmation code (e.g. 'AB23XY') "
            "of the booking to cancel."
        ),
    )
    confirm: bool = Field(
        False,
        description=(
            "Must be set to True to execute the cancellation — this cannot be "
            "undone. Leaving it False (the default) cancels nothing."
        ),
    )


def _cancel(
    booking_id: str, confirm: bool, expected: BookingType, tool_name: str
) -> dict:
    """Shared cancel path: guard confirm → load → type-check → cancel → dump."""
    log_tool_call(tool_name, {"booking_id": booking_id, "confirm": confirm})
    if not confirm:
        raise ToolException(
            "set confirm=true to cancel — this permanently cancels the booking"
        )
    with session_scope() as s:
        try:
            svc = BookingService(s)
            booking = svc.get(booking_id)
            if booking.type != expected:
                raise ToolException(
                    f"Booking {booking_id!r} is a {booking.type.value} booking, "
                    f"not a {expected.value} booking. "
                    f"Use cancel_{booking.type.value} instead."
                )
            return dump(svc.cancel(booking_id))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=CancelBookingArgs)
def cancel_flight(booking_id: str, confirm: bool = False) -> dict:
    """Cancel a FLIGHT booking. You MUST pass confirm=True — this cannot be undone.

    Raises ``ToolException`` if the id is unknown or refers to a hotel booking.
    Cancelling an already-cancelled booking is a no-op that returns it.

    :param booking_id: Booking UUID or 6-char confirmation code.
    :param confirm: Must be True to execute the cancellation.
    :return: The cancelled Booking (status='cancelled').
    """
    return _cancel(booking_id, confirm, BookingType.FLIGHT, "cancel_flight")


@tool(args_schema=CancelBookingArgs)
def cancel_hotel(booking_id: str, confirm: bool = False) -> dict:
    """Cancel a HOTEL booking. You MUST pass confirm=True — this cannot be undone.

    Raises ``ToolException`` if the id is unknown or refers to a flight booking.
    Cancelling an already-cancelled booking is a no-op that returns it.

    :param booking_id: Booking UUID or 6-char confirmation code.
    :param confirm: Must be True to execute the cancellation.
    :return: The cancelled Booking (status='cancelled').
    """
    return _cancel(booking_id, confirm, BookingType.HOTEL, "cancel_hotel")


BOOKING_TOOLS = [cancel_flight, cancel_hotel]
```

- [ ] **Step 4 — Run tests, verify pass** — `cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/tools/test_cancel_tools.py -x -q` → 5 passed. Then `ruff check app/tools/booking_tools.py && ruff format --check app/tools/booking_tools.py`.

> **Note on the wrong-type match string:** the guard message contains "not a flight booking" (for `cancel_flight` on a hotel). Keep the test's `match=` in sync with the message wording in `_cancel`.

---

### Task 2.1 — Register the 3 tools + MCP exposure test

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/tools/registry.py, apps/api/tests/mcp/test_mcp_server.py</files>
  <action>Wire BOOKING_TOOLS into the booking domain and add all 3 new names to _WRITE and _DESTRUCTIVE. Add an MCP test asserting the 3 tools are exposed with destructiveHint=True and "Cannot be undone." in the description. Depends on Tasks 1.1 + 1.2 (the tools must exist).</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py tests/tools/test_flight_booking_tool.py tests/tools/test_cancel_tools.py -x -q</verify>
  <done>MCP test asserts the 3 tools exposed + destructive; all tool + mcp tests pass; ruff clean.</done>
</task>
```

- [ ] **Step 1 — Write the failing MCP test** — Append to `apps/api/tests/mcp/test_mcp_server.py`:

```python
def test_book_and_cancel_tools_exposed_destructive():
    from app.mcp.server import build_mcp_server

    tools = {t.name: t for t in _list_tools(build_mcp_server())}
    for name in ("book_flight", "cancel_flight", "cancel_hotel"):
        assert name in tools, f"{name} not exposed over MCP"
        assert "Cannot be undone." in tools[name].description
        assert tools[name].annotations.destructiveHint is True
```

- [ ] **Step 2 — Run test, verify it fails** — `cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py::test_book_and_cancel_tools_exposed_destructive -x -q` → FAIL (`KeyError`/assert: tools not registered / not destructive).

- [ ] **Step 3 — Implement registry wiring** — In `apps/api/app/tools/registry.py`:

Add the import (alongside the other `app.tools.*` imports):

```python
from app.tools.booking_tools import BOOKING_TOOLS
```

Change the `booking` domain line so the cancels are included (`book_flight` already arrives via `FLIGHT_TOOLS`):

```python
    "booking": FLIGHT_TOOLS + HOTEL_TOOLS + BOOKING_TOOLS,
```

Extend the annotation sets:

```python
_DESTRUCTIVE = {"book_hotel", "book_flight", "cancel_flight", "cancel_hotel"}
_WRITE = {
    "add_place_to_trip",
    "add_itinerary_item",
    "add_expense",
    "save_user_preference",
    "book_hotel",
    "book_flight",
    "cancel_flight",
    "cancel_hotel",
}
```

- [ ] **Step 4 — Run tests, verify pass** — `cd apps/api && DATABASE_URL="sqlite:///:memory:" ../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py tests/tools/test_flight_booking_tool.py tests/tools/test_cancel_tools.py -x -q` → all pass. Then `ruff check app/tools/registry.py`.

- [ ] **Step 5 — Full-suite gate** — `cd apps/api && make test` → green (no regressions). If setup errors on a stale DB, rebuild `travel.db` first (`stale-travel-db-breaks-suite-on-schema-change`) — though no schema changed here.

---

## 5. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | New `booking_tools.py` group not wired into `TOOLS_BY_DOMAIN["booking"]` → tools silently absent from MCP. | Task 2.1 Step 1 MCP test fails loudly until wired. |
| 2 | `ruff-on-edit` strips the new `flight_tools.py` imports if added before use. | Add import + tool body together; `ruff check` in Step 4. (`ruff-on-edit-strips-unused-imports`) |
| 3 | Hotel arrange assumes Da Nang / 2027-04-10→14 yields ≥1 *available* room. | `.id`/`.available` on `HotelAvailability` are verified to exist (`app/schemas/hotel.py:139`); the `next(...)` now `assert`s a hotel was found rather than raising a bare `StopIteration`. |
| 4 | `public-contract` corroboration hook may flag the additive MCP surface at commit. | Authorize with `RISK_WARN_CATEGORIES="public-contract"` if it fires. (`public-contract-hard-gate`) |
| 5 | `.env` `OPENAI_API_KEY=test` / `DATABASE_URL=postgres:5433` break TestClient-lifespan setup. | Verify commands pin `DATABASE_URL=sqlite:///...`; run with `.env` aside if needed. (`env-openai-key-test-breaks-llm-tests`) |

## 6. Status Log

- 2026-07-09 — Plan drafted from `research-brief.md` (Reuse `book_hotel`). Waves: W1 = Tasks 1.1 + 1.2 (disjoint files, parallel); W2 = Task 2.1 (registry + MCP test).
- 2026-07-09 — Reviewer pass: **Approved** — every code block verified against source (`book_hotel` template, `BookingService` signatures, `FlightBookingRequest` XOR validator, `Booking`/enum shapes, registry sets, MCP annotation append, `HotelAvailability.id/.available`). Applied advisories: pinned verify `DATABASE_URL` to `:memory:` + dropped misleading `rm`; hardened `_book_a_hotel` with an `assert` instead of a bare `StopIteration`.
- 2026-07-09 — **Executed** (subagent-driven). Wave 1 = `41433cf` (Task 1.1 book_flight + Task 1.2 cancels; spec ✅ + quality ✅). Wave 2 = `f034fa5` (Task 2.1 registry + MCP test). Correctness-review follow-ups = `f9e0e38` (Rule 2 ×2: `_cancel` ValueError mapping; `book_flight` non-PII log). Correctness review: no reachable crash bug. Intent review: no divergence. New tests 12/12 green; full suite 1378 passed (5 pre-existing env failures, unrelated).
- 2026-07-09 — shipped via `feat/min-42-implement-mcp-tool` (PR pending).
