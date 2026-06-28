---
slug: agent-side-panel
status: active
owner: Minh Tran
created: 2026-06-27
---

# Agent side panel (kênh phụ)

A drawer beside the chat that auto-renders rich UI from agent tool results: directions → a
keyless map with the real road line; places → a list of cards; weather → a day-by-day forecast.
Built on the settled decision in `RESEARCH.md` (tools use `content_and_artifact`; the mapper emits
one new `panel` SSE event; the FE renders by artifact `kind`) and `DESIGN.md` (contracts, wire
shape, component tree). Map provider: **Option 1 — keyless MapLibre + OSM** in-drawer plus a
Google Maps deep-link button, matching the reference screenshot.

## 1. Motivation

Every tool already computes rich structured JSON; today the FE discards it and renders only prose
(`useAgentStream.ts:198`). Let the agent answer with a UI — a map, place cards, a forecast — in a
drawer next to the chat, auto-populated from the same tool call that produced the text answer,
while keeping the model's context lean (summary only).

## 2. Non-goals

- No new external dependency or committed API key (CLAUDE.md). Map is keyless: MapLibre + OSM tiles
  in-drawer + a Google Maps deep-link button.
- No change to the model's reasoning loop, the supervisor, or HITL. Purely additive: one tool
  return convention + one SSE event + FE drawer (+ keep the ORS geometry we already fetch).
- No `Command`-based tool returns, no FE re-fetch via REST (both rejected in `RESEARCH.md §3`).
- `place_tools` / `weather_tools` panel conversion is a fast-follow, not in this plan's critical path
  (route proves the pattern first).

## 3. Success Criteria

1. A directions / places / weather question opens the drawer with the matching render while the
   assistant's text answer streams as today.
2. The model's context receives only a short summary, not the full artifact (token economy).
3. The route map draws the real ORS road line (keyless, via MapLibre+OSM) with markers, an on-route
   duration/distance badge, and a working "Open in Google Maps" deep-link; estimate mode degrades to
   a straight dashed line.
4. The drawer sits left of the chat with a "Hide Map / Show Map" toggle (desktop) and a top sheet on
   mobile; existing FE keeps working with the new `panel` event present (forward-compat).

## 4. Tasks

### Task 1.0 — Keep ORS road geometry

```xml
<task id="1.0" wave="1">
  <files>apps/api/app/services/routing_service.py, apps/api/app/schemas/route.py, apps/api/tests/services/test_routing_service.py</files>
  <action>Capture features[0].geometry.coordinates in _ors_leg and thread the recommended-mode line onto RouteResponse.geometry (new optional `list[list[float]] | None = None`, [lng,lat]). None in estimate mode. Additive/nullable — existing REST endpoints unaffected.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_routing_service.py -x</verify>
  <done>RouteResponse.geometry populated from ORS when keyed; None on estimate; existing route tests green.</done>
</task>
```

### Task 1.1 — Shared panel contract (events + projection models)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/panels.py, apps/api/app/streaming/events.py, apps/api/tests/api/agent/test_stream_events.py</files>
  <action>Add Pydantic panel projection models (RoutePanel/PlacesPanel/WeatherPanel) + events.panel() factory emitting `event: panel` with {tool_call_id,kind,data}. Document `panel` in the events.py taxonomy docstring.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -x</verify>
  <done>events.panel(...) emits the typed event; projection models validate.</done>
</task>
```

### Task 1.2 — Panel helper + convert routing tools

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/tools/_base.py, apps/api/app/tools/routing_tools.py, apps/api/tests/tools/test_routing_tools.py</files>
  <action>Add panel_result() helper. Convert get_route/get_city_route to @tool(response_format="content_and_artifact"): one-line summary for the model + route artifact (endpoints, legs, recommended_mode, geometry, keyless gmaps_url). Keep ToolException paths. Reads RouteResponse.geometry from Task 1.0. NOTE: content_and_artifact changes the invoke contract — `ainvoke({args})` now returns the summary string, so REWRITE the existing dict-shape tests to invoke via a ToolCall ({type:"tool_call",id,name,args}) and assert on the returned ToolMessage's `.content` (summary) + `.artifact` (route dict).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_routing_tools.py -x</verify>
  <done>Tool yields ToolMessage with .artifact={kind:"route",data:...} + one-line .content; tests assert on artifact; error path still raises ToolException.</done>
</task>
```

