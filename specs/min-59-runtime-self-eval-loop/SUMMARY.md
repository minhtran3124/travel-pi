# min-59-runtime-self-eval-loop — Summary

Lane: normal
Confidence: high
Reason: 2–3 risk flags (existing runtime agent behavior + inherently weak proof around an LLM-judge + extra grader LLM calls), no hard gate. Design fork resolved by human 2026-07-10: option 2 — dedicated grader node (see COMPARISON.md §5, Phụ lục A).
Flags: existing-behavior, weak-proof, external-systems
Affects: agents/nodes.py (reflection loop), agents/graph.py, agents/subagents/*, agent prompt registry
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim from Linear MIN-59 (the scope-deciding text). -->

**MIN-59 — Phase 2: Prototype a runtime self-evaluation loop (Rubric-based) for the chatbot.**

Goal: Phase 2 of the evaluation system: prototype a **runtime self-evaluation loop** for the chatbot, inspired by LangChain Deep Agents' `RubricMiddleware` (see MIN-58). Prerequisite: only start after MIN-58 (offline evaluation with DeepEval + G-Eval) is complete and has a stable baseline result. In Phase 1 (MIN-58) the evaluation system runs offline as a test suite (dataset + G-Eval criteria), which measures quality but does not intervene at runtime. Phase 2 aims to let the agent self-grade and self-correct during execution, for important steps (e.g. before returning a booking result or hotel information).

Proposed mechanism (following the RubricMiddleware pattern): Define a **rubric** (a list of "done" criteria) for each type of important task (Hotel search results: correct language, includes enough price/location info, no hallucination; Booking flow: all required info present before confirming, no redundant questions — relates to MIN-51). A separate **grader sub-agent** (LLM-as-judge, ideally a cheaper model than the main one to optimize cost) reviews the transcript and returns a verdict: `satisfied` / `needs_revision` / `max_iterations_reached` / `failed` / `grader_error`. If `needs_revision`: per-criterion feedback is injected back into the conversation, the agent re-runs — with a loop limit (`max_iterations`) to avoid infinite loops.

Risks & questions to answer during the prototype: Latency (each self-eval round adds ≥1 LLM call); Cost (benchmark added cost by % of requests that trigger the loop); Scope of application (whole agent vs just 1–2 high-risk sub-agents — proposal: start with hotel search / booking flow); Grader false positives/negatives (compare grader results against manual assessment on a sample set).

Implementation plan (proposed): (1) Pick one experimental sub-agent (proposal: hotel search/booking flow). (2) Define the rubric from the MIN-58 offline eval criteria. (3) Implement the grader sub-agent in the LangGraph flow, using a cheaper model as judge. (4) Set a reasonable `max_iterations` (proposal: 2–3 rounds). (5) Measure latency & cost before/after. (6) Compare output quality via the MIN-58 offline eval set (with vs without the loop). (7) Write a trade-off assessment report (quality vs latency/cost). (8) If positive, plan a gradual rollout to the remaining sub-agents.

## What changed

All 8 tasks of `PLAN.md` implemented on `feat/min-59-runtime-grader`, including the measurement
deliverable (`REPORT.md`). E1–E4 in `ESCALATIONS.md` were raised by review, decided, and resolved.

**Outcome of the prototype: HOLD.** The grader works on hotel search — it caught a real
hallucination both live and in the offline A/B — but on the rest of the `concierge` sub-agent the
rubric makes the agent refuse to answer rather than answer accurately. Four of eight revised eval
cases became refusals, one already-correct answer was degraded. The headline `grounding +0.188`
is largely an abstention artifact. Details and the ship-blockers in `REPORT.md`.

- **New `grader` node** (`app/agents/grader.py`): per-flow rubric LLM-as-judge on the cheap tier.
  `satisfied` → END; `needs_revision` → per-criterion gaps injected as a `SystemMessage` (never a
  `HumanMessage`) + loop back to the sub-agent; disabled or ungraded flow → delegate to
  `reflection` (the exact baseline path, so the A/B lever is clean); grader error /
  cap → END, fail-open.
- **Graph rewiring** (`app/agents/graph.py`): `booking` + `concierge` → `grader`; the other three
  sub-agents keep their `reflection` edge.
- **Rubric prompts** `grader_booking/v1.md`, `grader_concierge/v1.md`, pinned in `active.yaml`.
- **Config surface**: `grader` added to `AGENT_CONFIG_GROUPS` + `FAST_AGENTS`; per-request
  `AgentContext.allow_grader` resolved from `agent_config."grader".enabled` in `_resolve_context`.

### Live evidence (dev stack, 2026-07-10)

The grader caught a **real hallucination** on its first live turn: the concierge's first draft
invented two hotels (`Merry Hotel Danang`, `Hilton Da Nang`) that no tool returned; the grader
failed `grounding`, and the final answer listed only the two hotels present in the tool output.
Verdict text and the injected feedback were both in Vietnamese, and the reply stayed Vietnamese —
no language flip.

Cost, measured: a concierge **hotel** turn ran 3 sub-agent invocations + 2 judge calls (baseline:
1 + 1). A concierge **weather** turn was `satisfied` on the first grade (1 judge call, 0
revisions). Cost is topic-dependent.

### Rationale

Prototype/spike of a rubric-based runtime self-eval loop. Normal lane: it changes runtime agent behavior on the booking/hotel path (existing, test-covered behavior) and adds an LLM-judge whose proof is inherently fuzzy, but touches no auth/authz/schema/migration/public-contract/high-blast file, so no hard gate.

**Mechanism decided (human, 2026-07-10): option 2 — dedicated grader node** that REPLACES reflection for the graded flows (`booking`, `concierge`), designed convergently with upstream `RubricMiddleware` semantics (verdict names, per-criterion `GraderResponse` shape, rubric prompts in the registry, grader model via DB `agent_config`) so it can later fold into the middleware when the path-B migration reaches those subagents. Full analysis: `COMPARISON.md`.

### Alternatives considered

Integration-mechanism fork — resolved 2026-07-10 (deep comparison in `COMPARISON.md`):
1. **Extend the existing `make_reflection_node`** — rejected: mixes task-rubric grading into a battle-tested node running on ALL 5 subagents, and entangles the A/B measurement the prototype exists to produce.
2. **New dedicated grader node** (hotel/booking, replaces reflection for graded flows) — **CHOSEN**: isolated blast radius, clean with/without toggle, ~0 marginal judge cost when satisfied, avoids the known HumanMessage language-flip bug, and bridges to `RubricMiddleware`.
3. **Literal `RubricMiddleware` port** — rejected for now: gated behind the high-risk `subagent-create-agent-migration` (booking/concierge migrate last), upstream injects `HumanMessage` (known language-flip risk), double-judge layering with reflection, deepagents 0.6.x beta churn. Remains the convergence target (COMPARISON.md Phụ lục A; 3-lite variant documented).

### Deviations

- Rule 1 — `apps/api/tests/api/agent/test_agent_chat.py`, `test_stream_persistence.py`,
  `test_identity_hybrid.py`: rerouting `concierge` through the grader changed which FakeLLM queue
  the judge reads (`structured_responses`, not `responses`), so three tests that scripted
  reflection's queue drifted by one item. Added a `grader_verdicts` fixture param and moved
  `test_stream_emits_reset_on_revised_answer` (the R2 / SSE-reset test) onto grader-driven
  revisions. The old fixtures had **no** `structured_responses`, so the grader silently took its
  fail-open path in every API test — the verdicts are now real.
- Rule 1 — `apps/api/tests/scripts/test_seed_agent_config.py`: hard-coded `== 9` node count
  replaced with `== len(AGENT_CONFIG_NODES)` (this file is gitignored; edit is local-only).
- Rule 1 — `app/agents/grader.py`: transient LLM errors are re-raised so the node's
  `retry_policy=LLM_RETRY` can fire; only non-retryable errors fail open. Found by
  `/correctness-review` (score 100).
- Rule 2 — `app/agents/grader.py`: `GraderResponse.evaluations` gained `min_length=1`; an empty
  verdict would otherwise have read as "nothing failed" and silently approved the answer. Found by
  `/correctness-review` (score 75).
- Plan `<files>` sets for tasks 1.3 / 3.1 / 3.2 were widened to name the test files above, after
  `hooks/blast-radius-check.sh` correctly flagged them as outside the declared scope.

**Second round — the four escalated decisions (E1–E4), all authorised by the human 2026-07-10.**
These reach outside the plan's `<files>` by design; see `ESCALATIONS.md` for the reasoning.

- E1 → `app/agents/state.py` (`grader_iterations`, `grader_verdict`), `app/agents/nodes.py`
  (reset both per turn in `load_context_node`), `app/agents/grader.py`. The grader no longer writes
  reflection's `revisions`.
- E2 → `app/data/agent_config.py` (`SEED_DISABLED_AGENTS`), `app/db/seed.py` (`enabled=False` on
  insert only). The prototype is gated off by default, as the intake required.
- E3 → `app/enums.py` (`GraderVerdict`); every outcome persists a verdict. `failed` deliberately
  omitted — unreachable once E4 lands (reasoning in `ESCALATIONS.md` E3).
- E4 → `app/agents/grader.py`: the cap is checked after the judge call, so the shipped answer is
  always graded.
- Rule 1 — `tests/api/agent/test_agent_chat.py`, `test_stream_persistence.py`: added
  `_force_grader_enabled()` + a cache-reset fixture. E2 turned the grader off by default, which
  broke the grader-scripted API tests **on a fresh DB only** — the developer's stale local
  `travel.db` still had `enabled=NULL` and masked it. Caught by the second `/correctness-review`
  pass, which reproduced it on a clean SQLite file.
- Rule 1 — `tests/agents/test_state.py`: `load_context_node`'s exact-shape (`==`) assertions updated
  for the two new per-turn resets (the `sse-additive-field-breaks-cross-dir-shape-test` pattern).

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Grader node unit tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_grader.py -q` | 0 | 11 passed (routing, fail-open, retry re-raise, empty-verdict) |
| Agent + agent-API suites | `cd apps/api && DATABASE_URL="sqlite:///./travel.db" ../../.venv/bin/python -m pytest tests/agents/ tests/api/agent/ -q` | 0 | 217 passed |
| Full BE suite, **fresh DB** | `cd apps/api && TMPDB=$(mktemp -d)/fresh.db DATABASE_URL="sqlite:///$TMPDB" ../../.venv/bin/python -m pytest tests/ -q` | 0 | 1435 passed. Must be run against a *fresh* DB: a stale `travel.db` predating `SEED_DISABLED_AGENTS` keeps `grader.enabled=NULL` and masks the seed default (this hid a CI-breaking failure once). 5 unrelated failures occur only with `apps/api/.env` present (`OPENAI_API_KEY=test`, ORS key); with `.env` moved aside those 5 files pass 17/17 |
| Seed default is off | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_seed_agent_config.py -q` | 0 | `grader` seeds `enabled=False`; re-seed never clobbers an operator toggle |
| A/B eval (Task 8) | `docker exec -w /app api-api-1 python -m eval.run_grader_ab --out /app/eval/_REPORT.md --json-out /app/eval/_ab.json` | 0 | 19 cases × 2 arms, real judge. Raw results in `ab-results.json` |
| Report deliverable | `test -s specs/min-59-runtime-self-eval-loop/REPORT.md && grep -q "needs_revision" specs/min-59-runtime-self-eval-loop/REPORT.md` | 0 | Task 4.2's `<verify>` |
| Rebuild report offline | `cd apps/api && ../../.venv/bin/python -m eval.run_grader_ab --from-json ../../specs/min-59-runtime-self-eval-loop/ab-results.json --out ../../specs/min-59-runtime-self-eval-loop/REPORT.md` | 0 | regenerates the tables with no agent/judge cost (overwrites the hand-written tail) |
| Lint | `cd apps/api && ruff check app/agents/grader.py tests/agents/test_grader.py` | 0 | clean |
| Prompt registry pins | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'You are' in registry.get('grader_booking'); assert 'You are' in registry.get('grader_concierge')"` | 0 | both rubrics resolve via `active.yaml` |
| Live A/B lever (dev stack) | `curl -s -X POST localhost:8000/agent/chat -d '{"message":"Tìm giúp mình khách sạn ở Đà Nẵng","user_id":"smoke","conversation_id":"<fresh>"}'` then `docker logs api-api-1 \| grep "grader →"` | 0 | grader on → `needs_revision`/`max_iterations_reached`; `grader.enabled=false` → `node=grader → reflection (delegated)` |
| SSE contract (R2) | same, against `/agent/stream` | 0 | 1 `event: done`, 2 `event: reset` (one per superseded draft), 0 grader text in the stream |
| Seed default, live | delete the `grader` row, restart, `select enabled from agent_config where agent_name='grader'` | 0 | `false`; a concierge turn then logs `node=grader → reflection (delegated)` — no judge call |
| E1/E3/E4, live | read the checkpoint for the smoke thread | 0 | `grader_iterations=2`, `grader_verdict='max_iterations_reached'`, `revisions=None` (never written); log line names the failing criteria, proving the final draft was graded |

### Advisory Findings

- `/correctness-review` finding on the shared `revisions` counter scored 75 (below the 80
  threshold) but is **not** treated as advisory: the controller reproduced it on the live stack,
  where every concierge turn ends at `revisions=2`. Promoted to `ESCALATIONS.md` E1.
- `/intent-review` finding 4: `GRADED_FLOWS` includes all of `concierge` (weather, visa, currency,
  places), not just hotel search as the request proposed. Feared spurious loops on non-hotel turns
  did **not** reproduce — a live weather turn graded `satisfied` on the first pass (n=1). Recorded
  as a measurement item for Task 8 rather than a blocker.
- `/intent-review` finding 6: the booking rubric adds `grounding` + `language` beyond the two
  criteria the request named. Reasonable safety properties; widens what can trigger a revision.

### Rollback

- `git revert <sha>` (prototype is additive; loop should be gated off by default until measured)

### Harness-Delta

- none
