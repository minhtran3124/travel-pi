# review-c2-chat-resilience — Summary

Lane: high-risk
Confidence: high
Reason: public-contract hard gate (E002-A: the BE conversation read contract is extended, additively, so the FE can rehydrate a pending HITL interrupt after reload) plus flags existing behavior, cross-platform (FE hook + BE router), multi-domain, weak proof (#109 has no reproducing test).
Flags: public contracts, existing behavior, cross-platform, multi-domain, weak proof
Affects: apps/api/app/routers/agent.py (+ schemas, conversation read), apps/web/src/components/chat/useAgentStream.ts, ChatPanel/ChatWidget/MessageList, side-panel state
Input-type: spec slice
Route: high-risk — brainstorming (interrupt rehydration contract shape; Stop semantics vs LangGraph cancel; side-panel persistence store) → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (parent ESCALATIONS E001–E003 decided 2026-09-04; see ../review-c-web-experience/ESCALATIONS.md)
Parent: review-c-web-experience

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> chay /feature-intake cho section "C. Web app & trải nghiệm" theo artifact link https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview
>
> (follow-up, 2026-09-04) 1. ok  2. lam hop dong BE  3. backlog A

Slice of the parent intent (verbatim review text in `../review-c-web-experience/SUMMARY.md` § Intent):

> Item 11: `useAgentStream.ts` (849 lines) lacks a Stop button while streaming; interrupt state is memory-only so a reload leaves the graph stuck at the plan node; the side panel is lost on close/reload; a failed claim (403) is silent so the user may lose history unknowingly; issue #109 (clarification re-streams ~3×) is still open.
>
> Decision E002-A: extend the BE conversation read contract (additive) for interrupt rehydration.

## What changed

<not started — intake record only>

### Rationale

<pending design/research>

### Alternatives considered

- pending

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Corroborate #109 open | `gh issue view 109 --repo minhtran3124/travel-pi --json state` | 0 | `"state":"OPEN"` | |
| Corroborate interrupt memory-only | `grep -n 'useState<InterruptState' apps/web/src/components/chat/useAgentStream.ts` | 0 | line 182; no rehydration path | |

### Not auto-verified

- none yet (no claims made)

### Rollback

- Intake only so far: `git rm -r specs/review-c2-chat-resilience`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- none
