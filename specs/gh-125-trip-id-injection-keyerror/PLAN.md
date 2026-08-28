---
status: complete
---

# gh-125 — Trip-scoped tools must tolerate a conversation with no trip

**Base:** `main` (`76a68ae`). **Branch:** `fix/gh-125-trip-id-injection-keyerror`.

Lane: normal · Confidence: medium · Issue: https://github.com/minhtran3124/travel-pi/issues/125
Inputs: `design.md` (approved 2026-08-28), `research-brief.md` (depth Standard).

## 1. Objective

A turn that routes to a trip-scoped tool while the conversation has no active trip must produce a
usable reply instead of `KeyError: 'trip_id'`. The five tools in `app/tools/trip_tools.py` take
`trip_id` as an optional injected argument and, when it is absent, return a guidance value that
reads identically in all three sub-agents that bind them.

## 2. Approach

Adopt LangGraph's existing optional-injected-state tolerance (`tool_node.py:1394-1397` and
`:2008-2012`: a missing state key is skipped for any `InjectedState` parameter whose pydantic
field is not required) by giving `trip_id` a default. Return the guidance as an ordinary dict, so
`ToolNode` builds the `ToolMessage` itself and `handle_tool_errors` is never consulted — this is
what makes the wording identical across `planner` (`_tool_error_logic_only`) and `journal` /
`budget` (`_tool_error_to_message`, which relabels raised errors as a transient outage).

## Global Constraints

- Every `Verify` and Success-Criteria command runs from `apps/api/`, using `../../.venv/bin/python`
  (per `CLAUDE.md`; `python` alone is not always on PATH — `docs/solutions/harness/commit-gate-bare-python.md`).
- Change exactly one source file: `apps/api/app/tools/trip_tools.py`. Do not touch
  `app/routers/agent.py`, `app/agents/state.py`, `app/agents/nodes.py`, the supervisor, or any
  prompt. Leaving `_turn_input()` alone is what keeps `specs/fix-trip-id-persist-across-turns`
  from regressing.
- Do not add an `InjectedToolCallId` parameter and do not return a `Command`.
  `app/mcp/server.py:39-40` skips any tool whose signature has `tool_call_id`, so either one
  silently removes all five tools from the MCP server — a Rule-4 remove-functionality gate.
- Do not hand-author an `args_schema`; keep the auto-derived schema and describe arguments inline
  via `Annotated[..., Field(description=...)]`
  (`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`).
- Add any new import together with its first usage in one edit — the PostToolUse ruff hook strips
  an import that is momentarily unused (`docs/solutions/harness/formatter-strips-unused-import.md`).
