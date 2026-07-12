---
slug: min-65-chatbot-intelligence
doc: baseline
created: 2026-07-12
status: documented-skip
---

# BASELINE — MIN-65 (pre-implementation eval, task 2.1)

## Status: documented-skip (real blocker, not a fabricated result)

Attempted a real, keyed run against `min65eval-api-1`/`min65eval-db-1` (isolated
`docker compose -p min65eval` project, `pgvector/pg17` + the app image, real
`OPENAI_API_KEY` sourced from `apps/api/.env`). The run reached the supervisor node
on the first eval case and failed:

```
openai.PermissionDeniedError: Error code: 403 - {'error': {'message':
"Project `proj_Gcmx4KKxxMVbsAQBprxH3UON` does not have access to model
`gpt-5`", 'type': 'invalid_request_error', 'param': None, 'code':
'model_not_found'}}
During task with name 'supervisor' and id '...'
```

## Root cause

Matches a previously-documented project gotcha (`eval-harness-bypasses-db-config-and-context`):
`eval/harness.py::build_eval_graph()` builds the graph with a bare `MemorySaver()` +
`InMemoryStore()` and never populates `AgentConfigCache` from the DB. Every node
therefore falls back to the hardcoded env-default model name (`gpt-5`), not whatever
model is actually configured per-agent in `agent_config`. This worktree's `.env` has
`LLM_MODEL`/`FAST_LLM_MODEL` commented out, so nothing overrides the default, and the
current `OPENAI_API_KEY`'s project does not have `gpt-5` access.

This is an eval-harness/environment gap, not a MIN-65 code defect — the harness
extensions from tasks 1.1/1.2 (multi-turn support, `memory_recall` /
`suggestion_relevance` metrics) are structurally sound (unit-tested with FakeLLM,
53/53 green) but were never exercised end-to-end with a real judge here.

## What would unblock a real run

One of:

1. Set `LLM_MODEL=openai/<model this key's project can access>` (and `FAST_LLM_MODEL`)
   in `apps/api/.env` before bringing the eval containers up, **or**
2. Fix `build_eval_graph()` to call `AgentConfigCache.reload_from_db()` (or seed
   `agent_config` rows) before building the graph, so per-agent model config from the
   DB is honored instead of the env fallback — the more durable fix, but out of
   MIN-65's scope (pre-existing MIN-58 harness gap, not something this ticket's
   plan should silently expand into).

## Exact re-run command (once unblocked)

```bash
cd apps/api
cp ../../apps/api/.env .env   # or otherwise ensure a working .env is present
docker compose -p min65eval up -d
docker exec min65eval-api-1 python -m eval.run_deepeval
docker compose -p min65eval down
```

## Consequence for this plan

Task 8.1 (final eval vs baseline) inherits the same blocker unless the model-config
gap above is resolved first. Recommend surfacing this to the user as a follow-up
before/alongside task 8.1: either fix the env/model config, or accept that MIN-65
ships with `make test`/`make test-docker` (unit-level) proof only, and the
LLM-judged quality delta is measured manually post-merge once a working model/key
combination is confirmed.

No fabricated scores are recorded here. `memory_recall` / `suggestion_relevance`
numbers remain unmeasured pending the fix above.
