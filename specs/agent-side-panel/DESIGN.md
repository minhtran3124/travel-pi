---
slug: agent-side-panel
status: proposed
owner: Minh Tran
created: 2026-06-27
---

# Agent side panel (kênh phụ) — design

Companion to `RESEARCH.md`. Decision is settled there: panel-capable tools use
`response_format="content_and_artifact"`; the mapper emits a new `panel` SSE event read off
`ToolMessage.artifact`; the FE renders a drawer by artifact `kind`.

## 1. Motivation

Let the agent answer with a UI, not just prose. "How do I get to the Dragon Bridge?" should open a
map; "good cafes in Da Nang?" a list of place cards; "weather this week?" a day-by-day forecast —
all in a drawer beside the chat, auto-populated from the same tool call that produced the text
answer. The data already exists; today the FE discards it (`RESEARCH.md §2`).

## 2. Non-goals

- No new external dependency or committed API key (CLAUDE.md). Map is keyless: **MapLibre + OSM
  tiles** in-drawer + a **Google Maps deep-link** button (Option 1, user-confirmed).
- No change to the model's reasoning loop, the supervisor, or HITL. Purely additive: one tool
  return convention + one SSE event + FE drawer (+ keep the ORS geometry we already fetch).
- No `Command`, no FE re-fetch (rejected in `RESEARCH.md §3`).

## 3. Success criteria

1. Asking a directions / places / weather question opens the drawer with the matching render,
   while the assistant's text answer streams as today.
2. The model's context receives only a **short summary**, not the full artifact (token economy).
3. Current FE keeps working with the new event present (forward-compat) even before the drawer
   ships — `panel` events are ignored until consumed.
4. Closing/reopening the chat, and switching `kind`s across turns, behaves predictably.

## 4. The artifact contract (BE ↔ FE shared shape)

A discriminated union keyed by `kind`. The FE renders on `kind`, never on tool name (so
`get_route` + `get_city_route` share one renderer).

```jsonc
// event: panel  data:
{
  "tool_call_id": "call_abc123",   // correlate with the tool_call/tool_result events
  "kind": "route",                  // route | places | weather | (future) itinerary | hotels | flights
  "data": { /* kind-specific, below */ }
}
```

### kind: "route"  (from get_route / get_city_route)
Projection of `RouteResponse` (`app/schemas/route.py`) — endpoints, metrics, deep-link.
```jsonc
{
  "origin":      { "name": "Hotel", "lat": 16.06, "lng": 108.22 },
  "destination": { "name": "Dragon Bridge", "lat": 16.06, "lng": 108.23 },
  "recommended_mode": "car",
  "legs": [ { "mode": "walk", "distance_km": 2.1, "duration_minutes": 26 },
            { "mode": "car",  "distance_km": 2.4, "duration_minutes": 7 } ],
  "straight_line_km": 1.9,
  "source": "estimate",                 // "openrouteservice" | "estimate"
  "geometry": [[108.22,16.06],[108.225,16.058],[108.23,16.06]],  // ORS road line [lng,lat]; null in estimate mode
  "gmaps_url": "https://www.google.com/maps/dir/?api=1&origin=16.06,108.22&destination=16.06,108.23"
}
```
> `geometry` is the recommended-mode leg's ORS road path (GeoJSON LineString coords), already
> returned by ORS and currently discarded (`RESEARCH.md §4`). `null` when `source == "estimate"`,
> so the FE falls back to a straight dashed line between the markers.

### kind: "places"  (from search_places / nearby_places)
```jsonc
{
  "anchor": { "label": "Da Nang", "lat": 16.06, "lng": 108.22 },   // optional map centroid
  "items": [
    { "id": "PLC-1234", "name": "43 Factory Coffee", "category": "cafe",
      "rating": 4.7, "price_level": 2, "lat": 16.05, "lng": 108.24 }
  ]
}
```

### kind: "weather"  (from get_weather / get_air_quality)
```jsonc
{
  "location": "Da Nang",
  "days": [ { "date": "2026-06-28", "temp_min_c": 27, "temp_max_c": 33,
              "condition": "Partly cloudy", "wmo_code": 2, "aqi": 41 } ]
}
```

> Each `data` is a strict projection of what the tool already computes via `dump()` — minus fields
> the model doesn't need. Type the union once in TS (`apps/web/src/lib/stream/panel.ts`) and mirror
> it in a Pydantic model (`app/streaming/panels.py`) so both ends stay in lockstep.

## 5. Wire protocol — one new SSE event

Add to the taxonomy (`events.py` docstring + factory). Everything else unchanged.

```
panel — structured side-panel payload: {tool_call_id, kind, data}
```

`events.py`:
```python
def panel(*, tool_call_id: str, kind: str, data: Any) -> TypedSSEEvent:
    return _event("panel", {"tool_call_id": tool_call_id, "kind": kind, "data": data})
```

## 6. Backend changes

