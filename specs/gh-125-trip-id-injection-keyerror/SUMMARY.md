# gh-125-trip-id-injection-keyerror — Summary

Lane: normal
Confidence: medium
Reason: Two risk flags fired (existing behavior — the fix must not reintroduce `specs/fix-trip-id-persist-across-turns`; public contract — `/agent/chat` client-visible behavior on a trip-less turn changes from an error fallback to a real reply). No manifest hard gate fires at intake: no auth/authorization, no schema or migration, no external provider, no route/method/envelope change, no high-blast file. Multi-file (router + tools + tests) so `tiny` is not available.
Flags: existing-behavior, public-contract (behavioral only — no route/method/envelope change)
Affects: apps/api/app/routers/agent.py (`_turn_input`), apps/api/app/tools/trip_tools.py (5 trip-scoped tools), apps/api/app/agents/state.py (`TravelAgentState.trip_id`)
Input-type: change request
Route: brainstorming (design fork) → xia2 (Standard depth) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (normal lane + medium confidence → notify-and-proceed; no hard gate at intake)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

GitHub issue https://github.com/minhtran3124/travel-pi/issues/125 —
**bug(agent): KeyError: 'trip_id' crashes any trip-scoped tool when the conversation has no trip**

## Summary

Any chat turn that routes to a trip-scoped tool crashes with `KeyError: 'trip_id'` when the
conversation has no active trip. The user sees the generic error fallback
*"I ran into a problem handling that request and couldn't finish my reply. Please try again in a moment."*

This is reproducible on `main` (`0947d27`) and is independent of PR #123 — see **Attribution** below.

## Reproduce

Signed in on http://localhost:3000/trips (the trip *list* page, so the client sends `trip_id: null`),
send any message whose intent routes to a trip tool, e.g. `Please send my itinerary`.

Or straight against the API, no auth needed:

```bash
curl -s -X POST http://localhost:8000/agent/chat -H 'Content-Type: application/json' \
  -d '{"message":"Please send my itinerary","user_id":"repro","conversation_id":null,"trip_id":null}'
```

**Expected:** the agent asks which trip is meant, or answers without the tool.
**Actual:** error fallback in the reply, and this in the API log:

```
File "langgraph/prebuilt/tool_node.py", line 1397, in _inject_tool_args
    raise KeyError(state_field)
KeyError: 'trip_id'
```

## Cause

Two deliberate decisions collide when there is no trip in the conversation:

1. `apps/api/app/routers/agent.py:155` — `_turn_input()` omits `trip_id` from the graph input when
   the client sends `null`. That is intentional (`specs/fix-trip-id-persist-across-turns`):
   `TravelAgentState.trip_id` has no reducer, so passing an explicit `None` would clobber a
   `trip_id` that the `create_trip` tool set mid-conversation.

2. `apps/api/app/tools/trip_tools.py` — five tools take `trip_id: Annotated[str, InjectedState("trip_id")]`:
   `get_trip_summary` (:49), `get_trip_budget` (:79), `list_trip_places` (:107),
   `add_place_to_trip` (:138), `add_itinerary_item` (:181).

`TravelAgentState.trip_id` is declared `str | None` (`apps/api/app/agents/state.py:94`) but a
LangGraph channel only exists once something writes it. On a fresh conversation with `trip_id: null`
nothing ever does, so `InjectedState("trip_id")` looks up a missing key and `_inject_tool_args`
raises `KeyError` instead of injecting `None`.

The state type says the value is nullable, but the injection path has no way to express "absent".

## Impact

- Every trip-scoped intent is broken from `/trips`, `/places`, `/bookings` and any new conversation —
  i.e. the default entry point, since a conversation only gets a `trip_id` after `create_trip` runs.
- The failure surfaces as a generic fallback, so it reads as a flaky model rather than a crash.
- It escapes the sub-agent tool-error self-correction: the `KeyError` is raised during argument
  injection, before the tool body runs, so it is not classified as a recoverable tool error.

## Possible directions

Not prescribing a fix, but the options seem to be:

1. Seed the channel once per conversation (e.g. write `trip_id: None` on the first turn only) so the
   key always exists while keeping the clobber protection for later turns.
