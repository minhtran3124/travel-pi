# gh-109-clarification-ledger-drain — Summary

Lane: normal
Confidence: high
Reason: public-contract hard gate fired (SSE token content + persisted reply change) but was narrowed by the user to a bug fix restoring intended behavior — one clarification turn = one question; no event type, route, or schema change. Remaining flags are existing-behavior + weak-proof.
Flags: public-contract (narrowed by human), existing-behavior, weak-proof
Affects: agent ledger routing (`app/agents/nodes.py` `dispatch_next`), `app/tools/date_tools.py` tool-error contract, `app/streaming/persistence.py` reply assembly
Input-type: change request
Route: normal → same branch as the mapper fix (`fix/gh-109-clarification-restream`, coupled — see Rationale) → `/subagent-driven-development`
Escalate: no — hard gate raised to the user at intake and explicitly narrowed to `normal`; the design fork was also put to the user and resolved

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> check latest message from agent chatbot from latest conversation and investigate why duplicated message
>
> ```
> You've already given Tokyo, Da Nang, 30/07 → 30 Jul 2026 (Thursday), and 2 adults. What date do you want to fly back?I can do that, but I'm missing the return date for your 3-day trip.
>
> You've already given Tokyo, Da Nang, 30/07 → 30 Jul 2026 (Thursday), and 2 adults. What date do you want to fly back?
> ```

> yes, do B and run /feature-intake

Where "B" is the option the user selected from the investigation:

> **B (chính):** chặn ledger drain khi lượt đã thành câu hỏi cho người dùng — không phụ thuộc model có gọi tool hay không. Đây là cùng lỗ hổng MIN-68 định bịt nhưng chỉ bịt được nhánh có tool.

Scope-deciding answers at intake:

> Cơ chế B: **Deterministic: tool resolve thất bại → set awaiting_user** — "không phụ thuộc model. Đúng với ca #109 (resolve_date đã được gọi và fail). Hẹp, dễ test, không đụng happy path."
>
> Persist join: **Có, sửa cho khớp REST path** — nối các câu trả lời của từng sub-agent bằng `"\n\n"` như `routers/agent.py:351`.
>
> Lane: **normal — narrow scope.**

## What changed

1. `app/tools/date_tools.py` — every `resolve_date` failure that only the traveller can
   settle (ambiguous, invalid, past date) now returns
   `Command(update={"awaiting_user": True, "messages": [ToolMessage(..., status="error")]})`
   via a new `_blocked_on_traveller` helper, instead of raising `ToolException`. The message
   text is unchanged and `status="error"` preserves the model-visible failure, the SSE
   `tool_result` status, and the MIN-49 transient/logic split. The provider-failure path in
   `_parse_via_llm` still raises — that is not a traveller-blocking condition.
   The explicit `@tool(args_schema=ResolveDateArgs)` had to go: the tool now takes an
   `InjectedToolCallId`, and a hand-authored schema omitting injected args breaks ToolNode
   injection. The argument description moved inline via `Annotated[str, Field(...)]`.
   Verified the model-facing schema is still exactly `['expression']`.
2. `app/agents/nodes.py` — **unchanged**, as predicted. The existing `dispatch_next` guard
   (`nodes.py:264-275`) fires correctly once the flag is set.
3. `app/streaming/persistence.py` — accumulated token content is joined with `"\n\n"` instead
   of `""`, matching `routers/agent.py:351`.
4. `app/streaming/mapper.py` — a `reset` is also emitted when a **different sub-agent**
   answers within the same turn. See "Correction" below: without this, the happy path was
   materially worse than before the fix.

### Correction (found by the user in live use, after the first "done")

Option B alone only covers the **clarification** path (`awaiting_user`). It does nothing for
the **happy path**, where every queued sub-agent legitimately runs. The wrong assumption was
that each ledger step contributes a *slice* of the answer; in reality **each step regenerates
a COMPLETE answer**. So a drained 4-step ledger produced four near-identical full replies.

Before any of this work, the bogus message-id `reset`s were clearing the persistence
accumulator between sub-agents, so only the last answer survived — the heuristic was wrong in
*name* but right in *effect* for this case. Removing it without replacing that effect made a
follow-up turn persist a **7934-char message with every line repeated 4×** (measured in the
DB), which is worse than the original bug.

Fix: key `reset` to the **sub-agent changing**, not to message-id inequality. That separates
the two cases precisely — a new sub-agent's answer supersedes the previous one (restoring the
old effect), while a new message inside *one* sub-agent's ReAct round does not (which is what
made the clarification visibly restart in #109).

Process failure worth recording: the first verification only exercised the clarification turn
and never a follow-up turn that drains a ledger. The measured "1 token / 1 subagent" result
was real but unrepresentative.

### Rationale

Root cause, confirmed against the running API rather than inferred: the model asked the
clarifying question in **plain prose without calling `needs_clarification`**, whose tool
(`app/tools/clarification_tools.py:44`) is the **only writer** of `awaiting_user`. The flag
stayed false, so `dispatch_next` drained the queued ledger and every sub-agent independently
re-answered the same question. Making a deterministic, code-level signal (a resolve tool that
cannot resolve a required fact) set the flag removes the dependency on model compliance —
which is precisely what failed.

