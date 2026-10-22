---
slug: gh-109-clarification-ledger-drain
status: shipped
owner: Minh Tran
created: 2026-07-23
branch: fix/gh-109-clarification-restream
---

# Stop the ledger draining when the turn became a question (gh-109, option B)

## 1. Motivation

A sub-agent asked the traveller for a missing date **in prose, without calling
`needs_clarification`**. That tool (`app/tools/clarification_tools.py:44`) is the only
writer of `awaiting_user`, so the flag stayed false, `dispatch_next` drained the queued
ledger, and every queued sub-agent re-answered the same question.

Measured on the running API with the #109 prompt:

- SSE: 4 `subagent` + 4 **identical** 292-char `token` events (planner, concierge, planner, budget)
- logs: `dispatch_next → concierge (pending=2) → planner → budget → reflection`
- persisted message: 1168 chars = 4 × 292, concatenated with no separator

## 2. Non-goals

- Do not change when the supervisor *builds* a ledger (`supervisor.py:311-331`) — draining
  is correct in the happy path.
- Do not add prose/question heuristics or an LLM judge to detect "this is a question".
- Do not touch the reflection loop.

## 3. Success Criteria

- The #109 prompt yields **one** clarification: 1 content-bearing `token` event, one
  persisted message, no repetition.
- Logs show `dispatch_next → reflection (awaiting traveller; abandoning N queued step(s))`.
- A legitimate multi-intent turn still runs every queued sub-agent and its answers are
  separated by a blank line, not glued.

## 4. Tasks

### Task 1.1 — `resolve_date` sets `awaiting_user` deterministically (wave 1)

- **Files:** `apps/api/app/tools/date_tools.py`, `apps/api/tests/api/tools/test_date_tools.py`
- **Action:** Replace every `raise ToolException(...)` in `resolve_date` (7 sites:
  ambiguous, invalid, past-date) with
  `Command(update={"awaiting_user": True, "messages": [ToolMessage(content=<same text>, tool_call_id=..., status="error")]})`.
  Add `tool_call_id: Annotated[str, InjectedToolCallId]`. Keep the message text unchanged so
  the model still gets its "do not guess — ask the traveller" instruction, and keep
  `status="error"` so the SSE `tool_result` still reports `error` and the MIN-49
  transient/logic split still sees a failed tool.
  Do **not** hand-author an `args_schema` — an explicit schema omitting the injected arg
  breaks LangGraph injection (`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`).
  Update the 8 `pytest.raises(ToolException)` cases to assert the returned `Command`'s
  update instead (flag set + message text + `status == "error"`).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/tools/test_date_tools.py -q`
- **Done:** Every `resolve_date` failure path sets `awaiting_user` without the model calling any tool.

### Task 1.2 — Separate sub-agent answers in the persisted reply (wave 1)

- **Files:** `apps/api/app/streaming/persistence.py`, `apps/api/tests/api/agent/` (new case)
- **Action:** Join accumulated token content with `"\n\n"` instead of `""`
  (`persistence.py:63`), matching the REST path (`routers/agent.py:351`). This is correct
  **only because** the staged mapper change coalesces each assistant message into exactly one
  `token` event — note that dependency in a comment.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/ -q`
- **Done:** A multi-answer turn persists with a blank line between answers, not glued.

### Task 2.1 — Regression: ambiguous date abandons the ledger (wave 2, depends on 1.1)

- **Files:** `apps/api/tests/agents/test_ledger_early_exit.py`
- **Action:** Add a case where the supervisor queues a ledger and the sub-agent calls
  `resolve_date` with an ambiguous expression **without** calling `needs_clarification`.
  Assert: the queued sub-agents never run, exactly one content-bearing answer, and
  `awaiting_user` is true. Add a second case pinning the accepted trade-off: a later
  *successful* `resolve_date` in the same turn does **not** clear the flag (the tool's
  contract is "do not guess", so ending the turn with a question is the intended bias).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_ledger_early_exit.py -q`
- **Done:** The prose-clarification path is covered; it was the gap that let #109 ship.

### Task 2.2 — Live verification against the running API (wave 2, depends on 1.1 + 1.2)

- **Files:** none (verification only)
- **Action:** Re-run the #109 prompt against `localhost:8000`, capture raw SSE, and read the
  persisted row. Compare against the recorded pre-fix baseline (4 tokens / 1168 chars).
- **Verify:** `curl -sN -X POST http://localhost:8000/agent/stream -d '{"message":"<#109 prompt>","user_id":"u-verify"}'` then `docker exec api-db-1 psql -U travel -d travel -c "SELECT length(content) FROM messages ORDER BY created_at DESC LIMIT 1;"`
- **Done:** 1 content-bearing token, ~292-char persisted message, no repetition.

### Task 3.1 — Full suite + lint (wave 3)

- **Files:** none
- **Action:** Run the full backend suite and lint; compare against the recorded baselines
  (5 pre-existing `.env`-induced failures; 6 pre-existing lint errors, none in changed files).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest -q && cd .. && .venv/bin/ruff check apps/api/app apps/api/tests`
- **Done:** No new failures attributable to this change.

## 5. Risks

- **Changed tool-error contract.** `resolve_date` no longer raises. Any caller that catches
  `ToolException` from it changes behavior — grep before editing; `DATE_TOOLS` is the only
  export and the tool is model-invoked, but confirm rather than assume.
- **Sticky flag within a turn.** `last_write_wins` (`state.py:37-51`) does not clear on a later
  success. Accepted deliberately (Task 2.1 pins it); revisit if it produces false abandonment.
- **Prompt/graph rebuild.** No prompt change is planned, so no rebuild is needed; if one gets
  added, the running graph is baked at lifespan and needs
  `docker exec api-api-1 touch app/main.py` (`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`).
- **Weakening-validation gate.** Removing 7 `raise` lines and 8 `pytest.raises` assertions will
  trip `risk-corroboration.sh`; the commit needs a human-run
  `RISK_WARN_CATEGORIES="weakening-validation"`.

## 6. Status Log

- 2026-07-23: Intake complete (lane `normal`, hard gate narrowed by the user). Root cause
  confirmed against the running API, not a fixture. Plan written.
- 2026-07-23: All tasks executed. Task 1.1 required removing the explicit `args_schema`
  (Rule-1 auto-fix, see SUMMARY Deviations). Task 1.2 done. Task 2.1 added two regressions,
  both verified to FAIL against pre-fix code. Task 2.2 confirmed live: 1 token / 1 subagent
  across 4 runs, two of which took the `resolve_date` path; ledger abandons 3 queued steps
  with no model tool call. Task 3.1: 1802 passed, 5 pre-existing failures, lint clean.
