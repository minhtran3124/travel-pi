# gh-125 — Trip-scoped tools must tolerate a conversation with no trip

Status: approved (user, 2026-08-28)
Lane: normal · Confidence: medium (see `SUMMARY.md`)
Issue: https://github.com/minhtran3124/travel-pi/issues/125

## Problem

Any turn routing to a trip-scoped tool crashes with `KeyError: 'trip_id'` when the conversation
has no active trip. The traveller sees the generic error fallback, so a hard crash reads as a
flaky model.

Three facts collide, all three verified against the working tree rather than taken from the
issue text:

1. `apps/api/app/routers/agent.py` — `_turn_input()` omits `trip_id` from the graph input when
   the client sends `null`. Deliberate: `TravelAgentState.trip_id` has no reducer, so an explicit
   `None` would clobber a `trip_id` that `create_trip` set mid-conversation
   (`specs/fix-trip-id-persist-across-turns`).
2. `apps/api/app/agents/state.py:94` — `trip_id: str | None`. A declared key is not a live
   LangGraph channel; the channel exists only once something writes it.
3. `apps/api/app/tools/trip_tools.py` — five tools take
   `trip_id: Annotated[str, InjectedState("trip_id")]` at lines 49, 79, 107, 138, 181.

On a fresh conversation with `trip_id: null` nothing ever writes the channel, so injection looks
up a missing key. The state type says nullable; the injection path had no way to say "absent".

## Root cause, precisely

`langgraph/prebuilt/tool_node.py:1394-1397`:

```python
elif state_field in state:
    injected_args[tool_arg] = state[state_field]
elif tool_arg not in injected._optional_state_args:
    raise KeyError(state_field)
```

and `tool_node.py:2008-2012` builds that set from exactly one condition:

```python
field_info = full_schema.model_fields.get(name)
if field_info and not field_info.is_required():
    _optional_state_args.add(name)
```

**A missing state key is already tolerated by LangGraph — but only when the tool's parameter has a
default.** Our five tools declare `trip_id` required, so they opt out of the tolerance that
already exists. This reframes the issue: no state seeding and no router change are needed.

Verified empirically before designing (`langgraph 1.2.6`, a `StateGraph` whose state declares
`trip_id: str | None` exactly like production, and whose `trip_id` channel is never written):

```
A  trip_id: Annotated[str, InjectedState("trip_id")]          -> KeyError: 'trip_id'
B  trip_id: Annotated[str | None, InjectedState(...)] = None  -> OK, content='got None'
```

Also confirmed in the same run: `tool_call_schema.model_fields` is `[]` in **both** cases, so
giving the parameter a default does not expose the internal trip UUID to the model, and the
`_has_injected_args` guard in `tests/tools/test_tool_registry.py:110` keeps passing.

## Second defect, found while designing

Making the tool tolerate `None` is only half the fix — the reply the traveller gets depends on
which sub-agent ran, because the five tools live in three sub-agents with two different
`handle_tool_errors`:

| Sub-agent | Trip tools bound | Handler | What the model is told on a raised `ToolException` |
| --- | --- | --- | --- |
| `planner` | all five | `_tool_error_logic_only` (`app/agents/retry.py:113`) | "The request looks invalid — check the arguments and try a corrected call, or tell the user what is needed." |
| `journal` | all five | default `_tool_error_to_message` (`app/agents/subagents/_base.py:143`) | "This is a **temporary upstream problem** … tell the user the information is currently unavailable and to try again shortly." |
| `budget` | `get_trip_budget` | default | as `journal` |

The issue's own repro (*"Please send my itinerary"*) routes to `journal`. So a plain
`raise ToolException` would fix the crash and still render "no trip yet" as a transient outage —
the exact symptom the issue reports.

Worse, `app/prompts/communication_style/v8.md:131` states *"Never call `needs_clarification`
because a tool failed or returned nothing — that is an honesty case, not a clarification case."*
Framing an absent trip as a **failure** therefore forbids the agent from asking which trip is
meant, which is the behaviour we want.

## Design

Return the guidance as an **ordinary tool return value** — a plain dict. `ToolNode` wraps a
non-`Command` return into a `ToolMessage` itself and pairs the `tool_call_id`, so the message
never passes through `handle_tool_errors` and all three sub-agents relay identical wording. It is
not a failure, so the prompt's clarification prohibition does not apply either.

All changes are confined to `apps/api/app/tools/trip_tools.py`.

1. On `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`,
   `add_itinerary_item`: `trip_id: Annotated[str | None, InjectedState("trip_id"), Field(...)] = None`,
   moved after the required parameters (Python defaults-last).
2. One module-level helper `_no_active_trip() -> dict` returning
   `{"error": "no_active_trip", "message": ..., "hint": ...}`, so the guidance text has a single home.
3. Each tool opens with `if not trip_id: return _no_active_trip()` — before `session_scope()`, so
   no DB session is opened for a call that cannot proceed.
4. Return annotations: unchanged (`dict`) for the four dict-returning tools; `list_trip_places`
   widens to `list | dict`.

