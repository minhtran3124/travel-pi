Lane: normal
Confidence: high
Reason: Single presentational component + i18n copy + one prop-threading change; no auth, migration, public contract, or SSE-shape change.
Flags: none
Affects: apps/web chat UI (AgentActivityTrail, MessageList, messages/en.json, messages/vi.json)
Input-type: change request

### Intent

"review screenshot and thinking to way improvement/enhance this UI/UX, make fancy or friendly
more" (image of the current tool-activity trail), followed by "look good, make design + plan
with git worktree and start implementation" after reviewing the approved mockup, and
"make sure branch name with prefix \"feature\"".

## What changed

`AgentActivityTrail` now groups consecutive same-family tool-call steps into a single row
with an icon + a `×N` count instead of repeating identical lines; a group containing a
failed step renders as an inline alert with family-specific copy and a Retry button wired to
the existing turn-regenerate action; the collapsed summary line's copy changed from "Used N
tools · Ns" to "Sorted N things for your trip · Ns" (and the Vietnamese equivalent). No
backend or SSE contract changes.

### Rationale

Mockup (https://claude.ai/code/artifact/91a6f41b-e28d-49db-acf3-f35b850d459a) was approved
as-is for direction; design.md narrows the two mockup elements that assumed backend
capabilities that don't exist today (a fabricated per-tool error reason, a granular
single-tool retry) down to what's actually wireable: family-generic error copy and retry via
the existing `regenerate()` action.

### Alternatives considered

- Per-tool (not per-family) grouping — rejected: still repetitive when the same tool fires
  many times in a row (the actual observed case), which is the bug being fixed.
- Adding a backend error-reason field to `tool_result` — rejected as out of scope; would
  require an agent/orchestration change beyond a UI redesign.

### Deviations

- Plan-accuracy correction (not a Rule 1-3 code fix): design.md/PLAN.md Task 3.1 assumed no
  test file existed for `AgentActivityTrail`; one already did (5 tests, `NextIntlClientProvider`
  + real `en.json`). Extended it in place with 6 new tests instead of creating a duplicate file.
- Branch hygiene: `EnterWorktree` branched from the local checkout's dirty HEAD, which was 3
  commits ahead of `main` from an unrelated in-flight task (`specs/review-c2-chat-resilience`,
  touching `apps/api/app/schemas/agent.py` and `apps/web/src/lib/query/agent.ts`). Backed up
  this task's working-tree diff, `git reset --hard main`, and reapplied the diff so the branch
  carries only this task's changes before commit/PR.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| locale JSON valid | `node -e "JSON.parse(require('fs').readFileSync('apps/web/messages/en.json'))"` | 0 | also ran for vi.json | |
| unit (dedup + count) | `pnpm --filter web vitest run src/components/chat/AgentActivityTrail.test.tsx` | 0 | 11/11 tests pass | SC-1 |
| unit (error + retry) | `pnpm --filter web vitest run src/components/chat/AgentActivityTrail.test.tsx` | 0 | includes retry-click and no-onRetry cases | SC-2, SC-3 |
| unit (summary copy) | `pnpm --filter web vitest run src/components/chat/AgentActivityTrail.test.tsx` | 0 | asserts "Sorted" in collapsed summary | SC-4 |
| full chat suite (regression) | `pnpm --filter web vitest run src/components/chat` | 0 | 109/109 tests pass, no existing test needed changes | |
| typecheck (full) | `pnpm --filter web exec tsc --noEmit -p tsconfig.json` | 0 | clean on the rebased branch (the earlier 3 errors belonged to the unrelated commits removed above, not this change) | |
| lint (changed files) | `pnpm --filter web exec eslint src/components/chat/AgentActivityTrail.tsx src/components/chat/AgentActivityTrail.test.tsx src/components/chat/MessageList.tsx` | 0 | | SC-5 |

### Not auto-verified

- Visual appearance against the mockup — reached provenance: manually UAT'd the real
  `AgentActivityTrail` component (a temporary, uncommitted local page rendering it with
  representative `ActivityStep` data) on a local `next dev` server, screenshotted with
  Playwright (grouped/dedup rows, the error+retry alert, and the collapsed/expanded
  summary), and compared by eye against the approved mockup. Not an automated visual-diff
  check, so re-running this claim requires repeating the manual UAT steps.

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
