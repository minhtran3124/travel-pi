---
slug: agent-trip-context
status: proposed
owner: minh.tran
created: 2026-07-18
---

# Agent trip_id flow — inject trip_id + add create_trip

## Design decisions

- **(a) InjectedState + drop args_schema.** The five trip tools use explicit
  `@tool(args_schema=…Args)` with a required `trip_id` (`trip_tools.py:24-61,63-127`). Mirror
  `memory_tools.py:33-98`: drop the `*Args` classes, use annotated signatures with
  `trip_id: Annotated[str, InjectedState("trip_id")]` (the args_schema-breaks-injection gotcha:
  `docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`). State already carries
  `trip_id` (`state.py:45`).
- **(b) MCP surface.** Leave InjectedState(str) trip tools exposed (external clients still pass
  `trip_id` as a plain string — no contract break). Exclude `create_trip`: it returns a `Command`
  and needs `InjectedToolCallId`, so add a `"tool_call_id" in params` skip mirroring the existing
  `"store"` skip (`server.py:37`).
- **(c) create_trip.** Args: `title` (required), `city`, `start_date`/`end_date` (ISO strings,
  resolved upstream by `resolve_date`), `travelers`; `tool_call_id: InjectedToolCallId`. Builds
  `TripCreate` (`schemas/trip.py:74`), calls `TripService.create_trip` (`trip_service.py:107`),
  returns `Command(update={"trip_id": trip.id, "messages":[ToolMessage(...)]})` so the new trip
  is active for the rest of the turn and round-trips to the client (`routers/agent.py`). **No
  `user_id`** — `Trip`/`TripCreate` have no owner column and trips are not user-scoped
  (verified `db/models/trip.py:9-20`), so ownership is neither possible nor needed here.
- **(d) No-trip planner UX.** Planner v9 never prints/asks a trip id (drop `trip_id=<id>` from
  `nodes.py:79`); with no active trip it asks destination + dates in human terms, then calls
  `create_trip`, then builds the itinerary.

## 1. Motivation

Every trip tool declares `trip_id` as a required, model-supplied argument via explicit
`args_schema` (`app/tools/trip_tools.py:24-61,63-127`), and `load_context_node` writes
`Use the trip tools with trip_id=<id>` into the system prompt (`app/agents/nodes.py:79`). The
model treats the internal trip UUID as user-facing data and asks the traveller for it — leaking
an internal id. `user_id` already avoids this by being injected (`memory_tools.py:37`).

Separately, there is no way for the agent to open a trip (`nodes.py:73` `if trip_id:` has no
else), so with no active trip the planner over-promises an itinerary then asks for a trip id.

This plan (A) injects `trip_id` from state on all trip tools so the model never sees or asks for
it, and (B) adds a `create_trip` tool + planner v9 so the agent opens a trip from destination/dates.

## 2. Non-goals

- No DB migration / no new column. `Trip`/`TripCreate` have no owner field; per-user trip
  ownership is not enforceable and is out of scope (trips are global in this mock backend).
- No change to destructive/HITL semantics. `create_trip` is a write, not destructive — it does
  not route through `plan_node`; `_DESTRUCTIVE` (`registry.py:65`) is untouched.
- No change to booking/journal/concierge/budget tool groups beyond adding `create_trip` to planner.
- No editing of an existing prompt version file (new planner v9 + `active.yaml` flip).

## 3. Success Criteria

- The five trip tools expose no `trip_id` in their model-facing `tool_call_schema`; `trip_id`
  is injected from `state["trip_id"]`; the `*Args` classes are gone.
- `create_trip` exists, bound to the planner only, `readOnly=False`/`destructive=False`, builds a
  valid `TripCreate`, and returns a `Command` that sets `state["trip_id"]`.
- `load_context_node` emits `Active trip: <title> (city: <city>).` with no `trip_id=` literal.
- MCP surface: `get_trip_summary` etc. still exposed; `create_trip` excluded.
- Planner v9 active; never asks for a trip id; with no active trip asks destination/dates then
  creates the trip.
- `make test` green.

## 4. Tasks

### Task 1.1 — Inject trip_id + add create_trip (wave 1)

- **Files:** apps/api/app/tools/trip_tools.py, apps/api/tests/tools/test_trip_tools.py
- **Action:** Drop the five `*Args` classes and every `@tool(args_schema=…)`; convert
  `get_trip_summary`/`get_trip_budget`/`list_trip_places`/`add_place_to_trip`/`add_itinerary_item`
  to annotated signatures with `trip_id: Annotated[str, InjectedState("trip_id")]` and model-facing
  args via `Annotated[..., Field(description=...)]`, mirroring `app/tools/memory_tools.py:33-98`.
  Add `create_trip(title, city, start_date, end_date, travelers,
  tool_call_id: Annotated[str, InjectedToolCallId]) -> Command`: build `TripCreate`
  (`app/schemas/trip.py:74`), call `TripService.create_trip` (`app/services/trip_service.py:107`),
  return `Command(update={"trip_id": trip.id, "messages":[ToolMessage(dump(trip), tool_call_id=...)]})`.
  Map `AppError`/`ValueError` → `ToolException` as the other tools do. Keep `create_trip` OUT of
  `TRIP_TOOLS` (export separately) so journal/concierge/budget do not inherit it. Update tests:
  drop the args_schema assertion; assert `trip_id` absent from each tool's model-facing
  `tool_call_schema` but present in the raw `fn` signature; drive at least one read + one write
  through `ToolNode` with `state={"trip_id": ...}` to prove injection; add a `create_trip` test
  asserting the returned `Command` sets `trip_id` and emits a `ToolMessage`.
