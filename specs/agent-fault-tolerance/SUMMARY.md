# agent-fault-tolerance — Summary

Lane: high-risk
Confidence: high
Reason: 4 flags fire (external-systems, existing-behavior, weak-proof, data-model). The load-bearing one is data-integrity: proposed-scope item 3 adds an `error_handler` on the booking tool path (`book_hotel`/`book_flight`) that issues a compensating cancel/delete on retry exhaustion — retrying a partially-succeeded booking write risks double-booking, a real DB side-effect, so this warrants high-risk ceremony. Plus retry/timeout on real external I/O (weather/routing/LLM) and a change to existing test-covered tool-error behavior (`_tool_error_to_message`). NO hard gate fires (no auth/authz, no schema migration, no NEW external provider, no high-blast file), so the work is not human-blocked; direction is unambiguous → confidence high → notify-and-proceed.
Flags: external-systems, existing-behavior, weak-proof, data-model (booking write/delete side-effect via SAGA compensation — no schema change)
Affects: `app/agents/subagents/_base.py` (`_tool_error_to_message` L43-61, assistant/tools node wiring L138/142), `app/agents/graph.py` (10 `add_node()` calls L112-131), booking tool path (`book_hotel`/`book_flight` — DB side effects). NOT touched: deterministic fake services (flights/hotels availability, trips, FX — no real I/O), no schema/migration, no dependency upgrade (`langgraph==1.1.6` already installed).
Input-type: change request
Route: high-risk full chain — brainstorming → xia2 → writing-plans → using-git-worktrees → subagent-driven-development. Notify-and-proceed (no hard gate, confidence high). Branch `tranhuuminh3124/min-49-adopt-langgraph-fault-tolerance-primitives` (from Linear). xia2 MUST verify a booking cancel/compensation path exists to reuse — if none exists, item 3 (SAGA) escalates mid-flight as a feasibility blocker.
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-49, verbatim from the Linear ticket description. -->

