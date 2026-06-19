---
slug: trip-budget
status: active
lane: normal
base: v2
branch: feat/trip-budget
---

# Trip Budget (per-category caps) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Add a stored, per-category budget (flights/hotels/activities/buffer) to a trip, exposed via `GET`/`POST /trips/{id}/budget`, and reject a trip-item add whose linked booking would push a category's spend past its cap with a `409` + hint.

**Architecture:** Caps persist as a single nullable JSON `budget_caps` column on `trips` (one additive `ensure_column` migration — the A0 convention). The cap **is** the "planned" figure; "spent" rolls up linked non-cancelled bookings grouped by `BookingType` (FLIGHT→flights, HOTEL→hotels; activities/buffer have no booking source until #15, so spent=0). `estimate_trip` is **not** reused — it is a stateless calculator needing inputs the stored trip lacks. Enforcement lives in `TripService.add_item` (the only place that knows both the trip's caps and the booking's price), mapping the `sqlite`-free domain to a `ConflictError`→409.

**Tech Stack:** FastAPI, Pydantic v2, raw SQLite (`crud/_migrations.ensure_column`), pytest. Layering: router → service (rules, domain exceptions) → crud (SQL).

**Source of decisions:** `specs/trip-budget/SUMMARY.md` (Resolved decisions). Lane: normal + migration waiver.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `app/enums.py` | `BudgetCategory` enum (canonical category set) | Modify (append) |
| `app/schemas/trip.py` | `CategoryBudget`, `BudgetCategories`, `TripBudget` (response), `TripBudgetSet` (POST body) | Modify (append) |
| `app/crud/trip.py` | `budget_caps` column + migration + `get_budget_caps`/`set_budget_caps` | Modify |
| `app/services/trip_service.py` | booking-type→category map, `_resolve_bookings` (extract), `_spend_by_category`, `get_trip_budget`, `set_trip_budget`, `_enforce_budget` wired into `add_item` | Modify |
| `app/routers/trips.py` | `GET`/`POST /trips/{id}/budget` | Modify |
| `tests/test_trip_budget.py` | API-level budget suite | Create |
| `tests/test_trips.py` | legacy-DB ALTER test for `budget_caps` | Modify (append one test) |
| `APIS.md` | endpoint-list doc | Modify (2 lines) |

**Conventions to honor:** Python 3.10+ hints (`X | None`), `Field(..., description=, examples=)` on every new field, services raise domain exceptions (never `HTTPException`), `_money` for all USD rounding, append-only column tuples, `str, Enum` for enums.

---

## Chunk 1: Enum + schemas + storage

### Task 1: `BudgetCategory` enum

**Files:**
- Modify: `app/enums.py` (append a new enum near the other trip/budget enums)

- [ ] **Step 1: Write the failing test** in `tests/test_trip_budget.py` (create the file with this first):

```python
"""API + enum tests for per-category trip budgets (specs/trip-budget)."""

from app.enums import BudgetCategory


def test_budget_category_values():
    assert {c.value for c in BudgetCategory} == {
        "flights",
        "hotels",
        "activities",
        "buffer",
    }
```

- [ ] **Step 2: Run it, expect failure**

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py::test_budget_category_values -q`
Expected: FAIL — `ImportError: cannot import name 'BudgetCategory'`.

- [ ] **Step 3: Implement** — append to `app/enums.py`:

```python
class BudgetCategory(str, Enum):
    """Spend buckets a per-trip budget cap can target.

    flights/hotels map 1:1 to BookingType; activities/buffer have no booking
    source yet (activity booking is unshipped, #15) so their spent is always 0.
    """

    FLIGHTS = "flights"
    HOTELS = "hotels"
    ACTIVITIES = "activities"
    BUFFER = "buffer"
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py::test_budget_category_values -q`
Expected: PASS.

---

### Task 2: Budget schemas

**Files:**
- Modify: `app/schemas/trip.py` (append after the estimate schemas, before `TripListResponse` if present — order doesn't matter, keep it grouped)

- [ ] **Step 1: Write the failing test** (append to `tests/test_trip_budget.py`):

```python
def test_trip_budget_schema_shape():
    from app.schemas.trip import (
        BudgetCategories,
        CategoryBudget,
        TripBudget,
        TripBudgetSet,
    )

    cat = CategoryBudget(cap=700.0, spent=600.0, remaining=100.0)
    cats = BudgetCategories(flights=cat, hotels=cat, activities=cat, buffer=cat)
    budget = TripBudget(
        trip_id="t1",
        categories=cats,
        total_cap=2800.0,
        total_spent=2400.0,
        total_remaining=400.0,
        over_budget=False,
    )
    assert budget.categories.flights.remaining == 100.0
    # POST body: all caps optional, negative rejected
    assert TripBudgetSet(flights=700).flights == 700
    assert TripBudgetSet().flights is None
```

- [ ] **Step 2: Run it, expect failure** (`ImportError`).

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py::test_trip_budget_schema_shape -q`

- [ ] **Step 3: Implement** — append to `app/schemas/trip.py`:

```python
class CategoryBudget(AppBaseModel):
    """Cap (the planned target) vs spent (booked rollup) for one category."""

    cap: float | None = Field(
        default=None,
        description="The budget cap for this category in USD, or null if unset.",
        examples=[700.0],
    )
    spent: float = Field(
        description="Booked spend in this category (USD): linked, non-cancelled "
        "bookings of the matching type. 0 for categories with no booking source.",
        examples=[600.0],
    )
    remaining: float | None = Field(
        default=None,
        description="cap - spent (USD); negative when over. null when no cap is set.",
        examples=[100.0],
    )


class BudgetCategories(AppBaseModel):
    """The four canonical spend buckets, each a cap/spent/remaining triple."""

    flights: CategoryBudget
    hotels: CategoryBudget
    activities: CategoryBudget
    buffer: CategoryBudget


class TripBudget(AppBaseModel):
    """Response for GET/POST /trips/{id}/budget — per-category caps vs spend."""

    trip_id: str = Field(description="Owning trip UUID.")
    categories: BudgetCategories = Field(
        description="Per-category cap vs spent vs remaining."
    )
    total_cap: float | None = Field(
        default=None,
        description="Sum of set caps (USD), or null if no cap is set anywhere.",
    )
    total_spent: float = Field(description="Sum of category spend (USD).")
    total_remaining: float | None = Field(
        default=None,
        description="total_cap - total_spent (USD); null when no cap is set.",
    )
    over_budget: bool = Field(
        description="True if any category with a cap has spent strictly above it."
    )


class TripBudgetSet(AppBaseModel):
    """Request body for POST /trips/{id}/budget. Replace semantics: every POST
    fully replaces the trip's caps — omitted/None categories become uncapped."""

    flights: float | None = Field(default=None, ge=0, description="Flights cap (USD).")
    hotels: float | None = Field(default=None, ge=0, description="Hotels cap (USD).")
    activities: float | None = Field(
        default=None, ge=0, description="Activities cap (USD)."
    )
    buffer: float | None = Field(default=None, ge=0, description="Buffer cap (USD).")
```

- [ ] **Step 4: Run it, expect pass.**

---

### Task 3: `budget_caps` column + CRUD accessors + legacy migration

**Files:**
- Modify: `app/crud/trip.py` (add `import json`; `_TRIPS_SCHEMA` column; `init_db` migration; two methods)
- Modify: `tests/test_trips.py` (append the legacy-DB ALTER test)

- [ ] **Step 1: Write the failing legacy-DB test** — append to `tests/test_trips.py` (mirror the A3 `test_init_db_adds_status_to_legacy_trip_items` precedent; check its imports/helpers and reuse them):

```python
def test_init_db_adds_budget_caps_to_legacy_trips(tmp_path):
    """A trips table created before budget_caps gets the column on init_db,
    and pre-existing rows read back with empty caps (NULL)."""
    import sqlite3

    from app.crud.trip import TripRepository

    db = str(tmp_path / "legacy.db")
    # Legacy trips table WITHOUT budget_caps.
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE trips (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
        "city TEXT, start_date TEXT, end_date TEXT, travelers INTEGER NOT NULL, "
        "notes TEXT, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO trips (id, title, travelers, created_at) "
        "VALUES ('old1', 'Legacy', 1, '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    repo = TripRepository(db)
    repo.init_db()  # must ALTER, not crash

    cols = {
        row[1]
        for row in sqlite3.connect(db).execute("PRAGMA table_info(trips)")
    }
    assert "budget_caps" in cols
    assert repo.get_budget_caps("old1") == {}
```

- [ ] **Step 2: Run it, expect failure**

Run: `.venv/bin/python -m pytest tests/test_trips.py::test_init_db_adds_budget_caps_to_legacy_trips -q`
Expected: FAIL — `AttributeError: 'TripRepository' object has no attribute 'get_budget_caps'` (or column missing).

- [ ] **Step 3: Implement** in `app/crud/trip.py`:

3a. Add `import json` at the top (after `import sqlite3`).

3b. Add the column to `_TRIPS_SCHEMA` (after `deleted_at`):

```python
    deleted_at      TEXT,
    budget_caps     TEXT
```

> Note: `budget_caps` is intentionally **not** added to `_TRIP_COLUMNS` / `_trip_values` /
> `_row_to_trip`. The budget is an independent sub-resource (like `trip_place_link`), set/read
> via dedicated methods; the core `Trip` model stays unchanged.

3c. In `init_db`, after the `status` `ensure_column` block, add:

```python
            # Add budget_caps to legacy trips tables (per-category caps, JSON).
            # Nullable; absent/NULL reads back as no caps set.
            ensure_column(conn, "trips", "budget_caps")
```

3d. Add two methods to `TripRepository` (place them after `delete_trip`, before `add_item`):

```python
    def get_budget_caps(self, trip_id: str) -> dict[str, float]:
        """Return the trip's per-category caps as a dict (empty if unset).

        No existence check here — the service has already 404'd a missing trip.
        A tombstoned/unknown trip simply yields {}.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT budget_caps FROM trips WHERE id = ? AND deleted_at IS NULL",
                (trip_id,),
            ).fetchone()
        if row is None or row["budget_caps"] is None:
            return {}
        return json.loads(row["budget_caps"])

    def set_budget_caps(self, trip_id: str, caps: dict[str, float]) -> None:
        """Persist the trip's caps (replace). Stores JSON; {} clears all caps."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE trips SET budget_caps = ? WHERE id = ? AND deleted_at IS NULL",
                (json.dumps(caps), trip_id),
            )
```

- [ ] **Step 4: Run it, expect pass.**

Run: `.venv/bin/python -m pytest tests/test_trips.py::test_init_db_adds_budget_caps_to_legacy_trips -q`
Expected: PASS.

- [ ] **Step 5: Guard against regressions** — the column add must not break existing trip CRUD (the `SELECT *` in `get_trip` now returns an extra column, which `_row_to_trip` ignores by name).

Run: `.venv/bin/python -m pytest tests/test_trips.py -q`
Expected: PASS (no regressions).

---

## Chunk 2: Service logic

### Task 4: Spend-by-category + get/set budget

**Files:**
- Modify: `app/services/trip_service.py`

- [ ] **Step 1: Write failing service tests** (append to `tests/test_trip_budget.py`). These use the API for setup but assert the GET budget contract:

```python
def _create_trip(client, **overrides):
    body = {"title": "Budget trip", "travelers": 1}
    body.update(overrides)
    resp = client.post("/trips", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_get_budget_no_caps_is_all_null(client):
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['id']}/budget")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trip_id"] == trip["id"]
    assert body["total_cap"] is None
    assert body["total_spent"] == 0.0
    assert body["over_budget"] is False
    for cat in ("flights", "hotels", "activities", "buffer"):
        assert body["categories"][cat]["cap"] is None
        assert body["categories"][cat]["spent"] == 0.0
        assert body["categories"][cat]["remaining"] is None


def test_post_budget_sets_and_get_reflects(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/budget",
        json={"flights": 700, "hotels": 600, "activities": 300, "buffer": 200},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["categories"]["flights"]["cap"] == 700.0
    assert body["categories"]["flights"]["remaining"] == 700.0  # nothing spent yet
    assert body["total_cap"] == 1800.0
    # GET mirrors it
    got = client.get(f"/trips/{trip['id']}/budget").json()
    assert got["categories"]["hotels"]["cap"] == 600.0


def test_post_budget_replace_semantics(client):
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": 700})
    # Second POST omits flights → it becomes uncapped again.
    client.post(f"/trips/{trip['id']}/budget", json={"hotels": 500})
    body = client.get(f"/trips/{trip['id']}/budget").json()
    assert body["categories"]["flights"]["cap"] is None
    assert body["categories"]["hotels"]["cap"] == 500.0


def test_post_budget_negative_is_422(client):
    trip = _create_trip(client)
    resp = client.post(f"/trips/{trip['id']}/budget", json={"flights": -1})
    assert resp.status_code == 422


def test_budget_unknown_trip_404(client):
    assert client.get("/trips/nope/budget").status_code == 404
    assert client.post("/trips/nope/budget", json={"flights": 100}).status_code == 404
```

- [ ] **Step 2: Run them, expect failure** (404/route-missing or AttributeError).

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py -q`

- [ ] **Step 3: Implement service helpers + methods** in `app/services/trip_service.py`:

3a. Imports: add `BudgetCategory` to the `app.enums` import block; add `TripBudget`, `TripBudgetSet`, `CategoryBudget`, `BudgetCategories` to the `app.schemas.trip` import block.

3b. Module-level map (near `_VALID_SOURCES`):

```python
# Which budget category a booking's spend lands in. Activities/buffer have no
# booking source yet (activity booking is unshipped, #15).
_BOOKING_TYPE_TO_CATEGORY: dict[BookingType, BudgetCategory] = {
    BookingType.FLIGHT: BudgetCategory.FLIGHTS,
    BookingType.HOTEL: BudgetCategory.HOTELS,
}
```

3c. Extract the booking-resolution loop from `get_trip_detail` into a method so spend logic is single-sourced (behavior-preserving):

```python
    def _resolve_bookings(self, trip: Trip) -> dict[str, object]:
        """Resolve every distinct linked booking_id once. Missing → None."""
        booking_svc = get_booking_service()
        resolved: dict[str, object] = {}
        for item in trip.items:
            if item.booking_id is None or item.booking_id in resolved:
                continue
            try:
                resolved[item.booking_id] = booking_svc.get(item.booking_id)
            except NotFoundError:
                logger.info(
                    "Booking %r not found for item %s — skipping spend",
                    item.booking_id,
                    item.id,
                )
                resolved[item.booking_id] = None
        return resolved
```

Then in `get_trip_detail`, replace the inline resolve block (the `booking_svc = ...` line and the `resolved: dict ... = {}` loop) with `resolved = self._resolve_bookings(trip)`. Leave the rest of `get_trip_detail` (total/gaps) unchanged.

3d. Spend-by-category (per-item sum, matching `total_spent`'s existing semantics so `sum(spend) == total_spent`):

```python
    def _spend_by_category(self, trip: Trip) -> dict[BudgetCategory, float]:
        """Sum booked spend per category. Per-item (matches total_spent)."""
        resolved = self._resolve_bookings(trip)
        spend: dict[BudgetCategory, float] = {c: 0.0 for c in BudgetCategory}
        for item in trip.items:
            if item.booking_id is None:
                continue
            booking = resolved.get(item.booking_id)
            if booking is None or booking.status == BookingStatus.CANCELLED:
                continue
            category = _BOOKING_TYPE_TO_CATEGORY.get(booking.type)
            if category is None:
                continue
            spend[category] += booking.total_price
        return {c: _money(v) for c, v in spend.items()}
```

3e. Build the budget view + the setter:

```python
    def get_trip_budget(self, trip_id: str) -> TripBudget:
        """Return per-category caps vs spend for a trip. 404 if unknown."""
        trip = self.get_trip(trip_id)
        caps = self._repo.get_budget_caps(trip_id)
        spend = self._spend_by_category(trip)
        return self._build_budget(trip_id, caps, spend)

    def set_trip_budget(self, trip_id: str, request: TripBudgetSet) -> TripBudget:
        """Replace the trip's caps and return the resulting budget. 404 if unknown."""
        self.get_trip(trip_id)
        caps = {
            c.value: getattr(request, c.value)
            for c in BudgetCategory
            if getattr(request, c.value) is not None
        }
        self._repo.set_budget_caps(trip_id, caps)
        logger.info("Set budget on trip %s: %s", trip_id, caps)
        return self.get_trip_budget(trip_id)

    @staticmethod
    def _build_budget(
        trip_id: str, caps: dict[str, float], spend: dict[BudgetCategory, float]
    ) -> TripBudget:
        cat_models: dict[str, CategoryBudget] = {}
        total_cap = 0.0
        any_cap = False
        over = False
        for c in BudgetCategory:
            cap = caps.get(c.value)
            spent = spend[c]
            remaining = _money(cap - spent) if cap is not None else None
            if cap is not None:
                any_cap = True
                total_cap += cap
                if spent > cap:
                    over = True
            cat_models[c.value] = CategoryBudget(
                cap=cap, spent=spent, remaining=remaining
            )
        total_spent = _money(sum(spend.values()))
        return TripBudget(
            trip_id=trip_id,
            categories=BudgetCategories(**cat_models),
            total_cap=_money(total_cap) if any_cap else None,
            total_spent=total_spent,
            total_remaining=_money(total_cap - total_spent) if any_cap else None,
            over_budget=over,
        )
```

- [ ] **Step 4: Run the Task-4 tests, expect pass.**

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py -q`
Expected: schema/no-cap/set/replace/422/404 tests PASS. (Enforcement + spend-from-booking tests come in Task 5.)

- [ ] **Step 5: Guard `get_trip_detail` refactor**

Run: `.venv/bin/python -m pytest tests/test_trips.py tests/test_trip_value_layer_api.py tests/test_trip_value_layer_service.py -q`
Expected: PASS (total_spent/gaps unchanged).

---

### Task 5: 409 enforcement on item add

**Files:**
- Modify: `app/services/trip_service.py` (`add_item` + `_enforce_budget`)

- [ ] **Step 1: Write failing enforcement tests** (append to `tests/test_trip_budget.py`). Reuse the booking helpers from `tests/test_bookings.py` and `tests/conftest.py`:

```python
import pytest

from app.services import hotel_service
from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    get_first_flight_booking_fields,
)


@pytest.fixture
def _flight_booking(client):
    """Create a real flight booking; return (booking_id, total_price)."""
    resp = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Test User",
            "passenger_email": "test@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    )
    # NB: /flights/book returns 200 (not 201) — it sets no status_code, so
    # FastAPI's POST default applies (see tests/test_flights.py::test_book_flight_returns_200).
    assert resp.status_code == 200, resp.text
    b = resp.json()
    return b["id"], b["total_price"]


def _add_item(client, trip_id, **overrides):
    body = {"day": 1, "kind": "place", "title": "Stop", "sort_order": 0}
    body.update(overrides)
    return client.post(f"/trips/{trip_id}/items", json=body)


def test_spent_rolls_up_linked_flight_booking(client, _flight_booking):
    booking_id, price = _flight_booking
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": price + 1000})
    resp = _add_item(client, trip["id"], booking_id=booking_id)
    assert resp.status_code == 201, resp.text
    body = client.get(f"/trips/{trip['id']}/budget").json()
    assert body["categories"]["flights"]["spent"] == price
    assert body["categories"]["flights"]["remaining"] == price + 1000 - price


def test_item_add_over_flights_cap_is_409(client, _flight_booking):
    booking_id, price = _flight_booking
    trip = _create_trip(client)
    # Cap below the booking price → adding the linked item must 409.
    client.post(f"/trips/{trip['id']}/budget", json={"flights": price - 1})
    resp = _add_item(client, trip["id"], booking_id=booking_id)
    assert resp.status_code == 409, resp.text
    msg = (resp.json().get("message", "") + resp.json().get("hint", "")).lower()
    assert "flights" in msg and "budget" in msg


def test_item_add_no_cap_for_category_not_blocked(client, _flight_booking):
    booking_id, _price = _flight_booking
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"hotels": 1})  # flights uncapped
    assert _add_item(client, trip["id"], booking_id=booking_id).status_code == 201


def test_item_add_at_cap_boundary_allowed(client, _flight_booking):
    booking_id, price = _flight_booking
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": price})  # exactly equal
    # spent would become exactly the cap; "over" is strictly greater → allowed.
    assert _add_item(client, trip["id"], booking_id=booking_id).status_code == 201


def test_item_add_without_booking_never_blocked(client):
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": 1})
    assert _add_item(client, trip["id"]).status_code == 201  # no booking_id
```

- [ ] **Step 2: Run them, expect failure** (adds currently 201 even when over cap).

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py -q -k "over or boundary or rolls_up or no_cap or without_booking"`

- [ ] **Step 3: Implement** in `app/services/trip_service.py`:

3a. Capture the trip in `add_item` (it already calls `self.get_trip(trip_id)`; keep the return) and call the guard **after** the idempotency-replay check, **before** building/inserting the item:

```python
    def add_item(self, trip_id, request, idempotency_key=None):
        trip = self.get_trip(trip_id)
        if idempotency_key:
            existing = self._repo.get_item_by_idempotency_key(idempotency_key)
            if existing is not None:
                ...  # unchanged replay block (return existing)
        self._enforce_budget(trip, request)   # <-- NEW, before insert
        item = TripItem(id=_new_id(), trip_id=trip_id, **request.model_dump())
        ...
```

> Order matters: replay returns the original item without re-checking (a replay is not a new
> charge); a fresh add is budget-checked before it is stored.

3b. The guard:

```python
    def _enforce_budget(self, trip: Trip, request: TripItemCreate) -> None:
        """Reject (409) when a linked booking would push its category over cap.

        No-ops unless the new item links a resolvable, non-cancelled booking
        whose category has a cap set. Boundary is strict: spent == cap is OK.
        """
        if request.booking_id is None:
            return
        caps = self._repo.get_budget_caps(trip.id)
        if not caps:
            return
        try:
            booking = get_booking_service().get(request.booking_id)
        except NotFoundError:
            return  # unpriceable link — consistent with total_spent skipping it
        if booking.status == BookingStatus.CANCELLED:
            return
        category = _BOOKING_TYPE_TO_CATEGORY.get(booking.type)
        if category is None:
            return
        cap = caps.get(category.value)
        if cap is None:
            return
        current = self._spend_by_category(trip)[category]
        projected = _money(current + booking.total_price)
        if projected > cap:
            over_by = _money(projected - cap)
            raise ConflictError(
                f"Adding this ${booking.total_price:.2f} {category.value} booking "
                f"would push {category.value} spend to ${projected:.2f}, over the "
                f"${cap:.2f} budget by ${over_by:.2f}.",
                hint=(
                    f"Raise the {category.value} cap via POST /trips/{trip.id}/budget, "
                    "or link a cheaper booking."
                ),
            )
```

- [ ] **Step 4: Run them, expect pass.**

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py -q`
Expected: all budget tests PASS.

---

## Chunk 3: Router + docs + full verification

### Task 6: Endpoints

**Files:**
- Modify: `app/routers/trips.py`

- [ ] **Step 1:** The API tests in Tasks 4–5 already exercise the routes; they fail at route-resolution until these exist. (No separate test step.)

- [ ] **Step 2: Implement** — add imports `TripBudget, TripBudgetSet` to the `app.schemas.trip` import block, then add two routes (place after `get_day_plan`, grouped with the trip-level reads/writes):

```python
@router.get(
    "/{trip_id}/budget",
    response_model=TripBudget,
    summary="Per-category budget: caps (planned) vs booked spend",
    responses=error_responses(404, 422),
)
def get_trip_budget(trips: TripsDep, trip_id: _TRIP_ID) -> TripBudget:
    """Return flights/hotels/activities/buffer caps vs spent vs remaining.

    'spent' rolls up linked, non-cancelled bookings by type (activities/buffer
    have no booking source yet, so 0). 404 if the trip UUID is unknown.
    """
    return trips.get_trip_budget(trip_id)


@router.post(
    "/{trip_id}/budget",
    response_model=TripBudget,
    summary="Set a trip's per-category budget caps (replace)",
    responses=error_responses(404, 422),
)
def set_trip_budget(
    trips: TripsDep, trip_id: _TRIP_ID, body: TripBudgetSet
) -> TripBudget:
    """Replace the trip's caps and return the budget. Every POST fully replaces
    the caps — omitted categories become uncapped. 404 if the trip is unknown.

    Once set, POST /trips/{id}/items returns 409 when a linked booking would
    push that category's spend over its cap.
    """
    return trips.set_trip_budget(trip_id, body)
```

- [ ] **Step 3: Declare the new 409 on the item-add route** — `add_item` now has a budget-exceeded 409 path, so its OpenAPI codes must list it (CLAUDE.md: "Routes declare codes via `responses=error_responses(...)`"). In `app/routers/trips.py`, change the `add_item` decorator:

```python
@router.post(
    "/{trip_id}/items",
    response_model=TripItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to a trip",
    responses=error_responses(404, 409, 422),   # was (404, 422); 409 = over budget
)
```

Update its docstring tail to mention the 409 (e.g. "409 if a linked booking would exceed a budget cap.").

- [ ] **Step 4: Run the full budget suite, expect pass.**

Run: `.venv/bin/python -m pytest tests/test_trip_budget.py -q`

### Task 7: Docs + full verification

**Files:**
- Modify: `APIS.md` (add the two endpoints under the Trips group, matching the existing format)

- [ ] **Step 1:** Add to `APIS.md` Trips section:
  - `GET /trips/{id}/budget` — per-category caps vs booked spend
  - `POST /trips/{id}/budget` — set per-category caps (replace; over-cap item adds 409)

- [ ] **Step 2: Full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: previously-green count + the new tests pass. **Baseline carry-over:** the 2 pre-existing failures in `tests/test_meta.py::test_root_endpoints_is_list` and `tests/test_operation_ids.py::test_operation_ids_are_handler_names` are dependency-drift (FastAPI 0.136/Starlette 1.2 route introspection), unrelated to this change — they must remain the ONLY failures (no new ones, and these two unchanged).

- [ ] **Step 3: Lint**

Run: `ruff check app tests && ruff format --check app tests`
Expected: clean on touched files. Run `ruff format app tests` if needed.

- [ ] **Step 4: Sanity-curl (optional, manual)** — `uvicorn app.main:app --port 8000`, then `POST /trips`, `POST /trips/{id}/budget`, `GET /trips/{id}/budget`, confirm the envelope.

---

## Review gates (normal lane — see SUMMARY.md)

- Per-task **spec review** (oracle: this PLAN) + **quality review** (maintainability) between tasks.
- Final **`/correctness-review`** (blind to plan): trace the per-item-vs-deduped spend semantics, the strict-`>` boundary, replay-before-enforce ordering, JSON NULL→`{}` round-trip, and the `_resolve_bookings` extraction preserving `total_spent`.
- Final **`/intent-review`** (oracle: SUMMARY `### Intent`): GET by category (planned=cap vs spent) + POST set caps + 409-on-exceed all delivered; no scope creep (no activity booking, no estimate reuse, no per-item planned cost).
- **Migration obligation (A0):** the legacy-DB ALTER test (Task 3 Step 1) is required, not optional.

## Out of scope (do NOT build)

- Activity booking (#15) — so activities/buffer `spent` stays 0; the mapping is ready for when it ships.
- Reusing `estimate_trip` inside `/budget` (rejected — see SUMMARY).
- Per-item planned-cost field.
- Enforcing budget at `/flights/book` · `/hotels/book` (they don't know the trip).
- Fixing the 2 pre-existing meta-introspection test failures (separate dependency-pin concern).
