<!--
  Canonical SUMMARY.md shape (templates/SUMMARY.template.md). Header block is machine-read:
  hooks/risk-corroboration.sh greps `Lane:`; the trust-metrics ledger reads Lane/Confidence/Flags.
-->

# gh-178-parallel-worker-output-dropped — Summary

Lane: high-risk
Confidence: high
Reason: no manifest hard gate in the *declared* scope, but 4+ risk flags — existing behavior (the turn-completion path every multi-intent turn passes through), multi-domain (supervisor fan-out, synthesis_worker, synthesize, reflection's awaiting_user guard), weak proof (the live symptom is LLM-mediated and was observed once), and remove-functionality risk (the `awaiting_user` early exit is a deliberate MIN-68/#99 guard — weakening it re-opens the bug it was added to fix).
Flags: existing behavior, multi-domain, weak proof, remove-functionality risk
Affects: apps/api/app/agents/subagents/synthesis_worker.py (the node's invocation mode) and the fan-out tests that execute it
Input-type: change request (bug #178, found by UAT while verifying #173)
Route: high-risk — worktree `.worktrees/fix/gh-178-parallel-worker-output-dropped` → xia2 (Deep) → design.md (a real fork exists) → writing-plans → subagent-driven-development.
Escalate: no — the direction is not ambiguous. Confidence was raised `medium` → `high` once the mechanism was proven: a deterministic reproduction refuted the diagnosis this spec was opened with and identified the real one (see below).

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> fix cho issue 178 di

Issue #178 (verbatim title): "Agent: a clarification early-exit discards the parallel worker's finished output (traveller loses the concierge answer)". It reports that on a fanned-out turn the concierge completes and calls `get_local_tips`, then the planner's `needs_clarification` ends the turn via `awaiting_user` and the concierge's output never reaches the traveller.

## What changed

`synthesis_worker`'s node is now **async** and awaits the specialist sub-agent
(`await subagent.ainvoke(...)` in place of `subagent.invoke(...)`). Nothing else about the worker
moved: the deep-copy isolation, the metadata merge, the changed-key propagation of
`trip_id`/`awaiting_user`, and the `task_results` shape are untouched.

Six agent tools are `async def` — `get_weather`, `get_packing`, `get_air_quality`, `get_climate`,
`get_route`, `get_city_route` — and both the planner and the concierge bind all six. Under the old
sync invocation the first such call raised `NotImplementedError: StructuredTool does not support
sync invocation`, which killed the entire `tools` node, so `TOOL_FAULT`'s `graceful_fallback`
handed the model a "temporarily unavailable" message for **every** call in that batch, healthy
synchronous siblings included. The specialist then reported a false outage that retrying
reproduced identically.

The fan-out tests that execute the node moved onto the async API via a small `_drive()` helper per
module; no assertion was changed, weakened, or removed.

**The eval harness drove the graph synchronously too** (`eval/adapters/langgraph_runner.py`), so it
had to move as well. That is a second, larger consequence: every multi-intent golden the eval suite
has ever scored ran on the broken path, where one async tool took its whole batch down and the
specialist reported a false outage. The committed baseline's fan-out numbers were measured there.
`asyncio.run` is the right tool in that one place and not inside the graph — the eval CLI is a
batch entry point with no enclosing event loop, which is exactly the condition `design.md` option C
could not satisfy.

### The diagnosis this spec opened with was WRONG — and was refuted before any code was written

I wrote #178 myself from one UAT trace. This intake recorded doubt about its stated mechanism
before implementing anything; the doubt was justified, and the issue has since been rewritten. The
original reasoning is kept below because the correction is the useful part of this record:

- **`synthesize` may well have run.** `reflection`'s `awaiting_user` guard
  (`nodes.py:231`) returns `Command(goto=END)` — but reflection runs *after* `synthesize`, so it
  cannot be what drops a worker's findings. `synthesize` (`nodes.py:179-203`) reads
  `state["task_results"]`, which both workers write. There is no code path I have found that
  discards `task_results` on the `awaiting_user` flag.
- **The observed reply reads like `synthesize` with an empty finding**, not like a discarded one.
  Its system prompt says *"If the findings are empty or unhelpful, say you are still looking into
  it"*, and the reply said *"the live trip data is currently unavailable, so I can't reliably check
  flights, hotels, weather, or local tips right now"* — a combined answer covering both workers'
  topics, with the concierge half empty.
- **`NO_ACTIVE_TRIP_MSG` is a strong suspect** (`constants.py:89-95`). `trip_guard`
  (`_base.py:131-166`) blocks *every* pending call — including the ones that did not need a trip —
  when a trip-scoped tool is called with no active trip, sets `awaiting_user`, and returns
  ToolMessages. That message states *"This is NOT an outage and retrying will fail identically"*,
  and the agent narrated exactly the outage misreading the message tries to prevent.
- Since no `trip_id` existed on that thread, a trip-scoped call from either worker would trip it.

**How it was resolved.** A deterministic reproduction — planner scripted to end on
`needs_clarification`, concierge scripted to return prose — printed the end-of-turn state:

```
awaiting_user: True
task_results: [{'agent': 'planner',   'findings': 'Which dates do you want ...'},
               {'agent': 'concierge', 'findings': 'Local tip: grab a Suica card ...'}]
synthesize called: 1 time — its prompt contained both findings
```

Nothing was discarded. The concierge's findings *were* delivered; they just said the data could not
be retrieved. Logging the exception that `graceful_fallback` swallows then gave the real cause in
one line — `NotImplementedError: StructuredTool does not support sync invocation` — and the
sync-vs-async table below settled it.

### Rationale

Lane `high-risk`: the change lands on the path every multi-intent turn takes, and the most obvious
"fix" (letting the turn continue past `awaiting_user`) would weaken a guard added deliberately in
MIN-68/#99 to stop reflection from re-running a sub-agent that is waiting on the traveller. That is
a remove-functionality risk, so it gets the full ceremony and a design fork written down.

### Alternatives considered

- Implementing the issue's suggested direction directly ("synthesize what finished alongside the
  clarification question") — rejected as premature: it presumes the mechanism this intake could not
  confirm. It stays a candidate for `design.md` once the reproduction says which mechanism is real.

### Deviations

- **Rule 3 (auto-fix blocking) — scope extended to `eval/`:** PLAN §2 listed `eval/` under "Out",
  but making the node async broke `eval/adapters/langgraph_runner.py`, which drove the graph with
  `graph.invoke`. The full suite caught it as a single failure
  (`tests/eval/test_langgraph_runner.py::test_run_meta_records_tasks_and_suggestions`). Fixed by
  routing its two call sites through an `asyncio.run(self._graph.ainvoke(...))` helper. Extending
  scope was not optional: leaving it would have shipped a broken eval harness.
- **Rule 3 (auto-fix blocking):** `ruff check --fix`/`ruff format` were invoked over all of
  `app tests` rather than the changed files, modifying 18 unrelated files. Caught by `git status`
  before commit and reverted; the in-scope files were reformatted individually. Recorded because the
  mistake was mine and the revert is the only reason the diff is clean.
- **Process:** the scratch reproduction (`tests/agents/test_gh178_repro.py`) was written to settle
  the diagnosis and deleted once `test_fanout_tool_execution.py` superseded it. It is not in the
  diff.
- **Environment:** this worktree was relocated mid-task (from `.worktrees/fix/...` to a sibling
  directory) by another session; the branch and all uncommitted work survived intact.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| reflection's `awaiting_user` guard runs after synthesize, so it cannot drop task_results | `sed -n '225,235p' apps/api/app/agents/nodes.py` | 0 | the guard is inside `make_reflection_node`, and `synthesize` is a separate earlier node | |
| synthesize reads task_results unconditionally | `sed -n '179,203p' apps/api/app/agents/nodes.py` | 0 | no `awaiting_user` branch in the node | |
| the worker propagates awaiting_user to the parent | `sed -n '110,125p' apps/api/app/agents/subagents/synthesis_worker.py` | 0 | only `trip_id` and `awaiting_user` cross back; `task_results` always written | |
| trip_guard abandons the whole batch and sets awaiting_user | `sed -n '131,167p' apps/api/app/agents/subagents/_base.py` | 0 | blocked and unblocked calls alike get an error ToolMessage | |
| the no-trip message forbids the outage reading the agent used | `sed -n '89,96p' apps/api/app/agents/constants.py` | 0 | "This is NOT an outage and retrying will fail identically" | |
| the container was serving v11, so one re-run observation was void | `docker exec api-api-1 grep supervisor app/prompts/active.yaml` | 0 | `supervisor: 11` — the main checkout is pinned pre-#176 by another session's untracked files | |

| the sync path fails and the async path succeeds, same sub-agent, same batch | scripted the concierge to call `get_local_tips` + `get_weather` in one batch, then compared `subagent.invoke(state)` with `await subagent.ainvoke(state)` | 0 | sync: both `status=error` "temporarily unavailable"; async: both `status=success`, 8 real tips and a real forecast | |
| the regression tests fail on unmodified code, for the right reason | `python -m pytest tests/agents/test_fanout_tool_execution.py -q` (before Task 2.1) | 1 | both failed on `GRACEFUL_MSG` appearing where real data belongs — not on an import or fixture error. This is the "before" evidence; the passing runs are the two rows below | |
| the async-only tool now reaches its own body | `python -m pytest tests/agents/test_fanout_tool_execution.py -q -k async_tool_succeeds` | 0 | was red on unmodified code with `GRACEFUL_MSG` | SC-1 |
| a healthy sync tool batched with it is no longer collateral-damaged | `python -m pytest tests/agents/test_fanout_tool_execution.py -q -k sibling_sync_tool` | 0 | returns real seeded tips instead of the outage message | SC-2 |
| the worker node is async | `grep -n "async def worker" app/agents/subagents/synthesis_worker.py` | 0 | | SC-3 |
| no sync sub-agent invocation remains | `grep -c "subagent.invoke(" app/agents/subagents/synthesis_worker.py` | 1 | exit 1 = no matches, which is the pass condition for this row | SC-4 |
| the fan-out topology and recursion-budget guarantees still hold | `python -m pytest tests/agents/test_plan_everything.py -q` | 0 | 2 passed; the recursion-budget assertion holds at its existing value under `ainvoke` | SC-5 |
| the whole agents suite passes, assertions intact | `python -m pytest tests/agents -q` | 0 | 409 passed | SC-6 |
| the single-specialist path is untouched | `python -m pytest tests/agents/test_graph.py tests/agents/test_trip_guard.py -q` | 0 | 16 passed | SC-7 |
| the full backend suite passes | `DATABASE_URL=sqlite:///<tmp> python -m pytest tests -q` | 0 | 2372 passed, 0 failed, in 3m15s | |
| the eval harness still runs its own suite | `python -m pytest tests/eval -q` | 0 | 160 passed | |
| lint on the touched files | `ruff check` over the 9 changed files | 0 | All checks passed | |
| no lint regression tree-wide | `ruff check app tests --output-format concise` | 1 | 11 errors — the same count `main` reports; all pre-existing | |

### Not auto-verified

- **Every past eval number for a fan-out golden was measured on the broken path.** This change
  makes the eval measure what the API serves, so re-running it after merge will produce *different*
  numbers, and those will be the trustworthy ones. No claim is made here about which goldens move
  or by how much — that is a measurement, and it has not been run. It may bear on the open
  rubric failures in #154; it does not invalidate #173's conclusion, which rests on
  `tasks_expected` (the supervisor's task list) rather than on tool content.
- **No live check has been run yet.** Everything above is offline. The traveller-facing claim —
  that the reply now carries real local tips — is Task 4.1 and is NOT yet done, because the `api`
  container bind-mounts the MAIN checkout, not this worktree, so the fix cannot reach the running
  agent until it lands there. Reached *truth* for the mechanism, *nothing* for the user experience.
- **The recursion-budget assertion in `test_plan_everything.py` was re-run, not re-baselined**, and
  it holds at its existing value under `ainvoke`. No claim is made that super-step accounting is
  *provably* identical — only that the existing assertion still passes.
- **`ruff check --fix` and `ruff format` were run tree-wide by mistake** and touched 18 files
  outside the declared scope. Those were reverted with `git checkout --`, and the tree-wide lint
  count returned to `main`'s 11. The revert is verified by `git status`, not by re-reading each
  file.

### Rollback

- `git revert <sha>`. The change is one node's invocation mode plus the test call sites that drive
  it; reverting restores the sync worker exactly. There is no data, schema, or contract change.

### Harness-Delta

- backlog → `compound`, two learnings, both earned the hard way here:
  1. **`graceful_fallback` discards the exception it is handling** and substitutes a message that
     *asserts* an outage. That single missing log line is why this looked like an infrastructure
     problem for hours and why the first diagnosis was wrong. Logging the cause there is a small,
     high-value change and is filed as a follow-up rather than bundled into this fix.
  2. **A test that asserts topology is not a regression test for behavior.**
     `test_plan_everything.py` exercised exactly this path and passed for months while the tools
     node crashed underneath it, because it asserted the task list and the recursion budget and
     never that a tool call returned data. The related trap: its `get_weather` stub replaces the
     *service*, which is correct — replacing the async *wrapper* with a sync stub would have made
     the suite green against the very defect under test.
