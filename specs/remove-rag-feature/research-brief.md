# remove-rag-feature — Research Brief

Captured from an Explore-agent codebase scan at intake time (see `specs/remove-rag-feature/SUMMARY.md`).
Substitutes for a separate `/xia2` pass since this is normal-lane, and the scan already
enumerated the full footprint below.

## What exists today

**Core module — `apps/api/app/rag/`**
- `embeddings.py` — `get_embeddings()` (OpenAI or deterministic fake) and `get_vector_store()`
  (pgvector via `langchain-postgres` PGVector on Postgres, `InMemoryVectorStore` elsewhere).
  Defines `EMBED_DIM = 1536` and `DEFAULT_COLLECTION = "travel_pois"`.
- `ingest.py` — turns `Place` records (via `PlaceService`) into chunked/templated `Document`s
  and upserts into the vector store (`ingest_places`).
- `retriever.py` — `hybrid_search()`: RRF fusion of semantic similarity + lexical overlap,
  with metadata filtering.

**DB / migrations**
- No app-owned ORM models for RAG. Only migration:
  `apps/api/alembic/versions/b68656f68e88_enable_pgvector_extension_postgres_only.py` —
  `CREATE EXTENSION IF NOT EXISTS vector` (Postgres only, no-op elsewhere; downgrade is a no-op).
  Embedding/collection tables are created at runtime by `langchain-postgres` PGVector, not
  Alembic-managed. **Decision: leave this migration in place** — it's generic pgvector infra,
  not RAG-specific data, and reverting it isn't required for correctness.

**Routers** — none. RAG was never an HTTP endpoint, only an agent tool.

**Live agent wiring (request-time, not dormant)**
- `apps/api/app/tools/rag_tools.py` — `search_destination_knowledge` tool wraps `hybrid_search`;
  exported as `RAG_TOOLS`.
- `apps/api/app/tools/registry.py:35` — `RAG_TOOLS` added to the `"concierge"` sub-agent's tools.
- `apps/api/app/agents/constants.py` (`RAG_TOOL_NAME`), `app/agents/context.py` (`allow_rag`
  flag, false for free tier), `app/agents/subagents/_base.py` (filters the RAG tool out of the
  concierge's bound tools when `allow_rag` is False).

**Cross-dependency (the one non-obvious coupling)**
`apps/api/app/memory/store.py` imports `EMBED_DIM, get_embeddings` from `app.rag.embeddings` to
build the semantic index for the LangGraph long-term `Store` (episodic/preference memory search).
This is unrelated to destination-knowledge RAG — it's reused infrastructure. **Deleting
`app/rag/` wholesale breaks this import.** Plan must relocate `get_embeddings`/`EMBED_DIM` (e.g.
into `app/memory/` or a small shared `app/core/embeddings.py`) before or as part of deleting
`app/rag/`.

**Specs** — `specs/travel-agent/PLAN.md` (Phase 4, Task 4.1/4.2) documents the original design:
pgvector cosine + tsvector RRF hybrid search, Postgres-only, degrades to "no results" on
SQLite/in-memory. Mark these sections superseded rather than deleting (historical record).

**Config** — `app/core/config.py`: `embedding_model = "text-embedding-3-small"`,
`openai_api_key`, `database_url` (picks pgvector vs in-memory). `embedding_model`/`openai_api_key`
stay (still used by memory's embeddings after relocation); nothing RAG-specific to remove here.

**Tests** — `apps/api/tests/rag/` (conftest, test_embeddings, test_retriever),
`apps/api/tests/tools/test_rag_tools.py`, plus `tests/eval/test_eval_smoke.py`.

**Eval / scripts** — `apps/api/eval/run_eval.py` + `eval/metrics.py` (RAGAS faithfulness,
retrieval dataset), `apps/api/scripts/ingest_rag.py` (manual ingestion CLI).

## What to reuse vs. build

Nothing to build — this is subtraction. The only "build" step is the embeddings relocation
for `memory/store.py`, which is a mechanical move of two symbols (`get_embeddings`, `EMBED_DIM`)
plus their `get_vector_store`-independent logic, not new functionality.

## Open questions for the plan

- `tests/eval/test_eval_smoke.py`: confirm whether it exercises only RAG (delete) or also
  covers non-RAG eval surface (keep, strip RAG-specific fixtures).
- Confirm no other module imports `app.rag.*` beyond `memory/store.py` and `tools/rag_tools.py`
  (grep at execution time as a safety check before deleting the package).
