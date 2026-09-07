---
slug: synthesis-attribution-and-config
status: shipped
owner: Minh Tran
created: 2026-09-03
---

# synthesis-attribution-and-config — Attribute worker steps, configure synthesize

**Base:** `main` (`a7f4ad3`). **Branch:** `fix/synthesis-attribution-and-config`.
Findings and the corrected premise are in `SUMMARY.md`; no design fork, so no `design.md`.

## Global Constraints

- Every `Verify` / SC check is one pipe-free command under 60s from `apps/api`, with every
  credential set to EMPTY (an unset var loses to `.env`, a set one wins) and a tmp SQLite URL:
  `env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= LANGFUSE_ENABLED=false
  DATABASE_URL=sqlite:///$(mktemp -d)/x.db ../../.venv/bin/python -m pytest … -q`.
  Never the whole suite; never move `apps/api/.env`.
- **The content boundary from `agent-run-trace-detail` still holds.** The specialist name is a
  static agent name (`planner`, `concierge`, …) — it is not user content. Nothing else may be
  added to a step, and `on_chain_end`'s `outputs` / `on_tool_start`'s `inputs` stay unread. The
  existing leak test must keep passing untouched.
- No schema change. `synthesize` is a seeded `agent_config` row, not a migration.
- Do not change how models are resolved. `synthesis_worker` keeps resolving the specialist's model.
- Same-wave tasks share no files. Stage and commit as SEPARATE commands. Use `git commit -F -`
  with a quoted heredoc so backticks survive.

## 1. Motivation

Two gaps recorded as follow-ups when `agent-run-trace-detail` shipped:

- Every LLM step of a multi-intent turn shows no prompt, because those calls run under
  `synthesis_worker` and the specialist never reaches the checkpoint namespace. On the busiest
  path the detail page answers "which prompt was this running under" with a blank.
- `synthesize` has no `agent_config` row, so it resolves the env default model. In practice that
  meant one `gpt-5` call inside turns whose every other call used `gpt-5.4-mini` — a 3.2x cost
  difference between two otherwise identical turns, and the reason a multi-intent turn 403'd
  before the account was granted `gpt-5`.

## 2. Non-goals

