# close-product-loop — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-08
- trigger: low-confidence
- question: Is this intake the whole "close the product loop" umbrella, or only the first slice (UI search/book flights & hotels + booking↔trip link) with the other six items as follow-up specs?
- context: brainstorming/xia2/writing-plans cannot start without a bounded scope; 7 surfaces = 7 PLAN.md-sized efforts
- options:
  - A) Slice 1 only now (`close-product-loop` = flights/hotels UI + booking↔trip); Hôm nay / recap / map / .ics / share / visa-tips each get their own spec later — smallest reviewable PR, matches the review's đợt-2 ordering
  - B) Umbrella program: one design.md with a phased roadmap, then per-slice PLAN.md — more upfront design, no code for longer
  - C) A different first slice (name it)
- default_if_no_response: BLOCK
- decision: B — umbrella program: one design.md with a phased roadmap, then per-slice PLAN.md
- decided_by: Minh Tran (user, via intake question)
- decided_at: 2026-09-08

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-08
- trigger: ambiguous-direction
- question: Should free-tier users be able to book flights/hotels through the new UI (booking today is agent-only and premium-only)?
- context: decides whether slice 1 touches tier/entitlement checks (authorization hard gate) or only adds screens over the existing premium path
- options:
  - A) Yes — UI booking open to all tiers (simulated inventory; no payment) → tier check added/relaxed on bookings routes
  - B) No — UI mirrors current policy: free users can search, booking stays premium
- default_if_no_response: BLOCK
- decision: B — UI mirrors current policy: free users can search, booking stays premium (no entitlement change)
- decided_by: Minh Tran (user, via intake question)
- decided_at: 2026-09-08
