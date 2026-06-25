# SUMMARY — travel-agent

Lane: high-risk
Confidence: medium
Reason: New external dependency tree (LangChain/LangGraph/OpenAI/Langfuse/pgvector/
MCP), schema changes (conversations/messages/jobs + pgvector), and new `/agent/*`
public endpoints. Implemented incrementally, one PR-sized phase per commit, every
phase green on SQLite + (final) Postgres.

## Rationale

Add an agentic multi-agent travel assistant on LangGraph (provider-agnostic,
OpenAI default) that plans, answers, takes notes, and updates state across a trip.
Built per `PLAN.md` Phases 0–9. Tests are zero-network: FakeLLM, FakeEmbeddings,
SqliteSaver / InMemoryStore stand in for real models and backends, so the suite
and CI need no API key.

## Alternatives

- OpenAI-only SDK (rejected — owner chose provider-agnostic `init_chat_model()`).
- Single ReAct agent (rejected — owner chose supervisor + sub-agents that
  communicate, reflect, and self-correct).
- Qdrant vector store (rejected — pgvector reuses the existing Postgres).
- LangSmith (the reference repos' choice) — owner chose Langfuse.

## Progress — all phases DONE

- **0 Deps & config**: requirements-ai.txt (langgraph 1.2.6, langchain 1.3.11,
  langchain-openai/anthropic, checkpoint sqlite+postgres 3.x, langchain-postgres
  +pgvector, langfuse 4.12, text-splitters, mcp 1.x); provider-agnostic settings.
- **1 Seams**: clients/llm.py (FakeLLM), prompts/registry.py, conversation/message/
  job models + repo + migration.
- **2 Memory**: checkpointer (Sqlite/Postgres/Memory) wired in lifespan; PostgresStore
  /InMemory store + summarizer.
- **3 Tools**: trip/place/flight/hotel/weather/expense/memory/RAG tools + registry
  (TOOLS_BY_DOMAIN + readOnly/destructive metadata).
- **4 RAG**: embeddings (OpenAI/fake) + pgvector/in-memory store, ingest, hybrid
  retriever (RRF), pgvector extension migration (probes availability).
- **5 Graph**: TravelAgentState, build_subagent ReAct factory, 5 specialists,
  supervisor (Command routing), nodes (load_context/summarize/reflection/plan HITL),
  build_graph.
- **6 API**: /agent/chat, /agent/stream (SSE), /agent/manifest + persistence.
- **7 Observability**: Langfuse callbacks (opt-in, off by default).
- **8 Eval**: routing + retrieval datasets, metrics, run_eval gate, CI smoke test.
- **9 MCP**: FastMCP server exposing registry tools with annotations.

## Deviations

- Rule 3 — Added several deps not in the original `0.1` list as integration
  surfaced them: `langchain-text-splitters` (RAG chunking, not transitive in
  langchain 1.x), `mcp` (Phase 9 server). Bumped `langgraph-checkpoint-sqlite/
  postgres` to >=3.0 (2.x calls a removed `JsonPlusSerializer.dumps`).
- Rule 2 — Added `app/tools/rag_tools.py` + `eval/`, `app/agents/observability.py`,
  `app/core/streaming.py` (llm-readiness 1.2 seam), and `schemas/agent.py` request
  schemas — required by the phases, in-scope.
- Rule 3 — `Dockerfile` now copies `requirements-ai.txt` (build broke without it).
- Adaptation — day-level note tool deferred (A8 day notes unshipped): journal uses
  `add_itinerary_item(notes=...)` + memory tools. `nearby_places` anchors on
  place_id; `search_hotels` via `check_availability`.
- Note — `scripts/` is gitignored; `scripts/ingest_rag.py` force-added (matches the
  precedent of the tracked scripts).
- Note — `ragas` is an optional extra (lazy-imported in `eval/metrics.py`); not
  pinned to keep the dep tree lean. RAG + Postgres checkpointer/store + pgvector
  are Postgres-only; SQLite/tests use the in-memory equivalents.

## Notes

- langfuse resolved to 4.12 → `from langfuse.langchain import CallbackHandler`.
- pgvector extension migration probes `pg_available_extensions` and skips cleanly
  on a stock Postgres image (postgres:17-alpine has no pgvector).

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Full suite (SQLite) | `pytest -q` | 0 | 843 passed |
| Alembic drift | `alembic upgrade head && alembic check` | 0 | no drift |
| Lint | `ruff check app scripts eval` | 0 | clean |
| Cross-engine (Postgres, py3.12) | `make test-docker` | 0 | see Status Log |

### Rollback

- Revert code: `git revert <sha>` per phase commit (each phase is one commit).
- Drop agent tables: `alembic downgrade 7a78a5d543fb`.
- Remove AI deps: delete `requirements-ai.txt` + its `-r` line in requirements.txt
  and the Dockerfile copy; `uv pip install -r requirements.txt`.
- Unregister API: remove `agent.router` from `app/routers/main.py`.
