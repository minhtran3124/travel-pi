---
slug: flights-side-panel
status: design
owner: Minh Tran
created: 2026-07-01
extends: specs/agent-side-panel/
---

# Flights side panel

Render `search_flights` results as a **compact list** in the existing chat side-drawer, so the
user compares every flight at a glance instead of scrolling markdown in the chat bubble. This is
a new `flights` panel *kind* on the already-shipped side-panel pipeline
(`content_and_artifact` tool return → `panel` SSE event → FE `panel/registry.ts`), the same path
`route` / `weather` / `air_quality` / `places` already use.

## 1. Motivation

`search_flights` returns rich structured JSON that today is flattened into prose in the chat.
Comparing 5 flights by price/time/stops in a text bubble is poor, especially on mobile. The
side-panel system already exists; this feature just adds one more `kind`. It directly answers the
original request: *"help user can easily view flights without scrolling down in chatbot."*

## 2. Non-goals

- **Hotels / places panels** — deferred; ship flights first, then clone the pattern.
- **Client-side sort/filter in the panel** — the tool already sorts via its `sort` param (the
  agent controls order). No sort chips in v1.
- **Booking from the panel** — there is no `book_flight` tool; flights are read-only. Booking
  stays an agent/chat action.
- **Loading skeleton** — panels arrive only when the tool call completes (no partial SSE), so
  there is no in-panel pending state to render.
- **Empty-state panel** — on no-match the tool opens **no** panel; the (already hardened) chat
  text explains "no flights match". See §5.

## 3. Design decisions (user-approved 2026-07-01)

| Decision | Choice |
|---|---|
| Layout | **Compact list** — one row per flight, all results visible without scrolling |
| Row interaction | **Static + expand** — click a row to reveal full detail; no sort chips |
| Scope | **Flights only** this iteration |
| Empty / error | **No panel** — chat text handles it (workstream A) |
| Booking | **Read-only** — no Book button (no `book_flight` tool) |
| Fields shown | Only real `Flight` schema fields (no invented aircraft/baggage/layover) |

## 4. Architecture & data flow

```
search_flights (tool)
  ├─ results  → panel_result(summary, kind="flights", data=FlightsPanel.from_flights(...))
  │              summary → LLM context (lean);  data → artifact (not in context)
  └─ empty    → (message, None)          # no artifact ⇒ no panel; workstream A text stands
  └─ error    → raise ToolException      # unchanged; _tool_error_to_message → user

streaming/mapper.py  (unchanged)  reads ToolMessage.artifact → events.panel(kind, data)
   → SSE: event: panel  data: {tool_call_id, kind:"flights", data:{...}}

useAgentStream.ts (unchanged)  upsertPanelByKind → panels state
SidePanel.tsx (unchanged)      tab "Flights" → PANEL_RENDERERS["flights"]
FlightsPanel.tsx (NEW)         renders compact list from artifact data
```

The BE mapper and FE stream/drawer plumbing need **no change** — they already dispatch any
`kind`. Work is: convert the tool, add one Pydantic projection model, add one FE component +
registry/type entries.

## 5. Contracts

### 5.1 Tool return (`app/tools/flight_tools.py`)

`search_flights` becomes `@tool(response_format="content_and_artifact")`. Its **docstring**
(`flight_tools.py:41-45`, which currently documents the empty `{"results":[],"reason",...}` dict)
must be updated to describe the new summary+artifact / `(message, None)` behaviour. It must return
a 2-tuple on every non-exception path:

- **Results present:** `panel_result(summary, kind="flights", data=FlightsPanel.from_flights(origin, destination, departure_date, results))`
  where `summary` is a short natural-language line for the model (route, count, cheapest,
  earliest).
- **Empty (no match):** `(message, None)` — `message` carries the same guidance workstream A
  added (which filters left nothing / relax them), and `None` artifact ⇒ mapper emits no panel.
- **Failure:** `raise ToolException(str(e))` — unchanged.

