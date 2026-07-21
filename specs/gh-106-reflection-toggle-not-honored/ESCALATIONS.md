<!--
  Escalation channel. Copy to specs/<slug>/ESCALATIONS.md.
  Default is DENY-ON-NO-RESPONSE: if `decision:` stays `pending`, the work stays BLOCKED.
  The agent appends an escalation block and stops; a human appends the decision.
-->

# gh-106-reflection-toggle-not-honored — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-07-21
- trigger: ambiguous-direction
- question: Given the reflection-disable toggle is fully correctly wired at the code level (per Explore investigation — `AgentContext.allow_reflection`, `AgentConfigCache` invalidation, and the `make_reflection_node` gate all check out, 42 tests pass), which direction should this issue take?
- context: GitHub issue #106 reports the reflection toggle as a no-op, but no code bug reproduces the report as filed. The one real gap found is that `AgentConfigCache` is a process-local singleton with no cross-process invalidation — only relevant if this API runs with >1 worker/replica, which this repo's own `docker-compose.yml` does not do. Implementation is blocked until a human picks a direction, since each option is a materially different piece of work.
- options:
  - A) Ask the reporter for repro details (deployment topology — worker/replica count, whether they restarted or waited past the 1h cache TTL, exact order of dashboard-save vs. chat-turn) before writing any code. Cheapest option; may resolve as could-not-reproduce.
  - B) Treat the multi-process cache staleness as the real bug and fix `AgentConfigCache` to invalidate across processes (shared TTL/pub-sub/read-through). This is a shared-component (high-blast) change, not a small patch — would need its own intake/plan.
  - C) Add an integration test covering the full path (dashboard POST → live `/agent/chat` graph run) regardless of A/B, to close the coverage gap the investigation surfaced. Low-risk, doesn't address the reported symptom on its own.
- default_if_no_response: BLOCK
- decision: B — fix cross-process cache invalidation in `AgentConfigCache`; treat the process-local-singleton gap as the real bug regardless of current single-process docker-compose topology.
- decided_by: Minh Tran
- decided_at: 2026-07-21

<!-- copy the E0xx block for each new escalation -->
