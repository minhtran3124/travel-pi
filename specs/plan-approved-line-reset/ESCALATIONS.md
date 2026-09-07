# plan-approved-line-reset — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-07
- trigger: low-confidence
- question: How should the HITL "plan approved" line survive the booking sub-agent's `reset`?
- context: fix implementation blocked until one approach is chosen (see SUMMARY.md → Alternatives)
- options:
  - A) Skip `reset` after a terminal-node token → one combined bubble; smallest diff; history still stores only the booking reply unless persistence is also changed
  - B) Drop the approve `AIMessage`; show approval as a status/activity step → no bubble, history consistent; booking agent loses the "Plan approved" context line
  - C) New SSE `notice` event rendered outside the answer bubble → cleanest UX; public-contract change → high-risk lane
- default_if_no_response: BLOCK
- decision: B — drop the approve AIMessage; surface approval as a status on the interrupt card / activity trail
- decided_by: Minh Tran (user, via AskUserQuestion)
- decided_at: 2026-09-07
