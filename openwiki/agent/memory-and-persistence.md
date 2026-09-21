---
type: architecture
title: Conversation memory and persistence
description: The three persistence layers behind an agent conversation — the LangGraph checkpointer (Postgres or ephemeral in-memory) keyed by thread id, the embedding-indexed long-term Store with per-user preference, procedural and episodic namespaces, and the conversations/messages tables — plus rolling summarization and the best-effort background memory extraction that writes to the store after each turn.
tags: [memory, checkpointer, langgraph-store, postgres, pgvector, summarization, extraction, persistence, conversations]
sources:
  - id: openwiki-source-a64c3aced180db6f1a30c537
    resource: repo://apps/api/app/agents/checkpointer.py
  - id: openwiki-source-aab651981316f0a542a5e4dd
    resource: repo://apps/api/app/agents/state.py
  - id: openwiki-source-0e29236b52482e5a3cdf5f04
    resource: repo://apps/api/app/agents/subagents/_base.py
  - id: openwiki-source-5300fab0b97a7cfb93201ea7
    resource: repo://apps/api/app/core/config.py
  - id: openwiki-source-f0d67c8926258128935ee4fb
    resource: repo://apps/api/app/core/embeddings.py
  - id: openwiki-source-bd6cd21e04f99bedcd541c52
    resource: repo://apps/api/app/db/models/conversation.py
  - id: openwiki-source-14276eb6600fc4bcd0ac053b
    resource: repo://apps/api/app/db/models/message.py
  - id: openwiki-source-400afaf04237d2d22ae612fc
    resource: repo://apps/api/app/memory/extraction_runner.py
  - id: openwiki-source-1ae919b0f3bdf4d33e0ac591
    resource: repo://apps/api/app/memory/extractor.py
  - id: openwiki-source-185823a428ccf3122dfd78c4
    resource: repo://apps/api/app/memory/guard.py
  - id: openwiki-source-a5c845beb00af03ac7650938
    resource: repo://apps/api/app/memory/store.py
  - id: openwiki-source-2924e63728b20261ea72a20e
    resource: repo://apps/api/app/memory/summarizer.py
  - id: openwiki-source-48cde84fc647394c277c19ac
    resource: repo://apps/api/app/repositories/conversation.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-aae2f3ae4e0843e6715ef3ac
    resource: repo://apps/api/app/tools/memory_tools.py
  - id: openwiki-source-0f2058c2da25b533f22d98bc
    resource: repo://apps/api/tests/agents/test_checkpointer.py
  - id: openwiki-source-1062a6db2b17199c8d24141d
    resource: repo://apps/api/tests/api/routes/test_no_memory_route_yet.py
  - id: openwiki-source-3080a957448998af5aa6ff21
    resource: repo://apps/api/tests/memory/test_extraction_runner.py
  - id: openwiki-source-5d1a7ebf1f2fd5e5efecdbe7
    resource: repo://apps/api/tests/memory/test_fact_age.py
  - id: openwiki-source-aa2fa0188bf2b6bd24abe74f
    resource: repo://apps/api/tests/memory/test_search_all.py
  - id: openwiki-source-36b2a5e944066755363a2812
    resource: repo://apps/api/tests/memory/test_summarize_token_budget.py
