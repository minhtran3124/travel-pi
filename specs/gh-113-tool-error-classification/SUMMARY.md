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

### Scope decision

The issue listed a third defect — "no `trip_id` selected" should be handled by a pre-flight guard on
trip-scoped tools. **Not implemented, deliberately.** The classification above already produces the
required user-visible behavior (the agent asks which trip instead of claiming an outage) without a
second mechanism to keep in sync with the tool inventory. A pre-flight guard is worth revisiting only
if the model turns out to ignore the message.

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

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| New classification tests | `pytest tests/agents/test_tool_error_classification.py -q` | 0 | 15 passed — one per failure class × both `handle_tool_errors` hooks |
| Full backend suite | `DATABASE_URL=sqlite:///<tmp> pytest tests/ -q` | 1 | 1813 passed, 5 failed — the **same 5** fail on unmodified `main` (`.env` supplies real `OPENAI_API_KEY`/`ORS_API_KEY`/Langfuse values, defeating "no key configured" assertions). They pass when run from a directory without `.env`. |
| Live behavior, real LLM | `scratchpad/repro_trip_lookup.py` (budget question, `trip_id=None`) | 0 | reply is now *"I couldn't find a trip record for **Tokyo** … if your trip is stored under a different name or ID, send that"* — before it was *"the budget service is temporarily unavailable … try again shortly"* |
| Lint | `ruff check app scripts` | 0 | clean |
| Format | `ruff format` on changed files | 0 | unchanged |

**Verification gap, stated plainly:** the live re-run took a different tool path than the original
repro — the model called `expense_summary(trip_id="Tokyo")`, so it exercised the **AppError/NotFound**
branch, not the **injected-arg** branch. Which tool the model picks is not reproducible on demand, so
the injected-arg branch is covered by unit test only. Both branches now avoid the false outage claim,
which is the defect being fixed.

### Rollback

- `git revert <sha>` — pure message-content change, no state or schema involved.

### Harness-Delta

- none.
