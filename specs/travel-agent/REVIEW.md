# Deep Review — `feat/travel-agent-foundation` vs LangChain/LangGraph 1.x best practices

**Date:** 2026-06-26
**Reviewer:** Claude (deep review, xhigh effort)
**Branch:** `feat/travel-agent-foundation` (Phases 0–9, ~36k LOC diff; agent layer ~1,700 LOC)

**Scope:** the agent layer — `app/agents`, `app/clients`, `app/tools`, `app/rag`, `app/memory`,
`app/prompts`, `app/mcp`, `app/routers/agent.py`.

**Stack under review:** LangGraph 1.2.6 · LangChain 1.3.11 · langgraph-checkpoint 3.x ·
langchain-postgres + pgvector · Langfuse 4.12 · MCP 1.x (FastMCP).

**Method:** read the full agent surface + three parallel best-practice research passes against the
official LangChain/LangGraph 1.0 docs (`docs.langchain.com/oss/python/*`), the LangChain 1.0 blog,
the LangGraph 1.0 GA changelog, langchain-postgres / Langfuse / MCP docs. (Context7 MCP was not
connected in this session; official docs/blogs were used as the sanctioned fallback.)

---

## Verdict

Architecture and layering are genuinely good — provider-agnostic `init_chat_model`, `@tool` +
`ToolException` + `ToolNode` self-correction, `Command(goto=)` handoffs with `destinations=`,
`RemoveMessage` trimming, `InjectedStore`, MCP annotations, zero-network fakes throughout.

But there are **4 correctness/resource bugs that defeat features this PR claims to ship**, plus a
cluster of 1.x-modernization gaps. All findings below are grep-confirmed against the code and
cross-checked against official docs.

---

## 🔴 Critical — features wired wrong or resource leaks

### C1. Graph + checkpointer + store rebuilt on *every request* (the `lru_cache` is dead code)

- **Evidence:** `app/routers/agent.py:35-43` — the `get_travel_graph` FastAPI dependency calls
  `build_graph(checkpointer=get_checkpointer(), store=get_store())` **fresh per request**.
  `app/agents/graph.py:80-86` defines an `@lru_cache`'d `get_compiled_graph()` that is **never
  called**. `app/core/lifespan.py:65` builds `app.state.agent_checkpointer` once at startup that
  the router **also never uses**.
- **Why it matters:** each `/agent/chat` / `/agent/stream` re-compiles 6 subgraphs and opens a new
  `sqlite3.connect(...)` / `PostgresSaver.from_conn_string(url).__enter__()` + `.setup()` (DDL) and
  a new `PostgresStore.__enter__()` + `.setup()` — none ever closed. Under load this exhausts
  Postgres connections / SQLite handles.
- **Best practice:** LangGraph persistence docs — compile once with a single long-lived
  checkpointer/store; `from_conn_string` returns a **context manager** that must be entered with
  `async with` for app lifetime, not per call.
- **Fix:** build graph + checkpointer + store **once** in `lifespan`, store on `app.state`, have
  `get_travel_graph` return `app.state.travel_graph`. Delete dead `get_compiled_graph` or use it.
- **Refs:** https://docs.langchain.com/oss/python/langgraph/persistence

### C2. Rolling summary is computed and old messages deleted — but the summary is never used

- **Evidence:** `app/agents/nodes.py:50-55` writes `{"summary": ..., "messages": <RemoveMessages>}`,
  actively dropping older turns. **Nothing reads `state["summary"]`** (grep: only the writer at
  `nodes.py:55` and the decl at `state.py:23`). Supervisor (`supervisor.py:38`) and every sub-agent
  (`subagents/_base.py:35`) build prompts from `state["messages"]` only.
- **Why it matters:** summarization makes the agent *worse* than doing nothing — it deletes history
  and throws the compression away (net context loss).
- **Best practice:** LangChain 1.x `SummarizationMiddleware` / langmem `SummarizationNode` keep the
  summary in state **and re-inject it** as a leading system message on every model call.
- **Fix (minimal):** prepend `SystemMessage(f"Conversation so far: {state['summary']}")` when
  `summary` is set. **Fix (idiomatic):** attach `SummarizationMiddleware(model=fast_llm,
  trigger=("tokens", N), keep=("messages", M))` to `create_agent` (see L4). Note the new
  `trigger`/`keep` API — `max_tokens_before_summary`/`messages_to_keep` are deprecated.
