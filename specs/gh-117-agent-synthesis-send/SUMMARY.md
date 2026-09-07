# gh-117-agent-synthesis-send — Summary

Lane: high-risk
Confidence: medium
Reason: Public-contract hard gate (client-visible /agent/chat and /agent/stream answer behavior) plus changes to shipped, test-covered multi-intent dispatch (#117) across agents, streaming, and tests.
Flags: public contracts, existing behavior, weak proof, multi-domain
Affects: apps/api/app/agents/ (graph topology, state, supervisor, subagents, nodes), apps/api/app/streaming/mapper.py, apps/api/app/routers/agent.py — public /agent/chat and /agent/stream response behavior
Input-type: change request
Route: high-risk chain: /brainstorming → /xia2 → /writing-plans → /using-git-worktrees → /subagent-driven-development; record architecture decision via /compound
Escalate: no (user explicitly selected Path A after reviewing risk trade-offs; public-contract hard gate acknowledged)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> User chose Path A after a detailed comparison of Options A and B.

Implement a proper decompose → execute → synthesize architecture for GitHub issue #117
(duplicate streaming responses on multi-intent turns) by refactoring the travel agent graph
to use LangGraph's `Send` / map-reduce pattern. The supervisor decomposes a multi-intent user
message into parallel sub-tasks, dispatches each sub-agent via `Send`, and a synthesis node
combines their structured results into one final answer. The REST `/agent/chat` and SSE
`/agent/stream` endpoints must return only that synthesized answer, replacing the current
"last answer wins" workaround (`superseded_message_ids` + token suppression).

Scope: Path A only — LangGraph `Send`/subgraph map-reduce. Not the minimal serial-synthesis
workaround (Path B), which was explicitly rejected.

### What changed

- Added `app/agents/schemas.py` with `AgentTask` and `TaskResult` models.
- Extended `TravelAgentState` with `tasks` (last-write-wins) and `task_results`
  (append reducer) state keys; `load_context_node` resets them per turn.
- Refactored `supervisor` to emit an ordered `tasks` list and removed its
  `Command(goto=...)` routing.
- Added `route_tasks` conditional edge that routes single-intent turns to the
  existing static sub-agents, booking to the HITL `plan` node, and multi-intent
  turns to parallel `synthesis_worker` instances via LangGraph `Send`.
- Added `app/agents/subagents/synthesis_worker.py`: a worker subgraph that reuses
  each specialist's existing compiled sub-agent, extracts its final prose answer
  as a structured finding, and returns it via `task_results`.
- Added `make_synthesize_node` that sorts `task_results` and asks the LLM to
  write one final user-facing answer.
- Updated `app/streaming/mapper.py` to suppress prose from `synthesis_worker`
  subgraphs and stream only the top-level `synthesize` node's tokens.
- Updated tests across `tests/agents/` and `tests/api/agent/` to assert the new
  parallel-synthesis behavior while preserving single-intent coverage.

### Rationale

LangGraph `Send` / map-reduce is the canonical pattern for decompose → execute →
synthesize. The hybrid routing keeps the proven single-intent path untouched and
only activates the new architecture for multi-intent turns, the only case with
user-visible duplication.

### Alternatives considered

- **Path B — serial synthesis node inside the existing graph:** rejected by the user after a
detailed comparison. It would have been smaller and lower-risk, but it still runs sub-agents
serially and requires sub-agents to "know" they are intermediate. Path A is the user's chosen
"proper" distributed pattern.

### Deviations

- Workers reuse the existing sub-agent subgraphs (which append prose to the shared
  `messages` channel) instead of isolated per-worker message channels. This means
  intermediate sub-agent prose still appears in checkpointed `messages`, but the
  synthesizer's answer is the last message and is what REST/SSE return. Isolating
  worker messages is a future refinement.
- Multi-intent clarification / `awaiting_user` does not abort already-running
  parallel workers. The reflection node's existing `awaiting_user` guard still
  ends the turn cleanly after synthesis.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Agent unit + integration | `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/ tests/api/agent/ -q` | 0 | 341 passed |
| Lint touched files | `ruff check app/agents/graph.py app/agents/nodes.py app/agents/state.py app/agents/supervisor.py app/agents/schemas.py app/agents/subagents/synthesis_worker.py app/streaming/mapper.py tests/agents/test_supervisor.py tests/agents/test_tier_gating.py tests/agents/test_state.py tests/agents/test_multi_intent_routing.py tests/agents/test_task_ledger.py tests/agents/test_ledger_early_exit.py tests/api/agent/test_agent_chat.py` | 0 | clean |

### Rollback

- Revert the branch. No database migration. The new state keys (`tasks`,
  `task_results`) are stored in checkpoints but are reset per turn, so old
  threads resume through the new graph topology (LangGraph supports topology
  changes for finished threads).

### Harness-Delta

(none)
