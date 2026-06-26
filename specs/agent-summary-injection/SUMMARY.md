# agent-summary-injection — Summary

Lane: normal
Confidence: high
Reason: Re-injects the rolling summary into the LLM prompt (REVIEW.md C2); modifies existing tested behavior (supervisor + sub-agent invocation) but no skill-listed hard gate fires.
Flags: existing-behavior
Affects: app/agents (state.py, subagents/_base.py, supervisor.py) — /agent/* answer quality
Input-type: change request

> `Lane` drives **ceremony**; `Confidence` drives **interruption**. No hard gate; direction
> unambiguous (single obvious fix), so PROCEED autonomously.

### Intent

> tiếp tục vs C2

Context: **C2** in `specs/travel-agent/REVIEW.md` — "Rolling summary is computed and old
messages deleted, but the summary is never used (net context loss)". The `summarize` node writes
`state["summary"]` and drops older messages via `RemoveMessage`, but nothing reads `summary` back
into the model's context, so summarization actively loses information.

## What changed

Added `system_with_summary(state, base)` in `app/agents/state.py`: when `state["summary"]` is set
it folds the summary into the system prompt (one `SystemMessage`), else returns the base prompt
unchanged. The sub-agent assistant (`subagents/_base.py`) and the supervisor router
(`supervisor.py`) now call the model with `system_with_summary(state, system)` instead of the bare
`system`, so summarized history reaches the model. Folding into a single system message (vs a
separate mid-stream one) also sidesteps the M2 multiple/mid-stream-system-message hazard.

### Rationale

Minimal, surgical fix that makes the *existing* summarizer effective without adopting the larger
`SummarizationMiddleware`/`create_agent` rewrite (REVIEW.md L4). One helper, two call sites.

### Alternatives considered

- Append the summary as a separate `SystemMessage` into `state["messages"]` — rejected: collides
  with the M2 ordering hazard (add_messages appends after the human turn) and accumulates summaries.
- Adopt LangChain 1.x `SummarizationMiddleware` — deferred (L4 modernization, larger change).

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Lint (app) | `ruff check app` | 0 | clean |
| Agent suite | `.venv/bin/pytest tests/agents -q` | 0 | incl. 2 new C2 tests |
| Full suite (SQLite) | `.venv/bin/pytest -q` | 0 | — |

### Rollback

- `git revert <sha>` (reversible — pure prompt-assembly change, no schema/contract)

### Harness-Delta

- none
