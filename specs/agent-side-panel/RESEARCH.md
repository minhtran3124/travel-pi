# Research — Side panel (kênh phụ) driven by agent tool results

**Date:** 2026-06-27
**Builds on:** `specs/agent-tools-mizumi-parity/RESEARCH.md` (the "Command vs plain JSON" tool-return decision)
**Goal:** A drawer that opens *next to* the chat panel and auto-renders rich UI from tool
results — ask directions → a map; ask places → a list of place cards; ask weather → a
day-by-day forecast; extensible to itinerary / hotels / flights / budget.

This is the productisation of the open question left by the mizumi-parity research: *if the FE
ever wants the map/cards side-channel, what is the doc-correct way to ship the structured data
to the UI without polluting the model's context?*

---

## 1. The core problem

Today every tool returns full structured JSON via `dump()`. That JSON goes **only to the model**
(wrapped into a `ToolMessage` by `ToolNode`) and the FE throws it away — `useAgentStream.ts`
explicitly ignores `tool_call` / `tool_result` and renders only assistant prose
(`useAgentStream.ts:198`).

So the data the drawer needs *already exists and is already computed*. The question is purely:
**how do we get a tool's structured result to the browser as a render-able UI payload, separate
from the model's text channel?**

Two sub-decisions:
1. **Tool → graph**: what does a "panel-capable" tool return?
2. **Graph → browser**: how does that payload cross the SSE wire?

---

## 2. How the data flows today (grounding)

```
sub-agent tool  ──dump()──▶ ToolMessage(content=JSON)
        │
        ▼
graph.astream(stream_mode=["messages","updates"], subgraphs=True)
        │
        ▼
mapper.py  ── reads ToolMessage in `updates` mode ──▶ events.tool_result(id, status)   # status only!
        │
        ▼  SSE  event: tool_result  data: {"id","status"}
        ▼
parseSSE.ts ──▶ useAgentStream.ts  (tool_result IGNORED — only `token` rendered)
        ▼
ChatPanel.tsx  (single floating panel; no drawer)
```

Key facts that make this cheap to extend:
- The mapper **already iterates every `ToolMessage`** in `updates` mode (`mapper.py:114`). It
  currently reads only `.status`. It can just as easily read a structured payload off the same
  object.
- The SSE taxonomy is a clean named-event protocol (`events.py`); adding one event type is additive.
- Both parsers are **forward-compatible**: unknown SSE events are skipped, not fatal
  (`parseSSE.ts:220`, `useAgentStream.ts:200`). So a new `panel` event can ship BE-first without
  breaking the current FE.

---

## 3. Options for "tool → browser" (the decision)

### Option A — `response_format="content_and_artifact"` ✅ RECOMMENDED

The tool returns a **2-tuple** `(summary_for_model, artifact_for_ui)`. `ToolNode` puts the first
on `ToolMessage.content` and the second on `ToolMessage.artifact`. The mapper reads `.artifact`
and emits a new `panel` SSE event.

Official docs (LangGraph 1.x, `docs.langchain.com/oss/python/langgraph`):
> Tools can be set up to return a `content` for the model and an `artifact` that is **not sent to
> the model** — the artifact rides on `ToolMessage.artifact`.

Why it wins here:
- **Model sees a short summary, UI gets rich data.** Directly satisfies the token-economy point
  from the prior research: don't dump full geometry/lists into the LLM context.
- **Persisted in the checkpoint.** The artifact lives on the `ToolMessage`, which is part of
  message history. A future "load past conversation" path can **rehydrate the drawer** for free.
- **Smallest diff.** The mapper already has the `ToolMessage` in hand (`mapper.py:114`); read one
  more attribute. No new stream mode, no graph-state changes.
- **Decouples tool from UI.** Keyed by `kind`, not tool name — `get_route` and `get_city_route`
  both emit `kind:"route"`.

### Option B — `get_stream_writer()` + `stream_mode="custom"` (ephemeral; defer)

A tool calls `writer({...})` mid-execution; the graph is streamed with `"custom"` added to
`stream_mode`. Doc-correct and good for **progress** ("Retrieved 0/100…"), but:
- **Not persisted** — the payload is ephemeral; reopening the conversation loses the drawer.
- Requires adding `"custom"` to the `astream` call and a `(ns, "custom", data)` branch in the mapper.

