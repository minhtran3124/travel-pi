---
type: architecture
title: Agent graph and supervisor routing
description: How the LangGraph travel-agent graph is assembled and how a turn flows from the PII guardrail through context loading, summarization, supervisor intent classification, task routing (single specialist, booking HITL plan, or parallel synthesis workers), synthesis and the bounded reflection loop.
tags: [langgraph, agent, supervisor, routing, multi-intent, reflection, hitl]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-21T09:19:54.601Z
sources:
  - id: openwiki-source-653637f2675661d4499c6d01
    resource: repo://apps/api/app/agents/constants.py
  - id: openwiki-source-a9279e30fdd03870c290e7ae
    resource: repo://apps/api/app/agents/graph.py
  - id: openwiki-source-7d788caf34a07e0d61dc3cd0
    resource: repo://apps/api/app/agents/nodes.py
  - id: openwiki-source-8929e56b195ad687c407cb68
    resource: repo://apps/api/app/agents/subagents/synthesis_worker.py
  - id: openwiki-source-6bf7699cddc35845704fa65b
    resource: repo://apps/api/app/agents/supervisor.py
  - id: openwiki-source-7e0cf60011c1a3e7f23d92e0
    resource: repo://apps/api/tests/agents/test_hitl_plan.py
  - id: openwiki-source-d4d8f3bb02b1bc007a632719
    resource: repo://apps/api/tests/agents/test_ledger_early_exit.py
  - id: openwiki-source-fd4516e413d1199b3d2e9be7
    resource: repo://apps/api/tests/agents/test_multi_intent_routing.py
generated: { by: "claude-code", at: "2026-09-21T09:19:54.601Z" }
---

# Agent graph and supervisor routing

The conversational assistant is one compiled LangGraph `StateGraph` built by `build_graph` in `apps/api/app/agents/graph.py`. It is compiled once per process during FastAPI startup (see [Backend request lifecycle](../architecture/backend-request-lifecycle.md)) with a checkpointer and a long-term store, stored on `app.state.travel_graph`, and rebuilt in place when the per-agent model configuration changes (see [LLM providers and per-agent configuration](llm-providers-and-agent-config.md)).

## Topology

```
START -> pii_guardrail -> load_context -> summarize -> supervisor -> route_tasks
route_tasks fans out to one of:
  - a single specialist node (planner | concierge | journal | booking | budget) -> reflection
  - plan (booking human-in-the-loop gate) -> booking -> reflection
  - Send(synthesis_worker) x N -> synthesize -> reflection
reflection -> <specialist> | synthesize | END
```

Key facts about the assembly (`graph.py`):

- **The PII guardrail is the first node**, deliberately placed before any model call, checkpointer write, or memory extraction can observe the turn. Its behavior is documented in [Guardrails](guardrails-pii-and-hitl.md).
- **Each node resolves its own LLM.** Non-specialist nodes (`supervisor`, `summarize`, `synthesize`, `reflection`) get a fixed model via `pick()`; specialist nodes get a deferred per-request resolver that memoizes built models per `ctx_model` hint inside the closure. Tests inject `llm` / `fast_llm` fakes which override the whole tier regardless of the per-request hint, and the memo cache is fresh per `build_graph` so fakes never leak between builds.
- **Nodes that call an LLM carry `LLM_RETRY`** as their LangGraph retry policy (`supervisor`, `summarize`, `synthesize`, `reflection`).
- **Declared destinations are load-bearing.** `plan` declares `("booking", "__end__")`; `reflection` declares every specialist, the `synthesize` node and `END`. `SYNTHESIZE_NODE` must equal a declared destination or a reflection REVISE routed via `goto=current_flow` is silently dropped by LangGraph (`constants.py`).
- **The compiled graph carries two extra attributes**: `extract_memory_llm` (the model the router uses for the background memory extractor, so it shares the same injection seam) and `prompt_versions` (a snapshot taken at build time so run attribution reports the versions actually baked in, not whatever `active.yaml` says later; see [Prompt registry](prompt-registry.md)).

