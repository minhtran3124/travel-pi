# agent-trip-context — Summary

Lane: high-risk
Confidence: high
Reason: Changes the MCP tool surface (adds `create_trip`, alters trip-tool signatures) — a public-contract hard gate per techstacks/guidelines.md — plus #8 existing-behavior (test-covered trip tools). Direction is settled (user chose option 2), so proceed with full ceremony, no blocking escalation.
Flags: public-contract (MCP tool surface), existing-behavior
Affects: apps/api/app/tools/trip_tools.py, app/tools/registry.py, app/mcp/server.py (surface), app/agents/nodes.py (context injection), app/prompts/planner/*, app/agents/context.py (tier)
Input-type: change request

> `Lane` drives ceremony; `Confidence` drives interruption. Hard gate forces high-risk; the
> human authorized the boundary by choosing the create_trip scope, so no ESCALATIONS block.

### Intent

> [conversation 373b88b5] "hiện tại tôi thấy flow đang ko đúng, user ko nên biết về trip id -
> đó chỉ là cách chúng ta handle ở phía BE thôi. chatbot said can draft full day-by-day nhưng
> lại đi hỏi trip id. hãy review all code changes hiện tại để hiểu rõ về luồng flow của chatbot.
> Và tư vấn xem nên fix gì"
>
> Chosen scope (reply "2"): **Fix A + Fix B Option 1** —
> A) stop `trip_id` leaking to the user (it is a BE detail), and
> B) give the agent a `create_trip` tool so it can open a trip transparently instead of asking
>    for a trip id when none is active.

Two root causes (evidence): trip tools take `trip_id` as a **required model-supplied arg**
(`trip_tools.py` explicit args_schema) and `load_context_node` prints `trip_id=<id>` into the
system prompt (`nodes.py:79`) → the model treats it as user-facing data and asks for it; and
there is **no create-trip tool** + no graceful no-trip branch (`nodes.py:73` has no `else`), so
the planner over-promises "draft a full itinerary" then asks for the internal id.

## What changed

`trip_id` is now injected from graph state (`InjectedState("trip_id")`) on all five trip tools
(the explicit `*Args` schemas dropped, per the args_schema-breaks-injection gotcha), so the model
never sees or asks for it; and `load_context_node` no longer prints `trip_id=<id>` into the system
prompt. A new `create_trip` tool (planner-only, non-destructive write) lets the agent open a trip
from destination/dates and returns a `Command` that sets `state["trip_id"]` so the fresh trip is
usable in the same turn. `create_trip` is excluded from the MCP surface (it returns a Command +
`InjectedToolCallId`); the read/write trip tools stay MCP-exposed. Planner prompt **v9** forbids
mentioning/asking a trip id and, with no active trip, asks destination + dates in human terms then
calls `create_trip` before building the itinerary. No DB migration (trips are un-owned/global).

### Rationale

Mirror the repo's own injection pattern: `trip_id` becomes `InjectedState("trip_id")` (like
`user_id` in memory_tools), so the model never sees or asks for it; add a `create_trip` tool
(user_id injected) so the agent can start a trip from destination/dates in human terms.

### Alternatives considered

- Fix B Option 2 (draft in-chat, no auto-create) — rejected by the user in favor of a real
  `create_trip` capability (option 1).

### Deviations

- Rule 1 — Test-design fix (Task 1.1): a bare `ToolNode(...).invoke(state)` raises in this
  langgraph version; the injection tests wrap the `ToolNode` in a compiled one-node
  `StateGraph(TravelAgentState)` so `InjectedState("trip_id")` resolves. `tests/tools/test_trip_tools.py`.
- Rule 1 — Updated `tests/prompts/test_active_versions_load.py` to expect `planner == 9` after the
  version bump (Task 3.1 plan gap — the test pins active versions and wasn't in the task's file list).
- Rule 3 — `ruff-on-edit` removed the `create_trip` import as unused mid-edit twice (registry &
  run_eval pattern); resolved by combining import + usage into one atomic edit.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full suite (worktree) | `DATABASE_URL=sqlite:///:memory: python -m pytest -q` | 1* | 1698 passed; *only failure is pre-existing `test_flight_tools_dates::test_one_day_tz_skew_is_tolerated`, confirmed failing on clean v3 (date-anchored flake, unrelated) |
| trip tools inject trip_id | `pytest tests/tools/test_trip_tools.py -q` | 0 | 14 passed; injection proven via ToolNode+StateGraph |
| registry + guard | `pytest tests/tools/test_tool_registry.py -q` | 0 | 48 passed; create_trip planner-only, write-not-destructive |
| MCP exclusion | `pytest tests/mcp/test_mcp_server.py -q` | 0 | 5 passed; create_trip excluded, get_trip_summary exposed |
| load_context string | `pytest tests/agents/test_state.py -q` | 0 | 14 passed; no trip_id in trip_context |
| planner v9 active | `python -c "...active_version('planner')==9; 'trip_id' not in get('planner')"` | 0 | v9 active, no trip_id, create_trip present |

### Rollback

- `git revert <sha>` (tool-signature refactor + new tool + prompt version; no DB migration —
  `create_trip` uses the existing `TripService.create_trip` + `trips` table).
- Prompt-only revert: flip `active.yaml` `planner` back to its prior version.

### Harness-Delta

- none