- **Refs:** https://reference.langchain.com/python/langchain/agents/middleware/summarization/SummarizationMiddleware

### C3. Long-term memory: semantic search is non-functional, and `user_id` is model-supplied

- **Evidence (1) — no index → `query=` ignored:** `app/memory/store.py:29,34` creates
  `PostgresStore.from_conn_string(url)` and `InMemoryStore()` **without an `index=` config**. Per
  the store docs, `store.search(ns, query=...)` only does semantic ranking when constructed with
  `index={"dims": ..., "embed": embeddings, "fields": [...]}`. So `get_user_preferences(query=...)`
  (`tools/memory_tools.py:33`) silently returns by recency, ignoring the query.
- **Evidence (2) — model-supplied `user_id`:** `save_user_preference(user_id, key, text, store)` /
  `get_user_preferences(user_id, ...)` (`tools/memory_tools.py:21,33`) make the model pass
  `user_id`. The model can hallucinate / cross-wire it, reading or writing another traveller's
  memories — a tenant-isolation hole (the namespace `("users", user_id, "prefs")` *is* the boundary).
  The real `user_id` already lives in `TravelAgentState.user_id`.
- **Fix:** (1) construct the store with an `index=` config wired to `get_embeddings()`. (2) Inject
  `user_id` from state via `Annotated[str, InjectedState("user_id")]` (hidden from the tool schema),
  or the 1.x `ToolRuntime` idiom (see L4).
- **Refs:** https://docs.langchain.com/oss/python/langchain/long-term-memory ·
  https://blog.langchain.com/semantic-search-for-langgraph-memory/

### C4. `/agent/stream` leaks internal node output (router/summarizer/reflection) to the user

- **Evidence:** `app/routers/agent.py:101-113` streams `stream_mode="messages"` and yields
  `chunk.content` for **every** model call in the graph, discarding metadata (`_meta`). Tokens from
  the supervisor router, the summarizer (`make_summarize_node`), and the reflection critic stream
  too — so the SSE feed can contain the rolling **summary text** or the literal **`OK`/`REVISE`**
  verdict (`nodes.py:76`) interleaved with the answer.
- **Best practice:** `stream_mode="messages"` yields `(chunk, metadata)`; filter on
  `metadata["langgraph_node"]` (or model `tags`) to emit only the user-facing node.
- **Fix:** only yield when `metadata.get("langgraph_node") in SUBAGENTS` (or tag the user-facing
  models and filter by tag). Also: anonymous streams collapse onto `conv_stream` (`agent.py:99`),
  colliding all unnamed sessions on one `thread_id`.
- **Refs:** https://docs.langchain.com/oss/python/langgraph/streaming

---

## 🟠 Medium — correctness smells & 1.x persistence/lifecycle

### M1. HITL `plan_node` is dead code, yet SUMMARY claims "plan HITL" shipped
`app/agents/nodes.py:92-100` defines the `interrupt()` approval node, but it is **never added to any
graph** (grep-confirmed) and has **no test**; `SUMMARY.md:41` lists "plan HITL" as done. Either wire
it in (conditional edge before destructive booking, resumed via `Command(resume=...)`) or remove it
and correct the SUMMARY. LangChain 1.x prefers `HumanInTheLoopMiddleware(interrupt_on={"book_hotel":
True})` over a hand-placed interrupt node.

### M2. `load_context_node` appends a `SystemMessage` via `add_messages` → lands after the human turn
`app/agents/nodes.py:42` returns `{"messages": [SystemMessage(...)]}`. `add_messages` **appends**, so
the trip-context system message ends up *after* the `HumanMessage`; the supervisor/sub-agents then
prepend their own system message → `[System, Human, System]`. A mid-conversation system message is
ignored by some providers and **rejected by Anthropic** (your stack supports `langchain-anthropic`).
**Fix:** carry trip context in a state field and inject at the front of the model call, or render it
into the system prompt — don't push it into `messages`.

