# SUMMARY — RAG vector-store build race

Lane: normal
Confidence: high
Reason: fixes existing RAG-infra behavior (#8) with a proven root cause; concurrency was untested (#9). No hard gate.
Flags: existing-behavior, weak-proof
Affects: apps/api/app/rag/embeddings.py (vector-store construction; no schema/auth/contract/external-provider change)
Input-type: Change request
Route: using-git-worktrees → subagent-driven-development (single cohesive fix)
Escalate: no

## Intent

User request (verbatim): "fix bug for RAG" — the latent bug surfaced during MIN-58 eval work:
`search_travel_knowledge` logged `sqlalchemy.exc.InvalidRequestError: Table
'langchain_pg_collection' is already defined for this MetaData instance`.

## Root cause (reproduced deterministically)

`langchain_postgres` registers its ORM tables (`langchain_pg_collection` /
`langchain_pg_embedding`) on a **process-global declarative `Base`** the first time any
`PGVector` is constructed, memoized in a module global `_classes`. That registration is **not
thread-safe**: `_get_embedding_collection_store` defines `CollectionStore(Base)` (registering
the table) *before* setting `_classes`. `functools.lru_cache` does not serialize concurrent
misses, so two threads racing a cold cache both enter the build and the second re-defines the
already-registered table → the error.

Trigger: the concierge fires tools in parallel, and the offline eval builds the store lazily
with **no lifespan pre-warm** (production pre-warms in `core/lifespan`, which is why it only bit
eval). A 6-thread repro against the dev Postgres failed 5/6 before the fix.

The tool already caught the exception and degraded to `{results: [], count: 0}`, so it never
crashed the agent — but RAG silently returned nothing under concurrent cold start.

## Fix

`app/rag/embeddings.py`: replace `lru_cache` with **double-checked locking** on a reentrant
`_build_lock` + a manual `_store_cache` dict, and serialize the `PGVector` construction inside
`_build_store` under the same lock. Exactly one build happens per `(url, collection)` key even
under a race, and the global table registration is never re-entered concurrently.

## Alternatives considered

- Keep `lru_cache`, only lock inside `_build_store`: fixes correctness but a cold race still
  builds (and discards) N `PGVector` engines. Rejected — the double-checked cache also dedupes.
- Bump `langchain-postgres` (0.0.17): larger, riskier dependency change for a bug we can fix
  cleanly in our own layer.

## Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| rag tests | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/rag -q` | 0 | 25 passed (incl. new concurrent-build-once test) |
| race repro | 6-thread cold-cache build against dev Postgres | 0 | 0/6 errors after fix (was 5/6 before) |
| lint | `cd apps/api && ../../.venv/bin/ruff check app/rag/embeddings.py tests/rag/test_vector_store.py` | 0 | clean |

Note: `tests/tools/test_routing_tools.py` has 2 **pre-existing** failures unrelated to this
change (they fail on clean v3 too) — `.env` carries a real `ORS_API_KEY`, so the routing tool
uses OpenRouteService and the offline-`estimate` assertion fails. Environmental, not this fix.

## Rollback

- Revert code: `git revert <sha>` (single-file logic change; no migration, no data, no contract).
