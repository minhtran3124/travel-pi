# research-brief — places-side-panel

No `design.md` for this slice — there's no design fork (single obvious approach: mirror an
already-shipped, proven pattern). Per `rules/orchestration.md` Artifact policy, `design.md` is
only required on a genuine ≥2-option fork or high-risk lane; neither applies here (normal lane,
high confidence).

## What already exists (reuse, don't rebuild)

**The side-panel mechanism is fully built and proven** by four prior tool conversions
(`specs/agent-side-panel`, `specs/flights-side-panel`, `specs/hotels-side-panel`):

- `@tool(args_schema=..., response_format="content_and_artifact")` → function returns
  `tuple[str, dict | None]`.
- `app/tools/_base.py:93` `panel_result(summary, *, kind, data)` — the standard artifact builder.
  Returns `(summary, {"kind": kind, "data": dump(data)})`.
- `app/streaming/panels.py` — one `XPanel(AppBaseModel)` projection + `from_x(...)` classmethod per
  kind. `PanelKind` (line 27) already reserves `"places"` in the `Literal`, with a code comment
  (line 10-11) saying the places projection "lands alongside its tool conversion" — this work IS
  that conversion.
- `app/streaming/mapper.py:154-164` reads `ToolMessage.artifact` off the LangGraph `updates`
  channel and re-emits a `panel` SSE event — generic over `kind`, needs no change.
- FE mirror: `apps/web/src/lib/stream/panel.ts` (`PanelKind` already includes `"places"`),
  `apps/web/src/components/chat/panel/registry.ts` (`PANEL_LABELS.places = "Places"` already
  wired; `PANEL_RENDERERS` has no `places` entry — the gap), `SidePanel.tsx` filters to registered
  kinds only (safe forward-compat — an unregistered kind renders nothing today).

**The gap is narrow:** only `search_places` (`app/tools/place_tools.py:71-104`) needs conversion.
`search_hotels` — despite the original request's premise — is already panel-capable
(`app/tools/hotel_tools.py:101`, kind `"hotels"`); no hotel-side work is needed.

## The exact contract to conform to

Copy `search_hotels` (`app/tools/hotel_tools.py:101-212`) and `HotelsPanel`
(`app/streaming/panels.py:415-476`) task-for-task:

1. Add `response_format="content_and_artifact"` to `search_places`'s `@tool` decorator.
2. On empty results: return `(explanatory message, None)` — no panel for an empty set (mirrors
   hotels/flights "no match" branches; the mapper never sends an empty panel to the drawer).
3. On non-empty results: return `panel_result(summary, kind="places", data=PlacesPanel.from_places(...))`.
4. Add `PlacesPanel(AppBaseModel)` + nested row model to `app/streaming/panels.py`, projecting from
   `list[app.schemas.place.Place]` (`app/schemas/place.py:30-92` — fields: `id`, `name`, `city`,
   `country`, `category`, `description`, `address`, `rating`, `review_count`, `price_level`,
   `opening_hours`, `image_url`, `tags`, `is_recommended`, `latitude`, `longitude`, `short_code`).
   Keep it lean like `HotelsPanel` — not every `Place` field needs to ride into the panel if the
   drawer doesn't render it.
5. Mirror the new shape into `apps/web/src/lib/stream/panel.ts` as `PlacesPanelData` +
   `PlacesPanelPlace` (per the `HotelsPanelData`/`FlightsPanelData` pattern already there).
6. New `apps/web/src/components/chat/panel/PlacesPanel.tsx`, mirroring
   `HotelsPanel.tsx`/`FlightsPanel.tsx` (compact expandable row list, header summary line). Places
   have no natural "cheapest" ring-highlight like hotels/flights — skip that affordance or use
   `is_recommended` instead if a highlight is wanted.
7. Register in `apps/web/src/components/chat/panel/registry.ts` `PANEL_RENDERERS.places`.

## Breaking-change gotcha (empirically verified, not documentation)

LangChain's `BaseTool.invoke()` behaves differently depending on the input shape:

- **Bare args dict** (`tool.invoke({"city": "Tokyo"})`) → returns **only the string content**,
  silently dropping the artifact — even for a `content_and_artifact` tool. Verified by a live probe
  against `search_hotels.invoke({...bare hotel args...})`, which returned a plain `str`, not a
  tuple.
- **`ToolCall` dict** (`tool.invoke({"type": "tool_call", "id": ..., "name": ..., "args": {...}})`)
  → returns a `ToolMessage` with `.content` (str) and `.artifact` (the dict). This is the form
  every existing panel-tool test uses (`tests/tools/test_hotel_tools.py:82-100`,
  `tests/tools/test_flight_tools.py`).

**Consequence:** `tests/tools/test_place_tools.py` lines 67–138 invoke `search_places` with the
bare-dict form and assert `isinstance(out, list)` / `out == []` directly on the return value. Once
`search_places` becomes `content_and_artifact`, these assertions break (`out` becomes a plain
string, the list is gone) — not a regression in behavior, just a test-invocation-style mismatch.
They must be rewritten to the `ToolCall` + `ToolMessage` form, asserting on `msg.content` /
`msg.artifact["kind"] == "places"` / `msg.artifact["data"]["places"]` instead. This is expected,
mechanical work (Rule 1, `auto-correct-scope.md`) — the same adaptation happened for
`search_hotels`/`search_flights` in their own conversions.

**No other caller is affected.** Grepped `app/` for `search_places` — every other reference
(`app/routers/places.py`, `app/routers/dashboard.py`, `app/services/place_service.py`, etc.) calls
`PlaceService.search_places()` (the service method), not the `@tool`-wrapped function. Only the
LLM agent (via LangGraph's `ToolNode`, which always uses the `ToolCall` form) and this one test
file touch the tool wrapper directly.

## Test precedents to mirror

- `tests/streaming/test_hotels_panel.py` → new `tests/streaming/test_places_panel.py` (projection
  unit test: field mapping + order preservation, no "cheapest" concept to test).
- `tests/tools/test_hotel_tools.py:82-100` → rewrite the 4 bare-invoke tests in
  `tests/tools/test_place_tools.py` (lines 67-138) to the `ToolCall`/`ToolMessage` form, plus add
  the artifact-shape assertion (`msg.artifact["kind"] == "places"`).
- FE: `HotelsPanel.test.tsx` / `FlightsPanel.test.tsx` → new `PlacesPanel.test.tsx`.
- `tests/api/agent/test_stream_events.py` (mapper/event-shape tests) are generic over `kind` —
  confirm still green, no change expected.
- `SidePanel.test.tsx` — check whether it has a kind-specific "unregistered kind renders nothing"
  case using `"places"` as the example; if so, that case's expectation flips once the renderer is
  registered.

## Risk classification (already done — do not redo intake)

Lane: normal · Confidence: high · Flags: public-contract (additive only) · no hard gate. Full
record in `specs/places-side-panel/SUMMARY.md`.
