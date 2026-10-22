# UAT — multi-intent single-path (option A)

**Date:** 2026-09-03 · **Branch:** `refactor/multi-intent-single-path` @ `d7e04c1` (PR #130)
**Base:** `main @ 54902d7`. **CI (Postgres):** api + web green.

## Result: 8 / 8 PASS

| # | Test case | Result | Evidence |
|---|---|---|---|
| TC01 | Independent multi-intent (flights + weather) → parallel `[planner, concierge]`, one synthesized answer | PASS | `UAT-summary.png` |
| TC02 | Dependent chain "flights, weather, then itinerary" → recurring planner collapsed to `[planner, concierge]` | PASS | `UAT-summary.png` |
| TC03 | A `plan` step equal to the primary is dropped (no duplicate specialist) | PASS | `UAT-summary.png` |
| TC04 | `booking` target emits exactly one task → HITL plan node, never a parallel follow-on | PASS | `UAT-summary.png` |
| TC05 | Single-intent turn routes to one sub-agent and answers (behaviour unchanged) | PASS | `UAT-summary.png` |
| TC06 | Multi-intent **end-to-end**: two parallel workers converge on ONE synthesized answer, flight block appears once (#117 fixed) | PASS | `UAT-summary.png` |
| TC07 | SC-1..SC-6 acceptance suite re-runs green (`verify_summary --check`) | PASS | `UAT-summary-fullpage.png` |
| TC08 | "Plan everything" dependent chain completes in one planner ReAct loop in 22/25 super-steps | PASS | `UAT-summary-fullpage.png` |

Machine-readable: `results.json`.

## Method — the acceptance oracle is routing behaviour, not UI pixels

This change is backend (the agent graph). Its acceptance criteria are *how the supervisor
decomposes intents and how the graph answers*, so each case drives the **real**
`make_supervisor` / compiled `build_graph` with a scripted `FakeLLM` — deterministic, zero
network, no LLM spend — and asserts the actual `tasks` decomposition and the single synthesized
answer. Capture script: session scratchpad `uat_capture.py`; report rendered to PNG with a Node 24
`@playwright/test` chromium shot of a local HTML file (`shot.cjs`). Neither is checked in.

- **TC06 is the headline:** it reproduces the exact turn from issue #117 ("flights to Tokyo and
  what to see there"). Before this branch the two queued specialists each regenerated the whole
  answer, so the flight block appeared **twice** and the reply contradicted itself. Here the two
  parallel workers converge on one `synthesize` node and the flight block appears **once**.

## Not covered here — live pixel-level chatbot UAT

The `screenshots/uat-chatbot-*` convention screenshots the real chatbot UI. Reproducing that for
this branch needs the full stack (Docker api + Postgres + Next dev) **and a real signed-in
Supabase session** — `/agent/*` is JWT-gated since PR #129 (security hardening) merged to main —
and it would spend real OpenAI credits on a "plan everything" turn. That run needs an interactive
login I can't perform unattended; available on request.
