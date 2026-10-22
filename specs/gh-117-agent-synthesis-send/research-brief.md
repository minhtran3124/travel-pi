# Research Brief — gh-117-agent-synthesis-send

## What already exists locally

### Multi-intent dispatch (shipped workaround)
- `apps/api/app/agents/state.py` — `TravelAgentState` carries `pending_flows: list[str]` (ordered ledger of follow-on sub-agents) and `superseded_message_ids: list[str]` (hides previous sub-agents' prose from follow-on sub-agents and SSE).
- `apps/api/app/agents/supervisor.py` — `SupervisorIntent` emits `target_agent` plus optional `plan` (ordered follow-ons). The supervisor normalizes the plan, caps length at `MAX_LEDGER_STEPS`, excludes `booking`, and applies tier gating.
- `apps/api/app/agents/nodes.py` — `dispatch_next` drains `pending_flows` serially, marks the last sub-agent answer as superseded, and routes to reflection when empty.
- `apps/api/app/agents/subagents/_base.py` — each sub-agent is a compiled ReAct subgraph (`StateGraph`) with an `assistant` node + optional `tools` node. The assistant filters out messages whose ids are in `superseded_message_ids`.
- `apps/api/app/agents/graph.py` — wires `load_context → summarize → supervisor → (sub-agent → dispatch_next)* → reflection`. Sub-agents are added as static compiled subgraph nodes.
- `apps/api/app/streaming/mapper.py` — SSE mapper suppresses intermediate sub-agent prose tokens when `pending_flows` is non-empty and emits `reset` between revised answers.
- Tests: `tests/api/agent/test_agent_chat.py` and `tests/api/agent/test_stream_events.py` cover the #117 workaround behavior.

### LangGraph capabilities relevant to Path A
- `Send` API (`langgraph.types.Send`) lets a conditional edge dispatch a node multiple times, each with a distinct state slice. This is the canonical map-reduce pattern.
- Subgraphs can be invoked dynamically via `Send` if the target is a compiled subgraph node.
- `Command(update=..., goto=...)` can route to multiple destinations; returning a list of `Send` objects from a conditional edge runs them in parallel in the next superstep.
- State reducers are required when parallel branches write to the same key.
- `MessagesState.add_messages` reducer handles message idempotency and appends.

## Gaps to close for Path A
1. Current sub-agents are static nodes; we need a worker invocation pattern that accepts per-task state via `Send`.
2. Need a place to hold structured sub-agent results before synthesis (new state key + reducer).
3. Need a `synthesize` node that consumes results and emits one final answer.
4. Streaming mapper must emit only the synthesized answer, not per-sub-agent prose.
5. Reflection needs to review the synthesized answer or be bypassed/restructured.
6. HITL `plan → booking` path must remain untouched.

## Reuse vs. build
- Reuse: existing sub-agent prompts, tools, tool-error handling, `AgentContext`, `TravelAgentState` base, checkpoint/store wiring.
- Build: new "orchestrator worker" invocation, new state keys for tasks/results, new synthesis node, new streaming/mapper logic, new tests.
