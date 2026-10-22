# gh-178-parallel-worker-output-dropped — Implementation Plan

Fix #178: `synthesis_worker` invokes each fanned-out sub-agent synchronously, so any async-only
tool in a batch crashes the whole `tools` node and every call in it is reported to the model as a
false outage. Decision and rejected alternatives: `design.md` (Option A — make the node async).

## 1. Global Constraints

- **The node becomes async-only.** Do not add a sync fallback (`design.md` option B): a second
  execution mode that production never uses is what hid this defect.
- **Do not change which tools are async**, `graceful_fallback`'s message, or the tool-fault policy.
  The fix is the invocation, nothing else.
- **A test that only asserts topology is not a regression test here.** `test_plan_everything.py`
  passes today while the tools node is crashing. Every new assertion must check a tool call's
  *result*, not the shape of the graph.
- **Do not stub the async-ness away.** A stub that replaces an async tool with a sync one recreates
  the blind spot. Where the network must be removed, keep the wrapper async and stub the service
  beneath it (the existing `_stub_weather` pattern is correct on this point).
- Backend commands run from `apps/api/`; this worktree has no `../../.venv`, so use the absolute
  interpreter `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python`.
- Prompt/graph changes are not hot-reloaded; live checks need `docker exec api-api-1 touch app/main.py`,
  and the container bind-mounts the MAIN checkout, not this worktree.

## 2. Scope

**In:** `apps/api/app/agents/subagents/synthesis_worker.py` (the node), and the fan-out tests that
execute it — `tests/agents/test_plan_everything.py`, `test_multi_intent_routing.py`,
`test_ledger_early_exit.py`, `test_task_ledger.py`, `test_specialist_metadata_end_to_end.py`,
`test_tier_gating.py` (only those that actually reach the worker), plus one new regression test.

**Out:** the async-ness of any tool; `app/agents/retry.py`; the supervisor prompt; #179 and #180;
logging the swallowed exception in `graceful_fallback` (recorded as a follow-up, not done here).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | A fanned-out worker's async-only tool call returns real data instead of the outage message | `PYTHONPATH=. VENV/bin/python -m pytest tests/agents/test_fanout_tool_execution.py -q -k async_tool_succeeds` | exit 0 |
| SC-2 | A healthy sync tool batched with an async one is no longer collateral-damaged | `VENV/bin/python -m pytest tests/agents/test_fanout_tool_execution.py -q -k sibling_sync_tool` | exit 0 |
| SC-3 | The worker node is async and awaits the sub-agent | `grep -n "async def worker" apps/api/app/agents/subagents/synthesis_worker.py` | exit 0 |
| SC-4 | No sync invocation of a sub-agent remains in the worker | `grep -c "subagent.invoke(" apps/api/app/agents/subagents/synthesis_worker.py` | exit 1 — no matches |
| SC-5 | The existing fan-out topology and recursion-budget guarantees still hold | `VENV/bin/python -m pytest tests/agents/test_plan_everything.py -q` | exit 0 |
| SC-6 | Every other fan-out test still passes | `VENV/bin/python -m pytest tests/agents -q` | exit 0 |
| SC-7 | The single-specialist path is untouched | `VENV/bin/python -m pytest tests/agents/test_graph.py tests/agents/test_trip_guard.py -q` | exit 0 |

> `VENV` is `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv` — spelled out in each
> command when run; abbreviated here only to keep the table readable.

## 4. Tasks

### Task 1.1 — A failing regression test that proves the defect (wave 1)

- **Files:** apps/api/tests/agents/test_fanout_tool_execution.py
- **Action:** Write the test FIRST, against the unfixed code, and confirm it fails for the right
  reason. Build the real graph, script the supervisor to `plan=["concierge"]`, and script the
  concierge to emit ONE `AIMessage` calling two tools in a single batch: `get_local_tips`
  (synchronous, real, seeded data) and `get_weather` (async-only, its *service* stubbed to a
  deterministic domain error so no network is touched — never stub the wrapper). Drive the parent
  with `asyncio.run(graph.ainvoke(...))`.
  Assert on the `ToolMessage`s the worker's inner sub-agent produced, which the worker does not
  propagate — so capture them by asserting on the specialist's `findings` in `task_results`
  together with a log/handler capture, or by invoking the concierge sub-agent directly for the
  tool-level assertions and using the graph test for the end-to-end shape. Two named tests:
  `test_async_tool_succeeds_in_a_fanned_out_worker` and
  `test_sibling_sync_tool_is_not_collateral_damaged`.
  The pre-fix failure must be the outage message appearing where real data belongs — record that
  exact output in the SUMMARY as the "before" evidence.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes the existing fan-out scaffolding in `tests/agents/test_plan_everything.py`
  (`_AgentAwareLLM`, `agent_db`, `_stub_weather`). Produces `tests/agents/test_fanout_tool_execution.py`.
