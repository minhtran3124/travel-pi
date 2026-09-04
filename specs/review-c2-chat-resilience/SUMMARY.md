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

Chat now has a Stop control while streaming, a pending HITL interrupt survives a page reload, and
a claim failure no longer permanently forfeits pre-login history on a transient error. Five plan
tasks, ten commits, one BE route response shape changed, no other production surface touched.
Side-panel persistence across a reload is explicitly out of scope (D6): closing/reopening the chat
never loses panels today — only a full page reload does, and that gap is not fixed here.

### Rationale

`interrupt_pending`/`interrupt_payload` already existed as a naming convention on `ChatResponse`;
reusing it kept the API surface consistent. The BE read reuses the same `graph.aget_state(cfg)`
idiom the streaming path already uses, confirmed sufficient with only `thread_id` by reading the
installed LangGraph 1.2.6 source directly.

### Alternatives considered

- A second, dedicated `GET .../interrupt` endpoint (kept the array-shaped `.../messages` response
  untouched) — rejected: two round-trips on every hydrate instead of one, and the user preferred
  folding the field into the existing read once told the "additive" framing was wrong either way.

### Deviations

- Rule 1 — Removed the now-unused `Message` import from `apps/api/app/routers/agent.py` after its
  only use site's return type changed to `ConversationMessages`. Commit `e3b78f1`.
- Rule 1 — Added `interrupt_pending`/`interrupt_payload` default assertions to the two existing
  empty-result list-messages tests (unknown conversation, non-owner), closing a task-2.1 review
  finding that the empty branch's shape was unpinned. Commit `3aac842`.
- Response-shape change — `GET /agent/conversations/{id}/messages` moved from a bare
  `list[Message]` to `ConversationMessages` (`{messages, interrupt_pending, interrupt_payload}`).
  Not additive in the strict JSON sense (array → object); the design corrected this framing before
  implementation (see `design.md` D2). Blast radius: one FE call site (`fetchConversationMessages`)
  and four BE test assertions, all fixed in the same commits (`9a76934`, `e3b78f1`).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Corroborate claim-403 swallowed | `grep -n "Fail silently" apps/web/src/components/chat/useAgentStream.ts` | 0 | two occurrences at intake, before this branch | |
| Corroborate panels never persisted | `grep -rn "panel" apps/api/app/db/models apps/api/app/schemas/agent.py` | 1 | no match at intake, out of scope per D6 | |
| A user-triggered stop resets isStreaming and shows no error | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.stop.test.tsx` | 0 | re-run by the controller at `5fd73fd` | SC-1 |
| GET .../messages reports interrupt_pending against a real interrupt | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py -k interrupt -q` | 0 | re-run by the controller at `3aac842` | SC-2 |
| The pre-existing list-messages assertions pass under the new shape | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py -q` | 0 | 8 passed; re-run by the controller at `3aac842` | SC-3 |
| The pre-existing PII-redaction test passes under the new shape | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -k test_chat_redacts_pii_in_persisted_messages -q` | 0 | re-run by the controller at `e3b78f1` | SC-4 |
| Claim keeps the key on non-403, clears on 403, hydration still runs | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.hydrate.test.tsx` | 0 | 4 tests; re-run by the controller at `5fd73fd` | SC-5 |
| Hydrating a pending interrupt sets state + a valid resume target, both branches | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.hydrate.test.tsx` | 0 | same file/run as SC-5 | SC-6 |
| Web package still type-checks | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec tsc --noEmit` | 0 | failed at `5dfd8a9` — a pre-existing ChatComposer test case was never updated for the new required props (vitest never type-checks test bodies, so 19/19 tests still passed with a broken package); fixed and re-run at `a72c01f` | SC-7 |
| Stop button + panel wiring test | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/ChatComposer.test.tsx src/components/chat/ChatPanel.test.tsx` | 0 | 19 passed; re-run by the controller at `5dfd8a9` | |

### Not auto-verified

