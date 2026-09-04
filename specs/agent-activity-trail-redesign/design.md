---
slug: agent-activity-trail-redesign
status: approved
owner: minhtran
created: 2026-09-04
---

# Agent Activity Trail Redesign

## Problem

`AgentActivityTrail` (apps/web/src/components/chat/AgentActivityTrail.tsx) renders one row
per raw tool-call event with no aggregation. A turn that calls `add_itinerary_item` eleven
times renders eleven identical "Updating your trip" rows; a failed tool call renders a bare
red dot with no explanation. Reviewed against the mockup at
https://claude.ai/code/artifact/91a6f41b-e28d-49db-acf3-f35b850d459a (approved by user).

## Decisions

1. **Dedup by consecutive family.** Adjacent `ActivityStep`s that resolve to the same
   `familyKey` collapse into one row carrying a count (`Updating your trip ×11`). Non-adjacent
   repeats of the same family stay separate rows (e.g. a flight search, then a hotel search,
   then another flight action — order is preserved, nothing is merged out of sequence).
   Group status = error if any member errored, else running if any member is running, else ok.
2. **Per-family icon replaces the bare dot as the leading glyph**; the status dot moves to a
   small trailing indicator (ok / running-pulse / error), so family and status are both legible
   at a glance without adding a second color. Icons are plain inline SVG, `currentColor`,
   14px, no new color tokens — ink/muted only, matching the One Signal Rule (lime stays
   reserved for the running-state pulse).
3. **Error rows get a one-line, family-specific message** ("Couldn't finish updating your
   trip") pulled from i18n, not a fabricated per-tool reason — the SSE `tool_result` event
   carries only `status`, no error detail, and inventing backend-sourced copy the UI doesn't
   have would be worse than a plain statement.
4. **Retry is wired to the existing `regenerate()` action**, not a new granular per-tool retry.
   There is no backend capability to re-run a single failed tool call in isolation today
   (out of scope here); `regenerate()` already re-runs the last completed assistant turn end
   to end, which is the closest real, already-wired behavior. `AgentActivityTrail` stays
   presentational — this is passed down as an optional `onRetry` prop from `MessageList` /
   `ChatWidget`, not a new hook access.
5. **Collapsed summary copy changes tone** ("Sorted {count} things for your trip in {seconds}s")
   to match the existing "well-traveled friend" voice used elsewhere (welcome strip), replacing
   the analytics-toned "Used N tools · Ns". Expand/collapse mechanics are unchanged.
6. **Motion**: a short settle-in transition per new/changed row (~180ms, transform+opacity
   only, `prefers-reduced-motion` respected) — no layout-property animation.

## Non-goals

- No backend/agent changes (no per-tool error reason, no granular retry of a single tool call).
- No change to the SSE event contract (`tool_call` / `tool_result` shapes unchanged).
- No redesign of the chat panel/launcher — scoped to the activity trail only.

## Files touched

- `apps/web/src/components/chat/AgentActivityTrail.tsx` — dedup, icons, error row, retry prop, motion.
- `apps/web/messages/en.json`, `apps/web/messages/vi.json` — new/updated `Chat.activity.*` keys.
- `apps/web/src/components/chat/MessageList.tsx` — thread `onRetry={regenerate}` down to the trail (only if it doesn't already receive `regenerate`).
- Existing tests: `AgentActivityTrail` currently has no dedicated test file — one is added.
