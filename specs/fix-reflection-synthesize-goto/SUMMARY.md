# fix-reflection-synthesize-goto — Summary

Lane: tiny
Confidence: high
Reason: one-file logic bug in the agent graph; no hard gate (no auth/schema/contract change), no new public callable.
Flags: existing behavior
Affects: apps/api/app/agents (reflection ↔ synthesize routing)
Input-type: change request
Route: tiny — branch `fix/reflection-synthesize-goto`, direct patch + test, quick-check proof.
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> make the spec/plan /feature-intake cho phần "A. Sửa ngay (bug & bảo mật)" trước.
>
> (from docs/reviews/2026-09-02-deep-review.md §3.A item 1) Reflection REVISE sau multi-intent bị
> nuốt — BUG. `synthesize` đặt `current_flow="synthesis"` nhưng reflection `goto=current_flow` và
> destinations khai báo `"synthesize"`. LangGraph log "wrote to unknown channel
> branch:to:synthesis, ignoring it": turn kết thúc, `revisions=1` bị đốt, `REFLECTION_REVISE_NOTE`
> (SystemMessage nội bộ) persist vào checkpoint history.

## What changed

The synthesize node (GH-117 parallel-intent convergence) emitted
`current_flow="synthesis"`, but the node — and reflection's declared destinations —
are named `"synthesize"`. When reflection judged the synthesized answer REVISE, its
`Command(goto=current_flow)` targeted a channel that does not exist, so LangGraph
dropped the routing (`wrote to unknown channel branch:to:synthesis, ignoring it`),
the turn ended without re-synthesizing, a revision budget was burnt, and the internal
`REFLECTION_REVISE_NOTE` was left as the last message in history.

Fix: a shared constant `SYNTHESIZE_NODE = "synthesize"` (app/agents/constants.py) is
now the single source for the node's registration name, reflection's `destinations`
tuple, the worker→synthesize and synthesize→reflection edges, the worker `goto`, and
the `current_flow` label the node emits — so the label can no longer drift from the
node name. Three stale test assertions that pinned the buggy `"synthesis"` label were
updated to `"synthesize"`, and a regression test drives REVISE after parallel
synthesis and asserts re-entry.

### Rationale

`synthesize` (apps/api/app/agents/nodes.py:201) writes `current_flow="synthesis"`, while the
reflection node (nodes.py:252) routes `Command(goto=state["current_flow"])` and the graph declares
its destinations as `(*SUBAGENTS, "synthesize", END)` (graph.py:174). The node is named
`synthesize`; the string must match it. Fix: emit the node name (ideally via a shared constant used
by both `graph.py` and `nodes.py`), and add a FakeLLM test that drives a two-intent turn through
`Send` fan-out → `synthesize` → reflection `REVISE` and asserts the graph re-enters `synthesize`
(second AIMessage, `revisions == 1`, no `REFLECTION_REVISE_NOTE` left as the last message).

### Alternatives considered

- Route reflection REVISE after synthesis back to `END` (skip revision for multi-intent) — rejected:
  silently disables a documented feature; the cheap fix is the name mismatch.
- Drop reflection entirely (PR #115) — out of scope; that is a product decision still open (see
  docs/reviews/2026-09-02-deep-review.md §2 callout).

### Deviations

- Rule 2 (auto-add): widened the fix from a one-line literal swap to a shared
  `SYNTHESIZE_NODE` constant threaded through graph.py, nodes.py and
  synthesis_worker.py, because the defect's whole cause is two string literals that
  must agree; the constant makes the drift unrepresentable.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| regression (red→green) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py -q` | 0 | new test fails on the pre-fix literal, passes after | |
| lint | `cd apps/api && ../../.venv/bin/ruff check app/agents/graph.py app/agents/nodes.py app/agents/subagents/synthesis_worker.py app/agents/constants.py` | 0 | clean | |
| agent+streaming+agent-API suites | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///tmp/t.db ../../.venv/bin/python -m pytest tests/agents tests/streaming tests/api/agent -q` | 0 | 426 passed (with .env moved aside; local .env points at down Postgres + a real OpenAI key — see memory env-openai-key-test-breaks-llm-tests) | |

### Not auto-verified

- Whole-suite run (SQLite, `.env` moved aside): `1894 passed` — confirms no other
  module pins the old label. Re-run: `mv apps/api/.env aside && cd apps/api && env -u
  OPENAI_API_KEY DATABASE_URL=sqlite:///tmp/full.db ../../.venv/bin/python -m pytest -q`.
  Reached truth. (The local `.env` points at a down Postgres + a real OpenAI key, so a
  bare `make test` errors ~576 setup-time; that is the environment, not this change.)
- No client depended on the `current_flow="synthesis"` string: the FE never branches on
  it (web tests use only planner/concierge/booking) and `_FLOW_SUGGESTIONS` has no
  synthesis/synthesize key (both resolve to `[]`) — reached provenance via grep over
  apps/web/src and app/agents/suggestions.py; not a behavioral re-run.

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
