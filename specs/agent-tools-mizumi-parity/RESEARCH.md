# Research — mizumi-ai tools vs travel-pi agent tools

**Date:** 2026-06-27
**Scope:** Compare three mizumi-ai chatbot tools against this repo's agent tools, decide
what to clone / learn / improve.

Sources reviewed:
- `mizumi-ai/chatbot/src/agents/tools/{weather,directions,search_nearby}.py` (+ their services)
- `apps/api/app/tools/*` and `apps/api/app/services/routing_service.py` (this repo)

---

## 1. The two architectures, briefly

| | mizumi-ai | travel-pi (this repo) |
|---|---|---|
| Framework | LangGraph, hotel-concierge graph | LangGraph supervisor + 5 ReAct sub-agents |
| Tool return | `Command(update=..., goto="assistant")` — mutates graph state + UI | plain JSON dict/list via `dump()`; errors → `ToolException` |
| Data sources | **external live APIs** (Google Maps, Google Places, Open-Meteo) | **mock/DB-seed** except real Open-Meteo (weather) + real ORS (routing) |
| Location | hotel coords injected from state (`origin="hotel"`) | free-text city/place id, fuzzy-resolved in services |
| LLM-facing formatting | per-tool (weather has its own 2nd LLM "humanize" pass) | centralised — `build_subagent` prepends `communication_style` |
| Tool registry | none; tool lists assembled per graph node | `registry.py` — `TOOLS_BY_DOMAIN` + MCP `readOnly`/`destructive` metadata |

Key philosophical difference: **mizumi calls live third-party APIs; travel-pi is a mock
backend by design** (CLAUDE.md: "everything faked except keyless Open-Meteo and `/*/route`").
That constraint decides most of the recommendations below — we do **not** want to introduce
Google Maps/Places dependencies.

---

## 2. Tool-by-tool comparison

### 2a. Weather — ✅ parity, minor learnings

- **mizumi** `lookup_weather` (`weather.py:138`): Open-Meteo async → deterministic WMO-code→text
  formatter → **second LLM pass** with `WEATHER_SUMMARY_PROMPT` to humanize + suggest activities.
- **travel-pi** `get_weather` / `get_packing` / `get_air_quality` (`weather_tools.py`): also real
  Open-Meteo, async, `ToolException` on failure. Already richer (packing + AQI). Humanization is
  handled once at the agent layer (`communication_style`), so mizumi's per-tool 2nd LLM pass would
  be redundant and slower here.
- **Verdict:** keep ours. Only optional learning: mizumi's "activity suggestions tied to weather
  conditions" is a nice product touch — but that's a prompt concern, not a tool concern, and can
  live in the concierge/planner prompt rather than a new tool.

### 2b. Directions / route — ❌ GAP (the one real action item)

- **mizumi** `lookup_directions` (`directions.py:22`): Google Directions API, `origin="hotel"`
  shortcut, returns duration/distance + a Google Maps deep-link, streams a map to the UI early.
- **travel-pi**: `routing_service.py` **fully exists** — real OpenRouteService road routing with a
  haversine offline fallback, in-process cache, per-mode (walk/bike/car) legs, recommended mode,
  resolves both **places** (`get_place_route`) and **cities** (`get_city_route`). It backs
  `GET /places/route` and `GET /cities/route` — **but it is NOT wrapped as an agent tool.**
  `grep routing_service app/tools/` → nothing.
- **Verdict:** **CLONE THE IDEA, REUSE OUR SERVICE.** The agent currently cannot answer "how do I
  get from my hotel to the Dragon Bridge / how far is it?" even though the backend can. Wrap
  `RoutingService` as one (or two) async tools. No new external dependency — ORS is already wired.

### 2c. Search nearby / places — ✅ parity, different-by-design

- **mizumi** `search_nearby_location` / `search_places` / `find_place` (`search_nearby.py`): live
  Google Places, free-text + type-enum, Haversine distance computed locally, UI recommendation cards.
- **travel-pi**: `search_places` (city/category/rating/price filter) + `nearby_places` (radius around
  a known place id, haversine, nearest-first) + `resolve_place` + `parse_nl_query` +
  `list_place_categories` (`place_tools.py`). Backed by seeded DB, by design.
- **Verdict:** keep ours — adopting Google Places would break the mock-first contract. Two patterns
  worth borrowing cheaply:
  1. **Enum-in-docstring**: mizumi inlines the valid place-type vocabulary into the docstring so the
     LLM picks valid args. We already have a *better* dynamic equivalent (`list_place_categories`
     tool) — no change needed, just confirm the planner/concierge prompt points the model at it.
  2. **`nearby_places` only anchors on an existing place id.** mizumi can search around arbitrary
     coords. Minor optional improvement: allow `nearby_places` to also anchor on a **city** (city
     centroid) so "things near Da Nang" works without first resolving a specific place. Low priority.

---

## 3. Patterns worth learning (cross-cutting)

| Pattern (mizumi) | Already have it? | Action |
|---|---|---|
| Graceful, on-brand fallback on every failure path | Yes — `ToolException` → recoverable `ToolMessage` | none |
| Local Haversine distance (don't trust API) | Yes — `core/geo.haversine_km`, used in routing + nearby | none |
| Enum-in-docstring to constrain LLM args | Equivalent: `list_place_categories` tool | confirm prompt usage |
| Early UI streaming of `map_data` | No (FE-dependent) | defer — only if web FE wants map rendering |
| Per-tool 2nd LLM humanize pass | Centralised at agent layer instead | skip (redundant) |
| Committed API key in `config.py:67` (mizumi bug) | N/A | avoid — keep ORS key in env only |

---

## 4. Recommendation summary

1. **Build a directions/route tool** wrapping the existing `RoutingService`. This is the only true
   capability gap. → PLAN.md.
2. *(optional, low priority)* Extend `nearby_places` to accept a city anchor.
3. *(prompt-only, no code)* Ensure concierge/planner prompts steer the model to
   `list_place_categories` and (once added) the route tool, and to weather-aware activity ideas.

Everything else is already at or above mizumi parity, with the deliberate difference that travel-pi
stays mock/DB-first and avoids Google API dependencies.