### Task 2.1 — Mapper emits panel events

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/streaming/mapper.py, apps/api/tests/api/agent/test_stream_events.py</files>
  <action>In the ToolMessage branch, if msg.artifact is a dict with "kind", yield events.panel(tool_call_id, kind, data) before tool_result. tool_result unchanged. Non-panel tools unaffected. Confirm persistence.py passes the panel event through untouched (it only accumulates token/reset).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/api/agent/test_stream_persistence.py -x</verify>
  <done>A panel-capable ToolMessage produces a `panel` SSE event with the right kind; plain tools do not; persistence still passes it through.</done>
</task>
```

### Task 3.1 — FE parser + stream hook

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/lib/stream/panel.ts, apps/web/src/lib/stream/parseSSE.ts, apps/web/src/components/chat/useAgentStream.ts, apps/web/src/lib/stream/parseSSE.test.ts</files>
  <action>Add PanelArtifact TS union (mirror of panels.py), SSEPanelEvent + case in parseSSE, panels/activePanel state + panel case (replace-by-kind) in useAgentStream. Expose {panels, activePanel}.</action>
  <verify>cd apps/web && pnpm test parseSSE</verify>
  <done>parseSSE yields a typed panel event; the hook exposes panels[].</done>
</task>
```

### Task 4.1 — Drawer + renderers + layout

```xml
<task id="4.1" wave="4">
  <files>apps/web/src/components/chat/panel/SidePanel.tsx, apps/web/src/components/chat/panel/RoutePanel.tsx, apps/web/src/components/chat/panel/PlacesPanel.tsx, apps/web/src/components/chat/panel/WeatherPanel.tsx, apps/web/src/components/chat/panel/registry.ts, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/ChatWidget.tsx</files>
  <action>Add SidePanel shell + Route/Places/Weather renderers + kind→component registry (unknown kind → null). RoutePanel: lazy-loaded MapLibre+OSM drawing data.geometry road line (straight dashed fallback when null), origin/destination markers, on-route duration/distance badge, "Open in Google Maps" deep-link. Wire drawer left of chat with a "Hide Map/Show Map" toggle (desktop) and top sheet (mobile); auto-open on first panel event.</action>
  <verify>cd apps/web && pnpm test --run panel</verify>
  <done>Drawer opens on first panel event and renders by kind; route panel shows the road line + badge; unknown kind renders nothing.</done>
</task>
```

## 5. Risks

- **Geometry only when ORS is keyed** — the real road line renders only with `ORS_API_KEY` set;
  estimate mode degrades to a straight dashed line. Acceptable and signalled by `source`.
- **MapLibre bundle size** — lazy-load `RoutePanel` so the GL lib is fetched only when a route panel
  opens.
- **Checkpoint size** — artifacts persist on `ToolMessage`; cap place lists (top ~10) in the
  projection and `log()` the cap so truncation isn't silent.
- **Multiple panels per turn** — default to replace-by-kind (latest wins); add a tab strip only if a
  turn commonly yields more than one kind.

## 6. Status Log

- 2026-06-27 — Plan drafted from `RESEARCH.md` + `DESIGN.md`. Map provider resolved to Option 1
  (keyless). Status: proposed.
- 2026-06-27 — Reviewed against **v3** (HEAD 4a5c314) in worktree `feat/agent-side-panel`. v3 ==
  prior working tree for all feature files; routing tool + streaming layer already present (v3 adds
  `streaming/persistence.py`). Corrected test paths: events+mapper → `tests/api/agent/test_stream_events.py`;
  routing service → new `tests/services/test_routing_service.py`. Flagged that `content_and_artifact`
  changes the tool invoke contract → Task 1.2 rewrites the existing dict-shape routing-tool tests.
  Status: active.
- 2026-06-27 — **Wave 1 ✓** (commit `ee6ea6b`): Tasks 1.0/1.1/1.2 — ORS geometry kept, `panels.py`
  RoutePanel projection, `panel_result` helper, routing tools → content_and_artifact. **Wave 2 ✓**
  (same commit): Task 2.1 — mapper emits `panel` from `ToolMessage.artifact`; persistence passes it
  through. BE: 41 tests green, ruff clean. **Wave 3 ✓** (commit `43b8da7`): Task 3.1 — FE `panel.ts`
  types, parseSSE panel case, `useAgentStream` panels state (replace-by-kind). FE: parseSSE 19/19,
  tsc + eslint clean. Note: 2 PRE-EXISTING failures in v3's `useAgentStream.stream.test.tsx`
  (localStorage/mock isolation), unrelated to this work.
- 2026-06-27 — **Wave 4 (Task 4.1) NOT STARTED** — the MapLibre+OSM drawer, per-kind renderers, and
  ChatWidget layout. Held for an interactive session: it adds the `maplibre-gl` dependency and needs
  browser/screenshot verification + two UX confirmations (drawer width split; map auto-fit/zoom feel).
