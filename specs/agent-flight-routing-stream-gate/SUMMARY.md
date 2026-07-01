---
slug: agent-flight-routing-stream-gate
created: 2026-07-01
---

# SUMMARY — agent-flight-routing-stream-gate

- **Lane:** normal
- **Confidence:** high
- **Reason:** Two independent BE fixes (prompt routing + streaming emission). No
  hard gate: no auth/authz, no DB migration, no external provider, no public API
  contract change (the SSE `token` event already exists — we just emit it in a
  previously-blank case), no tier-policy change. Root cause is fully diagnosed
  against the code → high confidence.

## Problem

Vietnamese flight-search query `"tìm chuyến bay từ Đà Nẵng ra Hà Nội…"` returns an
empty chat bubble for an anonymous (free-tier) user. Two stacked bugs:

1. **Misroute** — the supervisor classifies a flight *search* as `booking` intent.
   `booking` is premium-only, so a free user is tier-gated to `END`. A search
   should route to `planner` (owns `search_flights`, free-accessible).
2. **Silent stream** — the tier-gate emits `BOOKING_UPGRADE_MSG` via the
   supervisor node, but `stream_agent_events` only turns SUBAGENT-node messages
   into `token` events, so the message is dropped → blank bubble. Stream-only
   (`/agent/chat` returns it correctly).

## Rationale

Fix both: Fix 1 makes this exact query work (search → planner → flight results);
Fix 2 guarantees any tier-gated / unknown-intent turn shows its explanation
instead of an empty bubble. No tier-policy change — flight *search* stays free via
planner; `booking` stays premium.

## Alternatives considered

- Make `booking` free-tier — rejected: booking is intentionally premium; the real
  bug is the misroute, not the gate.
- Edit `supervisor/v3.md` in place — rejected: prompts are versioned (`active.yaml`),
  so a behavior change gets a new `v4`.
- FE-side "empty reply" banner handling — rejected: the BE should deliver the
  message; fixing the stream removes the blank entirely.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| (pending) per-task | see PLAN.md `<verify>` rows | — | filled during execution |

### Rollback

- Revert code: `git revert <sha>` (prompt bump + mapper change; no migration).
