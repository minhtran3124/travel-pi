---
slug: agent-summary-injection
status: shipped
owner: Minh Tran
created: 2026-06-26
---

# Re-inject the rolling summary into the LLM prompt (REVIEW.md C2)

## 1. Motivation

`specs/travel-agent/REVIEW.md` **C2**: the `summarize` node writes `state["summary"]` and drops
older messages (`RemoveMessage`), but nothing reads `summary` back into the model's context — so
summarization actively *loses* information instead of compressing it.

## 2. Non-goals

- Adopting LangChain 1.x `SummarizationMiddleware` / `create_agent` (REVIEW.md L4) — larger rewrite.
- Fixing M2 (load_context system-message ordering) — separate item; folding the summary into a
  single system message sidesteps it here but does not fix M2 itself.

## 3. Success criteria

- The rolling summary reaches the model on supervisor + sub-agent calls when present.
- No summary present → behaviour unchanged (base prompt passed as before).
- `ruff check app` clean; agent + full suites green, with a test proving the summary is injected.

## 4. Tasks (one wave)

### Task 1.1 — Summary-folding helper + call sites

```xml
<task id="1.1">
  <files>app/agents/state.py, app/agents/subagents/_base.py, app/agents/supervisor.py</files>
  <action>Add `system_with_summary(state, base)` to state.py (folds state["summary"] into one SystemMessage, or returns base unchanged). Use it at the sub-agent assistant call and the supervisor router call instead of the bare `system`.</action>
  <verify>.venv/bin/pytest tests/agents -q</verify>
  <done>Summary reaches the model; no-summary path unchanged.</done>
</task>
```

### Task 1.2 — Tests

```xml
<task id="1.2">
  <files>tests/agents/test_state.py</files>
  <action>Unit-test the helper (no-summary -> base; summary -> combined). Integration test: a capturing FakeLLM proves a sub-agent invocation receives the summary in its system message.</action>
  <verify>.venv/bin/pytest tests/agents/test_state.py -q</verify>
  <done>Both tests pass.</done>
</task>
```

## 5. Risks

- Two system messages / mid-stream system message rejected by some providers — mitigated by folding
  the summary into a *single* system message.

## 6. Status Log

- 2026-06-26 — implemented + verified. `ruff check app` clean; `pytest -q` 846 passed (SQLite);
  agent suite 30 passed incl. 2 new C2 tests. Branch `fix/agent-summary-injection` off
  `feat/travel-agent-foundation` (independent of C1 / PR #24).
