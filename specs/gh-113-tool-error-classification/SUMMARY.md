# gh-113-tool-error-classification — Summary

Lane: normal
Confidence: high
Reason: one function's return value, plus tests. No schema, route, auth, or contract change; the
handler keeps catching every exception class it caught before, so the 500-prevention guarantee is
untouched. Root cause was reproduced deterministically before the fix and the change was re-verified
live afterwards.
Flags: existing-behavior, user-facing-copy
Affects: `app/agents/subagents/_base.py` — the tool-error message every sub-agent built by
`build_subagent` relays to the model (planner, concierge, journal, booking, budget).
Input-type: bug report (GitHub #113)
Route: normal → direct implementation on a branch off `main`
Escalate: no

### Intent

> tao issue cho cai trip lookup error do → (#113) → 3. new branch from main and fix it

### Root cause

`_tool_error_to_message` is `ToolNode`'s `handle_tool_errors`. Its `exc: Exception` annotation is
deliberate — it makes `ToolNode` catch *every* tool error so an Open-Meteo timeout cannot propagate
out of `astream` and 500 `/agent/stream`. But the message hardcoded one verdict for all of them:

> This is a temporary upstream problem, not a bad request — do not retry the tool; tell the user the
> information is currently unavailable and to try again shortly.

So a deterministic failure was narrated to the traveller as an outage, with advice that could never
work. `app/agents/retry.py` already models the transient/logic split; this handler flattened it.

The reported symptom also explained the issue's "the error text is empty" observation, and the
explanation changed the fix. Observed message:

```
Tool call failed: Error invoking tool 'get_trip_budget' with kwargs {} with error:

 Please fix the error and try again.. This is a temporary upstream problem …
```

`ToolInvocationError` builds its text from `filtered_errors` — the validation errors **excluding
injected arguments** (`langgraph/prebuilt/tool_node.py`, `_filter_injected_errors`). `get_trip_budget`
takes `trip_id` from `InjectedState`, state `trip_id` was `None`, so the only error was on an injected
arg, langgraph filtered it out, and the list came back empty. The empty body is therefore a **signal**,
not a formatting bug: *nothing the model controls was wrong*.

### What changed

`_tool_error_to_message` now classifies before it narrates. Same breadth, four verdicts:

| Failure | Signal | Message |
|---|---|---|
| Missing injected/runtime arg | `ToolInvocationError` with empty `filtered_errors` | "NOT an outage … retrying will fail identically — ask the traveller for the missing detail, e.g. which trip they mean" |
| Bad model-supplied args | `ToolInvocationError` with `filtered_errors` | "arguments are invalid — fix them and call the tool again" |
| Genuine upstream outage | `__cause__` is `UpstreamError` | unchanged transient wording |
| Deterministic domain error | `__cause__` is another `AppError` | "a definite answer about the data, not an outage … use the hint if there is one" |
| Anything else | — | "cause is unknown — do not claim an outage" |

`__cause__` is reliable here: every tool raises `raise tool_error(e) from e`
(`app/tools/_base.py`), and `tool_error` already folds `AppError.detail` + `hint` into the text, so
the recovery pointer reaches the model on the domain-error branch.

### Scope decision — reversed after review

The issue's third defect (a pre-flight guard for trip-scoped tools) was first deferred on the
argument that the corrected message already produced the required behavior. The PR #116 review was
right that this does not hold: a message is advice, and acceptance criterion 1 of #113 ("asks the
traveller which trip") was therefore left to whether the model obeys prose. One live run behaving
correctly is not an invariant. Implemented — see "Deterministic trip guard" below.

### Deterministic trip guard (#113 acceptance criterion 1)

A `trip_guard` node sits between `assistant` and `tools`. When the model calls a tool whose `trip_id`
comes from `InjectedState` and no trip is active, the call never reaches `ToolNode`: the guard emits a
paired `ToolMessage` per pending call and sets `awaiting_user`, exactly as `needs_clarification` does,
so `dispatch_next` abandons the rest of the turn. The outcome is a graph fact, not an instruction.

Design notes:

- **Which tools need a trip is derived**, by inspecting `InjectedState(field="trip_id")` annotations
  — a new trip-scoped tool is covered when it is written, not when someone remembers a list.
- **Every pending call gets a ToolMessage**, including ones that were not blocked, or the provider
  rejects the next assistant turn on an unpaired tool call.
- **Signatures were not changed.** Making `trip_id` optional and returning a `Command` from each tool
  would have forced an `InjectedToolCallId` parameter onto five tools — and `mcp/server.py` skips any
  tool carrying one, so it would have silently dropped five tools from the MCP surface. That is the
  exact regression fixed on PR #114 as F2; a guard node avoids repeating it.
- **The message never asks for a trip id.** The traveller has never seen one (it is a system UUID),
  so it asks by destination and rough dates and offers to start a new trip, then confirms back before
  acting.

Verified non-vacuous: disabling the guard fails 3 of the 7 tests, including the end-to-end graph test.

### Known limitation — the traveller's trips cannot be listed

The reply asks "which trip do you mean" but cannot offer a list, because **`trips` has no owner**:
the table has no `user_id` column and `TripRepository.list_trips()` returns every trip in the
database. Listing them would expose other travellers' trips. The only user↔trip link that exists is
`conversations.user_id` + `conversations.trip_id`.

That blocks the richer flow requested (show the traveller their trips, confirm details, identify them
by a short human-readable code): a code would label globally-visible rows, which is not the same
feature. Trip ownership is a schema change and a data-exposure question — out of scope here, filed
separately.

### PR review follow-up (Codex, PR #116)

**F5 (P2) — the `ToolFaultPolicy` path never reached the new classifier. Confirmed and fixed.**
`planner.py` and `concierge.py` pass `tool_fault=TOOL_FAULT`, so `build_subagent` installs
`retry._tool_error_logic_only` instead of `_tool_error_to_message`. The planner binds
`get_trip_budget`, `get_trip_summary`, `list_trip_places` and other `InjectedState` tools, so the
exact #113 failure routed through the planner still answered "check the arguments and try a corrected
call" — asking the model to supply something it cannot reach. The first fix covered 3 of 5
sub-agents.

Fix: the classification moved to `retry.describe_tool_failure()`, the single source of truth both
hooks delegate to. Each hook keeps its own annotation (and therefore its own catch set — `Exception`
vs `ToolException`, which is what lets `UpstreamError` still reach the `RetryPolicy`); only the
wording is shared. The tests now parametrize every shared case over both hooks, which is what makes
this class of miss impossible to reintroduce.

Worth recording: this gap was named in the issue text ("even `retry.py`'s wording would be wrong
here") and still shipped unfixed — writing a risk down is not the same as covering it.

### Second review round (deep review, this branch)

**F1 (P2) — a causeless `ToolException` was filed as "cause unknown". Confirmed and fixed.**
Nine real raise sites (`date_tools`, `flight_tools` ×3, `hotel_tools` ×2, `booking_tools` ×2,
`tip_tools`) use `raise ToolException(...)` with no `from`, so `__cause__` is `None`. The classifier
sniffs `__cause__` only, so all nine fell through to *"the cause is unknown — do not retry blindly"*.
That contradicts the message being wrapped: several name the exact correction to make (`date_tools`
says "call the resolve_date tool"). It was also a **regression on the `ToolFaultPolicy` path**, which
previously answered "check the arguments and try a corrected call" — correct for this class.
Fix: a `ToolException` branch before the unknown fallback, treating the tool's own message as the
recovery it is.

**F2 (P3, latent) — a bare `UpstreamError` was filed as "cause unknown". Confirmed and fixed.**
`weather_tools`, `routing_tools` and `climate_tools` re-raise `UpstreamError` untouched
(`raise  # transient — let RetryPolicy retry the node`), so it arrives with no `__cause__`. Classifying
on `__cause__` alone broke acceptance criterion 2 (a genuine upstream failure must still read as
transient) for the catch-all hook. Not reachable today — every sub-agent holding an upstream-capable
tool (planner, concierge) has a `ToolFaultPolicy`, so the error reaches `RetryPolicy` instead — but the
catch-all is the documented backstop for *every* tool error, so it must classify this on its own.
Fix: `isinstance(exc, UpstreamError)` alongside the cause check.

**F3 (P4) — dead parameter. Fixed.** `_make_trip_guard(tools, needing_trip)` never used `tools`; the
docstring said so. Removed, with its four test call sites.

**Scope probes that came back clean (recorded so they are not re-litigated):** hardcoding `trip_id`
in the guard is *not* an over-narrow special case — it is the only nullable `InjectedState` field
(`user_id` is always set by `_turn_input` in `app/routers/agent.py`; `preferences` has defaults), so a
general "any missing injected field" mechanism would be speculative. Deriving the tool set from
annotations rather than a hardcoded list is likewise justified and tested.

**F4 (P3) — the guard failed open with no log. Fixed.** `_tools_needing_trip` swallowed
introspection failures, so any tool it could not read was silently dropped from the guard. Found the
hard way: a UAT probe that monkeypatched `tool.func` stripped the annotations and disabled the guard
under test, producing a convincing false failure with nothing in the logs to say so. It now warns,
naming the tool and stating that it will not be blocked.

Two details worth recording, because the obvious implementations are both wrong:

- The alarm fires on **zero readable type hints**, covering both shapes — annotations that will not
  resolve (a wrapper carries the strings but not the globals defining them) and annotations lost
  entirely (a plain wrapper). The first raises; the second returns `{}` and would otherwise stay
  silent, and it is the one that actually bit the UAT.
- It deliberately does **not** gate on `tool.args`. langchain hides injected params from `.args`, so
  it is empty for exactly the four trip-scoped tools the guard exists to protect
  (`get_trip_summary`, `get_trip_budget`, `list_trip_places`, `list_place_categories`) — gating on it
  would silence the alarm precisely where it matters. A first cut did this and the test caught it.

`test_every_registered_tool_is_introspectable` pins the invariant that keeps "no hints" free of false
positives: all 33 registered tools currently have readable hints.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| New classification tests | `pytest tests/agents/test_tool_error_classification.py -q` | 0 | 23 passed — one per failure class × both `handle_tool_errors` hooks (16 before the second round; +7 for the two classes F1/F2 uncovered) |
| Trip guard tests | `pytest tests/agents/test_trip_guard.py -q` | 0 | 7 passed; 3 fail with the guard disabled |
| All agent tests (after F3/F4) | `pytest tests/agents/ -q` | 0 | 276 passed — confirms dropping the dead `tools` param broke no call site, and covers the F4 warning (both fail-open shapes + the no-false-alarm case) |
| Full suite, second round | `pytest -q` (from `apps/api/`) | 1 | 1824 passed, 12 failed — **the same 12 fail on this branch before these changes** (1814 passed / 12 failed), so the delta is exactly the 10 new tests (7 classification + 3 fail-open). All 12 are `.env`-induced (real `OPENAI_API_KEY`/`ORS_API_KEY`/JWT issuer) or a stale hardcoded date in `test_preference_ranking`; **none is under `tests/agents/`**. |
| UAT-1 — issue repro, offline | `scratchpad/uat1.py` (real compiled `budget` graph, FakeLLM, `trip_id=None`) | 0 | tool never executed, `awaiting_user=True`, model received `NO_ACTIVE_TRIP_MSG`, zero outage language |
| UAT-2 — issue repro, live LLM | `POST localhost:8000/agent/chat` `{"message":"Break down my Tokyo trip expenses so far","trip_id":null}` | 0 | reply: *"I'm missing the trip record to read from … Which **Tokyo** trip do you mean — and what are the **rough dates**? If you don't have a trip set up yet, I can help you start one."* — the false-outage claim is gone |
| UAT-3 — criteria 2 & 3, catch-all path | `scratchpad/uat2.py` (sub-agent with no `ToolFaultPolicy`) | 0 | bare `UpstreamError` → transient message (F2); causeless `ToolException` → keeps its own `resolve_date` recovery text, no outage claim (F1); no exception escaped the graph (no 500) |
| Full backend suite | `DATABASE_URL=sqlite:///<tmp> pytest tests/ -q` | 1 | 1821 passed, 5 failed — the **same 5** fail on unmodified `main` (`.env` supplies real `OPENAI_API_KEY`/`ORS_API_KEY`/Langfuse values, defeating "no key configured" assertions). They pass when run from a directory without `.env`. |
| Live behavior, real LLM | `scratchpad/repro_trip_lookup.py` (budget question, `trip_id=None`) | 0 | reply is now *"I couldn't find a trip record for **Tokyo** … if your trip is stored under a different name or ID, send that"* — before it was *"the budget service is temporarily unavailable … try again shortly"* |
| Lint | `ruff check app scripts` | 0 | clean |
| Format | `ruff format` on changed files | 0 | unchanged |

**Verification gap — narrowed in the second round.** The first live re-run took a different tool path
than the original repro (the model called `expense_summary(trip_id="Tokyo")`, exercising the
**AppError/NotFound** branch rather than the **injected-arg** one), so that branch was unit-tested
only. UAT-1 now closes it deterministically: it drives the **real compiled `budget` graph** with a
scripted `get_trip_budget` call and `trip_id=None`, and asserts the tool never executes,
`awaiting_user` is set, and the model receives `NO_ACTIVE_TRIP_MSG` — no dependence on which tool a
live model happens to pick. What remains model-dependent is only *which* tool it reaches for; every
branch it can land on is covered, and none of them claims a false outage.

### Rollback

- `git revert <sha>` — pure message-content change, no state or schema involved.

### Harness-Delta

- none.
