---
slug: flights-side-panel
status: proposed
owner: Minh Tran
created: 2026-07-01
extends: specs/agent-side-panel/
---

# Flights Side Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Render `search_flights` results as a compact, expandable list in the existing chat side-drawer by adding one `flights` panel *kind* to the shipped side-panel pipeline.

**Architecture:** Mirror the route/weather/air_quality pattern (verified in `research-brief.md`): a BE `FlightsPanel` Pydantic projection + `"flights"` in `PanelKind`; `search_flights` converts to `@tool(response_format="content_and_artifact")` returning `panel_result(...)` on results and `(message, None)` on empty; the mapper + FE drawer already dispatch any `kind` unchanged; a new FE `FlightsPanel.tsx` + registry/type entries render it.

**Tech Stack:** FastAPI · Pydantic v2 (`AppBaseModel`) · LangChain 1.x (`content_and_artifact`) · Next.js 16 / React 19 / TS 5 · Tailwind (token classes: `border-line`, `bg-surface`, `text-muted`, `text-ink`).

**Branch:** off `feat/search-tool-hardening` (workstream A not yet merged to `v3`). Do NOT branch off `v3`.

**Non-goals (from design.md §2):** hotels/places panels; client-side sort/filter; Book action; loading skeleton; empty-state panel.

---

## Chunk 1: Flights panel (BE projection → tool → FE)

### File Structure

| File | Responsibility | Task |
|---|---|---|
| `apps/api/app/streaming/panels.py` | add `FlightsPanel*` models + `"flights"` in `PanelKind` | 1.1 |
| `apps/api/tests/streaming/test_flights_panel.py` (new) | unit-test `FlightsPanel.from_flights` projection | 1.1 |
| `apps/web/src/lib/stream/panel.ts` | add `FlightsPanelData` type + `"flights"` in FE `PanelKind` | 1.2 |
| `apps/web/src/components/chat/panel/FlightsPanel.tsx` (new) | compact-list + row-expand renderer | 1.2 |
| `apps/web/src/components/chat/panel/registry.ts` | register renderer + label | 1.2 |
| `apps/web/src/components/chat/panel/FlightsPanel.test.tsx` (new) | render rows / cheapest marker / expand toggle | 1.2 |
| `apps/api/app/tools/flight_tools.py` | convert `search_flights` to `content_and_artifact`; update docstring | 2.1 |
| `apps/api/tests/tools/test_booking_tools.py` | update the 3 tests broken by the conversion + add panel-artifact test | 2.1 |

**Waves:** Wave 1 = {1.1 BE, 1.2 FE} — disjoint (`apps/api` vs `apps/web`), run in parallel. Wave 2 = {2.1} — depends on `FlightsPanel` from 1.1.

---

### Task 1.1 — BE: `FlightsPanel` projection + `PanelKind`

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/panels.py, apps/api/tests/streaming/test_flights_panel.py</files>
  <action>Add the flights projection models to panels.py and extend PanelKind. Mirror RoutePanel's from_*_response classmethod pattern. Use only real Flight/Airline fields.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_flights_panel.py -x</verify>
  <done>from_flights projects every flight + cheapest_price/results_count; PanelKind includes "flights"; test green.</done>
</task>
```

**Steps (TDD):**

- [ ] **Step 1 — Write the failing projection test.** Create `apps/api/tests/streaming/test_flights_panel.py`:

```python
"""FlightsPanel projection (specs/flights-side-panel Task 1.1)."""

from datetime import datetime, timezone

from app.schemas.flight import Airline, Flight
from app.streaming.panels import FlightsPanel


def _flight(fnum: str, price: float, dep_hour: int) -> Flight:
    return Flight(
        id=f"FL-{fnum}",
        airline=Airline(code="VJ", name="VietJet Air"),
        flight_number=fnum,
        origin="HAN",
        destination="SGN",
        departure_time=datetime(2027, 3, 15, dep_hour, 0, tzinfo=timezone.utc),
        arrival_time=datetime(2027, 3, 15, dep_hour + 2, 15, tzinfo=timezone.utc),
        duration_minutes=135,
        price=price,
        currency="USD",
        seats_available=5,
        stops=0,
    )