**No `InjectedToolCallId`, and no `Command` return.** This is a hard constraint, not a style
preference: `app/mcp/server.py:39-40` skips any tool whose signature has a `tool_call_id`
parameter, so adding one would silently drop all five tools from the MCP server — removing
existing functionality (a Rule-4 judgment gate). `tests/mcp/test_mcp_server.py:50` asserts exactly
this boundary today (`create_trip` excluded, `get_trip_summary` exposed), so `create_trip` is not
a precedent for shipping a `Command` over MCP — it is the evidence that you cannot.

Deliberately **not** set: `awaiting_user`. Leaving it clear keeps the agent free to call
`create_trip` and continue within the same turn, rather than forcing the turn to end on a
question. `create_trip` sets it only because an anonymous caller genuinely cannot proceed.

Deliberately **unchanged**: `routers/agent.py` (`_turn_input`), `agents/state.py`,
`load_context_node`, the supervisor, and every prompt. Not touching `_turn_input` is what makes
re-introducing `specs/fix-trip-id-persist-across-turns` structurally impossible here.

Verified empirically on the installed stack, with a `ToolNode` deliberately given a
`journal`-style handler that mislabels everything as a transient outage, and a `trip_id` channel
that is never written:

```
status: success
content: {"error": "no_active_trip", "message": "...", "hint": "Ask the traveller which trip ..."}
tool_call_id paired: c1
model-facing schema: []
has tool_call_id param (MCP-blocking): False
```

The mislabelling handler was never reached, confirming the guidance is handler-independent.

## Error behaviour

- No active trip -> guidance `ToolMessage` (`status="success"`), identical across `planner` /
  `journal` / `budget`, handler-independent. The sub-agent chooses: ask which trip, or call
  `create_trip` and proceed.
- Trip present but wrong owner or missing -> unchanged. `AppError` -> `tool_error(e)` ->
  `ToolException`, preserving the `hint` recovery pointer (`app/tools/_base.py`).
- Direct and MCP callers -> unchanged for a supplied `trip_id`; an omitted one now returns the
  same guidance dict instead of raising `TypeError`. MCP exposure of all five tools is preserved.

## Tests

| # | Test | Proves |
| --- | --- | --- |
| 1 | Graph-level regression: a `StateGraph` that never writes the `trip_id` channel invokes each of the five tools | No `KeyError`; the guidance message comes back. This is the reproduction promoted to a permanent test. |
| 2 | Same graph, but the `ToolNode` is given the `journal`-style `_tool_error_to_message` handler | The guidance is NOT rewritten into "temporarily unavailable" — the wording is handler-independent. |
| 3 | Per-tool: invoke with `trip_id` absent | Guidance dict returned and **no DB session opened**. |
| 4 | Schema guard: `tool_call_schema.model_fields` for the five tools | `trip_id` still not model-facing — the internal UUID does not leak once the field is optional. |
| 5 | `tests/mcp/test_mcp_server.py` unchanged and passing | All five tools stay exposed over MCP; the fix added no `tool_call_id` parameter. |
| 6 | The existing cases in `tests/tools/test_trip_tools.py` | Happy paths unchanged (they call `.invoke({...})` by keyword, so the parameter reorder is safe). |

## Risks

- **`list_trip_places` return type** widens to `list | dict`. The other four keep `dict`. Callers
  that assume a list must tolerate the guidance shape; checked by test 3.
- **Parameter reorder.** Every call site found is keyword-based (`.invoke({...})` in tests; the
  agent path injects by name; `app/routers/trips.py` calls `TripService`, not the tools). A
  positional caller outside `apps/api/` would break.

## Alternatives considered

- **Seed the channel in `load_context_node`** (echo `state.get("trip_id")` into the per-turn reset
  dict at `app/agents/nodes.py:76`). Rejected as unnecessary given `_optional_state_args`: it adds
  a second state writer to fix something the tool signature already expresses. Kept on record as a
  defence-in-depth option if a future non-optional injected consumer of `trip_id` appears.
- **Issue option 2 — a supervisor trip-resolution step.** Largest diff, changes routing for every
  trip-scoped intent, and would itself be high-risk (prompt versioning). It also does not fix the
  direct/MCP call path, where the same `KeyError` class of failure lives.
- **Plain `raise ToolException`.** Rejected: correct wording on `planner`, "temporarily
  unavailable" on `journal` and `budget`, and it trips the prompt's clarification prohibition.
- **Return a `Command` + `ToolMessage`, mirroring `create_trip`'s anonymous refusal.** Considered
  first and rejected on evidence: it requires an `InjectedToolCallId` parameter, which
  `app/mcp/server.py:39-40` uses as its skip condition, so it would have removed all five tools
  from the MCP surface. A plain dict return achieves the same handler-independence with no
  signature change.
- **Give `journal` and `budget` `tool_fault=TOOL_FAULT`.** Would fix the wording but changes
  tool-error semantics for every other tool in those sub-agents — out of scope for a bug fix.