- **Verify:** `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/agents/test_fanout_tool_execution.py -q`
- **Done:** Both tests FAIL on unmodified code, and the failure text is the `GRACEFUL_MSG` outage string, not an import or fixture error.

### Task 2.1 — Make the worker async (wave 2)

- **Files:** apps/api/app/agents/subagents/synthesis_worker.py
- **Action:** Change `def worker(...)` to `async def worker(...)` and `subagent.invoke(inner_state,
  config=inner_config)` to `await subagent.ainvoke(inner_state, config=inner_config)`. Update the
  builder's return type annotation and the docstrings that describe the node as sync (the module
  docstring and `build_synthesis_worker`'s), saying why it must be async — async-only tools in the
  specialist toolsets, and the parent graph is always driven asynchronously in production. Change
  nothing else: the `deepcopy` isolation, the metadata merge, the changed-key propagation for
  `trip_id`/`awaiting_user`, and the `task_results` shape all stay exactly as they are.
- **Criteria:** SC-3, SC-4, SC-1, SC-2
- **Interfaces:** Consumes the failing tests from Task 1.1. Produces an async
  `app/agents/subagents/synthesis_worker.py`.
- **Verify:** `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/agents/test_fanout_tool_execution.py -q`
- **Done:** Both Task 1.1 tests pass; `grep -c "subagent.invoke(" ...` reports no matches.

### Task 3.1 — Move the fan-out tests onto the async API (wave 3)

- **Files:** apps/api/tests/agents/test_plan_everything.py, apps/api/tests/agents/test_multi_intent_routing.py, apps/api/tests/agents/test_ledger_early_exit.py, apps/api/tests/agents/test_task_ledger.py, apps/api/tests/agents/test_specialist_metadata_end_to_end.py, apps/api/tests/agents/test_tier_gating.py
- **Action:** Run the agents suite first and let the failures name the call sites — a sync
  `graph.invoke` that reaches an async node fails with `TypeError: No synchronous function provided
  to "synthesis_worker"`, so the error is self-identifying. Convert only those call sites to
  `asyncio.run(graph.ainvoke(...))`, leaving every assertion untouched. Do NOT convert tests that
  never fan out; they exercise the sync path deliberately and must keep doing so.
  If `test_plan_everything.py`'s recursion-budget measurement shifts, investigate rather than
  re-baseline the number: the super-step accounting should be identical under `ainvoke`, and a
  change means the fix altered graph behavior, which is out of scope.
- **Criteria:** SC-5, SC-6, SC-7
- **Interfaces:** Consumes the async node from Task 2.1. Produces the converted test modules.
- **Verify:** `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/agents -q`
- **Done:** The whole `tests/agents` suite passes with no assertion weakened or deleted, and the recursion-budget assertion holds at its existing value.

### Task 4.1 — Prove it on the running agent (wave 4)

- **Files:** specs/gh-178-parallel-worker-output-dropped/SUMMARY.md
- **Action:** The offline tests prove the mechanism; only a live turn proves the traveller's
  experience, which is what #178 is about. Merge or otherwise land this branch's code where the
  container can see it (the `api` service bind-mounts the MAIN checkout), run
  `docker exec api-api-1 touch app/main.py`, then send the #173 UAT message
  ("Plan everything for a Tokyo weekend: … local tips …") on a fresh thread and confirm the reply
  contains real local-tips content and no "temporarily unavailable" narration. Record the reply and
  the server trace in the SUMMARY's `### Verify`.
  If the container cannot be pointed at this code without merging, say so in the SUMMARY rather
  than claiming a live check that did not happen.
- **Criteria:** SC-1
- **Interfaces:** Consumes the merged fix. Produces the live evidence rows in `SUMMARY.md`.
- **Verify:** `grep -c "temporarily unavailable" /tmp/gh178-after-reply.txt`
- **Done:** The live reply carries local-tips content; the grep reports no matches; both are recorded in the SUMMARY.

## 5. Rollback

- `git revert <sha>`. The change is one node's invocation mode plus test call sites; reverting
  restores the sync worker exactly.