def test_from_flights_projects_all_fields_and_cheapest():
    flights = [_flight("VJ155", 98.0, 9), _flight("VJ179", 76.0, 20)]
    panel = FlightsPanel.from_flights("HAN", "SGN", "2027-03-15", flights)

    assert panel.origin == "HAN"
    assert panel.destination == "SGN"
    assert panel.departure_date == "2027-03-15"
    assert panel.results_count == 2
    assert panel.cheapest_price == 76.0
    assert [f.flight_number for f in panel.flights] == ["VJ155", "VJ179"]  # order preserved
    first = panel.flights[0]
    assert first.airline_name == "VietJet Air"
    assert first.airline_code == "VJ"
    assert first.price == 98.0 and first.currency == "USD"
    assert first.stops == 0 and first.seats_available == 5
```

- [ ] **Step 2 — Run it, verify it fails.**
Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_flights_panel.py -x`
Expected: FAIL — `ImportError: cannot import name 'FlightsPanel'`.

- [ ] **Step 3 — Add the models + PanelKind.** In `apps/api/app/streaming/panels.py`: add `Flight` to the schema imports, extend `PanelKind`, and append the two models.

```python
# at top, with the other schema imports
from app.schemas.flight import Flight

# replace the PanelKind line
PanelKind = Literal["route", "places", "weather", "air_quality", "flights"]
```

```python
# append near the end of panels.py (after the existing panel models)
class FlightsPanelFlight(AppBaseModel):
    """One flight row in a ``kind="flights"`` panel."""

    id: str
    flight_number: str
    airline_name: str
    airline_code: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    stops: int
    seats_available: int
    price: float
    currency: str


class FlightsPanel(AppBaseModel):
    """``data`` payload for a ``kind="flights"`` panel — the flights drawer's model."""

    origin: str
    destination: str
    departure_date: str
    results_count: int
    cheapest_price: float
    flights: list[FlightsPanelFlight]

    @classmethod
    def from_flights(
        cls, origin: str, destination: str, departure_date: str, flights: list[Flight]
    ) -> "FlightsPanel":
        """Project the tool's (non-empty) flight list into the panel render model.

        Order is preserved (the tool already applied the requested ``sort``).

        :param origin: Origin code echoed into the header.
        :param destination: Destination code echoed into the header.
        :param departure_date: Departure date echoed into the header.
        :param flights: The non-empty flight list from ``FlightService.search_flights``.
        :return: The flights panel render model.
        """
        return cls(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            results_count=len(flights),
            cheapest_price=min(f.price for f in flights),
            flights=[
                FlightsPanelFlight(
                    id=f.id,
                    flight_number=f.flight_number,
                    airline_name=f.airline.name,
                    airline_code=f.airline.code,
                    origin=f.origin,
                    destination=f.destination,
                    departure_time=f.departure_time,
                    arrival_time=f.arrival_time,
                    duration_minutes=f.duration_minutes,
                    stops=f.stops,
                    seats_available=f.seats_available,
                    price=f.price,
                    currency=f.currency,
                )
                for f in flights
            ],
        )
```

Add `datetime` to imports if not present: `from datetime import datetime`.

- [ ] **Step 4 — Run it, verify it passes.**
Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_flights_panel.py -x` → PASS.
Then lint: `cd apps/api && ../../.venv/bin/ruff check app/streaming/panels.py tests/streaming/test_flights_panel.py` → clean.

> If `tests/streaming/` has no `__init__.py`, follow whatever the sibling test dirs do (the suite uses `rootdir` config discovery — no `__init__` needed in this repo).

---

### Task 1.2 — FE: `FlightsPanel.tsx` + type + registry

```xml
<task id="1.2" wave="1">
  <files>apps/web/src/lib/stream/panel.ts, apps/web/src/components/chat/panel/FlightsPanel.tsx, apps/web/src/components/chat/panel/registry.ts, apps/web/src/components/chat/panel/FlightsPanel.test.tsx</files>
  <action>Add FlightsPanelData type + "flights" to FE PanelKind; create the compact-list + row-expand renderer; register it. Pure render, local expand state only.</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web test -- src/components/chat/panel/FlightsPanel.test.tsx</verify>
  <done>Renders N rows, marks cheapest, toggles expand; type + registry updated; typecheck clean.</done>
