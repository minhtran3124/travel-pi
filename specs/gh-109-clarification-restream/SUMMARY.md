# gh-109-clarification-restream — Summary

Lane: normal
Confidence: high
Reason: public-contract hard gate fired (SSE `reset` is client-visible) but was narrowed by the user to a bug fix restoring the already-documented `reset` = reflection-revision contract — no new/removed event type, no route change; remaining flags are existing-behavior + weak-proof.
Flags: public-contract (narrowed by human), existing-behavior, weak-proof
Affects: `apps/api/app/streaming/mapper.py` (SSE event contract, `reset` semantics)
Input-type: change request
Route: normal → `/using-git-worktrees` → `/subagent-driven-development` (two-stage agent review per task)
Escalate: no — hard gate raised to the user at intake and explicitly narrowed to `normal`

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> check issue https://github.com/minhtran3124/travel-pi/issues/109 , we have spec for reproduce bug in specs/gh-109-clarification-restream
>
> after get all let run /feature-intake

Scope-deciding answers at intake:

> Fix scope: **Chỉ sửa reset signal** — "Key `reset` vào tín hiệu reflection-revision thật thay vì message-ID inequality. Nhỏ, đủ để hết restart trong ca này, giữ nguyên hành vi stream prose. Rủi ro thấp nhất."
>
> Lane: **normal — narrow scope** — "đây là bug fix khôi phục contract đã tài liệu hoá (reset = reflection-revision), không thêm/xoá event type, không đổi route."

Underlying issue text (GitHub #109): *"Chatbot re-streams the same clarification reply ~3× before completing"* — expected behavior: *"The clarification reply streams once, monotonically, to completion — no restarts, no repeated partial segments."*

## What changed

`apps/api/app/streaming/mapper.py`, two coupled changes:

1. **`reset` is keyed to the reflection node.** It now fires only when the `reflection` node's
   `updates` entry bumps `revisions` (the critic said REVISE and re-ran the sub-agent), not on
   generic assistant message-ID inequality. It is emitted lazily, just before the revision's
   first token, and suppressed when nothing was streamed yet.
2. **Assistant prose is held until its message is disambiguated.** Chunks are buffered per
   message id; the completing `updates` entry decides — has `tool_calls` → the prose was a
   preamble the post-tool answer restates, so it is dropped; no `tool_calls` → flushed as one
   token. Two safety nets release the buffer if the completing update never arrives (end of
   stream) or the run crashes mid-message, so a reply is never swallowed.

Change 2 is not optional: with only change 1 the clarification stops flashing but the preamble
renders **twice** permanently, because the frontend appends tokens and the post-tool message
restates the preamble. Together they make the clarification stream once, monotonically — the
behavior #109 asks for.

### Rationale

Root cause is confirmed on current HEAD by a deterministic offline reproducer
(`reproduce.py`, `FakeLLM`, no network): the mapper's ID-inequality heuristic is broader
than the documented `reset` contract. Fixing the signal at the producer is the minimal
change that restores the contract; the frontend is already correct per the contract and
needs no change.

### Alternatives considered

- **Ship only the `reset` fix** (the intake scope). Abandoned once the reproducer showed it
  converts a transient flash into a permanently duplicated paragraph — a worse end state.
  Raised to the user mid-task; they chose to add the buffering.
- **Emit `reset` when a message turns out to carry tool calls** instead of buffering. Keeps
  time-to-first-token, correct semantics, but still shows one visible flash — i.e. #109 is
  reduced, not fixed. Rejected.
- **Also chase the duplicate `tool_result`** (DEBUG.md "Separate observation"). Not required
  to explain the visible restart; out of scope.
- **Frontend prefix deduplication.** Rejected in the investigation — it would hide incorrect
  server semantics and could mask duplicated graph/tool execution.

### Trade-off (reversible)

Buffering costs time-to-first-character: prose now starts rendering when the assistant message
completes, not as tokens arrive. It does **not** cost the typewriter effect — `smoothReveal`
animates client-side at 40 chars/sec with backlog-adaptive speed-up
(`apps/web/src/components/chat/useAgentStream.ts:21`), so a single large token still reveals
smoothly. To revert just this half, drop the buffering and flush each chunk directly; the
`reset` fix stands alone (but reinstates the duplicated preamble).

### Deviations

- **Scope expanded mid-task (escalated, not auto-corrected).** Intake authorized the `reset`
  fix only. The reproducer then showed that fix alone leaves the preamble duplicated
  permanently. Work paused and the finding was put to the user, who authorized adding the
  prose buffering. No unauthorized widening.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Offline reproducer: one monotonic reply | `.venv/bin/python specs/gh-109-clarification-restream/reproduce.py` | 0 | emits `tool_call → tool_result → token(full answer) → done`; zero `reset`, preamble not duplicated |
| Mapper/SSE unit tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q` | 0 | 23 passed |
| Genuine reflection reset still emitted (real graph) | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/ tests/agents/ -q` | 0 | 341 passed; includes `test_stream_emits_reset_on_revised_answer` (exactly one `reset`, between DRAFT and FINAL) |
| Full backend suite | `cd apps/api && DATABASE_URL=sqlite:///./test-gh109.db ../../.venv/bin/python -m pytest -q` | 1 | 1800 passed, 5 failed — the **same 5** fail on clean `v3` (verified via `git stash`): known `.env OPENAI_API_KEY=test` interference, unrelated |
| Frontend SSE parser | `cd apps/web && pnpm vitest run src/lib/stream/parseSSE.test.ts` | 0 | 21 passed; FE contract unchanged |
| Lint | `.venv/bin/ruff check apps/api/app apps/api/tests` | 1 | 6 errors, all pre-existing on `v3`, none in changed files; `ruff check app scripts` (the project's command) is clean |
| Format | `.venv/bin/ruff format --check` on both changed files | 0 | already formatted |

Regression tests added to `tests/api/agent/test_stream_events.py`:
`test_mapper_emits_reset_on_reflection_revision`,
`test_mapper_drops_preamble_of_a_tool_calling_message`,
`test_mapper_skips_reset_when_nothing_streamed_yet`.

Note: `test_mapper_no_duplicate_fallback_when_tokens_already_streamed` caught a real
regression in the first buffering draft (a crash mid-message dropped the partial answer and
replaced it with the generic fallback) — fixed by flushing the buffer in the exception handler.

Known gate friction (from memory): editing/removing an `assert` line trips the
weakening-validation gate — downgrade with `RISK_WARN_CATEGORIES="weakening-validation"` on
the commit if it fires on the retargeted mapper test.

### Rollback

- `git revert <sha>`

### Harness-Delta

- backlog: the investigation phase and the fix phase of one slug both want a `SUMMARY.md`
  with machine-read `Lane:`. Resolved here by archiving the investigation record as
  `SUMMARY.investigation.md`; the harness has no stated convention for multi-phase slugs.

### Prior phase

Investigation (read-only, shipped 2026-07-22) is recorded in `SUMMARY.investigation.md`,
`DEBUG.md`, `PLAN.md`, and `reproduce.py`.
