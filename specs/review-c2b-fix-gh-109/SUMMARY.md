# review-c2b-fix-gh-109 — Summary

Lane: normal
Confidence: medium
Reason: no hard gate — fixing a BE streaming/graph bug, not touching auth, migrations, public contracts, or high-blast files. Flags: existing behavior, weak proof (root cause is a hypothesis in the issue, not confirmed; no repro test exists yet). Confidence is medium, not high, because the actual mechanism (which node re-invokes and re-emits already-streamed tokens on the awaiting_user/reflection path) is not yet located in code — xia2 must find it before a design can be written with certainty.
Flags: existing behavior, weak proof
Affects: apps/api/app/agents/graph.py, apps/api/app/agents/nodes.py, apps/api/app/streaming/mapper.py (read-only reference for how tokens are emitted)
Input-type: spec slice
Route: normal — brainstorming (once xia2 has located the mechanism) → xia2 (Standard, may upgrade to Deep on evidence) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (parent ESCALATIONS E001–E003 decided 2026-09-04; see ../review-c-web-experience/ESCALATIONS.md). Split out of review-c2-chat-resilience during that spec's brainstorming (2026-09-04) because this is a BE LangGraph graph-invocation bug — a different subsystem, root cause, and debugging method than the FE/state-resilience items in c2.
Parent: review-c-web-experience

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> chay /feature-intake cho section "C. Web app & trải nghiệm" theo artifact link https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview
>
> (follow-up, 2026-09-04) 1. ok  2. lam hop dong BE  3. backlog A
>
> (split, 2026-09-04, during review-c2-chat-resilience brainstorming) Split #109 into its own spec — recommended.

Slice of the parent intent (verbatim review text in `../review-c-web-experience/SUMMARY.md` § Intent),
the #109 clause of item 11:

> issue #109 (clarification re-stream 3 lần) còn mở.

GitHub issue #109, verbatim:

> ## Summary
>
> When the agent needs to ask a clarifying question, the chatbot starts streaming its reply, cuts
> off after the first segment, and **re-streams the same text ~3 times** before finally streaming
> the complete reply. The user sees the same partial answer flash and restart repeatedly.
>
> ## Actual behavior
>
> - The reply begins streaming, but only a short segment renders before it restarts.
> - The text below re-streams from the top **~3 times**, then finally streams to completion.
>
> ## Expected behavior
>
> The clarification reply streams **once**, monotonically, to completion — no restarts, no
> repeated partial segments.
>
> ## Notes
>
> - Reproduces on the clarification / `needs_clarification` path (the reply asks the user to pin
>   down an exact date because "end of this month" is too broad).
> - Likely an SSE / streaming-emission issue where an early partial chunk is re-emitted (duplicate
>   stream restarts) rather than a single continuous token stream. Worth checking whether the
>   reflection/awaiting-user path re-invokes the streaming node and re-sends already-streamed
>   tokens.

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

### Not auto-verified

- none yet (no claims made)

### Rollback

- Intake only so far: `git rm -r specs/review-c2b-fix-gh-109`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- none
