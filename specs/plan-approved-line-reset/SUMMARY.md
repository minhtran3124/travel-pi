# plan-approved-line-reset — Summary

Lane: normal
Confidence: high
Reason: user chose option B (no new SSE event kind → no public-contract gate); flags = existing behavior (plan node reply) + multi-domain (BE plan node + FE interrupt card).
Flags: existing-behavior, multi-domain
Affects: app/streaming/mapper.py (reset emission), apps/web/src/components/chat/useAgentStream.ts (reset handling), app/routers/agent.py (reply persistence)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> make deep investigate for
> ```
> Khi user bấm "Đồng ý" duyệt booking, câu "Kế hoạch đã được phê duyệt. Tin đang tiến hành đặt chỗ." bị câu trả lời của booking agent đè trong cùng bubble. Hành vi có sẵn từ trước.
> ```

## What changed

Option B implemented. `plan_node` approve no longer appends an `AIMessage` (only `plan_approved: True` + `goto="booking"`), so nothing precedes the booking sub-agent and the mapper emits no `reset`; `PLAN_APPROVED_MSG` and the `plan_approved` system-copy key are removed. The web client records the approval as an activity-trail step (`plan_approved` → family `approved`, check icon, en "Plan approved · booking now" / vi "Đã duyệt · Tin đang tiến hành đặt chỗ") when the user approves, before the booking reply streams into the bubble.

### Findings (root cause, reproduced)

Event order on approve, reproduced with the mapper's own `_FakeGraph` harness (plan-node update, then one booking chunk):

`start → token("Plan approved. Proceeding with booking.") → reset → subagent(booking) → token(booking reply) → done`

1. `app/agents/nodes.py` `plan_node` appends the approve line as an `AIMessage` and `goto="booking"`.
2. `app/streaming/mapper.py` emits that line as a `token` (the `_TERMINAL_TEXT_NODES` branch, added by specs/agent-flight-routing-stream-gate so cancel/gated turns are not blank) and sets `emitted_token = True`.
3. The booking sub-agent's namespace then appears. The mapper's handoff rule ("each queued sub-agent regenerates the whole turn answer, so a new specialist supersedes the previous draft") sees `emitted_token` and emits `reset`.
4. `useAgentStream.ts` on `reset` clears the bubble's text (`revealRef.reset`), so the approve line is dropped and only the booking reply renders.
5. Persistence agrees with the UI: the REST path stores only the last content-bearing `AIMessage` of the turn, and the SSE persistence accumulator also honours `reset`. On reload the approve line is absent too, so the UI is *consistent*, just lossy.

The `reset` rule exists for two legitimate cases: multi-intent sequential specialists and reflection revisions. The plan-node line is neither: it is a status notice, not a draft answer. The language change (PR #145) did not introduce this; the English line behaved identically.

### Rationale

User picked **B** (ESCALATIONS.md E001, 2026-09-07): the approve line is a status, not an answer. Stop appending it as an `AIMessage` in `plan_node` (keep `plan_approved: True`); the FE shows approval as a resolved state of the interrupt card. No `reset` is triggered because no token precedes the booking sub-agent; persisted history matches the UI by construction.

### Alternatives considered

- **A. Do not reset after a terminal-node token** — in the mapper, track whether the pending tokens came from `_TERMINAL_TEXT_NODES`; skip `reset` on the first sub-agent handoff in that case. Result: approve line + booking reply in ONE bubble ("Kế hoạch đã được phê duyệt. Tin đang tiến hành đặt chỗ.\n\nMình chưa thể đặt ngay…"). Smallest diff (mapper + 1 test); but reload shows only the booking reply (persistence stores the last AIMessage) → UI/history drift unless the router also concatenates or persists both.
- **B. Make the approve line a status, not a message** — stop appending the `AIMessage` in `plan_node`; surface approval via the existing activity trail (`subagent`/`tool_result`-style event) or the interrupt card's resolved state. No bubble, no reset, history consistent. Changes the booking agent's context (it currently sees "Plan approved…" in `messages`) → needs a prompt/eval check; drops `plan_approved` from `SYSTEM_COPY` (one fewer translated line).
- **C. New SSE event kind (`notice`)** for terminal-node lines, rendered by the FE as a separate system line outside the answer bubble and immune to `reset`. Cleanest UX; but adds to the SSE contract (public-contract hard gate → high-risk lane), touches FE types/tests and the persistence accumulator.

Recommendation: **B** if the approve line is only a status (likely — the FE already shows "Đang chờ bạn đồng ý"/resolved state); **A** if the line must stay in the transcript and one combined bubble is acceptable.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| SC-1 approve silent, flag set | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py tests/agents/test_hitl_plan.py -q -k "plan"` | 0 | | SC-1 |
| SC-2 no reset before booking | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q -k "plan"` | 0 | | SC-2 |
| SC-3 FE approval step | `cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec vitest run src/components/chat/useAgentStream.stream.test.tsx src/components/chat/AgentActivityTrail.test.tsx` | 0 | 25 passed | SC-3 |
| BE agent/memory suites | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/agents tests/api/agent tests/memory -q` | 0 | 564 passed | |
| FE full suite | `cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec vitest run` | 0 | 198 passed | |
| FE lint + types | `cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm lint && pnpm exec tsc --noEmit` | 0 | one pre-existing exhaustive-deps warning at useAgentStream.ts:309 | |

### Not auto-verified

- Live approve flow in the browser (activity step visible, booking reply intact) — reached traceability; UAT pending (see screenshots/uat-plan-approved-line-reset once captured).

### Rollback

- `git revert <sha>`

### Harness-Delta

- none

## Route

- Escalate: resolved (E001 → B)
- Route: `using-git-worktrees` → `writing-plans` → `subagent-driven-development` (normal); branch `fix/plan-approved-line-reset` off `main`.