### 6a-pre. Keep the ORS geometry (`app/services/routing_service.py`, `app/schemas/route.py`)
`_ors_leg()` currently parses only `summary` and drops `features[0].geometry`. Capture the
geometry (GeoJSON LineString `coordinates`, `[lng,lat]`) and thread it onto the recommended-mode
leg / `RouteResponse.geometry`. Add `geometry: list[list[float]] | None = None` to `RouteResponse`
(optional, default `None` → no behaviour change for the existing REST endpoints; `None` in estimate
mode). This is the only backend-contract touch — additive and nullable, not a breaking change.

### 6a. Panel helper + tool convention (`app/tools/_base.py`)
A thin helper keeps panel tools readable and the summary/artifact split explicit:
```python
def panel_result(summary: str, *, kind: str, data: Any) -> tuple[str, dict]:
    """Return value for an @tool(response_format="content_and_artifact") panel tool."""
    return summary, {"kind": kind, "data": dump(data)}
```
Panel-capable tool (routing example):
```python
@tool(response_format="content_and_artifact")
async def get_route(origin_place_id: str, destination_place_id: str):
    """...docstring unchanged..."""
    with session_scope() as s:
        try:
            r = await RoutingService(s).get_place_route(origin_place_id, destination_place_id)
        except AppError as e:
            raise ToolException(str(e)) from e
    summary = f"{r.origin.name} → {r.destination.name}: {_leg(r).distance_km} km, " \
              f"~{_leg(r).duration_minutes:.0f} min by {r.recommended_mode}."
    return panel_result(summary, kind="route", data=_route_panel(r))
```
- `summary` (model-facing) replaces today's full JSON dump → fewer tokens.
- `_route_panel(r)` builds the §4 projection incl. the keyless `gmaps_url`.
- Errors still raise `ToolException` → recoverable `ToolMessage(status="error")` (unchanged).

Convert in priority order: `routing_tools` → `place_tools` (search/nearby) → `weather_tools`.
Non-panel tools (booking, expense, memory, trip writes) keep plain `dump()` returns untouched.

### 6b. Mapper emits `panel` (`app/streaming/mapper.py`)
In the existing `ToolMessage` branch (`mapper.py:114`), read the artifact:
```python
elif isinstance(msg, ToolMessage):
    artifact = getattr(msg, "artifact", None)
    if isinstance(artifact, dict) and "kind" in artifact:
        yield events.panel(
            tool_call_id=msg.tool_call_id,
            kind=artifact["kind"],
            data=artifact.get("data"),
        )
    status = "error" if msg.status == "error" else "ok"
    yield events.tool_result(id=msg.tool_call_id, status=status)
```
No new stream mode needed — `content_and_artifact` puts the artifact on the `ToolMessage` the
mapper already iterates. `tool_result` still fires (status pill logic unchanged).

## 7. Frontend changes

### 7a. Parser (`parseSSE.ts`)
Add `SSEPanelEvent { type:"panel"; toolCallId; kind: PanelKind; data: PanelData }` to the union and
a `case "panel"` in `parseSegment`. (Unknown events already skipped, so this is safe to lag the BE.)

### 7b. Stream hook (`useAgentStream.ts`)
- New state `panels: PanelArtifact[]` (append per turn) and derived `activePanel` (latest).
- `case "panel": setPanels(p => upsertByKind(p, ev))` — replace-by-kind so a fresh weather query
  supersedes the stale one; keep a small history for back-navigation if desired.
- Clear/retain policy: keep panels across turns; expose `clearPanels()`. Reset on new conversation.
- Expose `{ panels, activePanel }` from the hook.

### 7c. Drawer + renderers (new components)
```
components/chat/panel/
  SidePanel.tsx        // drawer shell: open/close, tab strip if >1 kind, a11y (role=complementary)
  RoutePanel.tsx       // MapLibre+OSM road polyline + markers + on-route badge + "Open in Google Maps"
  PlacesPanel.tsx      // scrollable place cards; click → center map / future add-to-trip
  WeatherPanel.tsx     // day cards (temp range, condition icon, AQI badge)
  registry.ts          // kind -> component map (forward-compatible: unknown kind -> null)
```
- **Map (matches the reference screenshot, keyless):** MapLibre GL + OSM raster tiles. Draw the
  **road polyline** from `data.geometry` (recommended-mode ORS line); when `geometry` is `null`
  (estimate mode) fall back to a dashed straight line. Origin = ringed circle marker, destination =
  pin marker; auto-fit bounds to the line. Overlay a **duration/distance badge** on the route for
  the recommended mode (e.g. "12 min · 11.5 km"). A keyless **"Open in Google Maps"** button uses
  `data.gmaps_url` to open the full Google surface in a new tab.

### 7d. Layout (`ChatWidget` / `ChatPanel`) — per reference screenshot
- Desktop: drawer sits **to the left of** the chat panel (chat stays anchored bottom-right), as in
  the reference. Combined width grows; respects the existing `fullscreen` toggle.
- A **"Hide Map" / "Show Map"** toggle lives in the chat panel (above the composer, as in the
  reference) so the user can collapse the drawer without losing it.
