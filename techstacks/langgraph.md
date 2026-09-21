<!-- LangChain/LangGraph profile for the AI-agent layer (apps/api/app/agents|tools|memory|rag).
     Deliberately high-level: the idioms, pins, and invariants an agent must honor — not a code
     walkthrough. Product architecture lives in WORKFLOW.md; layer SoT in architecture.md;
     agentic roadmap in specs/agentic-chatbot/research-brief.md. As of 2026-09-21. -->

# LangChain / LangGraph Profile — travel-pi agent layer

How this project applies the **LangChain 1.x / LangGraph 1.x** stack (floors raised 2026-09-18 in
`apps/api/requirements-ai.txt`: `langchain>=1.4.1`, `langgraph>=1.2.11`, `langchain-core>=1.6.3`,
`langchain-anthropic>=1.7.2`, `langchain-google-genai>=4.4.0`, all `<2.0`). Read before touching
anything under `apps/api/app/{agents,tools,memory,rag,clients,streaming}/`.

## Stack & posture

| Concern | Choice |
|---|---|
| Orchestration | **LangGraph `StateGraph`, hand-built** — no `create_agent`, no prebuilt ReAct, **no 1.x middleware** (yet; see Direction) |
| LLM access | **`init_chat_model()` only** — provider-agnostic (OpenAI default; Anthropic/Gemini wired); `FakeLLM` in tests, zero network |
| Persistence | Checkpointer (threads): `AsyncPostgresSaver` / `MemorySaver` fallback · Store (long-term memory): `PostgresStore`+pgvector / `InMemoryStore` |
| Streaming | `astream(stream_mode=["messages","updates"], subgraphs=True)` → typed SSE contract (`streaming/`) |
| Observability | Langfuse via LangChain `CallbackHandler`, per-run `config["callbacks"]`; off by default, degrades silently |
| RAG | `langchain-postgres` PGVector (cosine) / `InMemoryVectorStore` fallback; `DeterministicFakeEmbedding` when keyless |
| Eval | deepeval harness (`apps/api/eval/`), eval-only dep — never imported by runtime |

**Posture:** explicit over magic. The graph, the ReAct loops, retry, and error handling are all
hand-assembled so behavior is inspectable and testable offline. Prefer extending these seams over
introducing prebuilt abstractions that hide them.

## How the graph is built (the idioms that matter)

- **Topology:** the graph enters through `pii_guardrail` → `load_context` → `summarize` →
  `supervisor`. The supervisor emits an ordered `tasks` list and a **`route_tasks` conditional
  edge** (`add_conditional_edges`) dispatches it: a single task to its specialist, a `booking` task
  to the HITL `plan` node, or ≥2 tasks to parallel `synthesis_worker` instances via `Send` that
  converge on `synthesize`. `reflection` uses `Command(goto=…)` with `destinations=(*SUBAGENTS,
  SYNTHESIZE_NODE, END)` and routes a REVISE to `goto=current_flow` — every such target **must**
  stay declared in `destinations=` or LangGraph silently drops the edge. Sub-agents are hand-rolled
  ReAct loops (`assistant` ⇄ `ToolNode` + `tools_condition`) in `agents/subagents/_base.py`.
- **State:** `TravelAgentState(MessagesState)` — TypedDict, `add_messages` reducer inherited,
  one custom reducer (`merge_trip_facts`, None = no-update). Not Pydantic.
- **Runtime context ≠ state:** per-run `AgentContext` (frozen dataclass: tier, gates,
  max_revisions…) flows through the **1.0 context channel** — `context_schema=AgentContext`,
  read as `Runtime[AgentContext]` in nodes, passed as `ainvoke(..., context=ctx)`. It is not
  checkpointed and not `config["configurable"]` — keep it that way.
- **Model resolution:** `get_agent_llm(name)` + DB-backed `AgentConfigCache` per-node overrides;
  resolver closures are memoized for a compiled graph's life, and a config **generation counter**
  triggers a full graph rebuild (`resolve_travel_graph`). New LLM-calling components need their
  own agent-config node seeded — a missing one degrades silently
  (`docs/solutions/agent/new-agent-config-node-seeds-null-model.md`).

## Tools

- `@tool` functions wrapping services — **thin adapters, no business logic**. Registry
  (`tools/registry.py`, `ALL_TOOLS`) is the single source of truth; MCP + `/agent/manifest`
  derive from it automatically (readOnly/destructive annotations).
