# SUMMARY — web-streaming-smoothing

Lane: tiny
Confidence: medium
Reason: Only flag is a change to existing client-side streaming-render behavior; no hard gates (no auth/schema/contract/provider).
Flags: existing-behavior
Affects: apps/web chat streaming render (`useAgentStream.ts`) — client-only, not a public/shared contract
Input-type: Change request
Route: tiny → direct Edit on current branch (v3), machine gates as proof
Escalate: no

### Intent

> now, streaming text on UI too fast, make it slow a bit, and make smooth

The chatbot assistant text streams into the UI at raw wire speed (each SSE `token`
event appends immediately). The user wants the on-screen reveal to be a bit slower
and smoother.

### Rationale

Current path: `useAgentStream.ts` appends every `token` SSE event straight to React
state (`appendToAssistant`), so render cadence == server token cadence — fast, bursty.
Fix: decouple wire cadence from render cadence with a per-turn reveal buffer drained
by `requestAnimationFrame` at a bounded character rate (typewriter drip). This both
slows and smooths, and naturally catches up (bounded lag) on large bursts.

### Alternatives

- **Throttle React updates only** (batch every ~40ms): smooths but does NOT slow the
  overall reveal — rejected; user asked for both.
- **Streamdown animation props only**: no control over reveal speed for a custom SSE
  pipeline — insufficient.

### Assumptions

- Target speed ~90 chars/sec base with bounded backlog catch-up (≤~0.6s lag). Tunable
  via constants; can adjust if it feels too slow/fast.

### Files touched

- `apps/web/src/components/chat/smoothReveal.ts` (new) — plain rAF drip controller.
- `apps/web/src/components/chat/useAgentStream.ts` — buffer tokens through the controller
  in send/resume/retry; flush on new turn; clear on new conversation; dispose on unmount.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Typecheck web | `cd apps/web && npx tsc --noEmit` | 0 | clean |
| Lint changed files | `cd apps/web && npx eslint src/components/chat/useAgentStream.ts src/components/chat/smoothReveal.ts` | 0 | clean |
| Visual (typewriter pace) | run web dev + chat a turn | — | not run; needs Docker API :8000 + dummy Supabase env |

### Rollback

- `git checkout -- apps/web/src/components/chat/useAgentStream.ts && rm apps/web/src/components/chat/smoothReveal.ts`