### M3. Sync savers/stores under an async graph + manual `__enter__()` lifecycle
`checkpointer.py:46-56` and `store.py:29` use **sync** `SqliteSaver`/`PostgresSaver`/`PostgresStore`
while the router drives `await graph.ainvoke`/`astream`.
- Match saver to mode — use `AsyncSqliteSaver`/`AsyncPostgresSaver` for async graphs. The single
  shared `sqlite3` connection (`check_same_thread=False`, `checkpointer.py:46`) is not safe for
  concurrent writes across threadpool threads → "database is locked".
- `PostgresSaver.from_conn_string(url).__enter__()` (`checkpointer.py:54`) and
  `PostgresStore...__enter__()` (`store.py:29`) enter a CM that is **never exited** (the C1 leak).
- **Fix:** in `lifespan`, `async with AsyncPostgresSaver.from_conn_string(dsn) as cp: await
  cp.setup()` and hold on `app.state`. (Checkpoint ≥3.0 is correct — patches CVE-2025-64439 in
  `JsonPlusSerializer`; keep that floor.)
- **Refs:** https://docs.langchain.com/oss/python/langgraph/persistence ·
  https://github.com/langchain-ai/langgraph/security/advisories/GHSA-wwqv-p2pp-99h5

### M4. Langfuse handler rebuilt per request + likely-invalid v4 kwarg
`app/agents/observability.py:29-43` — `callbacks()` runs per request (`agent.py:60`) and each call
constructs a **new** `Langfuse(...)` client **and** `CallbackHandler(public_key=...)`. In Langfuse
**v3+/v4**, `CallbackHandler()` takes **no key kwargs** (reads the singleton `get_client()`), so
`public_key=` is ignored / may raise; per-request clients spin up flush threads repeatedly. The
`metadata` path (`trace_metadata` → `config["metadata"]`) is **correct** for v3+. **Fix:** construct
one cached `Langfuse(...)` + one `CallbackHandler()` at startup; pass the cached handler in
`config["callbacks"]`; verify the constructor against installed 4.12 (untested — Langfuse off in CI).
- **Refs:** https://langfuse.com/docs/observability/sdk/upgrade-path/python-v2-to-v3

### M5. RAG uses the legacy class and a hand-rolled hybrid that isn't truly hybrid
- `app/rag/embeddings.py:44` uses `PGVector`; langchain-postgres ≥0.0.12 ships **`PGVectorStore`**
  (v2: `PGEngine`, async, HNSW, `postgresql+psycopg://`). `PGVector` is legacy.
- `app/rag/retriever.py` re-ranks the **same** `similarity_search` candidate set by lexical overlap
  — the lexical leg can never surface a keyword match dense search missed; it's a re-rank, not
  hybrid. v2 provides **native** RRF via `HybridSearchConfig(fusion_function=reciprocal_rank_fusion)`
  (dense + `tsvector`).
- Metadata `filters` applied **after** fetch/rank (`retriever.py:48`) — a selective filter can
  starve results below `k`; push `filter=` into `similarity_search`.
- `app/rag/ingest.py:49` `store.add_documents(docs)` passes **no `ids=`** → re-ingest duplicates
  every document. Derive stable ids from `place.id`.
- **Refs:** https://pypi.org/project/langchain-postgres/ ·
  https://reference.langchain.com/python/langchain-postgres/v2/hybrid_search_config/reciprocal_rank_fusion

---

## 🟡 Low — polish & modernization

- **L1 — No `temperature=0`.** `clients/llm.py:51` `init_chat_model(...)` passes no `temperature`;
  the router (`with_structured_output`) and tool-calling sub-agents want deterministic decoding. Add
  a `temperature` setting (default 0).
- **L2 — Reflection critic under-informed & brittle.** `nodes.py:75-76` judges with only
  `[system, last]` (no user question to judge against) and string-matches `"REVISE"`. Pass the user
  turn and use `with_structured_output(Verdict)`.
- **L3 — Sync nodes for real I/O.** `subagents/_base.py:35`, `supervisor.py:38`, `nodes.py` call
  `llm.invoke` synchronously inside an async graph. Prefer `async def` nodes + `await llm.ainvoke`.