- **Injection rule:** every tool now declares an explicit `@tool(args_schema=…)` (PR #204). The
  schema **must itself declare the injected params** (`InjectedState`/`InjectedStore`/
  `InjectedToolCallId`) — `ToolNode` reads *which args to inject* from the schema, so a schema that
  lists only the model-facing fields hides the injected ones and the tool is called without them
  (`TypeError: … missing required argument`). See
  `docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`.
- **Panels:** `response_format="content_and_artifact"` — tool returns `(summary, artifact)`;
  the model sees the summary, the artifact rides `ToolMessage.artifact` into the SSE mapper.
- **Errors:** domain errors → `ToolException` → `ToolMessage(status="error")` for model
  self-correction. The tool-fault handler's `exc: Exception` annotation is load-bearing (widens
  ToolNode's caught types beyond validation errors). Real-I/O sub-agents add `RetryPolicy`
  (`agents/retry.py` — matches transient errors by class name, never imports provider SDKs;
  `init_chat_model(max_retries=0)` so the graph owns retry).

## LLM layer

- Structured output: `with_structured_output(Model, method="function_calling")` — the method
  is deliberate (avoids OpenAI's json_schema parse path). Supervisor emits `SupervisorIntent`;
  slots are extracted as raw text then **normalized in Python** ("LLM parses, code computes" —
  `docs/solutions/agent/llm-parses-code-computes.md`).
- `FakeLLM(BaseChatModel)` scripts turns: `responses` (text/tool_calls) + `structured_responses`
  cycled; `bind_tools` is a no-op. All agent tests inject it via `build_graph(llm=, fast_llm=)`.

## Persistence & memory

- Checkpointer: Postgres via `from_conn_string` + `setup()`, held open for process life in
  lifespan; fails fast in prod, degrades to `MemorySaver` in dev. SQLite is never a durable
  checkpointer target.
- Store: namespaces `("users", user_id, kind)` for prefs / procedural instructions / episodes.
  **Always constructed with the semantic `index=` config** (dims 1536 + embeddings) — without it
  `store.search(query=)` silently degrades to recency ordering.
- History trimming uses `RemoveMessage(id=…)` sentinels; memory extraction runs as a post-turn
  FastAPI background task, not an in-graph node.

## Streaming & HITL

- One canonical stream call in `streaming/mapper.py`; items are `(namespace, mode, data)`
  3-tuples. `"messages"` = token deltas (filtered to sub-agent namespaces, `AIMessage` only);
  `"updates"` = tool calls/results/panels/terminal text. **Interrupts are not stream events** —
  read post-drain from graph state (`.interrupts` streaming; `__interrupt__` key buffered).
- HITL: `interrupt(payload)` in `plan_node` gates booking; resume with
  `Command(resume={"approved": bool})`. Currently route-level and coarse (see Direction).

## Testing

- Whole graph offline: `build_graph(llm=FakeLLM(...), fast_llm=FakeLLM(...),
  checkpointer=MemorySaver(), store=InMemoryStore())`. No network, no DB, no provider keys.
- Prompts/graph are **baked at lifespan startup** — prompt or `active.yaml` edits need a graph
  rebuild to show up (`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`,
  `langgraph-thread-reset-and-prompt-reload.md`). Prompt registry: `prompts/<name>/vN.md` +
  `active.yaml` pointer — new behavior = new version file + pointer flip, never edit an old vN.

## Version pins that bite (requirements-ai.txt)

- `langgraph-checkpoint-{sqlite,postgres}>=3.1.0,<4.0` — 2.x breaks at runtime against
  checkpoint-core 4.x, and `<4.0` pins checkpoint<4.0 which `langgraph>=1.2.11` no longer allows.
- `numpy` and `langchain-text-splitters` are **explicit** deps (1.x dropped/never declared them;
  a stale venv hides the breakage, clean CI won't).
- AI deps must **never** force fastapi/starlette/pydantic past the core caps — escalate, don't nudge.

## Direction

- **Stay on hand-built `StateGraph`** for the top graph; adopt LangChain 1.x **middleware**
  (`create_agent` stack) only if/when a sub-agent's needs converge with what middleware ships
  (HITL-per-tool, todo ledger) — don't hand-roll what 1.x middleware now standardizes without
  checking it first.
- The agentic roadmap is spec'd in `specs/agentic-chatbot/research-brief.md` (P1–P7). The
  **plan-as-state task ledger** and **`Send` fan-out** have shipped (GH-117 Path A: the supervisor's
  `tasks` list + `route_tasks` + `synthesis_worker` → `synthesize`; the old sequential
  `dispatch_next`/`pending_flows` machinery is gone). Remaining seams: tiered per-tool HITL + undo,
  tool-grounded reflection (feeds `min-59`), background "trip sentinel", and memory verification.
  New agency should land through those seams, not new parallel mechanisms.
- Related in-flight specs: `llm-chat-suggestions`, `min-58/59` (eval loop), `web-content-enrichment`
  (concierge web-RAG tool). Check `specs/` before adding overlapping capability.
- **Documented exception — `app/research/`.** The one place we depart from "hand-built
  `StateGraph`, no `create_agent`/middleware" is the long-horizon trip-research job, a second graph
  built on the `deepagents` harness (`create_deep_agent`). It earns the exception because the harness
  ships *exactly* the capabilities this job needs and nothing we'd otherwise hand-roll: skills,
  file-backed artifacts, isolated subagents, and a rubric-with-tools grading loop. It shares the chat
  graph's checkpointer and store but runs as its own graph; the top chat graph and the 5 specialists
  stay hand-built and untouched. See `specs/trip-research-deep-agent/design.md` (§0–§1) and PR #TBD.
