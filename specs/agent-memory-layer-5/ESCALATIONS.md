# agent-memory-layer-5 — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-09-16
- trigger: in-flight
- question: PR #214 is still OPEN with all four CI checks failing, so `PLAN.md` Task 0.1 (the merge gate) does not pass — do we wait for #214, ship only the #214-independent subset, or land #214 first?
- context: Task 0.1 is wave 0 and gates every later task. Its stated rule: "If #214 is still open, **stop and escalate** — shipping a delete UI for a store that still accepts poisoned writes inverts the intended order (the guard stops new poison; this spec removes existing poison)." Evidence gathered 2026-09-16: `gh pr view 214` → `state: OPEN`, `mergedAt: null`, `mergeStateStatus: UNSTABLE`, `reviewDecision: ""` (no review yet), `updatedAt: 2026-09-16T06:01:24Z`. `gh pr checks 214` → `api`, `eval-smoke`, `secrets`, `web` all **fail in 3s** (web-e2e skipped). A 3-second failure across every job is a setup/infra failure, not a test failure — so #214 is not one push away from merging.
- options:
  - A) **Ship the #214-independent subset now** (P0#2 + P0#4: Tasks 1.1, 1.2, 2.1, 4.1), defer P0#3 (Tasks 2.2, 3.1, 3.2) to a follow-up branch after #214 merges. Consequence: unblocks the prompt-age and token-budget work immediately and touches nothing on the memory write path; the privacy/delete surface — the item with the actual launch-blocking privacy argument — still ships later, and this spec's PLAN must be re-sequenced into two waves of delivery.
  - B) **Fix #214's CI first**, merge it, then execute this plan whole. Consequence: preserves the intended order and the single-PR shape; cost is an unscoped detour into four failing CI jobs on another branch before any work here starts.
  - C) **Proceed with the full plan anyway**, treating #214 as a parallel track. Consequence: violates Task 0.1 as written. A `/memory` delete UI would ship against a store that still accepts poisoned writes — the delete path would be the only defence, and any turn between now and #214 merging can still write a poisoned standing instruction that is re-injected into every system prompt. Not recommended.
- default_if_no_response: BLOCK
- decision: **A** — ship the #214-independent subset now (Tasks 1.1, 1.2, 2.1, 4.1 = P0#2 + P0#4). P0#3 (Tasks 2.2, 3.1, 3.2 — the `/memory` routes, generated client types and settings UI) is **deferred** to a follow-up branch that may only start once #214 is merged. `delete_memory` / `list_memory` are still written in Task 1.1 but stay unreachable: no HTTP route, no tool, no UI calls them in this delivery, which is what keeps the ordering constraint intact.
- decided_by: Minh Tran
- decided_at: 2026-09-16
