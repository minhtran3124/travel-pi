# agent-web-search — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-23
- trigger: ambiguous-direction
- question: How should the two providers be exposed to the agent?
- context: Tool shape, config, and tests all depend on it; blocks brainstorming output.
- options:
  - A) Split by job (proposed default, confirmed/overturned by research): Tavily = `web_search` for open questions (LLM-ready extracted content, answer summary); SerpAPI = structured Google verticals (Google Events / Local / Hotels / Flights prices as reality check). Two tools, each with a narrow docstring.
  - B) One `web_search` tool behind a provider switch (Tavily primary, SerpAPI fallback) — simplest for the model, loses SerpAPI's structured verticals.
  - C) Decide after the xia2 use-case research, with no prior preference.
- default_if_no_response: BLOCK
- decision: A (accepted proposed default, user reply "ok, đồng ý vs suggestions")
- decided_by: Minh Tran
- decided_at: 2026-09-23

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-23
- trigger: ambiguous-direction
- question: Which agents get web search, and under what conditions may they call it?
- context: Tool binding + prompt rules; a shared tool description is a shared prompt, so scope must be decided up front.
- options:
  - A) Last resort only (proposed default): concierge (+ trip-research deep agent) may search ONLY when internal tools/RAG return nothing or the question is time-sensitive (events, advisories, opening hours, current entry rules). Never for flights/hotels/bookings, which stay on synthetic inventory.
  - B) Concierge + planner, with the same last-resort rule.
  - C) Every specialist.
- default_if_no_response: BLOCK
- decision: A (accepted proposed default, user reply "ok, đồng ý vs suggestions")
- decided_by: Minh Tran
- decided_at: 2026-09-23

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-23
- trigger: hard-gate
- question: Accept the external-provider + audit/security gates with these guards: off-by-default flag, keys only from env, per-user rate limit/quota on search calls, web output wrapped as untrusted (never written to long-term memory), sources cited in replies, FakeSearch in tests (no network)?
- context: Paid API spend and prompt-injection surface; needed before planning.
- options:
  - A) Yes, with the guards above.
  - B) Yes, plus a hard monthly call budget per provider.
  - C) Narrow scope further (say which).
- default_if_no_response: BLOCK
- decision: A (accepted proposed default, user reply "ok, đồng ý vs suggestions")
- decided_by: Minh Tran
- decided_at: 2026-09-23

## E004

- raised_by: orchestrator (worktree baseline)
- date: 2026-09-23
- trigger: in-flight (plan itself is wrong)
- question: The trip-research deep agent (`app/research/`, `tests/research/`, `tests/fixtures/tools_snapshot.json`) exists only on PR #221 (`feat/trip-research-deep-agent`, OPEN, not merge-ready), not on `main`. Where should the research wiring go?
- context: Tasks 4.1 (research binding + snapshot) and 4.2 (research skills), SC-8 and SC-12 reference files absent on `main`; the worktree branch `feat/agent-web-search` is cut from `main` (fc5a6869).
- options:
  - A) Base on `main`, concierge-only v1. Drop research binding, snapshot and skill edits from this plan; add them as a follow-up once #221 merges. PR is independent.
  - B) Rebase this branch onto `feat/trip-research-deep-agent` and keep the full plan. PR stacks on #221 and cannot merge before it.
- default_if_no_response: BLOCK
- decision: A (concierge-only v1 on main; research wiring is a follow-up after PR #221 merges)
- decided_by: Minh Tran
- decided_at: 2026-09-23