- **Verify:** `../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q`
- **Done:** trip tools inject trip_id; create_trip returns a state-updating Command; file test green.

### Task 1.2 — Clean load_context trip_context string (wave 1)

- **Files:** apps/api/app/agents/nodes.py, apps/api/tests/agents/test_state.py
- **Action:** In `load_context_node` (`app/agents/nodes.py:77-80`) drop the second sentence so
  `trip_context` reads `f"Active trip: {detail.title} (city: {detail.city})."` — no `trip_id=`
  literal. Update the `test_state.py` case that asserts the trip id appears in `trip_context` to
  stop asserting it (keep the title assertion).
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_state.py -q`
- **Done:** trip_context omits the trip id; test_state green.

### Task 2.1 — Register create_trip on planner + mark write (wave 2)

- **Files:** apps/api/app/tools/registry.py, apps/api/tests/tools/test_tool_registry.py
- **Action:** Import `create_trip` and add it to the `"planner"` domain only
  (`registry.py:34-43`) and to `_WRITE` (`:66-75`); do NOT add to `_DESTRUCTIVE` (`:65`). Add
  registry tests: `create_trip` in the planner group, absent from concierge/journal/booking/budget,
  and `TOOL_METADATA["create_trip"] == {"readOnly": False, "destructive": False}`.
- **Verify:** `../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q`
- **Done:** create_trip bound to planner only, annotated as a non-destructive write; registry green.

### Task 2.2 — Exclude create_trip from the MCP surface (wave 2)

- **Files:** apps/api/app/mcp/server.py, apps/api/tests/mcp/test_mcp_server.py
- **Action:** In the skip guard (`app/mcp/server.py:37`) also `continue` when `"tool_call_id" in
  inspect.signature(fn).parameters`, mirroring the `"store"` skip + comment — a Command-returning
  tool with an `InjectedToolCallId` cannot be served over MCP. Leave InjectedState(str) trip tools
  exposed. Add a test: `create_trip` NOT in the MCP tool names while `get_trip_summary` still is.
- **Verify:** `../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q`
- **Done:** create_trip excluded from MCP; existing trip tools still exposed; MCP test green.

### Task 3.1 — Planner v9 prompt + active flip (wave 3)

- **Files:** apps/api/app/prompts/planner/v9.md, apps/api/app/prompts/active.yaml
- **Action:** Copy `planner/v8.md` to a new `v9.md` (never edit v8). Remove any notion of a trip
  id from the traveller-facing flow; add a rule that the model never sees or asks for a trip id.
  Add a no-active-trip branch: when "Active trip" is absent from Known trip facts, ask destination +
  dates in human terms (relative dates via `resolve_date`), then call `create_trip`, then build the
  itinerary — never promise the itinerary before the trip exists, and create the trip in a step
  before adding items (state update applies between tool batches). Flip `planner: 8` → `9` in
  `active.yaml`. Graph is baked at lifespan — flip takes effect on restart.
- **Verify:** `../../.venv/bin/python -c "from app.prompts.registry import registry; t=registry.get('planner'); assert registry.active_version('planner')==9; assert 'trip_id' not in t; assert 'create_trip' in t"`
- **Done:** planner v9 active, contains no trip_id, instructs create_trip on no active trip.

## 5. Risks

- **Same-turn parallel tool calls.** If the model emits `create_trip` and `add_itinerary_item` in
  one batch, the second injects a stale `trip_id` (Command updates apply between ToolNode passes).
  Mitigation: planner v9 instructs create-first, then add items in the next step; the ReAct loop
  `assistant → tools → assistant` (`_base.py`) supports this.
- **FastMCP + Annotated metadata.** FastMCP builds its schema from the raw `fn` signature; it must
  treat `Annotated[str, InjectedState("trip_id")]` as a plain `str`. If it chokes, that is a
  public-contract regression — Task 2.2's verify (`test_mcp_server.py`) is the tripwire; escalate
  rather than silently dropping trip tools from MCP.
- **Registry ALL_TOOLS guard.** `test_tool_registry.py` parametrizes every tool and requires
  described model-facing fields; `create_trip` must describe each model-facing arg via
  `Annotated[..., Field(...)]` or that guard fails.
- **Full-suite regression.** The trip-tool signature change ripples to any test invoking them with
  a `trip_id=` kwarg; run `make test` before the wave-boundary commit, not just per-file verifies.

## 6. Status Log

- 2026-07-18 — All 5 tasks implemented on `feat/agent-trip-context` (waves 1→3, subagent-driven).
  Wave 1: trip tools → InjectedState trip_id + `create_trip` (Command sets state trip_id); prompt
  string cleaned. Wave 2: registry (create_trip → planner + _WRITE) + schema guard fix; MCP
  excludes create_trip. Wave 3: planner v9 + active.yaml flip. Verify: full suite 1698 passed
  (only the pre-existing `test_flight_tools_dates` tz-skew flake fails — also red on clean v3).
  Deviations (Rule 1×2, Rule 3×1) recorded in SUMMARY. Status → shipped-pending-review.