- Create a branch before the first source edit (`rules/auto-correct-scope.md` → Branch isolation).
- SC-6 needs the dev stack running: `docker compose up -d` from `apps/api/` (not `docker restart`,
  which loses DNS to `db`).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Invoking any of the five trip tools through a graph whose `trip_id` channel was never written returns the guidance value instead of raising `KeyError: 'trip_id'` | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q` | exit 0 |
| SC-2 | The guidance wording survives a `journal`-style `handle_tool_errors` that relabels errors as a transient outage | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q -k handler_independent` | exit 0 |
| SC-3 | `trip_id` stays out of every model-facing tool schema after gaining a default | `../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q` | exit 0 |
| SC-4 | All five trip tools remain exposed over MCP | `../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q` | exit 0 |
| SC-5 | Existing trip-tool happy paths are unchanged by the signature reorder | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q` | exit 0 |
| SC-6 | The tolerance also holds on the Docker stack (Python 3.12, langgraph 1.2.11) | `docker compose exec -T api python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q` | exit 0 |

## Tasks

### Task 1.1 — Failing regression tests for the absent trip channel (wave 1)

- **Files:** apps/api/tests/tools/test_trip_tools_no_active_trip.py
- **Action:** Write the new test module first, before any source change, so the reproduction is
  captured as a permanent test rather than a one-off script. Build a `StateGraph` over a state
  class declaring `user_id: str` and `trip_id: str | None`, whose `trip_id` channel is never
  written, with a `ToolNode` holding the five trip tools. Cover four cases:
  (1) parametrized over all five tools — invoking with no `trip_id` in state returns a
  `ToolMessage` whose content names `no_active_trip`, and raises nothing;
  (2) `handler_independent` — the same graph built with a `ToolNode` whose `handle_tool_errors`
  returns the `_tool_error_to_message` "temporary upstream problem" wording, asserting that
  wording is absent from the resulting content;
  (3) no DB session is opened on the absent-trip path (patch `app.tools.trip_tools.session_scope`
  and assert it was not called);
  (4) `trip_id` is absent from `tool_call_schema.model_fields` for all five tools.
  Reuse the existing fixtures in `tests/tools/` rather than adding new ones.
- **Verify:** `! ../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q`
- **Done:** The module collects, and the run fails with `KeyError: 'trip_id'` reported for the
  parametrized case; the negation makes the command exit 0 while the tests still fail.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes: the reproduction recorded in `design.md` and the existing fixtures under the tests/tools directory. Produces: `apps/api/tests/tools/test_trip_tools_no_active_trip.py`.

### Task 2.1 — Make trip_id optional and return guidance when it is absent (wave 2)

- **Files:** apps/api/app/tools/trip_tools.py
- **Action:** On `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`
  and `add_itinerary_item`, change `trip_id` to
  `Annotated[str | None, InjectedState("trip_id"), Field(description=...)] = None` and move it
  after the required parameters. Add one module-level helper `_no_active_trip() -> dict` returning
  `{"error": "no_active_trip", "message": ..., "hint": ...}`, where the hint tells the agent to ask
  the traveller which trip is meant or to call `create_trip` first; keep the wording in that one
  place. Open each of the five tools with `if not trip_id: return _no_active_trip()`, placed above
  the `log_tool_call` and `session_scope()` lines so no DB session is opened. Widen the return
  annotation of `list_trip_places` to `list | dict`; leave the other four as `dict`. Update each
  `:param trip_id:` docstring line to state that an absent trip returns the guidance value. Do not
  set `awaiting_user` and do not change `create_trip`.
- **Verify:** `../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py tests/tools/test_trip_tools.py tests/tools/test_tool_registry.py tests/mcp/test_mcp_server.py -q`
- **Done:** All four test modules pass; `grep -n "tool_call_id" app/tools/trip_tools.py` still
  reports only the `create_trip` occurrences.
- **Criteria:** SC-1, SC-2, SC-3, SC-4, SC-5
- **Interfaces:** Consumes: `apps/api/tests/tools/test_trip_tools_no_active_trip.py` from Task 1.1. Produces: `apps/api/app/tools/trip_tools.py`.

### Task 3.1 — Confirm the tolerance on the Docker stack (wave 3)

- **Files:** specs/gh-125-trip-id-injection-keyerror/SUMMARY.md
- **Action:** Bring the dev stack up with `docker compose up -d` from `apps/api/`, run the new
  regression module inside the `api` container, and record the result as a `### Verify` row in
  `SUMMARY.md` naming SC-6. This closes the evidence gap recorded in `research-brief.md`: all
  library evidence so far comes from the local langgraph 1.2.6 / Python 3.14 install, while the
  issue reports langgraph 1.2.11 / Python 3.12 in Docker. If the module fails there, stop and
  escalate — the fallback is the `load_context_node` channel seeding recorded as a rejected
  alternative in `design.md`, and switching to it is a plan change, not an auto-fix.
- **Verify:** `docker compose exec -T api python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q`
- **Done:** The container run reports 0 failures, and `SUMMARY.md` carries a `### Verify` row with
  that command, its exit code, and `SC-6` in the `Criterion` column.
- **Criteria:** SC-6
- **Interfaces:** Consumes: `apps/api/app/tools/trip_tools.py` from Task 2.1. Produces: the SC-6 evidence row in `specs/gh-125-trip-id-injection-keyerror/SUMMARY.md`.

## Out of scope

- Migrating the five tools from `InjectedState` to the officially recommended `ToolRuntime`. It
  would make the missing key impossible by construction, but the parameter would be named
  `runtime`, which `app/mcp/server.py:39-40` does not skip, so the tools would be advertised over
  MCP with an unservable parameter. It belongs in a dedicated migration.
- A supervisor trip-resolution step (issue option 2).
- Giving `journal` and `budget` a `tool_fault=TOOL_FAULT` policy — it would change tool-error
  semantics for every other tool those sub-agents bind.
- Seeding the `trip_id` channel in `load_context_node`; held as the fallback if SC-6 fails.

## Status Log

- 2026-08-28 — tasks 1.1, 2.1 complete; commits a5c48ca, 3616338
- 2026-08-28 — task 3.1 complete; SC-6 verified on Docker (py3.12.14 / langgraph 1.2.11), 16 passed
