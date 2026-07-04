<!--
  Canonical SUMMARY.md shape. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
-->

# summarizer-tool-call-pairing — Summary

Lane: normal
Confidence: high
Reason: One flag fired — existing-behavior (changes `summarize_conversation`'s tested trim
logic). No hard gate: no auth/authz, no schema/migration, no new external provider, no
weakened validation, no high-blast-radius file. Confidence high because the bug and its exact
mechanism were verified by reading the code directly (not guessed) and independently reproduced
via a failing test against the pre-fix logic before the fix, then confirmed green after —
discovered while live-debugging an unrelated feature (places-side-panel PR #57) in the same
session, not a design fork.
Flags: existing-behavior
Affects: `apps/api/app/memory/summarizer.py` (`summarize_conversation` trim boundary)
Input-type: maintenance

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane.

### Intent

> [Docker log excerpt shared by user, showing an `openai.APIError: ... "No tool call found for
> function call output with call_id call_xOukwDIg8c9Qu2rycmN0NIzL."` crash inside
> `app/agents/supervisor.py`'s `router.invoke(...)`, immediately following a
> `node=summarize (compressed 16 messages)` log line]
>
> "review changes for tool places above. Current with query `suggest me some cf in Da Nang` and
> have error right now"
>
> (Asked whether the places-side-panel work caused this crash; clarifying question — "Want me to
> fix the summarizer's message-pairing bug now?" — got no response within 60s, proceeded on best
> judgment given severity: this breaks any long tool-using conversation, not just places.)

## What changed

`summarize_conversation` (`apps/api/app/memory/summarizer.py`) previously trimmed old messages
with a naive `messages[:-keep_last]` slice. When the cut boundary landed inside an
`AIMessage(tool_calls=[...])` + its `ToolMessage` response(s) — e.g. splitting a parallel
two-tool-call turn — the kept tail could retain an orphaned `ToolMessage` whose parent tool-call
message was removed. The next model call then sent a tool result with no matching tool call,
which every provider (OpenAI direct, OpenAI-via-gateway, Azure fallback) rejected with `400 "No
tool call found for function call output with call_id ..."`, crashing the whole turn (and any
retry, since the corrupted history was already persisted to the checkpoint).

Added `_safe_split()`: walks the naive boundary backward past any `ToolMessage` run so a
tool-call/tool-result unit is always kept or removed together (`keep_last` becomes a *minimum*,
not an exact count). Added a regression test that reproduces the exact orphaning scenario
(2-tool-call AIMessage, boundary landing on the second `ToolMessage`) — confirmed it fails
against the pre-fix code, passes after.

### Rationale

Fix the boundary computation, not the removal mechanism — `RemoveMessage`/LangGraph's reducer
already work correctly; the bug was purely in *which* index was chosen to split on. Extending
`keep_last` backward (rather than, say, dropping the orphaned ToolMessage or the whole turn) was
chosen because it's the only option that doesn't lose information the model or user might need,
and it degrades gracefully (worst case keeps a few more messages than requested — never fewer,
never mispaired).

### Alternatives considered

- Drop the orphaned `ToolMessage` instead of extending the boundary — rejected: silently discards
  a real tool result from history, which could later cause the model to re-ask a question it
  already had an answer to, or misrepresent what was searched.
- Re-synthesize a placeholder `AIMessage(tool_calls=...)` for the orphaned `ToolMessage` — rejected:
  fabricates history that never happened; more moving parts than just not splitting the pair.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Regression test (pre-fix, sanity check) | `pytest tests/agents/test_memory.py::test_summarize_conversation_keeps_tool_call_pairs_intact -v` (against stashed pre-fix `summarizer.py`) | 1 | Failed as expected: `assert 'a0' not in {'a0', 'h0', 't0'}` — confirms the test catches the real bug |
| Memory/summarizer tests | `pytest tests/agents/test_memory.py -q` | 0 | 7 passed (incl. new regression test + pre-existing `test_summarize_conversation_uses_llm_and_trims`, unaffected) |
| Full backend suite | `DATABASE_URL="sqlite:////tmp/verify_summarizer_fix.db" pytest tests/ -q` | 1 | 1238 passed, 8 failed — same pre-existing/env-driven failures (LLM config defaults + routing offline-estimate) seen throughout this session on `v3`/`feat/places-side-panel`; unrelated |
| Lint (changed files) | `ruff check app/memory/summarizer.py tests/agents/test_memory.py` | 0 | All checks passed |

### Rollback

- `git revert <sha>` — purely additive/corrective logic change, no schema/data changes, fully
  reversible.

### Harness-Delta

- none — this session's `RISK_WARN_CATEGORIES` gotchas were already logged in
  `specs/places-side-panel/SUMMARY.md`.