2. Give the supervisor a trip-resolution step so a trip-scoped tool is never called without a trip.
3. Make the tools tolerate absence and return a "which trip?" tool error the sub-agent can recover from.

Option 1 is the smallest, but note it must not reintroduce `specs/fix-trip-id-persist-across-turns`.

## Attribution — not caused by PR #123

Found during UAT of #123 (PII guardrail); verified it is pre-existing:

1. #123's diff to `routers/agent.py` only swaps the message argument. It does not touch the
   `if trip_id is not None` conditional, the tools, or the state.
2. A **PII-free** message reproduces it on the #123 branch.
3. With the API restored to the `main` checkout (`app/agents/guardrails.py` absent, confirmed), the
   same PII-free request reproduces the same fallback and the same `KeyError`.

## Environment

- `main` @ `0947d27`
- langgraph `1.2.11`, Python 3.12 (Docker), Postgres 17 (pgvector)


## What changed

The five trip-scoped tools in `apps/api/app/tools/trip_tools.py` now declare `trip_id` as an
optional injected argument (`str | None = None`) and, when it is absent, return a guidance dict
naming `no_active_trip` before any DB session is opened. A conversation with no active trip — the
default entry point, since a conversation only gains a `trip_id` after `create_trip` runs — gets a
real reply asking which trip is meant instead of `KeyError: 'trip_id'` behind the generic error
fallback. No other source file changed.

### Rationale

LangGraph already tolerates a missing injected-state key, but only for parameters whose pydantic
field is not required (`tool_node.py:1394-1397` selecting on `_optional_state_args`, built at
`:2008-2012` from `not field_info.is_required()`). The five tools declared `trip_id` required and
so opted out of a tolerance that already existed — which is why the fix needs neither a router
change nor state seeding, and why `_turn_input()` stays untouched, making a regression of
`specs/fix-trip-id-persist-across-turns` structurally impossible.

The guidance is an ordinary return value rather than a raised `ToolException` because these tools
are bound by three sub-agents with two different `handle_tool_errors`: `planner` uses
`_tool_error_logic_only`, while `journal` and `budget` use the default `_tool_error_to_message`,
which relabels any raised error as a temporary upstream problem. The issue's own repro routes to
`journal`, so a raise would have fixed the crash and still told the traveller the system was down.
A plain return never reaches `handle_tool_errors`, so all three sub-agents relay identical wording.

### Alternatives considered

- **`Command` + `ToolMessage`, mirroring `create_trip`'s anonymous refusal.** Chosen first, then
  rejected on evidence: it needs an `InjectedToolCallId` parameter, and `app/mcp/server.py:39-40`
  skips any tool carrying one — it would have removed all five tools from the MCP server.
  `tests/mcp/test_mcp_server.py:50` pins that boundary, so `create_trip` is not a precedent for
  shipping a `Command` over MCP; it is the evidence that you cannot.
- **Seeding the `trip_id` channel in `load_context_node`.** Unnecessary once the tool signature
  expresses the same thing; held as the fallback had SC-6 failed on langgraph 1.2.11.
- **A supervisor trip-resolution step (issue option 2).** Largest diff, changes routing for every
  trip-scoped intent, and does not fix the direct/MCP call path.
- **Giving `journal` and `budget` `tool_fault=TOOL_FAULT`.** Would fix the wording but change
  tool-error semantics for every other tool those sub-agents bind.

### Deviations

- Isolation — used an in-place branch (`git switch -c`) instead of a linked worktree under
  `.worktrees/`. `using-git-worktrees` prefers a native worktree, but the harness-deploy step it
  names (`scripts/deploy-harness.sh`) does not exist in this repo and `.claude/` is untracked, so a
  fresh worktree would have run with every hook and gate silently absent. Branch isolation per
  `rules/auto-correct-scope.md` is satisfied either way.
