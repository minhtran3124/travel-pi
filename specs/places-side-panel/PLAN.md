---
slug: places-side-panel
status: shipped
owner: Minh Tran
created: 2026-07-03
---

# Places side panel

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to
> implement this plan task-by-task.

**Goal:** Make `search_places` panel-capable, the same way `search_hotels`/`search_flights`
already are, so a places question opens the side-panel drawer instead of only returning prose.

**Architecture:** Reuse the existing `content_and_artifact` convention end-to-end — no new
mechanism. Add a `PlacesPanel` Pydantic projection in `app/streaming/panels.py`, convert
`search_places` to return `panel_result(summary, kind="places", data=...)`, mirror the shape into
the FE `panel.ts`, add a `PlacesPanel.tsx` renderer, and register it. The SSE `panel` event, the
mapper, and the FE `SidePanel` shell all already exist and are generic over `kind` — no changes
needed there.

**Tech Stack:** FastAPI + LangChain `@tool(response_format="content_and_artifact")` (backend),
Next.js + React + Vitest (frontend). No new dependencies.

---

## 1. Motivation

`search_hotels`, `search_flights`, `get_route`/`get_city_route`, and `get_weather`/`get_air_quality`
already emit a side panel via the `content_and_artifact` tool convention
(`specs/agent-side-panel`, `specs/flights-side-panel`, `specs/hotels-side-panel`). `search_places`
is the one tool left on the old plain-text path — the FE already reserves `"places"` in `PanelKind`
and `PANEL_LABELS` (comment in `registry.ts`: "forward-compatible with a `places` panel added when
its tool becomes panel-capable"), and `panels.py`'s own docstring says the places projection "lands
alongside its tool conversion." This plan is that conversion.

## 2. Non-goals

- No change to `search_hotels` — it is already panel-capable; the original request's premise that
  hotel-search is text-only was stale (confirmed by code inspection at intake).
- No change to the SSE `panel` event, the stream mapper, or the FE `SidePanel` shell/tab logic —
  all already generic over `kind`.
- No map/geo affordance for places (no `RoutePanel`-style deep-link) — out of scope; places don't
  need a directions link here.
- No change to `nearby_places`, `resolve_place`, `parse_nl_query`, or `list_place_categories` —
  only `search_places` is being converted.

## 3. Success Criteria

1. A places question (e.g. "restaurants in Tokyo") opens the Places side panel with the matching
   results while the assistant's text answer streams as today.
2. The model's context receives only a short summary, not the full place list (token economy,
   matching every other panel-capable tool).
3. An empty result (unrecognized city/category, or no matches) returns a helpful message and **no**
   panel — the mapper must never send an empty panel to the drawer (matches hotels/flights).
4. Existing `search_places` business behavior (fuzzy city/category resolution, `exclude_names`,
   rating/price filters) is unchanged — only the *invocation contract* changes (content+artifact
   instead of a bare list), which is why the existing tests need rewriting, not new logic.

## 4. Tasks