- **L4 — Modernization: `create_agent` + middleware.** LangChain 1.0 makes the hand-rolled ReAct
  subgraph, summarizer, and HITL node largely unnecessary: `from langchain.agents import
  create_agent` returns a compiled graph; `SummarizationMiddleware` (fixes C2),
  `HumanInTheLoopMiddleware` (fixes M1), `dynamic_prompt`, and `ToolRuntime` (replaces
  `InjectedStore`/`InjectedState`, fixes C3 injection) are the supported seams.
  `langgraph-supervisor`'s `create_supervisor` can replace `make_supervisor`. Optional, but deletes
  code and aligns with library direction. (`ToolNode`/`tools_condition` you use are still current;
  it's `create_react_agent` from `langgraph.prebuilt` that's superseded — you're not using it.)
- **L5 — MCP annotations.** `mcp/server.py:39` sets `readOnlyHint`/`destructiveHint`; add
  `idempotentHint` (read tools) and `openWorldHint` (weather/route hit external APIs). Confirm no
  `print()` in the tool path (stdout corrupts stdio JSON-RPC — log to stderr).
- **L6 — `_PROVIDER_KEY_FIELD` KeyError.** `clients/llm.py:48` indexes the map with
  `s.llm_provider`; use `.get(...)` with a clear error if the enum widens.
- **L7 — Test gaps.** No tests exercise `/agent/stream` (`astream`/`stream_mode`), the
  `interrupt`/HITL path, summarize-then-recall, or multi-user memory isolation (grep-confirmed). Each
  maps to a bug above (C4, M1, C2, C3).

---

## ✅ What's genuinely well done
Provider-agnostic `init_chat_model` factory + clean `FakeLLM` double; `@tool` + `ToolException` →
`ToolMessage(status="error")` self-correction; `Command(goto=)` handoffs with `destinations=` hints
(correct 1.x routing idiom); `RemoveMessage` trimming (correct deletion sentinel); per-domain tool
binding to avoid sprawl; MCP server reusing the single tool registry; checkpoint floor ≥3.0
(CVE-patched); graceful degrade-to-in-memory everywhere; zero-network test suite.

---

## Priority order to fix
1. **C1** (per-request rebuild/leak) — highest impact, smallest diff: build once in `lifespan`.
2. **C2 + C3** (summary never used; memory search dead + `user_id` injection) — silently break two
   headline features.
3. **C4** (stream leaks internal output) — user-visible correctness.
4. **M1–M5** cleanup pass; **M4/M5** verify against the *installed* 4.12 / langchain-postgres before
   changing.
5. **L4** modernization as a follow-up branch once bugs are closed.

**Version caveat:** confirm the v3 streaming object (`stream_events(version="v3")`), `durability`
modes, and the exact Langfuse 4.12 `CallbackHandler` signature against your pins before adopting —
the `stream_mode` / `interrupt` / `Command(resume=)` APIs relied on here are stable across all of 1.x.

---

## Sources
- LangChain & LangGraph 1.0 — https://www.langchain.com/blog/langchain-langgraph-1dot0
- Agents / `create_agent` — https://docs.langchain.com/oss/python/langchain/agents
- Agent middleware — https://docs.langchain.com/oss/python/langchain/middleware/custom · https://blog.langchain.com/agent-middleware/
- Models / `init_chat_model` — https://docs.langchain.com/oss/python/langchain/models
- Tools / `ToolRuntime` — https://docs.langchain.com/oss/python/langchain/tools
- Structured output — https://docs.langchain.com/oss/python/langchain/structured-output
- Messages / content blocks — https://docs.langchain.com/oss/python/langchain/messages
- LangGraph graph API / state — https://docs.langchain.com/oss/python/langgraph/graph-api
- Persistence (checkpointers & store) — https://docs.langchain.com/oss/python/langgraph/persistence
- Streaming — https://docs.langchain.com/oss/python/langgraph/streaming
- Interrupts (HITL) — https://docs.langchain.com/oss/python/langgraph/interrupts
- CVE-2025-64439 (JsonPlusSerializer) — https://github.com/langchain-ai/langgraph/security/advisories/GHSA-wwqv-p2pp-99h5
- langchain-postgres / PGVectorStore — https://pypi.org/project/langchain-postgres/
- Long-term memory — https://docs.langchain.com/oss/python/langchain/long-term-memory
- Langfuse v2→v3 upgrade — https://langfuse.com/docs/observability/sdk/upgrade-path/python-v2-to-v3
- MCP build server — https://modelcontextprotocol.io/docs/develop/build-server · https://gofastmcp.com/servers/tools
