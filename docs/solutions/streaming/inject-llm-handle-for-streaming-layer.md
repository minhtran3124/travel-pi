---
problem_type: knowledge
module: streaming
tags: langgraph, streaming, sse, llm, fakellm, dependency-injection, async, ainvoke, translate
severity: standard
applicable_when: Code outside the LangGraph graph (e.g. the SSE mapper / async event generator) needs an LLM call, and the codebase runs FakeLLM in tests to stay offline.
affects:
  - apps/api/app/streaming/mapper.py
  - apps/api/app/agents/graph.py
supersedes: null
confidence: high
confirmed_at: 2026-07-08
---

## Applicable When

Code *outside* the LangGraph graph — the SSE mapper / async event generator in
`apps/api/app/streaming/mapper.py`, a background task, etc. — needs an LLM call (MIN-57:
translate free-form panel prose to Vietnamese at emission time), and tests run `FakeLLM` to
stay offline.

## Pattern

Attach the LLM handle to the **compiled graph** after `.compile()` and consume it via
`getattr(graph, "<handle>", None)`, mirroring the existing `extract_memory_llm` seam. This
routes the streaming layer's LLM through the same test-injection path the graph already uses.

Three rules make it correct:

- **Never call `get_fast_llm()` directly in the streaming layer** — that bypasses the test
  injection seam and hits the network under `FakeLLM` tests.
- **Async end-to-end (`ainvoke`)** so the SSE event loop is never blocked mid-stream.
- **Inject the callable into the pure transform** (dependency injection): the localizer/
  transform takes a `translator` param and has no LLM dependency of its own, so it is
  unit-testable with a plain fake and degrades gracefully when the handle is absent.

## How to Use

```python
# graph.py — after compile, alongside the existing extract_memory_llm seam
compiled = builder.compile(checkpointer=checkpointer, store=store)
compiled.extract_memory_llm = pick("extract_memory")
compiled.translate_llm = pick("extract_memory")   # reuse the fast-model seam

# mapper.py — inside the async SSE generator
_tl = getattr(graph, "translate_llm", None)
if _tl is not None:
    async def _translate(text: str) -> str:
        resp = await _tl.ainvoke([_TRANSLATE_SYSTEM, HumanMessage(content=text)])
        return resp.content
    translator = _translate
else:
    translator = None
# ... pass `translator` INTO the pure transform; it stays LLM-agnostic and testable.
```

Tests inject `FakeLLM` through the same `pick` / `build_graph(fast_llm=...)` override already
used for `extract_memory`, so no network call happens and no test needs to script this path
unless it exercises translation.

## Gotchas

- `resp.content` is assumed `str`. A provider returning content-blocks (a list) would inject
  a non-str downstream — a pre-existing whole-repo convention (`app/memory/extractor.py`,
  `app/agents/nodes.py` read `.content` the same way), not introduced here, but know it when
  porting the pattern.
- Per-item serialized `await` (one LLM call per element) is O(N) latency; a `(text, lang)`
  cache was deferred in MIN-57. Batch or cache if N grows.
- A value the graph writes to state (e.g. a `Command(update={"language": ...})` delta) only
  appears on turns where the producing node runs. A HITL-resume turn skips the supervisor
  and emits no delta, so seed such values from `await graph.aget_state(cfg)` **before** the
  astream loop (best-effort, default fallback).

## Related

- docs/solutions/agent/memory-extraction-background.md
