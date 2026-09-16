# rag-tool-output-wrapping — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: task 2.1 implementer (in-flight, "the plan itself is wrong")
- date: 2026-09-16
- trigger: hard-gate — the approved design's chosen seam breaks existing production fault tolerance
- question: Which seam labels tool output, now that langgraph's `wrap_tool_call` hook is proven to defeat `TRANSIENT_RETRY` + `graceful_fallback` for the two specialists that do real external I/O?
- context: |
  Design D1 chose `ToolNode(wrap_tool_call=…, awrap_tool_call=…)`, and design §4 asserted that
  guarding only the transform (never `execute`) preserves `graceful_fallback`. That assertion is
  false for langgraph 1.2.6.

  `_execute_tool_sync` gates its `except Exception` on the handled types derived from
  `handle_tool_errors` and re-raises anything outside them (`tool_node.py:982-1012`) — that re-raise
  is what lets `RetryPolicy` see a transient fault. The **wrapper** path has no such gate: it
  catches every exception and converts it straight to a `status="error"` message
  (`tool_node.py:1053-1067` sync, `:1205-1222` async; the `except GraphBubbleUp: raise` clause
  exists only at `:982` and `:1129`, not on the wrapper path). So with the hook wired,
  `_tool_error_logic_only` stops narrowing anything: a transient error is swallowed on the first
  attempt, `TRANSIENT_RETRY` never retries, and `graceful_fallback` never receives a `NodeError`.

  Measured, not inferred — with the hook wired:
  `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_fault_tolerance.py -q`
  → 2 failed, 2 passed; `test_tools_node_retries_then_succeeds` fails `assert 1 == 3` (the flaky
  tool ran once instead of three times) and `test_tools_node_graceful_after_exhaustion` fails with it.

  Affected specialists: planner and concierge (`planner.py:27`, `concierge.py:27`, both
  `tool_fault=TOOL_FAULT`) — which are exactly the two that call real external I/O (weather,
  routing), i.e. the highest-value injection surface in the spec.

  No fix exists inside the hook: any exception the hook re-raises is caught by langgraph's own
  unguarded `except`.
- options:
  - A) Insert a `label_tools` node between `tools` and `assistant` and drop the hook. The transform runs on state after the node has already succeeded, so the exception path is untouched and retry + `graceful_fallback` keep working. Uses the `add_messages` upsert-by-`id` contract. `graceful_fallback` returns `Command(goto="assistant")`, which bypasses the new node — correct, since D3 already says first-party messages are not wrapped. Cost: one extra super-step per tool round (3 instead of 2), spending the `agent_recursion_limit` budget faster.
  - B) Wrap at read time inside the `assistant` node. No extra super-step, and it also covers the four hand-built `ToolMessage` sites that bypass `ToolNode` entirely. But the label is never persisted to the checkpoint, so the summarizer and the eval adapter see raw content — D7 would have to be rewritten and shipped task 2.2 would become dead code.
  - C) Wire the hook only on the `:278` branch (no fault policy). Smallest diff, keeps the plan — but leaves planner and concierge unlabelled, which forfeits the spec's main target.
- default_if_no_response: BLOCK
- decision: A) `label_tools` node between `tools` and `assistant`; the `wrap_tool_call` / `awrap_tool_call` hook is abandoned
- decided_by: Minh Tran
- decided_at: 2026-09-16
- consequences: design D1, §3 diagram, §3.2, §4 and §5 rewritten; PLAN Global Constraints and Task 2.1 rewritten; SC-4 re-stated against the node; task 2.1's hook implementation and `tests/agents/test_tool_wrapping_hook.py` reverted before the re-implementation. Tasks 2.2 (eval adapter) and 3.1 (RAG) are unaffected — the wrapper still persists in state under A, so D7 stands.

## E002 (rag-tool-output-wrapping)

Note: this repo's `specs/memory-poisoning-hardening/ESCALATIONS.md` already used E001/E002 for its
own decisions. Numbering restarts within this spec's own file; the E001 above is this spec's own
first escalation, not a duplicate of the memory spec's E001/E002.