Per-worker prompt overrides; back-filling prompts onto existing `agent_run_steps` rows; giving
`synthesis_worker` its own model config (it must keep using the specialist's); any migration.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The worker passes its specialist to the inner sub-graph through the config metadata, without dropping the caller's own metadata | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/agents/test_synthesis_worker_specialist.py -q` | exit 0 |
| SC-2 | A step whose metadata carries a specialist records it, and one without it is unchanged | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py -q` | exit 0 |
| SC-3 | A worker step attributes to the specialist's prompts instead of an empty list, and a root-node step is unaffected | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py -q` | exit 0 |
| SC-4 | No user content reaches a step — the boundary is unchanged by the new field | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/agents/test_step_content_leak.py -q` | exit 0 |
| SC-5 | `synthesize` is a configurable node: seeded, listed in the config inventory, and described | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/db/test_seed_agent_config.py tests/api/agent_config -q` | exit 0 |
| SC-6 | Every node that resolves its own model through `get_agent_llm` has a config row, so a new node cannot silently fall back again | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/agents/test_agent_config_coverage.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Carry the specialist through the worker's inner config (wave 1)

- **Files:** apps/api/app/agents/subagents/synthesis_worker.py, apps/api/tests/agents/test_synthesis_worker_specialist.py
- **Action:** In `build_synthesis_worker`'s `worker`, build the inner config by merging
  `{"specialist": agent_name}` into the caller's `metadata` rather than replacing the config:
  take `base = getattr(runtime, "config", None) or {}`, then
  `config = {**base, "metadata": {**(base.get("metadata") or {}), "specialist": agent_name}}`, and
  pass that to `subagent.invoke`. The specialist is a static agent name, never user content.
  New test: a fake sub-agent captures the config it is invoked with and asserts the specialist is
  present AND that a pre-existing metadata key from the caller survives; the unknown-specialist
  early-return path is unchanged.
- **Criteria:** SC-1
- **Interfaces:** Consumes: the worker's existing runtime config and its task state (existing code). Produces: `apps/api/app/agents/subagents/synthesis_worker.py` (specialist in inner config metadata).
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t11.db ../../.venv/bin/python -m pytest tests/agents/test_synthesis_worker_specialist.py tests/agents/test_multi_intent_routing.py -q`
- **Done:** the inner graph receives the specialist and the caller's metadata is not lost.

### Task 1.2 — Record the specialist on the step and attribute its prompts (wave 1)

- **Files:** apps/api/app/agents/metrics.py, apps/api/app/agents/prompt_map.py, apps/api/tests/agents/test_turn_metrics_steps.py, apps/api/tests/agents/test_prompt_map.py
- **Action:** In `TurnMetricsHandler`, read `metadata.get("specialist")` in `on_chat_model_start`
  and `on_tool_start` (the two hooks that receive metadata) and store it as `specialist` on the
  step; leave it `None` when absent. Add it to the step dict `steps()` returns. In
  `prompt_map.enrich_steps` / `prompts_for`, when a step carries a specialist, resolve prompts as
  that specialist's assistant (`PROMPTS_FOR_NODE[f"{specialist}/assistant"]`) instead of the
  worker's empty entry; a step without one keeps today's behaviour exactly. Update the module
  docstring, which currently states the specialist cannot be attributed — it can now. Tests:
  a step with `specialist="concierge"` attributes to concierge + communication_style; a
  `synthesis_worker` step with no specialist still gives `[]`; root-node steps unchanged.
- **Criteria:** SC-2, SC-3, SC-4
- **Interfaces:** Consumes: the metadata key produced by 1.1 (contract: `specialist`). Produces: `apps/api/app/agents/metrics.py` (`specialist` on steps), `apps/api/app/agents/prompt_map.py` (specialist-aware attribution).
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t12.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py tests/agents/test_prompt_map.py tests/agents/test_step_content_leak.py -q`
- **Done:** SC-2, SC-3 and SC-4 pass; the leak test is untouched and still green.

### Task 2.1 — Make `synthesize` a configurable node, and stop the gap recurring (wave 2)

- **Files:** apps/api/app/data/agent_config.py, apps/api/tests/agents/test_agent_config_coverage.py
- **Action:** Add `synthesize` to `AGENT_CONFIG_GROUPS` (the "Support agents" group is its home —
  it is a convergence node, not a specialist) and give it an `AGENT_DESCRIPTIONS` entry describing
  what it does: combine the parallel workers' findings into one answer. `AGENT_CONFIG_NODES`,
  `db/seed.py` and the dashboard grid all derive from that list, so no other file changes and no
  migration is needed. Then add the guard that would have caught this: a new test asserting every
  node name passed to `get_agent_llm` in the graph is present in `AGENT_CONFIG_NODES`. Derive the
  names from the graph/source rather than hardcoding a list, so a future node that resolves its own
  model fails the test instead of silently taking the env default.
- **Criteria:** SC-5, SC-6
- **Interfaces:** Consumes: the existing agent-config group structure and the seeder that derives from it (existing code). Produces: `apps/api/app/data/agent_config.py` (synthesize node), `apps/api/tests/agents/test_agent_config_coverage.py`.
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t21.db ../../.venv/bin/python -m pytest tests/agents/test_agent_config_coverage.py tests/db/test_seed_agent_config.py tests/api/agent_config -q`
- **Done:** SC-5 and SC-6 pass; the dashboard lists `synthesize` among the configurable nodes.

## 5. Risks

- The `specialist` metadata key could collide with a LangGraph-reserved key. It is namespaced by
  nothing today; if a collision appears, rename to `app_specialist` — the contract lives in one
  producer (1.1) and one consumer (1.2).
- Seeding `synthesize` changes which model that node uses on an existing deployment (from the env
  default to the seeded default). That is the intent, but it is a behaviour change on deploy and
  is called out in the SUMMARY.

## 6. Status Log

- 2026-09-03 — intake (f16544d). Corrected one premise from the request: `synthesis_worker` needs
  no `agent_config` row because it resolves the specialist's own model via `worker_resolve`, which
  the live trace confirmed; only `synthesize` was missing. Also found the attribution recoverable
  after all — not from the namespace, but through the config the worker already passes to the
  inner sub-graph.

- 2026-09-03 — wave 1: c0a3c4f (worker merges the specialist into the inner config metadata) and
  63ad630 (handler records it; attribution re-keys onto `<specialist>/assistant`). Controller
  re-verify 484 passed. Review: spec pass, quality approved, two Minors — both fixed in 0ae1a54
  rather than deferred: the node span did not record the specialist so two rows for one node
  disagreed, and the leak test never drove a `specialist` value so it covered only the old surface.

- 2026-09-03 — wave 2: 75687f1 adds `synthesize` to the configurable node list plus the coverage
  guard. The guard is derived from the compiled graph and a source scan, and a negative control
  confirmed it fails by name when `synthesize` is removed — it would have caught the original bug.
  `synthesis_worker`'s exclusion is asserted so it cannot rot into a mystery.

- 2026-09-03 — SHIPPED. verify_summary --check: SC-1..SC-6 all re-run green; 595 passed across the
  agent, agent-config, scripts and db suites. Receipt at `.review-receipt.json`.