- Mobile: drawer becomes a **top sheet / tab** above the transcript (no room for side-by-side).
- Auto-open on first `panel` event of a turn. `kind` tab strip when a turn produced >1 panel kind.

## 8. Tasks

````markdown
### Task 1.0 — Keep ORS road geometry
```xml
<task id="1.0" wave="1">
  <files>apps/api/app/services/routing_service.py, apps/api/app/schemas/route.py, apps/api/tests/services/test_routing_service.py</files>
  <action>Capture features[0].geometry.coordinates in _ors_leg and thread the recommended-mode line onto RouteResponse.geometry (new optional `list[list[float]] | None = None`, [lng,lat]). None in estimate mode. Additive/nullable — REST endpoints unaffected.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_routing_service.py -x</verify>
  <done>RouteResponse.geometry populated from ORS when keyed; None on estimate; existing route tests green.</done>
</task>
```

### Task 1.1 — Shared panel contract
```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/panels.py, apps/api/app/streaming/events.py, apps/api/tests/streaming/test_events.py</files>
  <action>Add Pydantic panel projection models (RoutePanel/PlacesPanel/WeatherPanel) + events.panel() factory. Document `panel` in the events.py taxonomy docstring.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_events.py -x</verify>
  <done>events.panel(...) emits `event: panel` with {tool_call_id,kind,data}; models validate.</done>
</task>
```

### Task 1.2 — Panel helper + convert routing tools
```xml
<task id="1.2" wave="1">
  <files>apps/api/app/tools/_base.py, apps/api/app/tools/routing_tools.py, apps/api/tests/tools/test_routing_tools.py</files>
  <action>Add panel_result() helper. Convert get_route/get_city_route to response_format="content_and_artifact": short summary for model + route artifact (incl. keyless gmaps_url). Keep ToolException paths.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_routing_tools.py -x</verify>
  <done>Tool returns (summary, {kind:"route",data}); summary is one line; artifact matches schema.</done>
</task>
```

### Task 2.1 — Mapper emits panel
```xml
<task id="2.1" wave="2">
  <files>apps/api/app/streaming/mapper.py, apps/api/tests/streaming/test_mapper.py</files>
  <action>In the ToolMessage branch, if msg.artifact is a dict with "kind", yield events.panel(...) before tool_result. tool_result unchanged.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_mapper.py -x</verify>
  <done>A panel-capable tool produces a `panel` SSE event with the right kind; non-panel tools do not.</done>
</task>
```

### Task 3.1 — FE parser + stream hook
```xml
<task id="3.1" wave="3">
  <files>apps/web/src/lib/stream/panel.ts, apps/web/src/lib/stream/parseSSE.ts, apps/web/src/components/chat/useAgentStream.ts, apps/web/src/lib/stream/parseSSE.test.ts</files>
  <action>Add PanelArtifact TS union (mirror of panels.py), SSEPanelEvent + case in parseSSE, panels/activePanel state + panel case in useAgentStream (replace-by-kind).</action>
  <verify>cd apps/web && pnpm test parseSSE</verify>
  <done>parseSSE yields a typed panel event; hook exposes panels[].</done>
</task>
```

### Task 4.1 — Drawer + renderers
```xml
<task id="4.1" wave="4">
  <files>apps/web/src/components/chat/panel/*, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/ChatWidget.tsx</files>
  <action>Add SidePanel shell + Route/Places/Weather renderers + kind→component registry. Wire drawer into ChatWidget layout (desktop side, mobile sheet). Keyless MapLibre/OSM + Google Maps deep-link button.</action>
  <verify>cd apps/web && pnpm test --run panel</verify>
  <done>Drawer opens on first panel event and renders by kind; unknown kind renders nothing.</done>
</task>
```
````

Waves: 1.0 + 1.1 + 1.2 are file-disjoint (parallel) — 1.2 reads `RouteResponse.geometry` from 1.0,
so land 1.0 first if running strictly serial; 2.1 depends on 1.x; FE 3.1 then 4.1. Convert
`place_tools` and `weather_tools` to panels as a fast-follow after the route path proves out.

## 9. Risks & open questions

- **Geometry only when ORS is keyed** — the real road line renders only with `ORS_API_KEY` set;
  estimate mode degrades to a straight dashed line. Acceptable and clearly signalled by `source`.
- **MapLibre bundle size** — pulls a GL map lib into the web bundle. Lazy-load `RoutePanel` so it's
  only fetched when a route panel actually opens.
- **Checkpoint size** — artifacts persist on `ToolMessage`. Place lists could be large; cap items
  (e.g. top 10) in the projection. *(`log()` the cap so truncation isn't silent.)*
- **History rehydration** — artifacts persist, so a future "load past conversation" endpoint can
  replay panels. Out of scope here; the contract supports it.
- **Multiple panels per turn** — replace-by-kind (latest wins) vs. tab strip. Default to
  replace-by-kind; add tabs only if a turn commonly yields >1 kind.
- **Map provider** — RESOLVED: Option 1 (keyless MapLibre+OSM in-drawer with the real ORS road line
  + a "Open in Google Maps" deep-link button), matching the reference screenshot without a key.