### Task 1.1 — Backend: PlacesPanel projection + search_places conversion

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/panels.py, apps/api/app/tools/place_tools.py, apps/api/tests/streaming/test_places_panel.py, apps/api/tests/tools/test_place_tools.py</files>
  <action>
    Add `PlacesPanelPlace` + `PlacesPanel(AppBaseModel)` to panels.py with a `from_places(city, category, places: list[Place]) -> PlacesPanel` classmethod, projecting the lean fields the drawer renders (id, name, city, country, category, description, address, rating, review_count, price_level, opening_hours, image_url, tags, is_recommended) — mirror HotelsPanel's leanness, skip lat/lng (no map affordance in this panel). Update the panels.py module docstring's "lands alongside its tool conversion" note to reflect it landed.

    Convert `search_places` in place_tools.py to `@tool(args_schema=SearchPlacesArgs, response_format="content_and_artifact")`. On empty results (mirroring search_hotels's resolved-city check): if `city` was given, call `svc.resolve_city(city)` — if unresolved, return a "city not recognized" message + None; otherwise a "no matches for filters" message + None. On non-empty results, return `panel_result(summary, kind="places", data=PlacesPanel.from_places(city, category, results))` where summary is a one-line count + city/category echo ("N places in {city}... The full list is in the Places panel.").

    Rewrite the 4 existing bare-dict-invoke tests in test_place_tools.py (test_search_places_returns_list_for_seeded_city, test_search_places_unknown_city_returns_empty, test_search_places_no_args_returns_list, test_search_places_exclude_names_omits_matches) to the ToolCall+ToolMessage form (mirror test_hotel_tools.py:82-100) — bare-dict invoke on a content_and_artifact tool silently drops the artifact and returns only the content string (verified empirically against search_hotels), so `isinstance(out, list)` assertions no longer hold. Assert business behavior via `msg.artifact["data"]["places"]` (or `msg.artifact is None` for the empty-result cases) instead. Add one new test asserting `msg.artifact["kind"] == "places"` on a matching search.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_places_panel.py tests/tools/test_place_tools.py -q</verify>
  <done>search_places returns (summary, artifact) with kind="places" on matches and (message, None) on empty; PlacesPanel.from_places projects and preserves order; all place_tools tests green under the new invocation contract.</done>
</task>
```

### Task 2.1 — Frontend: PlacesPanel renderer + registration

```xml
<task id="2.1" wave="2">
  <files>apps/web/src/lib/stream/panel.ts, apps/web/src/components/chat/panel/PlacesPanel.tsx, apps/web/src/components/chat/panel/PlacesPanel.test.tsx, apps/web/src/components/chat/panel/registry.ts</files>
  <action>
    Add `PlacesPanelPlace` + `PlacesPanelData` interfaces to panel.ts, mirroring the backend `PlacesPanel`/`PlacesPanelPlace` field-for-field (mirror `HotelsPanelData`'s style).

    Add `PlacesPanel.tsx` mirroring `HotelsPanel.tsx`/`FlightsPanel.tsx`: a header summary line (city/category + results_count) and a compact expandable row per place (thumbnail, name, category, rating, price_level, address; expanded detail shows description + tags + opening_hours). No cheapest-style ring highlight (places have no natural "best" metric) — optionally ring `is_recommended` places instead.

    Register `places: PlacesPanel` in `registry.ts`'s `PANEL_RENDERERS` (PANEL_LABELS.places already exists — no change there). Update the registry.ts comment that currently says the places renderer is pending.

    Note: `SidePanel.test.tsx` mocks `./registry` directly (its own inline `PANEL_RENDERERS` stub with only route/weather) and uses `"places"` as its "unregistered kind renders nothing" example — that test is independent of the real registry and needs no change.
  </action>
  <verify>cd apps/web && pnpm vitest run src/components/chat/panel</verify>
  <done>PlacesPanel renders a row per place + the header summary; expand-on-click reveals description/tags; registry.ts routes kind="places" to it; existing panel tests (incl. SidePanel.test.tsx) stay green.</done>
</task>
```

## 5. Risks

- **Invented panel shape** — `PlacesPanel`'s exact field set isn't dictated by an existing contract
  (unlike, say, a REST response shape); Task 1.1 documents the chosen fields inline for review
  instead of pre-negotiating a design doc, since this is a normal-lane/high-confidence mirror of an
  established pattern, not a design fork.
- **Test rewrite scope** — Task 1.1's test changes touch existing (already-passing) tests, not just
  new ones; the empirically-verified bare-invoke-drops-artifact behavior is the reason, and is
  called out explicitly in the task so the executing agent doesn't mistake it for scope creep.

## 6. Status Log

- 2026-07-03 — Plan drafted (intake: Lane=normal, Confidence=high, Flags=public-contract only, no
  hard gate — see `SUMMARY.md`). Branch `feat/places-side-panel` created in-place off `v3`; backend
  baseline (`make test`) green before starting.
- 2026-07-03 — Wave 1 (Task 1.1) done: commit `916fcd6`. Spec review ✅, code-quality review ✅.
- 2026-07-03 — Wave 2 (Task 2.1) done: commit `f40a4fb`. Spec review ✅, code-quality review ✅.
- 2026-07-03 — Final adversarial correctness review: 4 candidates scored, 2 fixed (commits
  `8abccc1`, `4d7953e`), 1 advisory recorded (uncapped panel size, Rule 4 — not fixed), 1 dropped
  (false positive). Re-review ✅ clean.
- 2026-07-03 — Final intent review: ✅ no divergence found. Ready for
  `finishing-a-development-branch`.
- 2026-07-03 — shipped via `feat/places-side-panel` (PR #57 → base `v3`).
