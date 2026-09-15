---
problem_type: bug
module: agent/synthesis_worker
tags: langgraph, async, tools, fan-out, multi-intent, sse, streaming, graceful-fallback, eval-harness, gh-178, gh-179
severity: critical
applicable_when: Adding or reviewing any LangGraph node that invokes an inner graph, sub-agent or
  tool — check whether it uses `.invoke()` or `.ainvoke()` and whether the callee's toolset contains
  any `async def` tool. Also when a test drives the parent graph with `graph.invoke()` while
  production drives it with `ainvoke`/`astream`, and whenever an agent narrates an outage that the
  infrastructure cannot corroborate.
affects:
  - apps/api/app/agents/subagents/synthesis_worker.py
  - apps/api/app/agents/retry.py
  - apps/api/app/streaming/mapper.py
  - apps/api/eval/adapters/langgraph_runner.py
  - apps/api/tests/agents/test_fanout_tool_execution.py
  - apps/api/tests/streaming/test_synthesize_stream_chunks.py
confidence: high
confirmed_at: 2026-09-10
---

## Applicable When

A node runs an inner graph and the inner toolset mixes sync and async tools. In this codebase six
tools are `async def` — `get_weather`, `get_packing`, `get_air_quality` (`weather_tools.py`),
`get_climate` (`climate_tools.py`), `get_route`, `get_city_route` (`routing_tools.py`) — and both
the planner and the concierge bind all six.

Also applicable to the inverse: an execution mode that only tests use. If production runs `ainvoke`
and tests run `invoke`, the sync path is unowned, and a defect there is invisible to everyone.

## The bug

`synthesis_worker` — the node that runs each specialist on a fanned-out (multi-intent) turn — called
`subagent.invoke(...)`. The first async-only tool raised:

```
NotImplementedError: StructuredTool does not support sync invocation.
```

LangGraph kills the **whole `tools` node** on that, not just the offending call. `TOOL_FAULT`'s
`graceful_fallback` then emits `GRACEFUL_MSG` for *every* pending `tool_call_id` in the batch —
healthy synchronous siblings included. The specialist read six identical "temporarily unavailable"
tool results and told the traveller there was an upstream outage. There was none, and retrying
reproduced it identically.

Same sub-agent, same two-tool batch, changing only the invocation:

| Tool | `.invoke()` | `.ainvoke()` |
|---|---|---|
| `get_local_tips` (sync) | `status=error` — "temporarily unavailable" | `status=success` — 8 real tips |
| `get_weather` (async) | `status=error` — "temporarily unavailable" | `status=success` — real forecast |

## Why it survived

Three separate blind spots, each worth its own guard:

1. **The broken path was test-only.** Production always drives the graph with `graph.ainvoke` /
   `astream` (`app/routers/agent.py`, `app/streaming/mapper.py`). The sync worker node was the single
   sync link, reachable in practice only through the fan-out path.
2. **The existing fan-out test asserted topology, not behavior.**
   `tests/agents/test_plan_everything.py` exercises exactly this path and passed for months while
   the tools node crashed underneath it — it asserted the task list and the recursion budget, never
   that a tool call returned data.
3. **`graceful_fallback` discards the exception it handles** (`app/agents/retry.py`, filed as #186)
   and substitutes a message that *asserts* an upstream outage. With nothing logged, the visible
   evidence pointed at infrastructure. The first diagnosis of #178 was consequently wrong and the
   issue had to be rewritten.

## The fix

Make the node `async def` and `await subagent.ainvoke(...)`. Do **not** add a sync fallback and do
**not** wrap `asyncio.run` inside the node: the node body runs in LangGraph's thread pool under an
async parent, so `asyncio.run` would spin a fresh event loop per call and loop-affine clients
(httpx, the async checkpointer) would misbehave. Deleting the sync path is the point — a second
execution mode production never uses is what hid the defect.

Consequence: a sync `graph.invoke` cannot execute an async node, and fails loudly with
`TypeError: No synchronous function provided to "<node>"`. Every fan-out test call site moves to
`asyncio.run(graph.ainvoke(...))`; tests that never fan out are unaffected, because the error is
raised at node execution, not at compile time.

`asyncio.run` **is** correct in `eval/adapters/langgraph_runner.py`, which drove the graph
synchronously too: the eval CLI is a batch entry point with no enclosing event loop.

## The eval consequence

Because the eval harness ran the sync path, **every multi-intent golden it has ever scored ran on
the broken path**, where one async tool took its whole batch down. The committed baseline's fan-out
numbers were measured there. Re-run and re-baseline after this change; the new numbers are the
trustworthy ones.

## The second layer, immediately behind it (#179)

Fixing the tools exposed the next defect: the SSE mapper's `synthesize` branch deduped by "emit the
first event only", so the traveller received a one-character reply. Its comment assumed
`llm.invoke()` produces a single event — but `app/clients/llm.py` builds every model with
`streaming=True` (so OpenAI reports `usage_metadata`), which routes `invoke` through `_stream`.

Measured on a live fan-out turn, the synthesize branch receives:

```
73 × AIMessageChunk  id=lc_run--01a08922...   ← the answer, one shared id
 1 × AIMessage       id=84967879...           ← the aggregate duplicate
```

So the duplicate is real but arrives with a **different id**. Dedupe by message id, never by "first
event". The existing test scripted the duplicate as a *same-id* chunk and asserted
`names.count("token") == 1` — it encoded the assumption that caused the bug, and had to be corrected
to the measured shape.

## Rule to carry forward

**When a symptom appears at the last link in a chain, measure what the previous link emitted before
attributing the fault.** Both #178 and #179 were first filed against the wrong component — a state
handler and the frontend respectively — from looking at the visible end. What settled each of them
was measuring a boundary: the `ToolMessage`s the sub-agent actually received, and the events on the
SSE wire (`curl ... | grep -c '^event: token'`). Both took a couple of minutes and would have
prevented a wrong issue.

Corollary for tests: assert what crossed the boundary (a tool's returned content, the reassembled
answer), not the shape of the pipeline that carried it.