> **Reconciliation with workstream A:** A currently returns a bare dict
> `{"results": [], "reason": "no_match", "message": ...}` on empty, and a bare `list` on results.
> Converting to `content_and_artifact` changes **both** paths — on results the plain
> `.invoke({...dict})` now yields only the content string (the summary), and on empty it yields
> `(message, None)`. This breaks **three** existing tests in
> `apps/api/tests/tools/test_booking_tools.py`, all of which must be updated:
>
> 1. `test_search_flights_returns_list` (asserts `isinstance(result, list)`).
> 2. `test_search_flights_with_price_sort` (asserts a `list`, then reads `item["price"]` to check
>    sort order). **Sort order is no longer observable from the tool's content** — the assertion
>    must be **re-homed** onto the artifact: assert ascending `price` across
>    `FlightsPanel.flights` (projected from the `ToolMessage.artifact` `data`).
> 3. `test_search_flights_no_match_returns_reason` (asserts the empty dict) → assert the
>    `(message, None)` 2-tuple; the `reason`/filter detail folds into `message`.
>
> To observe the artifact in a test, invoke the tool with a **ToolCall** and read the resulting
> `ToolMessage.artifact`, not a plain dict `.invoke` (which returns content only). Follow the
> existing pattern in `apps/api/tests/tools/test_routing_tools.py:35`.

### 5.2 Panel payload (`app/streaming/panels.py`)

```python
class FlightsPanelFlight(AppBaseModel):
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
    origin: str
    destination: str
    departure_date: str
    results_count: int
    cheapest_price: float
    flights: list[FlightsPanelFlight]

    @classmethod
    def from_flights(cls, origin, destination, departure_date, flights) -> "FlightsPanel": ...
```

`PanelKind` literal gains `"flights"`. Cap `flights` at the tool's existing 5-result limit (no
extra truncation needed; log if a future change raises the cap).

### 5.3 FE types + component

- `apps/web/src/lib/stream/panel.ts`: add `FlightsPanelData` interface mirroring `FlightsPanel`;
  add `"flights"` to the FE `PanelKind` union.
- `apps/web/src/components/chat/panel/FlightsPanel.tsx`: `FlightsPanel({ data }: { data: FlightsPanelData })`.
  - **Header:** `{origin} → {destination}` · `{departure_date} · {results_count} results · cheapest ${cheapest_price}`.
  - **Row (collapsed):** `HH:MM → HH:MM  {dur}` / `{airline_name} {flight_number} · {nonstop|N stops} · {seats} seats` / `${price}` + a stop-color dot. Cheapest row: subtle lime ring.
  - **Row (expanded, on click):** full detail using only real fields — airline (name + code),
    flight number, full departure/arrival datetimes, duration, stops count, seats available,
    price + currency. No Book action.
  - Pure render, no network, no state beyond local "which row is expanded".
- `registry.ts`: `flights: FlightsPanel` in `PANEL_RENDERERS`; `flights: "Flights"` in labels.

## 6. Testing

**BE** — invoke the tool with a **ToolCall** and inspect the returned `ToolMessage` (`.content`
and `.artifact`); a plain `.invoke({dict})` returns content only. Pattern:
`apps/api/tests/tools/test_routing_tools.py:35`.
- `search_flights` results → `ToolMessage.artifact == {"kind":"flights","data":{...}}`; the
  `data` validates against `FlightsPanel`.
- **Update the 3 workstream-A tests broken by the conversion** (`test_booking_tools.py`):
  - `test_search_flights_returns_list` → assert on the artifact's `FlightsPanel.flights`, not a
    bare list.
  - `test_search_flights_with_price_sort` → **re-home** the sort assertion: assert ascending
    `price` across `data.flights` (the artifact), since sort order is no longer in the content.
  - `test_search_flights_no_match_returns_reason` → assert `(message, None)` (no artifact).
- `search_flights` bad date → raises `ToolException` (unchanged).
- `FlightsPanel.from_flights` projection: field mapping + `cheapest_price`/`results_count`.
- Mapper emits a `panel` event with `kind="flights"` for a flights ToolMessage (reuse existing
  `test_stream_events`-style test).

**FE**
- `parseSSE` accepts a `flights` panel event.
- `FlightsPanel` renders N rows, marks the cheapest, expands a row on click, shows real fields.
- `registry` maps `flights` → component; unknown kind still renders nothing.

## 7. Sequencing / dependency

This feature depends on **workstream A** (`feat/search-tool-hardening`, not yet merged to `v3`).
Branch this work off `feat/search-tool-hardening` (or merge A into `v3` first). The empty-return
reconciliation (§5.1) edits A's just-added empty test.

## 8. Risks

- **Public-contract (additive):** a new `panel` `kind` and the tool's `content_and_artifact`
  return are additive — no route/endpoint shape removed. If `risk-corroboration.sh` flags
  public-contract on commit, authorize with `RISK_WARN_CATEGORIES="public-contract"` per the
  repo convention (memory `public-contract-hard-gate`), matching how `agent-side-panel` shipped.
- **Model context:** the `summary` (not the artifact) is what the LLM sees — keep it short so we
  don't bloat context; the flight detail rides the artifact only.
