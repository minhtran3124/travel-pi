# synthesis-attribution-and-config — Summary

Lane: normal
Confidence: high
Reason: no manifest hard gate fires — no migration, no new route, no auth or authorization change. Flags: existing behavior (the worker's inner invoke gains config metadata; the metrics handler records one more field) and multi-domain (agents, metrics, prompt map, config data, dashboard grid, tests). Both fixes have a single obvious approach, so no design fork.
Flags: existing behavior, multi-domain
Affects: apps/api/app/agents/subagents/synthesis_worker.py, app/agents/metrics.py, app/agents/prompt_map.py, app/data/agent_config.py, tests/{agents,api/agent_config}
Input-type: change request
Route: normal — PLAN.md → branch `fix/synthesis-attribution-and-config` (off main) → subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> - attribution prompt trống trên nhánh multi-intent
> - synthesize/synthesis_worker thiếu row agent_config nên rơi về model mặc định
>
> newbranch va lam 2 cai nay di

## What changed

Both follow-ups closed, and the second one narrower than the request implied.

- **Attribution.** The synthesis worker merges its specialist into the metadata of the config it
  invokes the inner sub-graph with — the one channel that reaches the callback hooks, since the
  checkpoint namespace never carries it. The handler records it on LLM, tool and node steps, and
  attribution re-keys such a step onto `<specialist>/assistant`. A multi-intent turn's steps now
  resolve to e.g. concierge + communication_style instead of an empty list.
- **Config.** `synthesize` joins the configurable node list, so it stops resolving the env default
  model. `synthesis_worker` deliberately gets no row. A coverage test now asserts every node that
  resolves a model through `get_agent_llm` has a row, with names derived from the compiled graph
  and a source scan rather than a hand-written list — removing `synthesize` makes it fail by name,
  so it would have caught the original bug.

### Intake findings (one premise corrected)

- **`synthesis_worker` does not need an `agent_config` row.** It resolves the *specialist's* model
  at runtime through `worker_resolve` → `resolver_for(agent_name)` (`graph.py:150-156`), so a
  worker running concierge already uses concierge's configured model. The live trace confirms it:
  the worker's inner `assistant` calls used `gpt-5.4-mini` (the specialist's row) while only
  `synthesize` fell back to the env default `gpt-5`. **Only `synthesize` is missing a row** —
  it resolves via `pick(SYNTHESIZE_NODE)` → `get_agent_llm("synthesize")` (`graph.py:162-166`).
- **The specialist name is recoverable after all, but not from the namespace.** A live
  multi-intent turn's checkpoint namespace is `synthesis_worker:<uuid>|assistant:<uuid>` — no
  specialist segment. However the worker invokes the inner sub-graph with
  `subagent.invoke(inner_state, config=runtime.config)`
  (`synthesis_worker.py`), so the specialist can be merged into that config's `metadata` and will
  then reach `on_chat_model_start` / `on_tool_start`, which both receive `metadata`.
- `AGENT_CONFIG_NODES` is derived from `AGENT_CONFIG_GROUPS` (`app/data/agent_config.py`), which
  also drives `db/seed.py` and the dashboard grid — adding a node there covers seeding, the UI and
  the description in one place, with no migration.

### Scope

In:
- Add `synthesize` to `AGENT_CONFIG_GROUPS` + `AGENT_DESCRIPTIONS` so it is seeded, configurable
  from the dashboard, and no longer silently falls back to the env default model.
- Pass the specialist name through the worker's inner-graph config metadata; record it on the
  step; use it so a `synthesis_worker` step attributes to the specialist's prompts instead of `[]`.

Out: changing how models are resolved; per-worker prompt overrides; back-filling prompts onto the
`agent_run_steps` rows already written; any migration (the new node is data, not schema).

### Rationale

The specialist is threaded through config metadata rather than recovered from the namespace
because a live turn proved it is not in the namespace at all. The merge is deliberate: replacing
the config would drop `langgraph_node` and the checkpoint namespace, which the handler keys node
timing and dedupe on, so a test pins the caller's metadata surviving — a "specialist is present"
assertion alone would pass while that regression shipped.

`synthesize` is added to the group list rather than seeded directly because the seeder, the node
inventory and the dashboard grid all derive from that one list, so a single data edit covers all
three with no migration.

### Alternatives considered

- Parse the specialist from the namespace: impossible — verified against a live turn, it is not
  there.
- Give `synthesis_worker` its own `agent_config` row: wrong fix. It would add a knob that changes
  nothing, because the worker deliberately resolves the specialist's model, not its own.

### Deviations

- Rule 1 (controller, wave-1 review): the node span did not record the specialist, so a worker's
  `assistant` node row and the LLM row inside it disagreed on the detail page; `on_chain_start`
  now records it too.
- Rule 2 (controller, wave-1 review): the leak test was byte-unchanged but never drove a
  `specialist` value, so it proved the boundary for the old surface only. It now hands the handler
  a hostile specialist and asserts the stored row is clean.
- Task 2.1 reported running `git checkout --` on its own file during a negative-control check and
  re-applying the edit; the controller verified the final file content independently.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| worker passes the specialist, merge preserves caller metadata | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s1.db ../../.venv/bin/python -m pytest tests/agents/test_synthesis_worker_specialist.py -q` | 0 | configurable + caller keys survive; None-config path; unknown specialist untouched | SC-1 |
| handler records the specialist | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s2.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py -q` | 0 | present when given, None when absent | SC-2 |
| specialist-aware attribution | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s3.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py -q` | 0 | worker step -> specialist prompts; no specialist -> unchanged | SC-3 |
| content boundary unchanged | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s4.db ../../.venv/bin/python -m pytest tests/agents/test_step_content_leak.py -q` | 0 | hostile specialist never reaches the stored row | SC-4 |
| synthesize is configurable | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s5.db ../../.venv/bin/python -m pytest tests/scripts tests/api/agent_config -q` | 0 | seeded, listed, described | SC-5 |
| no node can fall back silently again | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s6.db ../../.venv/bin/python -m pytest tests/agents/test_agent_config_coverage.py -q` | 0 | derived from the graph + a source scan; negative control fails by name | SC-6 |

### Not auto-verified

- The end-to-end result on a real multi-intent turn — reached traceability (each link is unit
  tested: the worker sets the metadata, the handler records it, attribution consumes it), but no
  live turn was driven after the change, so the rendered detail page has not been seen with a
  populated prompt column on the worker path.
- The behaviour change from seeding `synthesize` — on an existing deployment that node moves from
  the env default to the seeded default model. Intended, but it takes effect on the next seed run
  and was not exercised against a live graph here.

### Rollback

- `git revert <sha>`. No schema change: the new `agent_config` row is seeded data, removable with
  a `DELETE FROM agent_config WHERE agent_name = 'synthesize'`.

### Harness-Delta

- Several stale plans still carry `status: active`, so `hooks/lib/lane.sh` resolves the first one
  lexically (`specs/conversation-persistence`) rather than the spec being worked on. It only warned
  here because that SUMMARY has no `Lane:` line and the diff trips no hard gate, but it makes the
  corroboration signal unreliable. Flipping shipped plans to `shipped` would fix it.
- Implement-only subagents have no documented non-git way to undo an edit for a negative-control
  check; one reached for `git checkout --` and lost its own work.
