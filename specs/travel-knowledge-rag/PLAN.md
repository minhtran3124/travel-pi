---
slug: travel-knowledge-rag
status: proposed
owner: Minh Tran
created: 2026-07-08
relates-to: specs/remove-rag-feature/, specs/web-content-enrichment/, specs/local-tip-agent-tool/
---

# Travel Knowledge RAG — Visa & Local Tips

> Re-introduce a focused retrieval-augmented-generation (RAG) feature over the
> **visa** and **local-tips** seed data: render the structured records into
> natural-language text, embed them, and let the concierge sub-agent query them
> via a hybrid (semantic + lexical, RRF) search tool. This restores the RAG
> capability that `specs/remove-rag-feature` deleted (2026-07-04), re-scoped from
> *places* to *visa + tips*, using the same pgvector backend the removal took out.

**For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Two deliverables — (1) **generate data → text**: turn `app/data/visa.py`
(`COUNTRY_VISA`, 16 countries) and `app/data/tips.py` (`COUNTRY_TIPS`, `CITY_TIPS`,
`COUNTRY_SUMMARIES`) into embedding-friendly `Document`s; (2) **query → RAG**: a
`search_travel_knowledge` concierge tool that runs hybrid retrieval over those
documents and returns ranked snippets (or an empty signal).

**Architecture:** The old RAG lived in `app/rag/{embeddings,ingest,retriever}.py`,
was wrapped by `app/tools/rag_tools.py` (`search_destination_knowledge`), wired
into `app/tools/registry.py` (concierge), and backed by pgvector
(`langchain-postgres` PGVector) on Postgres / `InMemoryVectorStore` on SQLite.
All of that was deleted in `specs/remove-rag-feature` — except
`app/core/embeddings.py` (the `get_embeddings()`/`EMBED_DIM` relocation that the
memory store still uses) and the `enable_pgvector_extension_postgres_only`
Alembic migration. This plan re-creates `app/rag/` over the **surviving**
`app/core/embeddings.py`, re-adds the deleted deps, and points the corpus at
visa + tips instead of places. Two changes vs. the old design close real gaps:
(a) `get_vector_store()` is a **cached singleton keyed by `database_url`** plus
**auto-ingest at startup** — the old tool returned nothing on SQLite/tests unless
a test ingested in-process, which made RAG effectively a no-op everywhere but
Postgres; (b) the corpus reads through the **repository layer** (not `app.data`
directly), honoring the repo's "`from app.data` appears only in `app/db/seed.py`"
rule. No Alembic migration is needed: the pgvector extension migration already
exists, and PGVector auto-creates collection tables at runtime (as before).

**Tech Stack:** Python 3.10+, FastAPI, LangGraph 1.2.6, LangChain 1.3.11
(`InMemoryVectorStore` from `langchain_core`), `langchain-postgres` (PGVector,
re-added), `pgvector`, `langchain_text_splitters`, pytest (async via
`asyncio.run(...)`), `DeterministicFakeEmbedding` test double (no key/network).

**Reference:** recovered original implementation from git history (`3d0dc6a^`
deleted `app/rag/`, `8366805^` deleted `rag_tools.py`); `specs/remove-rag-feature/research-brief.md`
(full old footprint); `specs/travel-agent/PLAN.md` Task 4.1/4.2 (original design,
marked superseded by removal).

---

## 1. Motivation

The RAG feature was removed because the product direction was "tool-calling
first; RAG retrieval deferred indefinitely" (`specs/remove-rag-feature`). Since
then the concierge answers visa/tips questions only through the exact-lookup
`get_visa`/`get_local_tips` tools — which work when the traveller names a
destination, but cannot answer free-text questions like "do I need a visa for a
45-day stay?" or "what should I watch out for with money and transport in
Vietnam?" without the model first guessing the country/category. A small,
static, high-signal corpus (visa policies + curated local tips + country
overviews) is the ideal RAG use case: hybrid semantic+lexical retrieval surfaces
the right passage from a natural-language question, then the model grounds its
answer on it. Re-scoping to visa + tips (not the old places index) keeps the
corpus small, deterministic, and seed-driven — no web crawling, no staleness.

## 2. Non-goals