- raised_by: task 2.1 implementer (in-flight, "the plan itself is wrong")
- date: 2026-09-16
- trigger: repeated `<verify>` failure — E001's own remedy failed the task's Verify set
- question: The `label_tools` node chosen in E001 adds one super-step per tool round. Is that acceptable, and if not, what replaces it?
- context: |
  Measured, not argued: `.venv/bin/python -m pytest apps/api/tests/agents/test_trip_guard.py apps/api/tests/agents/test_prompt_map.py -q`
  on the `label_tools` implementation → 2 failed, 34 passed.

  `test_sequential_ten_round_budget_fits_recursion_limit`'s own docstring states the arithmetic
  this repo already optimized once: "Old topology (assistant, trip_guard, tools per round):
  3*10+1 = 31 super-steps — over budget. New topology (assistant, tools per round, guard skipped
  when a round doesn't need it): 2*10+1 = 21." `agent_recursion_limit` is 25
  (`app/core/config.py:177`). `label_tools` reintroduces exactly the discarded third step:
  3*10+1 = 31 > 25 → `GraphRecursionError`.

  `test_prompt_map.py::test_map_covers_exactly_the_graphs_node_keys` also fails: the new node adds
  six `{specialist}/label_tools` keys with no matching `PROMPTS_FOR_NODE` entries.

  Separately (found by the same implementer, not yet a blocking test failure): design D3 claimed
  `clarification_tools.py:55` and `trip_tools.py:583` are covered by the `status == "error"` skip.
  They are not — both build **success** `ToolMessage`s with no `goto`, inside a `Command.update`.
  Through the node seam they arrive as ordinary state messages and get wrapped, risking suppression
  of `needs_clarification`'s own control instruction (MIN-68). This is a plan gap the node seam
  could not have caught either way, but the replacement seam must close it.
- options:
  - A) Keep `label_tools`, raise `agent_recursion_limit` (25 → 36) and restate the budget test. Rejected: shared runtime config is a Rule 4 hard gate (raises the ceiling for every path, not only the tool round), and does not touch the `PROMPTS_FOR_NODE` gap or the D3 gap.
  - B) Wrap at read time inside `assistant` (this spec's original alternative B). No extra super-step and closes the D3 gap for free (four hand-built sites all read through `assistant`). Rejected again: the label is never persisted to the checkpoint, so D7 (summarizer keeps tags, eval strips them) becomes unimplementable and the already-shipped task 2.2 becomes dead code.
  - C) Wrap the `tools` node's own callable — replace `ToolNode(...)` with `RunnableLambda(sync, afunc=async)` around an unchanged, uncalled-elsewhere `ToolNode` instance, post-processing the return value. Verified by probe (`scratchpad/probe_node_wrap.py`, executed in this session): a flaky tool still runs 3 times under `RetryPolicy` (exception propagates through the wrapper, unlike the hook — the wrapper never intercepts execution, only the finished return value, so there is nothing for the wrapper to swallow); both `invoke` and `ainvoke` wrap; `id` is preserved; a `Command`-returning tool arrives as a bare `Command` in a `list`, distinguishable from the `dict` shape a `ToolMessage` batch returns, so it passes through untouched with no `status` check needed. Same node, so no added super-step — `test_trip_guard.py` and `test_prompt_map.py` are both left alone.
- default_if_no_response: BLOCK
- decision: C) Wrap the `tools` node's own callable (`RunnableLambda` around `ToolNode`) — `label_tools` (E001's answer) is itself abandoned
- decided_by: Minh Tran
- decided_at: 2026-09-16
- consequences: design D1/§3/§3.2/§4/§5 rewritten again, this time to the callable-wrap seam; PLAN Global Constraints, Task 2.1 and SC-4 rewritten again; the `label_tools` node code and its test file (not yet committed) discarded before re-implementation; the D3 gap (`clarification_tools.py:55`, `trip_tools.py:583`) is closed as a named test in the rewritten Task 2.1, not deferred.