Verdict: the right tool for *live progress*/streaming partials later (e.g. "drawing route…"), **not**
for the durable panel content. Keep in back pocket.

### Option C — `Command(update=...)` ❌ REJECTED (same conclusion as prior research)

Couples UI payloads into core graph state, bloats every checkpoint with render data, and forces a
hand-built `ToolMessage` + `tool_call_id` on every tool. No control-flow benefit (the ReAct loop
already routes `tools → assistant`). This is exactly the misuse the mizumi-parity research warned
against.

### Option D — FE re-fetches via REST on `tool_result` ❌ REJECTED

FE sees `tool_result`, then calls `GET /places/route` etc. itself. Doubles the work already done
inside the tool, reintroduces a race (which args? which place ids?), and needs the FE to reverse-
engineer arguments it never saw. The data was already computed once — don't compute it twice.

**Decision: Option A (`content_and_artifact`) as the durable mechanism; Option B reserved for
future live-progress.**

---

## 4. Route geometry: fetched today, discarded today — keep it (cheap)

`RouteResponse` (`app/schemas/route.py`) carries `origin`/`destination` coordinates, per-mode
`legs` (distance + duration), `recommended_mode`, `straight_line_km`, and `source` — **but no
polyline**. Crucially, the polyline is **already in the ORS response**: `_ors_leg()`
(`routing_service.py:120-127`) parses only `features[0].properties.summary` and throws away
`features[0].geometry` — the GeoJSON road line ORS returns in the *same* call. No extra request.

This matters because the visual target (the mizumi reference screenshot) shows a **real road
polyline** with origin/destination markers and a duration/distance badge on the route — not a
straight line. To reproduce that **keylessly** we just need to *stop discarding* the geometry:

- **ORS configured (`ORS_API_KEY` set):** keep `geometry` for the recommended-mode leg → the
  keyless OSM/MapLibre map draws the true road line, matching the reference.
- **Estimate mode (no key):** no geometry → the map gracefully degrades to a straight dashed line
  between the two markers.

This resolves the user's **Option 1 (keyless)** choice against the no-Google-API-key ethos
(CLAUDE.md): the in-drawer map is **MapLibre + OSM tiles** (no key) drawing the real ORS road line,
plus a keyless **"Open in Google Maps" deep-link** button
(`https://www.google.com/maps/dir/?api=1&origin=…&destination=…`) for users who want the full
Google surface in a new tab. No API key is committed anywhere.

> Decision change vs. the first draft: adding `geometry` moves from "optional v2" to **v1**, because
> the reference look requires it and the data is already fetched — keeping it is nearly free.

---

## 5. What's panel-capable (and the data already on hand)

| Intent | Tool(s) | `kind` | Data already returned |
|---|---|---|---|
| Directions / "how far" | `get_route`, `get_city_route` | `route` | endpoints+coords, per-mode legs, recommended mode, source |
| "places in / near X" | `search_places`, `nearby_places` | `places` | list of places w/ category, rating, price, coords |
| Weather / "what's it like" | `get_weather`, `get_air_quality` | `weather` | per-day forecast / AQI |
| (future) itinerary view | `get_trip`, itinerary tools | `itinerary` | day-by-day plan |
| (future) hotels / flights | `search_hotels`, `search_flights` | `hotels` / `flights` | result lists |

Every row's data is **already computed** by the existing tool — the artifact is a projection of
what `dump()` already produces, minus what the model doesn't need.

---

## 6. Recommendation summary

1. Adopt **`content_and_artifact`** for panel-capable tools; emit a new **`panel`** SSE event from
   the mapper when `ToolMessage.artifact` is present.
2. Model the artifact as a **discriminated union keyed by `kind`**; the FE renders by `kind`, never
   by tool name.
3. Ship the **route map keyless** (OSM/MapLibre in-drawer + Google Maps deep-link button); defer
   the real road polyline to a v2 `geometry` field on `RouteResponse`.
4. Reserve **`get_stream_writer` / custom mode** for future live progress, not durable content.
5. Reject `Command` and FE-re-fetch.

Concrete contracts, wire shape, component tree, and a phased plan are in `DESIGN.md`.