- No Rule 1-3 auto-fixes were needed in either implementation task.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Absent trip channel returns guidance, not KeyError | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q` | 0 | 16 passed. Run from `apps/api/`. | SC-1 |
| Guidance survives a handler that relabels errors as an outage | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q -k handler_independent` | 0 | 5 passed, 11 deselected. | SC-2 |
| `trip_id` stays out of every model-facing schema | `../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q` | 0 | 49 passed. | SC-3 |
| All five trip tools stay exposed over MCP | `../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q` | 0 | 5 passed. | SC-4 |
| Existing trip-tool happy paths unchanged | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q` | 0 | 14 passed. | SC-5 |
| Tolerance holds on the Docker stack | `docker compose exec -T api python -m pytest tests/tools/test_trip_tools_no_active_trip.py -q` | 0 | 16 passed on Python 3.12.14 / langgraph 1.2.11 — the exact stack the issue reports. Closes the research brief's evidence gap. | SC-6 |
| The issue's own end-to-end repro | `curl -s -X POST http://localhost:8000/agent/chat -H 'Content-Type: application/json' -d '{"message":"Please send my itinerary","user_id":"repro-gh125","conversation_id":null,"trip_id":null}'` | 0 | Reply: *"I can send it, but I don't have an active trip loaded for this chat yet. Which trip do you mean?"*, `current_flow: "journal"`. API log shows `journal → tools (1 call(s))` and zero `KeyError`. | |
| Pre-existing failures are not mine | `../../.venv/bin/python -m pytest tests/tools/test_routing_tools.py -q` | 1 | 2 failed (`*_offline_estimate`, network-dependent). Reproduced identically with `trip_tools.py` reverted to base `76a68ae`, so they pre-date this branch. | |

### Not auto-verified

- **The optional-injected-state tolerance is an undocumented library internal.** `_optional_state_args`
  is private and the official docs describe `ToolRuntime`, not defaulted `InjectedState`. Reached
  **truth** on langgraph 1.2.6 and 1.2.11 by execution, but the pin is `>=1.0,<2.0`, so a future
  minor bump inside that range is not covered. `tests/tools/test_trip_tools_no_active_trip.py` is
  the tripwire.
- **Full-suite parity.** Only the four affected modules plus `test_routing_tools.py` were re-run;
  the whole suite runs at `finishing-a-development-branch` and in CI.
- **Minor (task 1.1 review):** post-fix, the handler-independence assertion is weakly
  discriminating in isolation — any successful non-error return satisfies it. It retains its value
  as a guard against the rejected `raise ToolException` design, which is what it was specified for.
- **Minor (found during the live repro):** the guard sits above `log_tool_call`, so a trip-less
  tool call now leaves no `[tool]` log line at all. Confirmed in the container: `journal → tools
  (1 call(s))` appears with no corresponding `[tool]` entry. The path is therefore not observable
  in production logs. Left as-is to keep the diff surgical; worth a follow-up if the frequency of
  this path ever needs measuring.

### Rollback

- `git revert 3616338` — reverts the fix only.
- `git revert 3616338 a5c48ca` — reverts the fix and its regression tests.

### Harness-Delta

- `backlog` — `brainstorming/references/spec-review-loop.md` and
  `writing-plans/references/review-loop.md` both dispatch a reviewer prompt file
  (`spec-document-reviewer-prompt.md`, `plan-document-reviewer-prompt.md`) that does not exist in
  either `references/` directory. Both review gates are unrunnable as written.
- `backlog` — the `reviewer` and `task-reviewer` agent bindings have no `SendMessage` tool, so they
  cannot return a verdict to the controller; three dispatches went idle with no result. Per-task
  review had to be re-dispatched through a general-purpose agent to restore the return path.
- `backlog` — `commit-quality-gate.sh` Check 1.6 fires on any staged `specs/<slug>/` file and
  demands full SC coverage in `SUMMARY.md`, so a `PLAN.md` carrying an SC table cannot be committed
  until every criterion already passes. The plan is therefore absent from git for the whole time it
  is being executed, and all spec artifacts are forced into one final commit.
- `backlog` — `using-git-worktrees` instructs `bash scripts/deploy-harness.sh`, which does not
  exist here; with `.claude/` untracked, following the skill literally produces a worktree with no
  hooks, skills, or gates.