generated: { by: "claude-code", at: "2026-09-21T09:19:54.601Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-21T09:19:54.601Z
---

# Conversation memory and persistence

Three independent stores hold conversational state, each with a different lifetime and owner:

| Layer | Backend | Keyed by | Owner |
|---|---|---|---|
| Graph checkpoint (short-term, per thread) | `AsyncPostgresSaver` or `MemorySaver` | LangGraph `thread_id` | `app/agents/checkpointer.py` |
| Long-term memory (cross-session) | `PostgresStore` with pgvector index or indexed `InMemoryStore` | `("users", user_id, kind)` namespaces | `app/memory/store.py` |
| Durable chat record (queryable history) | `conversations` and `messages` tables via SQLAlchemy | `conversation_id` | `app/repositories/conversation.py` |

Both LangGraph backends are opened once in the FastAPI lifespan and passed to `build_graph`; a config-driven graph rebuild reuses them so conversation state survives (see [LLM providers and per-agent configuration](llm-providers-and-agent-config.md)).

## Checkpointer: thread state and its degradation rules

`open_checkpointer(database_url)` selects `AsyncPostgresSaver` for any URL starting with `postgres` (after stripping SQLAlchemy's `+psycopg` driver suffix so libpq accepts it) and calls `setup()` to create its tables. Anything else yields `MemorySaver`. If Postgres is configured but unreachable, the behaviour depends on the environment: **production refuses to start** (a critical log, then re-raise) rather than silently running on ephemeral state, while development and test log a warning and degrade to `MemorySaver`, meaning history will not survive a restart. `tests/agents/test_checkpointer.py` covers all three outcomes and `test_checkpointer_selection.py` checks the URL-prefix variants.

The agent router derives the thread id as `user_{user_id}_trip_{trip_id or 'none'}_conv_{conversation_id}` and passes it in `configurable.thread_id`, together with `recursion_limit` from `AGENT_RECURSION_LIMIT`, the tracing callbacks plus the per-turn metrics handler, and the LangChain root `run_id` set to the `agent_runs` row id so metrics correlate. A new turn's input includes `trip_id` **only when the client supplied one**: that state channel has no reducer, so omitting the key preserves the checkpointed value while an explicit `None` would clobber a trip selected mid-conversation. See [Agent chat endpoints, SSE streaming and side panels](streaming-and-side-panels.md).

## Rolling summarization

The graph's `summarize` node calls `should_summarize` and, when it fires, `summarize_conversation` (`app/memory/summarizer.py`). The trigger is an **OR** of two branches:

- **Message count** — `len(messages)` exceeds `SUMMARIZE_THRESHOLD` (default 20). This branch is never bypassed.
- **Token pressure** — the estimated token count exceeds `SUMMARIZE_TOKEN_BUDGET * 0.85` (default budget 12000; the 15% headroom is left for the system prompt and the next reply). The estimate is `chars / 4` over message content **plus tool-call names and arguments**, so a fan-out turn that carries most of its weight in tool payloads is caught even below the message threshold. It deliberately avoids `llm.get_num_tokens_from_messages()`, whose base implementation needs `transformers` (not installed) and raises for models that do not override it, including the test `FakeLLM`. The branch is floored at `DEFAULT_KEEP_LAST` (5): with five or fewer messages there is nothing the compressor could remove, so it does not fire.

`summarize_conversation` computes the split **before** calling the model. The split keeps at least the last five messages verbatim and **walks back past any `ToolMessage` run** so a tool-call/tool-result pair is never separated; an orphaned tool result is rejected by the provider on the next call. If nothing is removable it returns `("", [])` without an LLM call, and the node returns no update, so "the node fired" and "the node made progress" stay the same event and an existing summary is never blanked.

When a rolling summary already exists, the node passes it back in as `previous_summary` and the model is asked to **merge** it with the newer messages into one summary of at most 250 words that never drops a concrete fact (destinations, dates, budget, booked items, preferences, constraints), because the messages behind the old summary are already deleted. Without the merge, repeated compression would narrow the summary to the latest window and the agent would forget facts stated earlier in the same session. The word limit is only a request, so code also caps the stored summary at 1800 characters and logs a warning when the cap truncates; that warning signals a prompt problem, since truncation can cut carried-forward facts. The summary is injected at the front of every model call by `system_with_summary` (see [Agent state, runtime context and reply language](state-context-and-language.md)). `tests/memory/test_summarize_token_budget.py` covers both trigger branches, the tool-payload count, the nothing-removable early return and the merge.

## Long-term store

`open_store` mirrors the checkpointer: a Postgres URL gets `PostgresStore` with a semantic index, any other URL or any init failure gets an indexed `InMemoryStore` (logged, never raised). The index embeds the `text` field of each value with `EMBED_DIM=1536` dimensions; `get_embeddings()` returns OpenAI `text-embedding-3-small` when `OPENAI_API_KEY` is set and a `DeterministicFakeEmbedding` of the same size otherwise, so dimensions are stable across modes and dev/test never need network. A Postgres image without pgvector falls back to the in-memory store, and without a semantic index a `query` is silently ignored and search degrades to recency.

### Namespaces and kinds

Every item lives under `("users", <user_id>, <kind>)` with three kinds, exposed as the `MemoryKind` enum:

- **`prefs`** (guard kind `preferences`): key-addressed traveller preferences. The reserved keys `name`, `gender`, `travel_group` form the **profile** (`get_profile`), and `load_context` reports the remaining keys as preferences.
- **`procedural`** (guard kind `instructions`): standing instructions injected into every prompt.
- **`episodes`**: past-trip outcomes, key-addressed by trip id or a normalized slug so re-extracting a trip **overwrites** rather than appends, with `trip_id`, `city` and `outcome` (`proposed` or `approved`) alongside the text.

Every upsert stamps `updated_at` (UTC ISO) and runs the write guard; every read runs the read guard and drops or truncates rows accordingly. Both guards are described in [Guardrails](guardrails-pii-and-hitl.md).

### Read semantics

`store.search` has no unlimited mode, so unqueried reads page through the namespace in pages of 100, de-duplicating by `(namespace, key)` and stopping on a short page **or a page with nothing new**, so a backend that mishandles `offset` cannot spin. A semantic `query` is a top-k search (k=10) and is deliberately never paged. Episodes default to a limit of 3. `search_memory` / `search_memory_typed` dispatch over the three kinds and return typed `Preference`, `Instruction` and `Episode` records; the typed variant keeps the key so `load_context` can separate profile keys from other preferences. `tests/memory/test_search_all.py` pins the paging and termination rules.

### Recorded age of remembered facts

Typed `Preference`, `Instruction` and `Episode` records carry the stored `updated_at`, and `load_context` renders it as a `(recorded …)` suffix on each standing-instruction and preference line (see [Agent graph and supervisor](graph-and-supervisor.md)). `format_age` computes whole **elapsed months** in code — the model only reads the phrase — and never produces a day count, because a string that changed daily would churn the cached system prompt for every user. It returns `None`, and the line renders with no marker, when the stamp is missing, unparseable or in the future; a future stamp (clock skew, bad backfill) would otherwise be labelled maximally fresh.

There are two vocabularies, chosen by where the block sits in the system prompt:

| Vocabulary | Used for | Phrases |
|---|---|---|
| Coarse | standing instructions (early in the prompt, ahead of `summary`) | `in the last month`, `1-11 months ago`, `over a year ago` |
| Fine | preferences (last block, after which only the daily date note follows) | `in the last month`, `1-3 months ago`, `4-8 months ago`, `9-15 months ago`, `over a year ago` |

The coarse table changes at most twice in a row's lifetime to protect the cached prefix; the fine table can afford more churn because the cached prefix already ends before it. The freshest phrase is "in the last month", not "this month", because elapsed months do not map to calendar months. `AGE_FRESH` is a public constant that `state.py` imports to build the prompt rule that only fresh lines may be acted on without confirmation, so the rule and the emitted vocabulary cannot drift apart. `tests/memory/test_fact_age.py` pins the buckets, the future-stamp rule and the shared literal.

### Management helpers (no HTTP route yet)

`list_memory` returns a user's rows for one kind with the store `key` preserved (the key is spread last so a stored value cannot shadow the delete handle), and `delete_memory` hard-deletes one row by `(kind, key)`, idempotently. Both coerce `kind` through `MemoryKind` before building the namespace, so an unknown kind raises instead of reaching the store; on an indexed `PostgresStore` the delete also removes the pgvector row by cascade. Nothing reachable calls them yet: the `/memory` list/delete routes and their settings UI are deferred, and `tests/api/routes/test_no_memory_route_yet.py` fails if a `/memory` path appears in the OpenAPI document before that deferral is lifted.

### Tools over the store

`app/tools/memory_tools.py` exposes `save_user_preference`, `get_user_preferences` and `recall_past_trips`, all receiving the store through `InjectedStore` (declared explicitly in their `args_schema`, see [Specialist sub-agents and the tool registry](specialists-and-tools.md)). `recall_past_trips` is the episodic-recall tool bound to the planner and is filtered out of the tool set when `AgentContext.allow_episodic` is `False`.

## Background memory extraction

Extraction is **not** a graph node. After a completed (non-interrupted) turn the router schedules `run_memory_extraction` as a FastAPI background task; the streaming endpoint uses `run_memory_extraction_from_stream`, which reads the final graph values from a sink that `stream_agent_events` fills only after the SSE stream fully drains, and is a no-op when the sink is empty or a plan-approval interrupt is pending.

`extract_memories` (`app/memory/extractor.py`) sends the `memory_extraction` prompt plus **only the last user turn and the final non-tool-calling assistant answer**; `ToolMessage`s and intermediate tool-calling `AIMessage`s are excluded so tool or RAG output carrying a smuggled "from now on…" directive never reaches the extractor. The JSON reply is parsed defensively and any failure yields an empty result.

`run_memory_extraction` then upserts each preference, instruction and episode **per item**, catching `MemoryRejected` and the malformed-JSON exception family (`TypeError`, `AttributeError`, `KeyError`, `ValueError`) individually so one poisoned or malformed item never drops its siblings; rejections are logged with kind, key and reason but never the text. Episodes record `outcome="approved"` when the turn passed the booking plan-approval gate, otherwise the extractor's default `proposed`. The whole run is skipped when `allow_memory_write` is false or there is no user id or store, and any other error is swallowed. When a `run_id` and session factory are supplied, the extractor's LLM calls, tokens and wall-clock are recorded onto the turn's `agent_runs` row in a separate try block so a metrics failure cannot starve the writes. `tests/memory/test_extraction_runner.py` covers the mixed-batch and malformed-item cases.

## Durable chat record

`Conversation` rows carry `user_id`, optional `trip_id`, `title` and `domain`; `Message` rows carry `conversation_id`, `role`, `content`, optional `tool_calls` JSON and an `agent_run_id` that links an assistant reply to its run (NULL for user turns and pre-link history). The router persists the redacted user turn **before** the graph runs (skipping on a client retry to avoid a duplicate bubble) and the assistant reply after, reusing the message id it already sent to the client. `ConversationRepository` also serves the free-tier quota (`count_user_turns_since`), ownership-scoped listing and message retrieval, and message lookup for feedback. Schema for these tables is managed by Alembic on Postgres; see [Data layer and migrations](../architecture/data-layer-and-migrations.md).

## Operational notes

- Run the dev Postgres (`cd apps/api && docker compose up -d db`) if you want conversation history and long-term memory to survive an API restart; without it both degrade to in-memory with a warning.
- Restarting only the API container is enough to lose in-memory state; a thread that seems to "remember" a bad behaviour across turns is usually a poisoned checkpoint, so start a new conversation rather than editing prompts.
- Travel-knowledge retrieval uses a separate vector store; see [Travel knowledge RAG](rag-travel-knowledge.md).