The graph is always driven asynchronously in production (`ainvoke` / `astream` from the agent router), and the synthesis worker must stay `async` because several planner/concierge tools are async-only; a sync invoke inside it made the whole `tools` node fail and produced false "temporarily unavailable" reports (`synthesis_worker.py` module docstring, issue #178).

## Pre-routing nodes

**`load_context`** (`nodes.py`) is best-effort and resets per-turn state before anything else runs: `plan_approved`, `awaiting_user`, `tasks` and `task_results` are cleared at the start of every fresh turn. A resume turn (`Command(resume=...)`) does *not* re-enter this node, which is exactly why the approving turn keeps `plan_approved=True` long enough for background memory extraction to read it. It then loads, into plain state fields rather than into `messages`, the active trip snapshot (through the owner-scoped `TripService`, so a foreign `trip_id` yields nothing rather than leaking a title into the prompt), standing instructions, profile and non-profile preferences from the long-term store. Instructions and preferences are read as typed rows so each line can carry a month-granularity `(recorded …)` age marker built by `_with_age`; a row without a usable `updated_at` renders with no marker. Carrying context in state fields rather than as an appended `SystemMessage` keeps a single leading system message intact for providers that require it; `system_with_summary` injects them at the front of every model call (see [Agent state, runtime context and reply language](state-context-and-language.md)).

**`summarize`** compresses older turns into `state["summary"]` only when `should_summarize` says the history is long or token-heavy enough; otherwise it is a no-op. It passes the existing rolling summary back in so a new compression merges with it, and returns no update when nothing was removable, so an existing summary is never blanked. Details live in [Conversation memory and persistence](memory-and-persistence.md).

## The supervisor

`make_supervisor` (`supervisor.py`) binds the routing model with `with_structured_output(SupervisorIntent, method="function_calling")`. The `function_calling` method is chosen deliberately to avoid OpenAI's native JSON-schema parse path, whose parsed field trips a Pydantic serializer warning in `langchain-openai`.

`SupervisorIntent` carries:

- `target_agent`: one of the five specialists.
- `plan`: optional list of *additional independent* specialists to run in parallel this turn. `booking` can never appear here (the secondary-target literal excludes it), and a `before` validator degrades malformed values (nested objects, unknown names, non-lists) to bare names or drops them with a warning instead of failing the whole routing decision. The validator is written so that unhashable model output cannot escape as a `TypeError` (GH-180).
- `task_queries`: optional per-specialist restatement of the message, positionally aligned with `[target_agent, *plan]`; a second `before` validator wraps bare strings and blanks non-string entries while *preserving positions* so the alignment check still holds.
- `language`: the traveller's dominant conversation language, fed back as the "established" language so a lone interjection does not flip it.
- `slots`: verbatim trip mentions (destination, dates as free text, counts, budget text, cabin class, hotel area).

The node prepends the established language to the supervisor prompt, grounds the current date as the outermost (last) system addition so the cacheable prefix stays stable, and invokes the router over the full message list.

### Decisions the supervisor makes in code, not in the model

1. **Unknown intent ends the turn** with a localized `unknown_intent` system reply.
2. **Tier gate**: when `AgentContext.allowed_subagents` excludes the target, the turn ends with a localized `booking_upgrade` reply. Because `plan` is only reachable through this branch, this is also what keeps free-tier users out of the booking HITL path.
3. **Slot normalization** ("LLM parses, code computes"): raw date text is resolved with `resolve_travel_date` and *dropped* if ambiguous or unparsable, never guessed; counts must be positive (children may be zero); budget is reduced to "number + optional currency hint" or dropped. Only resolved keys are emitted as `trip_facts`, because the reducer treats an absent key as "no update", not "delete".
4. **Task list construction**: the primary intent is task 0; follow-ons from `plan` are deduplicated, filtered against the tier allow-list and `booking`, and capped so the total never exceeds `MAX_LEDGER_STEPS` (4), which keeps the parent graph inside `agent_recursion_limit` with room for the revise loop. A `booking` target always produces exactly one task with no follow-ons.
5. **Per-task queries**: only when there is more than one task *and* `task_queries` has the same length as the model's own `[target, *plan]` list are queries trusted; otherwise, and always for a single task, the last user message is used verbatim (a model paraphrase can drop counts or dates). Queries shorter than three characters fall back too.

The node returns a `Command` updating `current_flow`, `language`, `trip_facts` and `tasks`.

## Routing: `route_tasks`

`route_tasks` (`nodes.py`) is the conditional edge after the supervisor:

- no tasks → `END` (the supervisor already wrote a reply);
- first task is `booking` → `plan`;
- exactly one task → that specialist node directly (the pre-existing single-intent path is preserved unchanged);
- more than one task → a list of `Send("synthesis_worker", {**state, "task": t})`, one per task.

`Send` does **not** merge parent state into the worker input, so the payload carries a shallow copy of the whole parent state plus the task. Test `test_route_tasks_passes_parent_state_to_parallel_workers` pins this.

## Parallel synthesis workers and `synthesize`

A **synthesis worker** (`subagents/synthesis_worker.py`) wraps the *same* compiled specialist subgraph used on the single-intent path, so prompts, tools and tool-fault policies are identical. Per invocation it:

- deep-copies `messages` so the inner `add_messages` reducer never mutates the parent list;
- narrows `tasks` to `[task]` and sets `current_flow` to the specialist (the inner subgraph drops undeclared keys, so the specialist reads its slice from `tasks`);
- merges `{"specialist": name}` into the run config metadata, the only channel that reaches the metrics callbacks (see [Observability](observability-and-metrics.md));
- awaits the specialist, takes the last content-bearing `AIMessage` as `findings`, and emits one `task_results` entry;
- propagates back only `trip_id` and `awaiting_user`, and only when they actually changed, so parallel siblings cannot overwrite each other's mutations with stale values.

Unknown specialists produce a "no facts gathered" result instead of an error. Workers always `goto` the `synthesize` node.

`synthesize` sorts `task_results` by `index`, asks its model for a single answer in the conversation language, and sets `current_flow` to its own node name so a later REVISE re-enters synthesis rather than being dropped. Test `test_reflection_revise_after_synthesis_re_enters_synthesize` covers that path, and `test_task_results_cleared_between_turns` confirms results do not leak across turns.

## The booking HITL gate: `plan`

`plan_node` calls `interrupt({"type": "plan_approval", "draft": <last message>})`. The caller resumes with `Command(resume={"approved": bool})`. On rejection it ends with a localized "booking cancelled" reply; on approval it sets `plan_approved=True` and routes to `booking` **without** emitting an AI message, because a "plan approved" line would be streamed as a token and then wiped by the stream mapper's sub-agent handoff reset. The client renders approval as an activity step. Tests in `test_hitl_plan.py` cover the interrupt, both resume outcomes, that non-booking flows never interrupt, and that `plan_approved` resets on the next turn. See [Guardrails](guardrails-pii-and-hitl.md) for the wider safety picture.

## Reflection: bounded self-review

`make_reflection_node` judges the last message with the `reflection` prompt and either accepts it (`END`) or, when the verdict contains `REVISE`, increments `revisions`, appends `REFLECTION_REVISE_NOTE` as a **SystemMessage** (never a HumanMessage, so language detection and "latest traveller message" rules do not misfire) and routes `goto=current_flow`. Three guards run **before** the judge call:

1. `awaiting_user` is set → `END`. A clarifying question is an intentionally incomplete answer; reviewing it would re-run the specialist and answer without the missing detail (MIN-68).
2. A booking write tool (`book_flight` / `book_hotel`) succeeded since the last `HumanMessage` → `END`. A REVISE would re-run the booking specialist and double-book (gh-193). "Succeeded" means a `ToolMessage` whose `status` is not `"error"`.
3. `allow_reflection` is false or `revisions >= max_revisions` (both from `AgentContext`, defaulting to enabled and 1) → `END`.

`test_supervisor.py::test_reflection_revise_loops_back_then_stops` and `test_ledger_early_exit.py::test_blocked_turn_survives_revise_prone_reflection` pin the loop bound and the awaiting-user exit respectively.

## Early exits and single-turn flags

The "ledger early exit" design (MIN-68) makes `awaiting_user` a single-turn flag: a specialist that calls the clarification tool marks the turn as blocked, reflection ends it without review, and the next turn's `load_context` clears it so fresh work is never abandoned. `tasks`, `task_results` and `plan_approved` follow the same per-turn reset.

## Where to look next

- Specialist internals, the tool registry and tool-fault handling: [Specialist sub-agents and the tool registry](specialists-and-tools.md).
- State channels, reducers, trip facts and the reply-language rule: [Agent state, runtime context and reply language](state-context-and-language.md).
- Checkpointer, store and background memory extraction: [Conversation memory and persistence](memory-and-persistence.md).
- How the graph's events become SSE events and side panels: [Agent chat endpoints, SSE streaming and side panels](streaming-and-side-panels.md).
