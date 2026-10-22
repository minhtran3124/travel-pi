---
type: architecture
title: Travel knowledge RAG
description: How the concierge's travel-knowledge retrieval works — seeded visa, local-tip and country-summary rows serialized to prose and embedded into a pgvector or in-memory vector store at startup as an idempotent upsert, hybrid semantic-plus-lexical retrieval with Reciprocal Rank Fusion and metadata filters, the tool that exposes it, and how it degrades when the store or embeddings fail.
tags: [rag, pgvector, embeddings, retrieval, hybrid-search, concierge, visa, tips]
sources:
  - id: openwiki-source-f0d67c8926258128935ee4fb
    resource: repo://apps/api/app/core/embeddings.py
  - id: openwiki-source-f18f564b85852ec3a8a054dc
    resource: repo://apps/api/app/core/lifespan.py
  - id: openwiki-source-3c220403326f2311b6c656b2
    resource: repo://apps/api/app/rag/embeddings.py
  - id: openwiki-source-6069f82aa4cfd09478f9ae68
    resource: repo://apps/api/app/rag/ingest.py
  - id: openwiki-source-66d63a80427e314511162eae
    resource: repo://apps/api/app/rag/retriever.py
  - id: openwiki-source-b382d662352789d3dd40199d
    resource: repo://apps/api/app/research/tools.py
  - id: openwiki-source-52775f3d9e219ac7ac49c5a6
    resource: repo://apps/api/app/tools/rag_tools.py
  - id: openwiki-source-97b1fd4b365c73190c64c4c1
    resource: repo://apps/api/app/tools/registry.py
  - id: openwiki-source-6121a92e8487c6cf0bdfdce8
    resource: repo://apps/api/tests/rag/test_retriever.py
  - id: openwiki-source-3cdb1299cb5cb7a383fd3d3f
    resource: repo://apps/api/tests/rag/test_vector_store.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
---

# Travel knowledge RAG

The concierge answers free-text questions about entry requirements and practical local advice through `search_travel_knowledge`, a retrieval tool over a small vector store built from the **seeded reference data** (visa rules, local tips, country overviews). This is separate from the long-term traveller memory store described in [Conversation memory and persistence](memory-and-persistence.md), though both use the same embedding selection.

## Store selection and caching

`get_vector_store()` in `apps/api/app/rag/embeddings.py` picks the backend by `DATABASE_URL`: a Postgres URL gets `langchain_postgres.PGVector` (collection `travel_knowledge`), anything else gets an `InMemoryVectorStore`. The store is **cached per `(database_url, collection)`**, because an in-memory store's contents live on the instance; without caching, SQLite and test runs would embed at startup and then query an empty new instance. The cache uses double-checked locking on a reentrant lock rather than `lru_cache`, because `PGVector`'s first construction registers ORM tables on a process-global SQLAlchemy `Base` that is not thread-safe; concurrent cold misses used to collide with "Table already defined". Passing explicit `embeddings` bypasses the cache and returns a private instance; `reset_vector_store()` clears the cache so a test that repoints `DATABASE_URL` does not reuse a store cached against the old URL. `tests/rag/test_vector_store.py` covers the singleton, per-URL isolation, reset and the concurrent-build-once guarantee.

Embeddings come from `app/core/embeddings.py`: OpenAI `text-embedding-3-small` when `OPENAI_API_KEY` is set, otherwise a `DeterministicFakeEmbedding` of the same 1536 dimensions, so dev and test need no network and dimensions stay stable across modes. The pgvector extension itself is enabled by an Alembic migration on Postgres (see [Data layer and migrations](../architecture/data-layer-and-migrations.md)).

## Corpus and ingestion

`build_knowledge_corpus(session)` (`app/rag/ingest.py`) reads through the **repository layer**, so the corpus reflects the seeded database rather than `app.data` directly. It produces three document kinds, each serialized to a natural-language template rather than raw JSON so the text embeds well:

- `visa` — one per country with a visa record: summary, visa-free days (or "a visa is generally required"), visa-on-arrival, e-visa and passport-validity phrasing; metadata `{source, country}`.
- `tip` — country-scoped tips for every country that has a seeded city, plus city-scoped tips resolved from the city record; metadata carries `scope`, `country`, `category`, `title`, `is_essential` and `city` when present.
- `summary` — a destination overview per country that has one.

`ingest_knowledge(store, session)` splits long content with a recursive splitter (400 characters, 50 overlap) so a detail buried in a long tip embeds against its own vector, and derives a **stable id per document** (`visa-<country>`, `summary-<country>`, `tip-<city>-<country>-<category>-<title>`; chunks get a `#i` suffix). Because ids are stable, `add_documents` is an idempotent upsert: re-running ingestion replaces rather than appends. Tip ids include category so two same-titled tips in one location do not collide. `tests/rag/test_ingest.py` and `test_retriever.py::test_ingest_knowledge_stable_ids_no_duplicate` pin these shapes.

Ingestion runs during application startup: the lifespan pre-warms the store so the tool works from the first request. For a persisted backend it probes `similarity_search("visa", k=1)` and **skips re-embedding when the corpus is already present**; an in-memory store is always re-ingested. The whole block is wrapped so a failure only logs and the tool degrades to empty results, never blocking startup. `scripts/ingest_rag.py` runs the same upsert on demand against a Postgres URL when embeddings should persist.

## Retrieval

`hybrid_search` (`app/rag/retriever.py`) fetches `fetch_k = 4 × k` candidates by semantic similarity with the metadata filter **pushed into `similarity_search`**, so the pool is filtered before fusion; filtering afterwards starved results when matching documents were sparse in the semantic top-N. It then ranks the same candidates by lexical token overlap (lower-cased `\w+` tokens, so a punctuated "Vietnam?" still matches) and fuses the two orderings with Reciprocal Rank Fusion (`k = 60`), returning the top `k` (5 by default). The filter is adapted per backend: a callable predicate for `InMemoryVectorStore`, a metadata dict for `PGVector`. `tests/rag/test_retriever.py` checks the empty-store case, metadata filtering, no-starvation under filtering and top-k without a filter.

## The tool

`search_travel_knowledge` (`app/tools/rag_tools.py`) accepts `query` plus optional `country`, `city` and `source` (`visa` / `tip` / `summary`). Country and city are **fuzzy-resolved to the seeded canonical names** first, because the store filters by exact metadata equality and an inexact spelling would otherwise return a spurious empty result. The tool returns `{results: [{content, metadata}], count}`; an empty result is a signal (`count: 0`), never an error, and any store or embedding failure is caught and returns the same empty shape. Its docstring instructs the model to present results as guidance snippets and to remind travellers that visa rules depend on nationality and change.

The tool is part of the concierge's tool group in the registry (`KNOWLEDGE_TOOLS`), so knowledge questions route to the concierge; the supervisor prompt treats visas and general travel knowledge as concierge-only, which is why a planning message that also asks about visas fans out to the concierge (see [Agent graph and supervisor routing](graph-and-supervisor.md) and [Specialist sub-agents and the tool registry](specialists-and-tools.md)). Because it needs no injected state or store, it is also served over MCP (see [MCP server exposure](../integrations/mcp-server.md)). The trip-research deep agent reuses the same tool unchanged: its `entry_season` subagent binds `search_travel_knowledge` next to `get_visa`, `get_local_tips`, `get_climate` and `get_packing` (see [Trip-research deep agent](trip-research-deep-agent.md)).

## Operational notes

- On SQLite or when Postgres lacks pgvector, retrieval works but is in-memory and re-embedded on every start; with the fake embeddings, semantic ranking is deterministic but not meaningful, and the lexical leg carries the results.
- Changing seeded tips or visa rows requires re-ingestion: on a persisted store the startup probe will see existing content and skip, so run `python scripts/ingest_rag.py` to upsert the new text.
