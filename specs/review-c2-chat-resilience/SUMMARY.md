# review-c2-chat-resilience — Summary

Lane: high-risk
Confidence: high
Reason: public-contract hard gate (E002-A: the BE conversation read contract is extended, additively, so the FE can rehydrate a pending HITL interrupt after reload) plus flags existing behavior, cross-platform (FE hook + BE router), multi-domain, weak proof (claim-403 and panel-loss have no regression test).
Flags: public contracts, existing behavior, cross-platform, multi-domain, weak proof
Affects: apps/api/app/routers/agent.py (+ schemas, new interrupt read), apps/web/src/components/chat/useAgentStream.ts, ChatPanel/ChatWidget/MessageList, apps/web/src/components/chat/panel/SidePanel.tsx
Input-type: spec slice
Route: high-risk — brainstorming (interrupt rehydration contract shape; Stop semantics vs LangGraph cancel; side-panel persistence scope) → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (parent ESCALATIONS E001–E003 decided 2026-09-04; see ../review-c-web-experience/ESCALATIONS.md)
Parent: review-c-web-experience

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> chay /feature-intake cho section "C. Web app & trải nghiệm" theo artifact link https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview
>
> (follow-up, 2026-09-04) 1. ok  2. lam hop dong BE  3. backlog A
>
> (split, 2026-09-04, decided during this spec's own brainstorming) issue #109 moved to its own
> spec `review-c2b-fix-gh-109` — a BE LangGraph graph-invocation bug, a different subsystem, root
> cause, and debugging method than the four items kept here.

Slice of the parent intent (verbatim review text in `../review-c-web-experience/SUMMARY.md` § Intent):

> Item 11: `useAgentStream.ts` (849 lines) lacks a Stop button while streaming; interrupt state is
> memory-only so a reload leaves the graph stuck at the plan node; the side panel is lost on
> close/reload; a failed claim (403) is silent so the user may lose history unknowingly. (issue
> #109, clarification re-stream 3 lần, moved to `review-c2b-fix-gh-109`.)
>
> Decision E002-A: extend the BE conversation read contract (additive) for interrupt rehydration.

## What changed

<not started — brainstorming in progress>

### Rationale

<pending design>

### Alternatives considered

- pending

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Corroborate interrupt memory-only | `grep -n 'useState<InterruptState' apps/web/src/components/chat/useAgentStream.ts` | 0 | line 182; no rehydration path | |
| Corroborate no Stop affordance | `grep -n "Stop" apps/web/src/components/chat/ChatComposer.tsx apps/web/src/components/chat/ChatPanel.tsx` | 1 | no match | |
| Corroborate claim-403 swallowed | `grep -n "Fail silently" apps/web/src/components/chat/useAgentStream.ts` | 0 | two occurrences (claim step, hydrate step) | |
| Corroborate panels never persisted | `grep -rn "panel" apps/api/app/db/models apps/api/app/schemas/agent.py` | 1 | no match — Message has no panel field, no panel table | |

### Not auto-verified

- none yet (no claims made)

### Rollback

- Intake only so far: `git rm -r specs/review-c2-chat-resilience`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- Split-during-brainstorming: #109 turned out to be a different subsystem than the rest of item 11
  once the code was read. `feature-intake`'s Step 3 slicing (parent → children) happens before any
  code is read, so it cannot see this kind of internal-boundary mismatch; `brainstorming` Step 1
  ("decompose if the request spans subsystems that share no files") is the right place to catch it,
  which is what happened here.
