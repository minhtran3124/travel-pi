---
slug: gh-109-clarification-restream
status: shipped
owner: Minh Tran
created: 2026-07-22
---

# Investigate clarification reply re-streaming

## 1. Motivation

GitHub issue #109 reports that a clarification reply begins, resets to the same
prefix about three times, and only then completes. Determine whether the repeated
render originates in the LangGraph/SSE producer, the browser consumer, or their
interaction, and identify the smallest defensible fix scope.

## 2. Non-goals

- Do not change runtime behavior in this investigation.
- Do not update the GitHub issue or close it.
- Do not broaden the investigation to unrelated chat rendering behavior.

## 3. Success Criteria

- Trace the clarification response from graph execution through SSE mapping to UI state.
- Identify the most likely root cause with code and/or test evidence.
- Record a reproducible verification strategy and recommended fix scope.

## 4. Tasks

### Task 1.1 — Trace backend clarification emission (wave 1)

- **Files:** apps/api/app/agents/, apps/api/app/streaming/, apps/api/tests/api/agent/
- **Action:** Trace the needs-clarification path through LangGraph and the SSE mapper,
  including message IDs, reset events, reflection loops, and terminal messages.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q`
- **Done:** Backend evidence establishes whether duplicate token/reset sequences can be emitted.

### Task 1.2 — Trace frontend stream consumption (wave 1)

- **Files:** apps/web/src/components/chat/, apps/web/src/lib/stream/
- **Action:** Trace token/reset handling, smooth-reveal buffering, request lifecycles,
  retry/resume behavior, and Strict Mode safeguards.
- **Verify:** `cd apps/web && pnpm vitest run src/lib/stream/parseSSE.test.ts`
- **Done:** Frontend evidence establishes which event sequence causes visible restarts.

### Task 1.3 — Locate regression history and missing coverage (wave 1)

- **Files:** specs/, .git/
- **Action:** Inspect relevant specs and commit history to identify the behavioral change
  that introduced the issue and the smallest missing regression test.
- **Verify:** `git log --oneline -- apps/api/app/streaming apps/web/src/components/chat`
- **Done:** Candidate regression commits and test gaps are documented with evidence.

### Task 2.1 — Synthesize root cause and recommendation (wave 2)

- **Files:** specs/gh-109-clarification-restream/DEBUG.md, specs/gh-109-clarification-restream/SUMMARY.md, specs/gh-109-clarification-restream/reproduce.py
- **Action:** Reconcile backend, frontend, and history evidence; record confidence,
  add an offline deterministic reproducer, and record a surgical fix recommendation
  without editing runtime code.
- **Verify:** `git diff --check -- specs/gh-109-clarification-restream`
- **Done:** The investigation has an evidence-backed conclusion, re-runnable reproduction,
  and actionable next step.

## 5. Risks

- A real-provider-only graph sequence may not reproduce under `FakeLLM`; distinguish
  observed code behavior from inferred provider behavior.
- React development Strict Mode may amplify symptoms but should not be blamed without
  confirming whether multiple network requests are actually started.

## 6. Status Log

- 2026-07-22: Investigation started; issue metadata collected and three read-only traces dispatched.
- 2026-07-22: Current HEAD reproduced the invalid clarification reset with an offline
  `FakeLLM` graph probe. Backend/frontend traces and history agree the reset heuristic
  is broader than its reflection-only contract. No runtime code changed.
- 2026-07-22: Added `DEBUG.md` with the full trace, ruled-out causes, test gap,
  and recommended fix boundary.
