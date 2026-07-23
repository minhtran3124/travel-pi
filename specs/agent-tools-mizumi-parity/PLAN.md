---
slug: agent-tools-mizumi-parity
status: shipped
owner: Minh Tran
created: 2026-06-27
---

# Agent tools — mizumi parity (directions/route tool)

## 1. Motivation

Comparison with mizumi-ai's tools (see `RESEARCH.md`) found this repo already at or above parity
on **weather** and **nearby/places**, with one deliberate difference (we stay mock/DB-first, no
Google APIs). The single real capability gap: **the agent has no directions/route tool**, even
though `app/services/routing_service.py` already provides real OpenRouteService road routing (with
an offline haversine fallback) and is HTTP-exposed at `/places/route` and `/cities/route`.

Goal: wrap the existing `RoutingService` as agent tool(s) so the assistant can answer "how far / how
long from A to B, and by what mode?" — cloning mizumi's *idea*, reusing our *service*, adding **no**
new external dependency.

## 2. Non-goals

- No Google Maps / Google Places integration (breaks the mock-first contract).
- No new external dependency — ORS is already wired; offline fallback already exists.
- No UI map streaming (mizumi's `map_data` push) — defer until the web FE wants route rendering.
- No second per-tool LLM "humanize" pass — humanization stays centralised in `communication_style`.
- No change to the routing service, its cache, schemas, or the existing HTTP endpoints.

## 3. Success criteria

- A `get_route` tool (place→place) callable by the planner and concierge sub-agents.
- A `get_city_route` tool (city→city) for inter-city "how far is Hanoi from Da Nang" questions.
- Both async (the service is async), both reuse `session_scope()`, both map `AppError`→`ToolException`.
- Registered in `registry.py` with `readOnly: true`, surfaced via `/agent/manifest`.
- Tests pass offline (no ORS key → haversine estimate path), suite stays green.

## 4. Tasks

### Task 1.1 — Add routing tools wrapping RoutingService

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/tools/routing_tools.py</files>
  <action>Create routing_tools.py modelled on weather_tools.py (async) + place_tools.py (session_scope). Define two @tool async functions:
- get_route(origin_place_id: str, destination_place_id: str) -> dict — opens `with session_scope() as s:`, calls `await RoutingService(s).get_place_route(origin_place_id, destination_place_id)`, returns `dump(...)`. Docstring: explains it returns distance + duration per travel mode (walk/bike/car), a recommended mode, and straight-line km; accepts place ids or PLC-XXXX short codes; note that an unknown place id or one without coordinates raises (suggest GET /places/search). Mirror the docstring quality of search_places.
- get_city_route(origin_city: str, destination_city: str) -> dict — same shape via `get_city_route`; docstring notes fuzzy/typo-tolerant city names (e.g. 'danang' -> 'Da Nang').
Both wrap the body in `try/except AppError as e: raise ToolException(str(e)) from e`. Export `ROUTING_TOOLS = [get_route, get_city_route]`. Module docstring should note these wrap the real-or-fallback ORS routing service (like weather, a real outbound call).</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -c "from app.tools.routing_tools import ROUTING_TOOLS; print([t.name for t in ROUTING_TOOLS])"</verify>
  <done>Module imports; prints ['get_route', 'get_city_route'].</done>
</task>
```

### Task 1.2 — Register routing tools in the tool registry

```xml
<task id="1.2" wave="2">
  <files>apps/api/app/tools/registry.py</files>
  <action>Import ROUTING_TOOLS from app.tools.routing_tools. Add it to the planner and concierge domain groups in TOOLS_BY_DOMAIN (planner: itinerary/logistics; concierge: on-the-ground navigation). Both tools are read-only — do NOT add to _WRITE or _DESTRUCTIVE (the default _meta already marks them readOnly:true). No other change.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -c "from app.tools.registry import get_tools_for, TOOL_METADATA; assert 'get_route' in [t.name for t in get_tools_for('concierge')]; assert TOOL_METADATA['get_route']['readOnly'] and not TOOL_METADATA['get_route']['destructive']; print('ok')"</verify>
  <done>get_route present in concierge + planner groups; metadata readOnly true, destructive false.</done>
</task>
```

### Task 1.3 — Tests for the routing tools (offline path)

```xml
<task id="1.3" wave="2">
  <files>apps/api/tests/tools/test_routing_tools.py</files>
  <action>Add tests using the agent_db fixture (offline: no ORS key, so the service uses the haversine estimate path — no network). Use asyncio.run(tool.ainvoke({...})) since the tools are async. Cover:
- get_city_route between two seeded cities returns a dict with keys 'legs', 'recommended_mode', 'straight_line_km', 'source' == 'estimate'; legs has 3 entries (walk/bike/car).
- get_route between two valid seeded place ids in the same city returns a dict with the same shape (resolve two place ids first via PlaceService or search_places).
- get_route with an unknown place id raises ToolException.
Keep assertions on shape, not exact distances (seed data may shift).</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/tools/test_routing_tools.py -x</verify>
  <done>All routing tool tests pass offline.</done>
</task>
```

### Task 1.4 — Full tool + agent suite regression

```xml
<task id="1.4" wave="3">
  <files>apps/api/tests/tools/</files>
  <action>Run the tool + registry suite to confirm no regression from the new registry wiring (manifest/registry tests included). No code change expected; fix only if the new tool count breaks an assertion in test_tool_registry.py.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/tools/ -q</verify>
  <done>Whole tests/tools/ suite green.</done>
</task>
```

## 5. Risks

- **Async tool + sync `session_scope`**: the session is used only *before* the `await` (endpoint
  resolution); the ORS call uses httpx, not the DB session, so holding the sync session across the
  await is safe under single-threaded asyncio. Mirrors how routing_service itself is structured.
- **`test_tool_registry.py` may assert an exact tool count / name set** — Task 1.4 covers updating it.
- **`.env` OPENAI_API_KEY=test** can break unrelated LLM tests locally (see memory) — scope verify
  commands to `tests/tools/`, which don't hit the LLM.
- Optional `nearby_places` city-anchor improvement (RESEARCH §2c) is **out of scope** here — file
  separately if wanted.

## 6. Status Log

- 2026-06-27 — Plan drafted from RESEARCH.md. Status: proposed.
- 2026-06-27 — Executed all 4 tasks. Added `app/tools/routing_tools.py`
  (`get_route`, `get_city_route`), registered in planner+concierge groups,
  added `tests/tools/test_routing_tools.py` (3 tests, offline estimate path).
  `pytest tests/tools/` → 28 passed; `ruff check` clean. Status: shipped.
