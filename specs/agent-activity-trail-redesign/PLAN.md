---
slug: agent-activity-trail-redesign
status: shipped
owner: minhtran
created: 2026-09-04
---

# Agent Activity Trail Redesign

## 1. Motivation

`AgentActivityTrail` prints one row per raw tool-call event, so a turn that repeats the same
tool (e.g. `add_itinerary_item` x11) shows eleven identical rows, and a failed call shows a
bare red dot with no explanation. Design approved in `design.md` against the mockup at
https://claude.ai/code/artifact/91a6f41b-e28d-49db-acf3-f35b850d459a.

## 2. Non-goals

- No backend/agent changes — no per-tool error reason, no granular single-tool retry.
- No SSE event contract changes.
- No redesign outside the activity trail (chat panel/launcher untouched).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | 11 consecutive same-family steps render as one row with a count | `pnpm --filter web test -- AgentActivityTrail` | exit 0 |
| SC-2 | A group containing an errored step renders the error copy + retry control | `pnpm --filter web test -- AgentActivityTrail` | exit 0 |
| SC-3 | Clicking retry on an error row invokes the passed `onRetry` | `pnpm --filter web test -- AgentActivityTrail` | exit 0 |
| SC-4 | Collapsed summary uses the new friendly copy key | `pnpm --filter web test -- AgentActivityTrail` | exit 0 |
| SC-5 | Web lint/typecheck pass on the changed files | `pnpm --filter web lint` | exit 0 |

## 4. Tasks

### Task 1.1 — i18n copy for the redesigned trail (wave 1)

- **Files:** apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Under `Chat.activity`, replace `summary` with the friendlier phrasing
  ("Sorted {count, plural, one {# thing} other {# things}} for your trip · {seconds}s" or
  equivalent — keep it short and in the existing "well-traveled friend" voice) and add:
  `error` (generic fallback, e.g. "Couldn't finish this step"), one `error.<family>` key per
  existing family (hotels/flights/places/weather/route/airQuality/budget/journal/working) for
  a family-specific phrasing ("Couldn't finish updating your trip"), and `retry` ("Retry").
  Keep every existing family label key (`hotels`, `flights`, …) as-is — they're reused as the
  row's primary label. Mirror every new key into `vi.json` with a real Vietnamese translation,
  not a copy of the English string.
- **Verify:** `node -e "JSON.parse(require('fs').readFileSync('apps/web/messages/en.json'))" && node -e "JSON.parse(require('fs').readFileSync('apps/web/messages/vi.json'))"`
- **Done:** Both locale files parse as valid JSON and contain the new keys.

### Task 2.1 — Dedup + icons + error/retry in AgentActivityTrail (wave 2)

- **Files:** apps/web/src/components/chat/AgentActivityTrail.tsx
- **Action:** Add a grouping pass over `steps` that folds consecutive steps sharing the same
  `familyKey` into one group: `{ familyKey, count, status, ids }` where `status` is `"error"`
  if any member errored, else `"running"` if any member is running, else `"ok"`. Render one
  row per group: a small inline-SVG icon per family (flights/hotels/weather/airQuality/route/
  places/budget/journal/working — reuse the existing family keys, one icon each, `currentColor`,
  14px) as the leading glyph, the family label + `×{count}` when count > 1, and a trailing
  status indicator (existing `STATUS_DOT` treatment, kept for ok/running; on error render the
  row as an inline alert: family-specific error copy from `Chat.activity.error.<family>`
  (fallback to `Chat.activity.error`) plus a `Retry` button that calls the new optional
  `onRetry` prop (component stays presentational — no hook access). Update the collapsed
  summary line to use the new i18n key. Add a short settle-in transition (transform+opacity,
  ~180ms) per row, respecting `prefers-reduced-motion` via the existing `tp-*` motion
  convention (check `globals.css` for the pattern already used elsewhere, e.g. `tp-msg-in`) —
  do not invent a new motion utility if one already fits.
- **Verify:** `pnpm --filter web exec tsc --noEmit -p tsconfig.json`
- **Done:** Component compiles; dedup/icon/error/retry logic implemented per design.md.

### Task 2.2 — Thread `onRetry` from MessageList (wave 2)

- **Files:** apps/web/src/components/chat/MessageList.tsx
- **Action:** Pass `onRetry={isLastAssistant ? onRegenerate : undefined}` to
  `AgentActivityTrail` (MessageList already receives `onRegenerate` — no new prop threading
  above this component).
- **Verify:** `pnpm --filter web exec tsc --noEmit -p tsconfig.json`
- **Done:** Only the last assistant message's trail can trigger retry.

### Task 3.1 — Tests for the redesigned trail (wave 3)

- **Files:** apps/web/src/components/chat/AgentActivityTrail.test.tsx
- **Action:** New test file (none exists today). Cover: (a) 11 consecutive same-family steps
  render as a single row with the count text; (b) non-adjacent same-family steps stay separate
  rows; (c) a group containing one errored step renders the error copy and a retry control;
  (d) clicking retry calls the `onRetry` prop; (e) the collapsed (non-streaming) summary uses
  the `activity.summary` key with the right interpolation values. Mock `next-intl` the same
  way `MessageList.render.test.tsx` does (`useTranslations` → identity key or a small resolver
  for the interpolated keys).
- **Verify:** `pnpm --filter web test -- AgentActivityTrail`
- **Done:** All five behaviors covered and passing.

## 5. Risks

- **Grouping heuristic edge case:** a single group spanning a mix of ok+error+running (e.g.
  10 ok itinerary adds then 1 running) reads as one row with the worst-status color, which
  slightly hides which specific call is in-flight vs done. Acceptable per design.md — the
  count already signals "several of these happened"; per-item status inside a group is out of
  scope.
- **i18n drift:** new keys must land in both `en.json` and `vi.json` in the same task or the
  `vi` locale silently falls back/breaks — Task 1.1 does both together.

## 6. Status Log

- 2026-09-04 — Plan created, mockup approved by user, worktree `feature/agent-activity-trail-redesign` created.
- 2026-09-04 — Tasks 1.1, 2.1, 2.2, 3.1 implemented. `AgentActivityTrail.test.tsx` already
  existed (5 tests) — extended in place with 6 new tests rather than created fresh, per
  SUMMARY.md Deviations. Full chat suite (109 tests), tsc, and eslint all green.
- 2026-09-04 — Discovered the worktree branch had inherited 3 unrelated commits from a dirty
  local checkout (`specs/review-c2-chat-resilience`); reset onto `main` and reapplied this
  task's diff cleanly (SUMMARY.md Deviations). Ready to commit and open PR.