This work is **coupled to the staged mapper fix** on `fix/gh-109-clarification-restream` and
must ship with it: `persistence.py:60-61` clears the accumulator on `reset`, so the bogus
resets the mapper fix removes were accidentally acting as separators that hid this duplication
at the DB layer. Shipping the mapper fix alone makes the persisted duplication worse.

### Alternatives considered

- **Prompt-level: force `needs_clarification`.** Keeps one writer for `awaiting_user`, but
  still depends on model compliance — the exact failure mode observed. Rejected by the user.
- **Structural: stop the ledger when a sub-agent's answer looks like a question.** Covers every
  cause, but a heuristic errs in both directions and would break legitimate multi-intent turns
  (the 2676-char Tokyo plan is a real multi-sub-agent composite). Rejected as riskiest.
- **Never drain the ledger.** Rejected — draining is correct and intended in the happy path.
- **Fix only the mapper `reset` heuristic** (`DEBUG.md`'s "confirmed root cause"). It is a real
  defect and is fixed, but it is not the live cause; #109 reproduces with it fixed.

### Deviations

- **Rule 1 (auto-fix):** removed the hand-authored `ResolveDateArgs` schema. Not in the plan
  as written, but forced by it — the injected `tool_call_id` cannot coexist with an explicit
  `args_schema` that omits it. The argument description was preserved verbatim inline.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| **New tests fail without the fix** | swap in `git show HEAD:apps/api/app/tools/date_tools.py`, re-run the two new cases | 1 | both FAILED pre-fix, pass post-fix — proves they are real regressions, not tautologies |
| Live SSE: one clarification, one token | `curl -sN -X POST http://localhost:8000/agent/stream …` ×4 | 0 | **1 `subagent` + 1 `token`** every run (pre-fix baseline: 4 + 4 identical 292-char tokens). Runs 1 & 3 took the `resolve_date` path — the exact pre-fix failure mode |
| **Live: follow-up turn that drains a full ledger** | two-turn `curl` (clarify → `"30 Jul"`) | 0 | the check missing from the first pass. 4 sub-agents each answer, each new one preceded by `reset`; persisted **1324 chars, 0 duplicated lines** (before this correction: 7934 chars, every line 4×) |
| Clarification turn unaffected by the correction | re-ran after the mapper change | 0 | 1 `token`, no `reset`, 313 chars persisted |
| New code path fires live | `docker logs api-api-1 \| grep "blocked on traveller"` | 0 | `tool=resolve_date blocked on traveller: 'the end of this month' is ambiguous…` |
| Ledger abandoned without any model tool call | `docker logs api-api-1 \| grep dispatch_next` | 0 | `dispatch_next → reflection (awaiting traveller; abandoning 3 queued step(s))` |
| Persisted reply is not repeated | `docker exec api-db-1 psql -U travel -d travel -c "SELECT length(content) …"` | 0 | 244 / 70 / 270 / 82 chars — all single-copy (pre-fix: 1168 = 4 × 292) |
| Model-facing tool schema unchanged | `resolve_date.tool_call_schema.model_json_schema()` | 0 | `['expression']` — `tool_call_id` correctly hidden from the model |
| Date tool tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/tools/test_date_tools.py -q` | 0 | 15 passed |
| Ledger tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_ledger_early_exit.py -q` | 0 | 10 passed (2 new) |
| Full backend suite | `cd apps/api && DATABASE_URL=sqlite:///./t.db ../../.venv/bin/python -m pytest -q` | 1 | 1803 passed, 5 failed — the **same 5** fail on clean `v3`: known `.env OPENAI_API_KEY=test` interference, unrelated |
| Lint | `.venv/bin/ruff check apps/api/app apps/api/tests` | 1 | 6 errors, all pre-existing on `v3`, none in changed files |
| Format | `.venv/bin/ruff format --check` on the 4 changed files | 0 | already formatted |

Tests added: `test_prose_clarification_after_failed_resolve_abandons_queue` (the shipped bug),
`test_later_successful_resolve_does_not_clear_the_flag` (pins the sticky-flag trade-off), and
`test_mapper_resets_when_a_different_subagent_answers` (the correction — the 4x-duplicate
happy path that the first verification pass missed).

### Rollback

- `git revert <sha>`

### Harness-Delta

- backlog: `/feature-intake` was run on this issue once and produced a `Lane`/route from a
  spec whose "confirmed root cause" was wrong — the investigation never validated its
  hypothesis against the running system, only against a `FakeLLM` fixture. Worth a
  `docs/solutions/` entry: a root cause reproduced only in-fixture is a hypothesis, not a
  confirmation.

### Related

- `specs/gh-109-clarification-restream/` — the mapper `reset` fix (staged, uncommitted) and the
  original investigation. Its `SUMMARY.md` "Findings" are superseded on the question of what
  causes the user-visible duplication; its mapper defect is real and independently fixed.
