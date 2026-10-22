# multi-intent-single-path — Research brief

Depth: **Deep** (high-risk lane). Surface: none external (local refactor of the agent graph;
LangGraph `Send`, `Command`, `StateGraph` APIs already in use, pinned `langgraph>=1.0,<2.0`).

## What already exists (reuse)

| Need | Existing seam | Evidence |
| --- | --- | --- |
| Parallel fan-out + single answer | `route_tasks` → `Send("synthesis_worker")` → `synthesize` → `reflection` | `nodes.py:301-333`, `graph.py:163-195`, `synthesis_worker.py` |
| Clarification early-exit without `dispatch_next` | `reflection` already returns `END` when `awaiting_user` | `nodes.py` reflection node (MIN-68 guard) |
| Sequential executor for a dependent chain | the planner sub-agent's own ReAct loop (`_base.py` assistant ⇄ ToolNode) with the full planner toolset | `tools/registry.py TOOLS_BY_DOMAIN["planner"]` |
| Versioned prompt flip | `prompts/registry.py`, `active.yaml`, `CHANGELOG.md`; graph rebuild on config generation | `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md` |
| Task dedupe point | `supervisor.py` task-list build (`task_agents`) | `supervisor.py:308-336` |
| Multi-intent goldens + FakeLLM graph tests | `eval/datasets/multi_intent.json`; `tests/agents/test_multi_intent_routing.py`, `test_task_ledger.py` | both graph-level |

## What is missing

- No supervisor rule for "dependent chain inside one toolset → one specialist"; v8 only says
  "pick the one that unblocks the user first" and the `plan` field description contradicts the
  runtime.
- No dedupe of recurring specialists in `tasks` (parallel duplicates).
- No test that a dependent chain routes to a single planner task; no plan-everything golden; no
  recursion-budget assertion for a long specialist loop.
- No proof that removing the mapper's legacy suppression leaves SSE output byte-identical for
  single-intent, multi-intent and reflection-revision turns (`tests/api/agent/test_stream_events.py`
  covers shape; add a multi-intent token/reset count assertion).

## Lightest credible path

Three waves in dependency order: (1) supervisor semantics + prompt v9 (stop emitting
`pending_flows`; dedupe; truthful `plan` description; routing rule) — behaviour-visible, so it
gets the routing/golden tests first; (2) remove the dead machinery and rewire sub-agents →
reflection, plus the mapper cleanup, in disjoint files; (3) plan-everything golden + recursion
check + docs. No new abstraction, no new node.

## Source Pack

- none (local-only; no external surface — LangGraph primitives already pinned and in use).
