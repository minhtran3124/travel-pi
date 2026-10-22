# gh-178 — Fanned-out workers must invoke sub-agents asynchronously

## Problem

`synthesis_worker.worker` is a **sync** node that calls `subagent.invoke(...)`. Six agent tools
are `async def` and therefore async-only — `get_weather`, `get_packing`, `get_air_quality`
(`weather_tools.py`), `get_climate` (`climate_tools.py`), `get_route`, `get_city_route`
(`routing_tools.py`) — and both the planner and the concierge bind all six.

Under a sync invocation one such call raises `NotImplementedError: StructuredTool does not support
sync invocation`. That kills the whole `tools` node, so `TOOL_FAULT`'s `graceful_fallback` emits
`GRACEFUL_MSG` for **every** pending call in the batch, including healthy synchronous ones. The
specialist then tells the traveller the data is temporarily unavailable — which is false, and
identical on retry.

Measured on one sub-agent, one tool batch, changing only the invocation:

| Tool | `.invoke()` (fan-out path) | `.ainvoke()` (single-specialist path) |
|---|---|---|
| `get_local_tips` | `status=error` — "temporarily unavailable" | `status=success` — 8 real tips |
| `get_weather` | `status=error` — "temporarily unavailable" | `status=success` — real forecast |

Production drives the graph asynchronously everywhere (`graph.ainvoke` / `graph.astream`,
`app/routers/agent.py:393`, `app/streaming/mapper.py:145`). The sync worker is the **only** sync
link in an otherwise async chain, and it exists solely because the node was written that way.

## Goal

A fanned-out worker's tool calls behave exactly like the same specialist's tool calls on a
single-specialist turn. No false outage.

Non-goals: changing which tools are async; changing `graceful_fallback`'s message; fixing the
model's tendency to narrate an outage (that is the second-order problem behind #179's neighbours).

## Options

### A — Make the node async (recommended)

`async def worker(...)` awaiting `subagent.ainvoke(...)`. LangGraph runs the async node natively
under the async parent; sync nodes elsewhere keep running in a thread pool.

- **Removes the sync path entirely.** There is then no second execution mode that can silently
  differ from production — which is exactly how this bug survived: the broken path was reachable
  only from tests, and the tests did not assert tool success.
- **Cost:** a sync `graph.invoke` cannot execute an async node. LangGraph raises
  `TypeError: No synchronous function provided to "synthesis_worker". Either initialize with a
  synchronous function or invoke via the async API`. Every test that *reaches* the worker must
  switch to `ainvoke`. Tests that never fan out are unaffected — the error is raised at node
  execution, not at compile time.
- Blast radius measured, not guessed: 40 `graph.invoke(` call sites across 18 test files, but only
  the fan-out ones execute this node.

### B — Dual sync + async node

Register the node as `RunnableLambda(sync_worker, afunc=async_worker)` so LangGraph picks the
implementation matching the invocation mode.

- No test changes.
- **Rejected.** It preserves a sync path that is still broken for async tools, so the defect stays
  reachable and untested-for; and it doubles the code that has to stay in step. The reason to
  prefer A is precisely that "the mode tests run in" and "the mode production runs in" stop being
  different things.

### C — Keep the node sync, `asyncio.run(subagent.ainvoke(...))` inside it

- No test changes, one code path.
- **Rejected.** The node body runs in LangGraph's thread pool under an async parent, so
  `asyncio.run` would spin a *fresh* event loop per worker call. Async clients and pools created on
  another loop (httpx, the async checkpointer) are loop-affine; this trades a visible failure for a
  class of intermittent ones. Not worth it to avoid editing a handful of tests.

## Decision

**Option A.** The fix is to delete a sync path that should never have existed, not to make it work.

## Consequences

- Fan-out tests move to `asyncio.run(graph.ainvoke(...))` (or an async test). This is mechanical.
- `tests/agents/test_plan_everything.py` currently passes while the tools node crashes underneath
  it, because its stub replaces `weather_service.get_weather` (the service) rather than the async
  tool wrapper, and it asserts only topology and recursion budget. A regression test must assert
  that a fanned-out worker's tool call actually **succeeded** — that is the assertion whose absence
  let this ship.
- The recursion-budget measurement in that file must be re-checked under `ainvoke`: super-step
  accounting should be identical, but it is an assertion about the graph, so it gets re-run rather
  than assumed.

## Open question, deliberately out of scope

`graceful_fallback` swallows the exception it handles and substitutes a message that *asserts* an
outage. That is why this looked like an infrastructure problem for as long as it did. Logging the
cause there would have made the diagnosis immediate. Worth its own change; noted in the SUMMARY's
Harness-Delta rather than bundled here.
