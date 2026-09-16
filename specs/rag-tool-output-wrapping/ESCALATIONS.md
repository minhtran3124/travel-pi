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