- **`trip_id` divergence between the interrupt-read and interrupt-write paths.** The read (Task
  2.1) derives its LangGraph thread id from `conversation.trip_id`, set once at creation and never
  updated. An active turn derives it from the request's live `trip_id`. If a client ever sent a
  different `trip_id` on a later turn than the one that created the conversation — against the
  documented client contract (`ChatResponse.trip_id`'s docstring already tells clients to keep
  sending the conversation's original value) — the read would silently report
  `interrupt_pending: false` for a real pending interrupt. Found by the task 2.1 review; recorded
  as a Risk in `PLAN.md` §5, not fixed (a proper fix is a public-contract or data-model change
  beyond this design's scope). Reached traceability (the code paths were read and the divergence
  traced); not reproduced end-to-end.
- **Four Minor findings from the task 3.1 and 4.1 reviews**, none blocking: `stop()` leaves
  `userStoppedRef` set if called with nothing streaming (self-corrects on the next real stream;
  low impact since post-unmount `setState` is a no-op in React 18); the rehydrated interrupt
  payload uses a non-null assertion with no runtime guard against a degenerate BE payload shape
  (prescribed by the brief, not a deviation); the new claim-behavior test covers both failure
  branches but not the success path's `removeItem` call; the hydrate test's local `ClaimError`
  mock can't catch drift in the real class (covered separately by `agent.test.ts`). Reached
  provenance (each was read and traced against the live code); none re-verified by a new test in
  this change.

### Correctness note (found while closing SC-7)

Task 4.1's own vitest run (19/19) passed while the package failed `tsc --noEmit`: one pre-existing
`ChatComposer.test.tsx` case still constructed `ChatComposerProps` without the new required
`isStreaming`/`onStop` fields. Vitest does not type-check test bodies, so the gap was invisible to
the task's own Verify command; only running SC-7 (the plan-wide criterion) caught it. Fixed in
`a72c01f`.

### Correctness review

Six angles ran over the full branch diff (two rounds — the second after task-level review fixes
landed). Findings that survived verification, all fixed:

| Finding | Why it mattered | Angle(s) |
| --- | --- | --- |
| `GraphDep` raises `UpstreamError` at dependency-resolution time, before the route body runs — wrapping the checkpoint read in try/except never helped | Coupled a previously graph-independent, pure-DB read (including its early-return path) to agent-runtime availability; a down/not-yet-built graph 502'd the whole message-history read | guard-completeness, enclosing-function, call-site-impact, stack-defects (4-way convergence) |
| `stop()` never flushed the typewriter reveal buffer | The assistant bubble kept visibly "typing" already-received text for up to 6s after Stop, the opposite of what the control promises | stack-defects |
| `userStoppedRef` set unconditionally, even with nothing to abort | Could go stale and cause a later unmount-cleanup abort to be misclassified as a deliberate stop | guard-completeness (task 3.1 review also flagged this independently, Minor) |
| Task 4.1's own vitest pass hid a `tsc` failure | One pre-existing `ChatComposer.test.tsx` case was never updated for the new required props; vitest doesn't type-check test bodies | task 4.1 review, closed running SC-7 |

Fixed with `GraphOptionalDep` — a sibling dependency that resolves the graph the same way but
returns `None` instead of raising — rather than a try/except inside the route body, since the
raise happens before the body ever runs. Commits `a72c01f` (tsc fix), `d8ea6c7` (first pass at the
graph guard, superseded), `c920133` (the real fix: `GraphOptionalDep` + reveal flush).

Two findings recorded, not fixed, both pre-existing conditions accepted by design:

- **`trip_id` divergence** between the interrupt-read and interrupt-write paths — confirmed by
  three independent angles across two review rounds (task 2.1 review, enclosing-function,
  call-site-impact). See `PLAN.md` §5 Risks; not fixed because a proper fix is a public-contract
  or data-model change beyond this design's scope.
- **Unbounded claim retry with a visible error** for a permanently-failing (non-403) claim —
  `removed-behavior` flagged that the old "at most once, silent" guarantee is genuinely gone. This
  is the intended behavior from `design.md` D5's error table, not a regression; no retry cap was
  in scope.

`prior-art` found nothing: the one topically-adjacent lesson
(`docs/solutions/harness/sse-additive-field-breaks-cross-dir-shape-test.md`) doesn't apply — this
diff updates both the producer and every consumer of the changed response shape together.

### Intent Findings

Intent review verdict: **approved with findings** (1 gap, 2 drift, 1 excess; none blocking).

- **Drift, low** — the intent named a silent **403** claim failure as the problem; the shipped fix
  surfaces an error on every *other* failure and keeps 403 silent (D5: a real 403 means "not the
  user's history," nothing to retry). Reasoned in `design.md` D5 and re-confirmed with the user at
  design time; the requester's literal 403 case still shows nothing, by design.
- **Drift, low, disclosed** — E002-A said "additive"; the shipped change is a breaking
  array→object reshape. Already recorded under `### Deviations` above and re-confirmed with the
  user mid-design once the "additive" framing was found wrong (see `### Alternatives considered`).
- **Gap, low** — `apps/web/src/lib/api/schema.d.ts` (the checked-in `pnpm gen:api` output) was not
  regenerated and still declares the old `Message[]` response shape. Harmless: `lib/query/agent.ts`
  hand-mirrors `Message`/`ConversationMessages` rather than importing from `schema.d.ts` (the
  established convention for these hand-rolled history endpoints — see `PLAN.md` Global
  Constraints), so nothing consumes the stale entry and `tsc` stays clean. That file's docstring is
  already stale in an unrelated way (still describes anonymous callers, pre-dating review-A) — this
  change did not introduce the drift, only left it uncorrected. Follow-up: run `pnpm gen:api`
  against a running API and commit the regenerated file in a later change.
- **Excess, trivial** — two whitespace-only line changes in `test_agent_chat.py` (ruff-format
  spacing around a slice, `lines[0][len("event: "):]` → `lines[0][len("event: ") :]`) landed on a
  test this change didn't otherwise touch — the project's own format-on-edit hook reformatting the
  file it was already editing for the new interrupt test, not a deliberate edit.

### Rollback

- Intake only so far: `git rm -r specs/review-c2-chat-resilience`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- Split-during-brainstorming: #109 turned out to be a different subsystem than the rest of item 11
  once the code was read. `feature-intake`'s Step 3 slicing (parent → children) happens before any
  code is read, so it cannot see this kind of internal-boundary mismatch; `brainstorming` Step 1
  ("decompose if the request spans subsystems that share no files") is the right place to catch it,
  which is what happened here.
