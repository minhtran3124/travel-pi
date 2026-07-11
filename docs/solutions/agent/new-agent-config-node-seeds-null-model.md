---
problem_type: bug
module: agent/config
tags: agent-config, seed, llm, get_agent_llm, fast-agents, 403, silent-degradation, deploy
severity: critical
applicable_when: Adding a NEW agent-config node (a new sub-agent, or any component that calls get_agent_llm with a new name) — including a tool that makes its own LLM call.
affects:
  - apps/api/app/data/agent_config.py
  - apps/api/app/db/seed.py
  - apps/api/app/clients/llm.py
  - apps/api/scripts/seed_agent_config.py
supersedes: null
confidence: high
confirmed_at: 2026-07-11
---

## Problem

A brand-new agent node (`date_resolution`, the LLM date parser behind `resolve_date`) worked in
every test, then failed on **every single call** against the running Docker stack. The user-visible
symptom was the agent apologising:

> "Mình chưa chốt được **thứ 6 tuần sau** vì hệ thống đang lỗi khi đổi ngày."

The tool trace showed `resolve_date` being called and nothing after it. The container log showed:

```
[httpx] INFO: HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 403 Forbidden"
```

Every *other* agent node was working fine at the same moment.

## Root Cause

Two mechanisms combine, and each looks harmless alone.

1. **`app/db/seed.py::_seed_agent_config` inserts the row with only `agent_name`** — `provider`,
   `model` and `base_url` are left NULL. So the node *appears* configured (the row exists, the
   dashboard lists it) while carrying no model.

2. **`get_agent_llm(name)` treats a NULL/absent override as "use the env default"** and falls back
   to `get_llm(fast=name in FAST_AGENTS)` → `settings.fast_llm_model` → `gpt-5-mini` **against
   OpenAI directly**. On an account that reaches models through a gateway, that is a 403.

The working nodes were not working by luck — they had real rows:

```
   agent_name    | provider |    model
-----------------+----------+--------------
 booking         | openai   | gpt-5.4-mini
 planner         | openai   | gpt-5.4-mini
 date_resolution |          |                <-- NULL: falls back to the env model
```

The env fallback is the trap: it makes a misconfigured node look configured, and the failure only
appears at the provider boundary, at runtime, in one feature.

## Fix

Seed the new node with the same provider/model as its siblings, then rebuild the graph (the config
cache and the graph are both built at lifespan):

```bash
docker exec -w /app -e PYTHONPATH=/app api-api-1 \
  python scripts/seed_agent_config.py --provider openai --model gpt-5.4-mini --nodes date_resolution

docker exec api-api-1 touch app/main.py   # rebuild the graph / reload the config cache
```

Note `-w /app -e PYTHONPATH=/app`: without them the script dies with `ModuleNotFoundError: No module
named 'app'` inside the container.

Checklist when adding any node that calls `get_agent_llm`:

1. `app/data/agent_config.py` → add to `AGENT_CONFIG_GROUPS`/`AGENT_CONFIG_NODES` **and**
   `AGENT_DESCRIPTIONS` (the dashboard breaks on a node with no description).
2. `app/agents/constants.py` → add to `FAST_AGENTS` if it should use the cheap model.
3. **Seed the row's provider/model in every environment.** The startup seeder will NOT do this for
   you — it only inserts the name.

## Regression Test

`tests/scripts/test_seed_agent_config.py` asserts the seeded set equals `AGENT_CONFIG_NODES`, so a
node missing from the data module is caught. It does **not** catch a NULL model — that is an
environment/data state, not code. The mechanical guard that would catch it is a startup check that
every `AGENT_CONFIG_NODES` row has a non-NULL provider+model, failing loudly at boot instead of at
the first provider call. Not built yet (see the improvement backlog).

While fixing this, the same test's `assert len(rows) == 9` was replaced with
`len(AGENT_CONFIG_NODES)` — the set assertion on the line above already pins *which* nodes exist, so
the literal count added no coverage and broke only when a legitimate node was added.

## Prevention

- **A new agent node is a deploy step, not just a code change.** Ship the seed command with it.
- When a feature works in tests and fails everywhere in the real stack, suspect **config/data state,
  not logic** — and read the container log for the provider's HTTP status before reading the code.
- Design the failure so it is loud: `resolve_date` converts the provider error to a `ToolException`,
  so the agent asked for a concrete date instead of inventing one. The feature degraded; it did not
  lie. That property is worth preserving in any tool that calls an LLM.

## Related

- [llm-parses-code-computes](llm-parses-code-computes.md)
- [langgraph-thread-reset-and-prompt-reload](langgraph-thread-reset-and-prompt-reload.md)
- [local-postgres-checkpointer](local-postgres-checkpointer.md)