> ## Context
>
> Reference: [Fault tolerance in LangGraph](https://www.langchain.com/blog/fault-tolerance-in-langgraph). `langgraph==1.1.6` is already installed (pinned `>=1.0,<2.0` in `apps/api/requirements-ai.txt`) and `StateGraph.add_node()` already supports `retry_policy`, `timeout`, and `error_handler` — no dependency upgrade needed.
>
> Currently none of these are used anywhere in `app/agents/`:
>
> * `app/agents/graph.py:112-131` — 10 `add_node()` calls, no policies.
> * `app/agents/subagents/_base.py:138,142` — `assistant`/`tools` node wiring, no policies.
>
> ## Key finding — tool error handling actively blocks retry today
>
> `app/agents/subagents/_base.py:43-61` (`_tool_error_to_message`) catches **every** tool exception — including real transient upstream failures (the docstring names Open-Meteo timeouts explicitly) — converts it to a `ToolMessage`, and instructs the model **not to retry**. This means adding a bare `RetryPolicy` to the `"tools"` node would not fire today: no exception propagates out for LangGraph to catch. The error-classification logic needs to change before `RetryPolicy` has any effect.
>
> ## Proposed scope
>
> 1. Split tool error handling into two classes:
>    * **Transient** (network error, 5xx, timeout) → re-raise so it propagates to the node and `RetryPolicy` can retry.
>    * **Logic/input** (bad args, `ValueError`, domain `AppError` for bad requests) → keep converting to `ToolMessage` so the LLM can self-correct.
> 2. Add `RetryPolicy` (+ `TimeoutPolicy` with `idle_timeout` for streaming) to:
>    * The `assistant` node in `build_subagent()` (`_base.py`) — covers real LLM provider calls (rate limits/network).
>    * The `tools` node, scoped to `weather_service` / `routing_service` calls — the only real external I/O per `CLAUDE.md`.
> 3. Add an `error_handler` (not blind retry) on the booking-related tool path (`book_hotel`, `book_flight` — DB side effects) for SAGA-style compensation (log + trigger a compensating cancel on retry exhaustion), since retrying a partially-succeeded write risks double-booking.
> 4. Consider `set_node_defaults()` to apply a baseline retry/timeout across all 5 ReAct sub-agents instead of repeating config per node.
>
> ## Non-goals
>
> * No change to deterministic fake services (flights/hotels availability, trips, FX) — they don't hit real I/O, so retry/timeout doesn't apply there.
>
> ## Suggested next step
>
> Write `specs/agent-fault-tolerance/PLAN.md` (touches >2 files across `_base.py`, `graph.py`, booking tools — meets the plan-format threshold) before implementation, since the transient-vs-logic error classification is a design decision, not a mechanical change.

### Design forks to resolve in planning (HOW, not WHAT — do not block intake)

1. **Transient-vs-logic boundary** — exact exception taxonomy that re-raises (httpx timeouts, 5xx, connection errors, `UpstreamError`) vs converts to `ToolMessage` (`ValueError`, bad-arg `AppError`/`NotFoundError`/`ConflictError`). This is the core design decision the issue flags; resolve in `/brainstorming` + `design.md`.
2. **Booking SAGA feasibility** — does a booking cancel/compensation path already exist to reuse (repo/service method)? `/xia2` must confirm. If none exists, item 3 grows scope → mid-flight escalation.
3. **`set_node_defaults()` vs per-node config** (item 4, "Consider") — optional; decide during planning.

## What changed

Implemented `specs/agent-fault-tolerance/PLAN.md` in full (7 tasks, 4 waves): a new `app/agents/retry.py` centralizes `LLM_RETRY`/`TRANSIENT_RETRY`/`TOOL_FAULT`/`graceful_fallback`; the four top-level LLM nodes in `graph.py` and every sub-agent's `assistant` node now carry `retry_policy=LLM_RETRY`; concierge/planner's `tools` node (weather/routing — the only real-I/O tool paths) narrows its error handler to `ToolException` only, retries `UpstreamError` via `TRANSIENT_RETRY`, and degrades gracefully via `graceful_fallback` on exhaustion; `clients/llm.py` sets `max_retries=0` so the graph is the single retry owner. Booking/budget/journal sub-agents are unchanged (today's catch-all handler, no retry) — the SAGA/compensation fork flagged at intake was dropped in design.md, so no booking-path behavior changed.

### Rationale

The core intent — adopt LangGraph fault-tolerance primitives, gated behind reclassifying tool errors into transient (re-raise) vs logic (ToolMessage) — is unambiguous and stated with file:line precision. The three forks above are HOW-level and the issue itself pre-slates them to the planning stage. High-risk lane is chosen for the data-integrity substance (booking write compensation / double-booking hazard) plus real external-I/O retry, not for direction uncertainty — hence confidence stays high and no human gate is needed at intake.

### Alternatives (considered, not chosen)

- **Normal lane (3 flags)** — reachable by arguing item 3's compensation reuses an existing cancel and changes no schema, dropping the data-model flag. Rejected: the double-booking / partial-write risk on real DB writes is exactly the data-integrity hazard the high-risk lane exists for, and the issue author flags it explicitly.
- **Escalate at intake for a human decision** — rejected: no hard gate fires and direction is unambiguous. The one genuine unknown (booking compensation feasibility) is a research question for `/xia2`, not an intent question — it becomes a mid-flight escalation only if infeasible.

### Deviations

- Rule 1 — `tests/tools/test_tool_registry.py::test_weather_tool_maps_upstream_error` asserted the pre-plan contract (`WeatherUnavailableError` → wrapped `ToolException`) that Task 1.2 intentionally inverts (architecture section: "Weather/routing tools re-raise `UpstreamError` unwrapped so `RetryPolicy` fires"). PLAN.md's Task 1.2 `<files>` only listed `test_weather_tools.py`/`test_routing_tools.py`, missing this pre-existing assertion in a different file. Updated the test to `pytest.raises(UpstreamError)` — same intent, now matching the shipped contract. Not scope creep: it is the direct, obvious consequence of the plan's stated behavior change, flagged by `blast-radius-check.sh` for this record.
- Rule 1 — `tests/agents/test_subagent_fault_tolerance.py` Task 4.1's plan-supplied test snippet used `lambda _=None: _tool_calling_llm()`, recreating a fresh `FakeLLM` (cursor reset to 0) on every `assistant`-node call since `resolve_model` is invoked per request (`_base.py:102`) — caused an infinite assistant↔tools loop. Fixed by hoisting one `llm = _tool_calling_llm()` instance and closing over it, matching the pattern already used by `test_assistant_node_retries_transient_llm_error`. Test-fixture bug in the plan's snippet, not a production-code bug; no `app/` files touched by this fix.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| unit — retry.py | `pytest tests/agents/test_retry.py -x -q` | 0 | 5 passed |
| unit — weather/routing re-raise | `pytest tests/tools/test_weather_tools.py tests/tools/test_routing_tools.py -x -q` | 0 | 17 passed |
| unit — subagent fault-tolerance | `pytest tests/agents/test_subagent_fault_tolerance.py -x -q` | 0 | 4 passed |
| unit — graph compiles w/ retry_policy | `pytest tests/agents/test_hitl_plan.py -q` | 0 | 4 passed |
| unit — SDK max_retries=0 | `pytest tests/clients/test_llm_max_retries.py -x -q` | 0 | 1 passed |
| lint | `ruff check app/agents/retry.py app/agents/subagents/_base.py app/agents/subagents/concierge.py app/agents/subagents/planner.py app/agents/graph.py app/clients/llm.py app/tools/weather_tools.py app/tools/routing_tools.py tests/` | 0 | All checks passed |
| full regression | `pytest tests/agents tests/tools tests/clients -q` (`.env` moved aside — live ORS/OpenAI keys otherwise skew 2 pre-existing offline-estimate/model-name tests, unrelated to this change) | 0 | 253 passed |

### Rollback

- `git revert d059bb6` (commit on `feat/agent-fault-tolerance`, off `v3`).
- Pre-merge: `git switch v3` to abandon the branch without reverting.
