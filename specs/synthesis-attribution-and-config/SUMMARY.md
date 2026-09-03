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

<not started — intake only. Fill at ship.>

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

<fill at ship>

### Alternatives considered

- Parse the specialist from the namespace: impossible — verified against a live turn, it is not
  there.
- Give `synthesis_worker` its own `agent_config` row: wrong fix. It would add a knob that changes
  nothing, because the worker deliberately resolves the specialist's model, not its own.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake evidence | `python3 .claude/scripts/verify_summary.py --lane synthesis-attribution-and-config` | 0 | lane/confidence/reason + rollback present | |

### Not auto-verified

- none yet — intake only; every claim above is a code-reading or live-trace finding.

### Rollback

- `git revert <sha>`. No schema change: the new `agent_config` row is seeded data, removable with
  a `DELETE FROM agent_config WHERE agent_name = 'synthesize'`.

### Harness-Delta

- none