</task>
```

**Node:** all FE commands need Node 24 — `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"` first.

**Steps:**

- [ ] **Step 1 — Add the FE types.** In `apps/web/src/lib/stream/panel.ts`:

```ts
// extend the union
export type PanelKind = "route" | "places" | "weather" | "air_quality" | "flights";

// append with the other panel data interfaces
export interface FlightsPanelFlight {
  id: string;
  flight_number: string;
  airline_name: string;
  airline_code: string;
  origin: string;
  destination: string;
  departure_time: string; // ISO (model_dump mode="json")
  arrival_time: string;
  duration_minutes: number;
  stops: number;
  seats_available: number;
  price: number;
  currency: string;
}

export interface FlightsPanelData {
  origin: string;
  destination: string;
  departure_date: string;
  results_count: number;
  cheapest_price: number;
  flights: FlightsPanelFlight[];
}
```

- [ ] **Step 2 — Write the failing component test.** Create `apps/web/src/components/chat/panel/FlightsPanel.test.tsx` (mirror the existing FE test setup — vitest + @testing-library/react; check a sibling `*.test.tsx` for the exact import style and adapt):

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FlightsPanel } from "./FlightsPanel";
import type { FlightsPanelData } from "@/lib/stream/panel";

const DATA: FlightsPanelData = {
  origin: "HAN",
  destination: "SGN",
  departure_date: "2027-03-15",
  results_count: 2,
  cheapest_price: 76,
  flights: [
    { id: "1", flight_number: "VJ155", airline_name: "VietJet Air", airline_code: "VJ",
      origin: "HAN", destination: "SGN", departure_time: "2027-03-15T09:40:00Z",
      arrival_time: "2027-03-15T11:55:00Z", duration_minutes: 135, stops: 0,
      seats_available: 5, price: 98, currency: "USD" },
    { id: "2", flight_number: "VJ179", airline_name: "VietJet Air", airline_code: "VJ",
      origin: "HAN", destination: "SGN", departure_time: "2027-03-15T20:30:00Z",
      arrival_time: "2027-03-15T23:05:00Z", duration_minutes: 155, stops: 1,
      seats_available: 3, price: 76, currency: "USD" },
  ],
};

