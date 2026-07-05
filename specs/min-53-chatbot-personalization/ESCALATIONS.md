# min-53-chatbot-personalization — Escalations

## 2026-07-05 — Intent divergence on the "ask" dimension (name, gender)

**Trigger:** Final intent review (blind to PLAN) found the built prompts asked only
about trip company, while the verbatim MIN-53 proposal also asks to softly request
**name** ("hỏi nhẹ nhàng để xưng hô") and **gender** ("hỏi nhẹ nhàng để điều chỉnh
cách xưng hô"). Both were narrowings introduced during planning without explicit
requester sign-off, so shipping them silently would diverge from the original ask.

**Classification:** finding 1 = gap (name), finding 2 = drift (gender). Capture + reuse
plumbing was complete for all three fields; only the proactive ask diverged.

**Decision (requester, 2026-07-05):**

| Item | Decision | Action |
|---|---|---|
| Name ask | ADD a gentle, optional, skippable name ask | concierge v8 / planner v5 — commit `c00eaa6` |
| Gender ask | KEEP "never ask directly" (PII-safe); capture/use only if volunteered | No code change; recorded in SUMMARY + CHANGELOG |

**Status:** RESOLVED. Intent re-review confirmed both findings closed. No open escalations.