- **Does not index places/hotels.** The old RAG indexed catalog places; this
  re-introduction is scoped to visa + local tips + country summaries only (per
  the user's "visa tip and local tips" scope).
- **Does not restore the old `search_destination_knowledge` tool name/contract.**
  The new tool is `search_travel_knowledge` to signal the new scope and avoid
  confusion with the deleted places-based tool.
- **Does not add a tier gate (`allow_rag`).** Knowledge search is cheap/local, so
  it is ungated for this re-introduction. The episodic-style gating pattern
  (`allow_*` flag on `AgentContext` + filter in `subagents/_base.py`) can be
  added later if desired — tracked as a future option, not a task here.
- **Does not add an HTTP router endpoint.** RAG stays an agent tool, as before.
- **Does not restore the eval harness / RAGAS metrics** in this pass. A focused
  eval dataset can follow; this plan ships unit + integration coverage only.
- **Does not touch `app/memory/store.py`.** It already sources
  `get_embeddings`/`EMBED_DIM` from `app/core/embeddings.py` — unchanged.
- **Does not add or alter Alembic migrations.** The
  `enable_pgvector_extension_postgres_only` migration already exists and backs
  both the memory store's semantic index and the new RAG collection.
- **Does not integrate PixelRAG / web content.** That is the separate
  `specs/web-content-enrichment` track (which assumed RAG still existed and is
  now stale — left for a separate human decision).

## 3. Architecture & data flow

```
OFFLINE / STARTUP (core/lifespan.py, after seed_all):
  app/data/{visa,tips}.py ──seed_all──▶ DB (Visa, Tip, CountrySummary rows)
                                              │
  build_knowledge_corpus(session) ────────────▶ list[Document]   (text rendering)
     reads via VisaRepository / TipRepository / CityRepository / CountryRepository
                                              │
  ingest_knowledge(store, session) ───────────▶ PGVector (Postgres) / InMemoryVectorStore (SQLite)
     stable ids: "visa-{country}", "tip-{tip.id}", "summary-{country}"
     idempotent upsert — re-ingest is a no-op

RUNTIME (concierge ReAct loop):
  user query ──▶ search_travel_knowledge tool
                       │ get_knowledge_store()  (cached singleton, auto-ingested)
                       ▼
                  hybrid_search(store, query, filters, k)
                       │ RRF(semantic similarity_search, lexical token overlap)
                       ▼
                  {"results": [{content, metadata}], "count": n}  (or empty signal)
```

**Singleton store + auto-ingest.** `InMemoryVectorStore` is per-instance (its
state does not persist across calls), so the old tool returned *nothing* on
SQLite/tests unless a test ingested in-process. To make the tool work
out-of-the-box on every backend, `get_vector_store()` is a **cached singleton
keyed by `database_url`**, and the corpus is **auto-ingested at startup**
(lifespan, immediately after `seed_all`) and lazily on the first tool call.
`reset_vector_store()` is exposed for test isolation, mirroring the existing
`weather_service.clear_geocode_cache()` pattern. On Postgres, PGVector reads the
persisted collection; startup ingest keeps it current (idempotent via stable ids).

## 4. Part 1 — Generate data → text (corpus rendering)

New `app/rag/ingest.py` renders each record into an embedding-friendly passage
(never raw JSON), reading through the repository layer. Examples:

**Visa** (`visa_to_document`):
```
Visa & entry requirements for Vietnam.
Many nationalities get 45 days visa-free; others can apply for a 90-day e-visa online before arrival.
Visa-free stay: 45 days. Visa-on-arrival: available. E-visa: available. Passport validity: 6 months beyond entry.
```
metadata: `{source:"visa", country:"Vietnam"}` · id: `visa-Vietnam`

**Tip** (`tip_to_document`) — country & city scope:
```
Local tip — Hanoi, Vietnam (transport, essential): Crossing the road: walk slow and steady.
Traffic won't stop for you, but it will flow around you. Step out at a steady, predictable pace...
```
metadata: `{source:"tip", scope:"city", city:"Hanoi", country:"Vietnam", category:"transport", title:"...", is_essential:true}` · id: `tip-{tip.id}`

**Country summary** (`summary_to_document`):
```
Vietnam — destination overview.
<the COUNTRY_SUMMARIES prose>
```
metadata: `{source:"summary", country:"Vietnam"}` · id: `summary-Vietnam`

`build_knowledge_corpus(session)` assembles all three; `ingest_knowledge(store,
session)` embeds them with stable ids. `chunk_text()` (400/50 overlap splitter) is
retained for any long prose.

## 5. Part 2 — Query → RAG (retrieval + tool)

- **`app/rag/retriever.py`** — restored `hybrid_search(store, query, filters, k,
  fetch_k)` + `_store_filter_kwargs`: RRF of semantic `similarity_search` +
  lexical token overlap; the metadata filter is pushed into `similarity_search`
  to avoid result starvation. Engine-agnostic — works on in-memory + pgvector.
- **`app/tools/rag_tools.py`** — new `search_travel_knowledge` tool:
  `@tool(args_schema=SearchTravelKnowledgeArgs)`, `log_tool_call`, calls
  `get_knowledge_store()` → `hybrid_search`, returns
  `{"results": [{content, metadata}], "count": n}` (empty → `{"results": [], "count": 0}`).
  Args: `query` (required), optional `country` / `city` / `source` metadata
  filters. Follows the `get_local_tips` tool conventions (hand-authored
  `AppBaseModel` args schema, `readOnly` tool metadata).
- **`app/tools/registry.py`** — import `KNOWLEDGE_TOOLS` and add to
  `TOOLS_BY_DOMAIN["concierge"]`.
- **Concierge prompt v9** — v8 + a short section instructing the LLM to call
  `search_travel_knowledge` for visa/entry and local-advice questions, grounding
  on its results. Bump `active.yaml` `concierge: 8 → 9`.

**Tool name:** `search_travel_knowledge` (distinct from the deleted
`search_destination_knowledge` to signal the new visa+tips scope).

## 6. File changes

**New:**
| File | Purpose |
|---|---|
| `apps/api/app/rag/__init__.py` | re-create package |
| `apps/api/app/rag/embeddings.py` | `get_vector_store()` (PGVector/InMemory, cached singleton by url) + `DEFAULT_COLLECTION` + `reset_vector_store()`; imports `get_embeddings`/`EMBED_DIM` from `app/core/embeddings` (no duplication) |
| `apps/api/app/rag/ingest.py` | `chunk_text`, `visa_to_document`, `tip_to_document`, `summary_to_document`, `build_knowledge_corpus`, `ingest_knowledge` |
| `apps/api/app/rag/retriever.py` | restored `hybrid_search` + `_store_filter_kwargs` |
| `apps/api/app/tools/rag_tools.py` | `search_travel_knowledge` tool + `KNOWLEDGE_TOOLS` |
| `apps/api/scripts/ingest_rag.py` | CLI to ingest knowledge into the configured store (Postgres) |
| `apps/api/app/prompts/concierge/v9.md` | v8 + knowledge-search guidance |
| `apps/api/tests/rag/conftest.py` | `seeded_session` + `reset_vector_store` fixture |
| `apps/api/tests/rag/test_embeddings.py` | `get_vector_store` selects in-memory for SQLite; fake embeddings deterministic |
| `apps/api/tests/rag/test_retriever.py` | hybrid_search: empty store, metadata filter, no-starvation, top-k (restored) |
| `apps/api/tests/rag/test_ingest.py` | visa+tips corpus build + ingest + stable-id no-duplicate |
| `apps/api/tests/tools/test_rag_tools.py` | tool args_schema + behavior (returns results / empty) |
| `specs/travel-knowledge-rag/PLAN.md` | this document |

**Modified:**
| File | Change |
|---|---|
| `apps/api/requirements-ai.txt` | re-add `langchain-postgres` + `pgvector` (compatible pins; keep explicit `numpy`) |
| `apps/api/app/tools/registry.py` | import + add `KNOWLEDGE_TOOLS` to concierge |
| `apps/api/app/prompts/active.yaml` | `concierge: 8 → 9` |
| `apps/api/app/core/lifespan.py` | after `seed_all`, pre-warm `get_knowledge_store()` (auto-ingest) |
| `apps/api/app/agents/subagents/concierge.py` | refresh stale docstring ("place/weather tools + RAG retrieval") |
| `apps/api/tests/tools/test_tool_registry.py` | assert `search_travel_knowledge` in concierge + `readOnly=True` metadata |
| `apps/api/tests/agents/test_subagents.py` | (optional) re-add `test_concierge_has_knowledge_tool` |

**No Alembic migration** — the pgvector extension migration (`b68656f68e88_…`)
already exists; PGVector auto-creates collection tables at runtime (as before).

## 7. Dependencies

Re-add to `requirements-ai.txt` (must coexist with langchain 1.3.11 /
langchain-core 1.4.8 / langgraph 1.2.6 — `pip check` after install):
- `langchain-postgres` (provides PGVector; verify import name/API — current
  versions may expose `PGVectorStore` instead of `PGVector`).
- `pgvector` (SQLAlchemy/pgvector type support).

Keep the explicit `numpy>=1.21,<3` (still needed by the fake-embeddings path in
`app/core/embeddings.py`, independently of this feature).

## 8. Task waves

| Wave | Tasks | Parallelism | Depends on |
|---|---|---|---|
| 1 | 1.1 deps · 1.2 `rag/embeddings.py` · 1.3 `rag/retriever.py` · 1.4 `rag/ingest.py` | 4 (disjoint files) | — |
| 2 | 2.1 `tools/rag_tools.py` · 2.2 `registry.py` · 2.3 prompt v9 + `active.yaml` | 3 (disjoint files) | Wave 1 |
| 3 | 3.1 `lifespan.py` pre-warm · 3.2 `scripts/ingest_rag.py` | 2 | Wave 2 |
| 4 | 4.1 `tests/rag/*` · 4.2 `tests/tools/test_rag_tools.py` · 4.3 update `test_tool_registry.py` + `test_subagents.py` | 3 | Waves 1–3 |
| 5 | 5.1 `specs/travel-knowledge-rag/PLAN.md` | 1 | — (already drafted) |

## 9. Testing strategy

- **No network / no key:** tests run with `DeterministicFakeEmbedding` (unset
  `OPENAI_API_KEY`), so `tests/rag/` and `tests/tools/test_rag_tools.py` are
  hermetic. An `agent_db`-style fixture seeds a temp SQLite DB;
  `reset_vector_store()` between tests prevents singleton leakage.
- **Coverage:** corpus rendering (visa/tip/summary docs), ingest idempotency
  (stable ids, no duplicates), `hybrid_search` (empty / filter / no-starvation /
  top-k), tool schema (required `query`, optional filters), tool returns results
  on a seeded DB + empty on no-match, registry wiring + readOnly metadata,
  concierge sub-agent still builds.
- **Cross-engine:** `make test-docker` exercises the pgvector path on Postgres.

## 10. Verify

```bash
cd apps/api
ruff check app scripts && ruff format app scripts
make test                  # SQLite suite green (fake embeddings, no network)
make test-docker           # Postgres suite green (pgvector hybrid path)
../../.venv/bin/pip check  # no dep conflicts from re-adding langchain-postgres
```

## 11. Decisions, tradeoffs & non-goals

- **Decided:** pgvector backend (owner choice) — restores hybrid RRF quality at
  the cost of re-adding two deliberately-removed deps; in-memory degrade keeps
  SQLite/tests zero-config.
- **Singleton + auto-ingest** (vs. old manual-only ingest): makes the tool work
  on SQLite/tests out-of-the-box; idempotent on Postgres.
- **Read via repos** (not `app.data` directly): honors the repo's seed-source
  rule; the corpus reflects the seeded DB.
- **Ungated** (no `allow_rag` tier flag): simplest re-intro; episodic-style
  gating is a future option, not a task here.
- **Risk:** `langchain-postgres` API drift since removal (`PGVector` vs
  `PGVectorStore`) — mitigated by checking the installed version's import surface
  during Wave 1 and `pip check`.

## 12. Status Log

- 2026-07-08 — Plan drafted from codebase exploration (recovered the deleted
  RAG implementation from git `3d0dc6a^` / `8366805^`) and an owner decision to
  re-add the pgvector backend. Status: proposed. Not yet isolated on a feature
  branch.
- 2026-07-08 — Implementation on branch `feat/travel-knowledge-rag` (off `v3`).
  Re-added `langchain-postgres` 0.0.17 + `pgvector` 0.3.6 (`pip check` clean).
  Created `app/rag/{embeddings,retriever,ingest}.py` (corpus = 140 docs: 16 visa
  + ~108 country/city tips + 16 summaries), `app/tools/rag_tools.py`
  (`search_travel_knowledge`), wired into the concierge registry, concierge
  prompt v9 (`active.yaml` 8→9), lifespan auto-ingest pre-warm, and
  `scripts/ingest_rag.py`. Tests: `tests/rag/{test_vector_store,test_retriever,
  test_ingest}` + `tests/tools/test_rag_tools.py` + registry/subagent/prompt
  guards — all hermetic (fake embeddings, no network). 84 RAG/tool/registry/
  subagent/prompt tests green; full suite 1393 passed, 8 failed — the 8 are
  pre-existing env-dependent failures (real `OPENAI_API_KEY`/`LANGFUSE_*` in
  `apps/api/.env`), confirmed passing on the clean `v3` baseline (no `.env`);
  none caused by this change. Status: implemented, ready for review.