describe("FlightsPanel", () => {
  it("renders a row per flight and the header count", () => {
    render(<FlightsPanel data={DATA} />);
    expect(screen.getByText(/2 results/i)).toBeInTheDocument();
    // Flight number sits in a mixed text node ("VietJet Air VJ155 · nonstop · 5 left"),
    // so match with a regex — the repo convention (see RoutePanel.test.tsx).
    expect(screen.getByText(/VJ155/)).toBeInTheDocument();
    expect(screen.getByText(/VJ179/)).toBeInTheDocument();
  });

  it("expands a row on click to reveal detail", () => {
    render(<FlightsPanel data={DATA} />);
    expect(screen.queryByText(/seats left/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/VJ155/));
    expect(screen.getByText(/seats left/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3 — Run it, verify it fails.**
Run: `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web test -- src/components/chat/panel/FlightsPanel.test.tsx`
Expected: FAIL — cannot resolve `./FlightsPanel`.

- [ ] **Step 4 — Create the component.** `apps/web/src/components/chat/panel/FlightsPanel.tsx`:

```tsx
"use client";

import { useState } from "react";

import type { FlightsPanelData, FlightsPanelFlight } from "@/lib/stream/panel";

/**
 * Flights side-panel (specs/flights-side-panel) — a compact list so every result
 * is visible without scrolling the chat. One dense row per flight; click a row to
 * expand full detail. Read-only (no booking tool). Pure render + local expand state.
 */

function hhmm(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

function dur(mins: number): string {
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function stopLabel(stops: number): string {
  return stops === 0 ? "nonstop" : `${stops} stop${stops > 1 ? "s" : ""}`;
}

function Row({ f, cheapest }: { f: FlightsPanelFlight; cheapest: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="rounded-[11px] border border-line"
      style={cheapest ? { boxShadow: "0 0 0 1px var(--color-lime)" } : undefined}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-bold tabular-nums text-ink">
            {hhmm(f.departure_time)} → {hhmm(f.arrival_time)}{" "}
            <span className="font-medium text-faint">{dur(f.duration_minutes)}</span>
          </div>
          <div className="truncate text-[11.5px] text-muted">
            {f.airline_name} {f.flight_number} · {stopLabel(f.stops)} · {f.seats_available} left
          </div>
        </div>
        <div className="text-right">
          <div className="text-[15px] font-extrabold tabular-nums text-ink">
            ${Math.round(f.price)}
          </div>
          <div
            className="text-[10.5px] font-bold"
            style={{ color: f.stops === 0 ? "var(--color-status-confirmed)" : "var(--color-coral-ink)" }}
          >
            {stopLabel(f.stops)}
          </div>
        </div>
      </button>
      {open && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-line px-3 py-2.5 text-[12px]">
          <Detail k="Airline" v={`${f.airline_name} (${f.airline_code})`} />
          <Detail k="Flight" v={f.flight_number} />
          <Detail k="Route" v={`${f.origin} → ${f.destination}`} />
          <Detail k="Duration" v={dur(f.duration_minutes)} />
          <Detail k="Stops" v={stopLabel(f.stops)} />
          <Detail k="Seats left" v={String(f.seats_available)} />
          <Detail k="Price" v={`${f.price.toFixed(2)} ${f.currency}`} />
        </dl>
      )}
    </div>
  );
}

function Detail({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-muted">{k}</dt>
      <dd className="font-semibold text-ink">{v}</dd>
    </div>
  );
}

export function FlightsPanel({ data }: { data: FlightsPanelData }) {
  const { origin, destination, departure_date, results_count, cheapest_price, flights } = data;
  return (
    <div className="h-full overflow-y-auto p-md">
      <div className="mb-2.5">
        <div className="flex items-center gap-2 text-[15px] font-bold text-ink">
          {origin} <span className="font-black text-lime">→</span> {destination}
        </div>
        <div className="text-[12.5px] text-muted">
          {departure_date} · {results_count} results · cheapest ${Math.round(cheapest_price)}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {flights.map((f) => (
          <Row key={f.id} f={f} cheapest={f.price === cheapest_price} />
        ))}
      </div>
    </div>
  );
}
```

> Token classes match `WeatherPanel.tsx` (`border-line`, `text-ink`, `text-muted`, `text-faint`, `p-md`). CSS vars (`--color-lime`, `--color-status-confirmed`, `--color-coral-ink`) are the same tokens defined in `apps/web/src/app/globals.css`. Do NOT use `max-w-{sm,md,lg}` (they resolve to spacing px in TW v4 here — memory `tailwind-spacing-shadows-max-w-tshirt`); use arbitrary `[..rem]` if a width cap is ever needed.

- [ ] **Step 5 — Register the renderer.** In `apps/web/src/components/chat/panel/registry.ts`:

```ts
import { FlightsPanel } from "./FlightsPanel";
// ...
export const PANEL_RENDERERS: Record<string, ComponentType<{ data: unknown }>> = {
  route: RoutePanel as unknown as ComponentType<{ data: unknown }>,
  weather: WeatherPanel as unknown as ComponentType<{ data: unknown }>,
  air_quality: AirQualityPanel as unknown as ComponentType<{ data: unknown }>,
  flights: FlightsPanel as unknown as ComponentType<{ data: unknown }>,
};

export const PANEL_LABELS: Record<string, string> = {
  route: "Route",
  places: "Places",
  weather: "Weather",
  air_quality: "Air Quality",
  flights: "Flights",
};
```

- [ ] **Step 6 — Run test + typecheck.**
Run: `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web test -- src/components/chat/panel/FlightsPanel.test.tsx` → PASS.
Run: `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web typecheck` → clean.

---

### Task 2.1 — BE: convert `search_flights` to `content_and_artifact`

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/tools/flight_tools.py, apps/api/tests/tools/test_booking_tools.py</files>
  <action>Convert search_flights to @tool(response_format="content_and_artifact"): on results return panel_result(summary, kind="flights", data=FlightsPanel.from_flights(...)); on empty return (message, None); keep ToolException on failure. Update docstring. Update the 3 tests broken by the conversion and re-home the price-sort assertion onto the artifact.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x -k flight && ../../.venv/bin/ruff check app/tools/flight_tools.py</verify>
  <done>Results → ToolMessage.artifact kind="flights"; empty → (msg, None); bad date → ToolException; 3 updated tests + panel-artifact test green; lint clean.</done>
</task>
```

**Steps (TDD — update tests first, they will fail against the old shape):**

- [ ] **Step 1 — Rewrite the flight tests for the new shape.** In `apps/api/tests/tools/test_booking_tools.py`, add a ToolCall invoke helper (sync tool → `.invoke`, not `ainvoke`) and update the three flight tests:

```python
from langchain_core.messages import ToolMessage


def _invoke_flight(args: dict) -> ToolMessage:
    """Invoke the sync content_and_artifact search_flights via ToolCall → ToolMessage."""
    from app.tools.flight_tools import search_flights
    return search_flights.invoke(
        {"type": "tool_call", "id": "t1", "name": "search_flights", "args": args}
    )


def test_search_flights_returns_panel_artifact(agent_db):
    msg = _invoke_flight({"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15"})
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()  # model-facing summary
    assert msg.artifact["kind"] == "flights"
    data = msg.artifact["data"]
    assert data["results_count"] == len(data["flights"]) >= 1
    assert "flight_number" in data["flights"][0]


def test_search_flights_price_sort_orders_artifact(agent_db):
    # Sort order is observable on the artifact now, not the content.
    msg = _invoke_flight(
        {"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15", "sort": "price_asc"}
    )
    prices = [f["price"] for f in msg.artifact["data"]["flights"]]
    assert prices == sorted(prices)


def test_search_flights_no_match_returns_message_no_panel(agent_db):
    msg = _invoke_flight(
        {"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15", "max_price": 1}
    )
    assert isinstance(msg, ToolMessage)
    assert msg.artifact is None          # no panel on empty
    assert "no flights" in msg.content.lower()
```

Delete/replace the three now-obsolete tests: `test_search_flights_returns_list`, `test_search_flights_with_price_sort`, `test_search_flights_no_match_returns_reason`. Keep `test_search_flights_bad_date_raises` (still valid — `ToolException` on bad date is unchanged).

- [ ] **Step 2 — Run, verify failure.**
Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x -k flight`
Expected: FAIL — old tests reference removed behavior / new tests hit a tool still returning a list.

- [ ] **Step 3 — Convert the tool.** Rewrite `apps/api/app/tools/flight_tools.py` — decorator, imports, docstring, body:

```python
from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.services.flight_service import DEFAULT_SORT, FlightService
from app.streaming.panels import FlightsPanel
from app.tools._base import log_tool_call, panel_result, session_scope


@tool(response_format="content_and_artifact")
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str | None = None,
    max_price: float | None = None,
    max_stops: int | None = None,
    sort: str = DEFAULT_SORT,
) -> tuple[str, dict | None]:
    """Search flights for a route and date with optional filters and sort.

    Returns up to 5 deterministic flights — same query always returns the same
    results. On success the model sees a short summary and the full comparison is
    sent to the Flights side panel. If no flights match, returns a short message
    and no panel; tell the user none were found and never invent flights.

    :param origin: 3-letter IATA code for the origin airport (e.g. 'HAN', 'SGN', 'NRT').
    :param destination: 3-letter IATA code for the destination airport (e.g. 'HAN', 'SGN', 'NRT').
    :param departure_date: ISO date YYYY-MM-DD.
    :param airline: 2-letter IATA code to filter by carrier (e.g. 'VN').
    :param max_price: Keep only flights at or below this fare.
    :param max_stops: 0 = nonstop only, 1 = up to one stop.
    :param sort: departure_asc | departure_desc | price_asc | price_desc |
        duration_asc | duration_desc. Defaults to departure_asc.
    :return: A (summary, artifact) tuple. On matches the artifact is a
        ``{"kind": "flights", "data": ...}`` side-panel payload; on no match the
        artifact is ``None`` (no panel) and the summary explains the empty result.
    """
    log_tool_call("search_flights", locals())
    with session_scope() as s:
        try:
            results = FlightService(s).search_flights(
                origin,
                destination,
                departure_date,
                airline=airline,
                max_price=max_price,
                max_stops=max_stops,
                sort=sort,
            )
            if not results:
                applied = []
                if airline:
                    applied.append(f"airline={airline}")
                if max_price is not None:
                    applied.append(f"max_price={max_price}")
                if max_stops is not None:
                    applied.append(f"max_stops={max_stops}")
                suffix = f" matching your filters ({', '.join(applied)})" if applied else ""
                return (
                    f"No flights from {origin} to {destination} on {departure_date}{suffix}. "
                    "Tell the user none were found and suggest relaxing the filters — "
                    "do not invent flights.",
                    None,
                )
            cheapest = min(results, key=lambda f: f.price)
            earliest = min(results, key=lambda f: f.departure_time)
            summary = (
                f"{len(results)} flights {origin}→{destination} on {departure_date}. "
                f"Cheapest {cheapest.flight_number} ${cheapest.price:.0f}; "
                f"earliest {earliest.flight_number} at {earliest.departure_time:%H:%M}. "
                "The full comparison is in the Flights panel."
            )
            return panel_result(
                summary,
                kind="flights",
                data=FlightsPanel.from_flights(origin, destination, departure_date, results),
            )
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


FLIGHT_TOOLS = [search_flights]
```

Drop the now-unused `dump` import if present (ruff-on-edit will flag it). Note the removed empty-dict branch from workstream A is intentionally replaced by the `(message, None)` return.

- [ ] **Step 4 — Run, verify pass.**
Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x` → all green (flight + hotel + book_hotel).
Then the streaming test: `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_flights_panel.py -x` → green.
Lint: `cd apps/api && ../../.venv/bin/ruff check app/tools/flight_tools.py tests/tools/test_booking_tools.py` → clean.

- [ ] **Step 5 — Full BE regression (guard against agent/registry breakage).**
Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/tools tests/streaming -q` → green. (`search_flights` is bound in `registry.py` under planner + booking; the registry test asserts tool presence, not return shape, so it is unaffected — confirm it stays green.)

---

## Verify (whole feature)

| Check | Command |
|---|---|
| BE panel projection | `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_flights_panel.py -x` |
| BE tool + updated tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x` |
| BE lint | `cd apps/api && ../../.venv/bin/ruff check app/tools/flight_tools.py app/streaming/panels.py` |
| FE component | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web test -- src/components/chat/panel/FlightsPanel.test.tsx` |
| FE typecheck | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web typecheck` |
| Manual e2e | Ask the agent "flights HAN→SGN Mar 15" in the web chat → a **Flights** tab renders the compact list; filter to `max_price 1` → no panel, chat says none found. |

## Risks

- **Public-contract (additive):** new SSE `panel` kind + tool return shape. If `risk-corroboration.sh` blocks the commit, authorize with `RISK_WARN_CATEGORIES="public-contract"` (memory `public-contract-hard-gate`), as `agent-side-panel` did.
- **Sequencing:** branch off `feat/search-tool-hardening`; Task 2.1 rewrites the workstream-A empty test — expected, not a regression.

## Status Log

- 2026-07-01 — plan drafted from `design.md` + `research-brief.md` (writing-plans). Awaiting plan review + execution-mode choice.
