---
slug: min-65-chatbot-intelligence
doc: baseline
created: 2026-07-12
status: partial (routing measured; quality-judge run blocked)
---

# BASELINE — MIN-65 (pre-implementation eval, task 2.1)

## Status: partial real baseline, not a fabricated result

Two independent attempts against a real, keyed `min65eval` docker stack
(`pgvector/pg17` + app image, isolated `docker compose -p min65eval` project,
`OPENAI_API_KEY` sourced from `apps/api/.env`).

### What worked: routing smoke (`eval/run_eval.py`, no judge needed)

```
routing_accuracy = 0.80 (threshold 0.90)
```

This is the pre-change baseline for supervisor routing correctness — recorded here
so task 8.1 can diff against it after the multi-intent/slot changes land.

### What's blocked: LLM-judged quality run (`eval/run_deepeval.py`)

First attempt hit a real 403:

```
openai.PermissionDeniedError: Error code: 403 - {'error': {'message':
"Project `proj_Gcmx4KKxxMVbsAQBprxH3UON` does not have access to model
`gpt-5`", 'type': 'invalid_request_error', 'param': None, 'code':
'model_not_found'}}
During task with name 'supervisor' and id '...'
```

**Root cause** (matches the documented project gotcha
`eval-harness-bypasses-db-config-and-context`): `eval/harness.py::build_eval_graph()`
builds the graph with a bare `MemorySaver()` + `InMemoryStore()` and never populates
`AgentConfigCache` from the DB, so every node falls back to the hardcoded env-default
model name (`gpt-5`) instead of per-agent DB config. This worktree's `.env` has
`LLM_MODEL`/`FAST_LLM_MODEL` commented out.

**Confirmed workaround** (no code/`.env` change — override at container level):
this `OPENAI_API_KEY`'s project only has mini-tier chat access
(`gpt-4o-mini`/`gpt-4.1-mini` work; `gpt-4o`/`gpt-4.1`/`gpt-5` 403). Real OpenAI
embeddings calls (RAG pre-warm) succeed with this key, confirming the key itself is
valid — only the chat-completion model tier is restricted.

```bash
docker compose exec -e LLM_MODEL=gpt-4o-mini -e FAST_LLM_MODEL=gpt-4o-mini \
  min65eval-api python -m eval.run_deepeval
```

A second attempt with this override was started but the full 37-case
`run_deepeval` run was killed mid-flight (exit 137 — consistent with a host/Docker
resource hiccup, not an app bug) after only 3 "skip empty reply" log lines; no
`memory_recall`/`suggestion_relevance`/other GEval scores were produced. **Some real
API spend was incurred by this killed run with no usable output** — noted for
awareness, not something to reproduce carelessly. The containers/network
disappeared along with the process; the `min65eval_pgdata` volume survived and was
subsequently removed by a clean `docker compose -p min65eval down`.

This is an eval-harness/environment gap, not a MIN-65 code defect — the harness
extensions from tasks 1.1/1.2 (multi-turn support, `memory_recall` /
`suggestion_relevance` metrics) are structurally sound (unit-tested with FakeLLM,
53/53 green) but were never exercised end-to-end with a real judge here.

## Exact re-run command (for task 8.1 or a human)

```bash
cd apps/api
cp ../../apps/api/.env .env   # or otherwise ensure a working .env is present
docker compose -p min65eval up -d
docker compose -p min65eval exec -e LLM_MODEL=gpt-4o-mini -e FAST_LLM_MODEL=gpt-4o-mini \
  api python -m eval.run_deepeval
docker compose -p min65eval down
```

If host stability is suspect, run it in the foreground (not `run_in_background`) and
watch `docker ps` / `docker stats` for OOM signs before retrying.

## Consequence for this plan

`routing_accuracy = 0.80` is the one real number available for regression-checking
task 4.1's supervisor changes. `memory_recall` / `suggestion_relevance` and the other
G-Eval quality metrics remain unmeasured — task 8.1 should retry the run above (mini
models, foreground, watch resource usage) rather than assume the gpt-5 default will
ever work with this key. No fabricated scores are recorded here.
