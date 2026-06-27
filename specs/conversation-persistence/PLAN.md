---
slug: conversation-persistence
status: active
owner: Minh Tran
created: 2026-06-27
---

# Conversation Persistence Wiring

> Diagnosis source: `specs/travel-agent/RUNNABLE_CONFIG_RESEARCH.md` follow-up investigation.
> This plan does **not** do the LangGraph `Runtime`/`context` refactor — that is orthogonal and
> not a fix for these bugs. See §2 Non-goals.

## 1. Motivation

Three user-visible bugs, all from missing persistence *wiring* (the data model already exists):

1. **Reload loses the conversation.** FE keeps `conversationId` only in a React ref
   (`useAgentStream.ts:83`) → lost on reload; no history is fetched on mount; no GET endpoint
   exists to fetch it.
2. **Messages don't carry context across turns / restarts.** The checkpointer degrades to an
   ephemeral `MemorySaver` whenever `DATABASE_URL` is non-Postgres (`checkpointer.py:46`,
   default `sqlite:///travel.db` in `config.py:86`) → graph state is wiped on every process
   restart (and uvicorn `--reload` restarts constantly in dev).
3. **Nothing the user does is persisted.** **The FE only calls `/agent/stream`**
   (`useAgentStream.ts:159`), and `stream_agent_events` (`streaming/mapper.py`) **never writes
   to the DB** — it only yields SSE. The `/agent/chat` route *does* persist
   (`agent.py:100-137`) but the FE never calls it. So no `Conversation` row and no `Message`
   rows are ever created for real chats, and `/stream` even invents a throwaway
   `stream-<uuid>` thread id when `conversation_id` is null (`agent.py:159`).

**Already in place (do not rebuild):** `models.Conversation`, `models.Message`,
`ConversationRepository.{create_conversation,append_message,list_for_user,list_messages}`
(`repositories/conversation.py`), and the `Conversation`/`Message` Pydantic schemas
(`schemas/agent.py:67-83`).

## 2. Non-goals

- **No `RunnableConfig`/`Runtime`/`context_schema` refactor in *this* plan.** Orthogonal to
  these bugs — moving `user_id` out of state fixes none of them. It is now **greenlit as a
  sibling plan** (`specs/runtime-context-config/`, driver: user-selectable *mode* + *tier*),
  but sequenced after persistence. This plan must stay **forward-compatible**: see the
  invoke-site note in Task 1.1 so the refactor doesn't have to undo work done here.
- **No conversation sidebar / multi-conversation switcher** in this plan. Restoring the
  *current* conversation on reload fixes all three reported bugs. A list UI is a follow-up
  (the BE list endpoint is built here so the follow-up is cheap).
- **No DB schema change / migration.** Tables and columns already exist.
- **No auth changes.** `user_id` continues to arrive from the FE (Supabase identity) as today.

## 3. Success Criteria

- After sending turns then reloading the page, the prior messages reappear and the next turn
  continues the same thread (agent remembers earlier context).
- A `Conversation` row + a `Message` row per user/assistant turn exist in the DB after a
  `/agent/stream` turn.
- Message-to-message context survives a backend restart (durable Postgres checkpointer used
  locally).
- New `GET /agent/conversations` and `GET /agent/conversations/{id}/messages` return the
  persisted data, scoped by `user_id`.

## 4. Tasks

### Task 1.1 — Persist conversation + messages on the `/agent/stream` path

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/routers/agent.py, apps/api/app/streaming/persistence.py, apps/api/tests/api/agent/test_stream_persistence.py</files>
  <action>Make the streaming path persist like /chat does. In agent_stream: when body.conversation_id is None, call repo.create_conversation(user_id, trip_id) and use its real id (drop the `stream-{uuid4}` fallback at agent.py:159) so thread_id and the FK are valid; echo this id in the existing `start` event. Append the user message (repo.append_message role="user") BEFORE returning the StreamingResponse, using the request-scoped session. Add app/streaming/persistence.py with an async wrapper generator `persist_assistant_turn(events_iter, *, conversation_id)` that passes every TypedSSEEvent through unchanged while accumulating assistant text from `token` events and clearing it on `reset` events (mirroring the FE's reset semantics in mapper.py:92); on stream completion it writes the final assistant text via repo.append_message role="assistant" using an ISOLATED session (own sessionmaker from app.db.session, NOT the request-scoped Depends session — that may be torn down during streaming; see rules/guidelines.md Data Access). Wrap stream_agent_events(...) with this generator in sse_response. Do not persist on resume turns that only continue an interrupt unless a final assistant text is produced. Rule 2: guard empty assistant text (skip the append). Leave /agent/chat unchanged.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_persistence.py -x</verify>
  <done>After a POST /agent/stream turn, DB has 1 Conversation + a user Message + an assistant Message with the streamed reply; thread_id uses the real conversation id.</done>
</task>
```

> **Forward-compat note (re: sibling `runtime-context-config` plan).** Keep passing `user_id`
> and `trip_id` in the invoke **state dict** as today — do *not* pre-emptively switch the
> invoke to `context=` here. The sibling refactor will change the invoke signature once; doing
> half of it now would create a confusing intermediate state. Just avoid adding *new* per-run
> values (mode/tier) to state — those belong to the refactor's `context_schema`.

### Task 1.2 — Enable durable Postgres checkpointer for local dev

```xml
<task id="1.2" wave="1">
  <files>apps/api/.env.example, apps/api/tests/agents/test_checkpointer_selection.py, docs/solutions/agent/local-postgres-checkpointer.md</files>
  <action>Per the chosen approach (Postgres locally), document and lock in the durable path. The selection logic in checkpointer.py:46 already routes any `postgres`-prefixed DATABASE_URL to AsyncPostgresSaver with setup(); confirmed against https://docs.langchain.com/oss/python/langgraph/checkpointers (AsyncPostgresSaver.from_conn_string + await setup()). Do NOT change the selection code unless the test below proves a gap. Add/extend .env.example with a commented local Postgres DATABASE_URL (e.g. `postgresql+psycopg://postgres:postgres@localhost:5432/travel?sslmode=disable`) and a one-line note that non-Postgres URLs degrade to ephemeral MemorySaver (no cross-restart memory). Add a fast unit test that monkeypatches AsyncPostgresSaver to assert a postgres URL selects it (and a non-postgres URL yields MemorySaver) WITHOUT requiring a live DB. Write a short docs/solutions note capturing the "MemorySaver wipes on uvicorn --reload" gotcha and how local Postgres fixes message continuity.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_checkpointer_selection.py -x</verify>
  <done>Test proves postgres→AsyncPostgresSaver and non-postgres→MemorySaver; .env.example + docs note explain enabling local Postgres.</done>
</task>
```

### Task 2.1 — History read endpoints

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/routers/agent.py, apps/api/app/schemas/agent.py, apps/api/tests/api/agent/test_agent_history.py</files>
  <action>Expose the existing repo reads. Add GET /agent/conversations?user_id=... → repo.list_for_user(user_id) returning list[Conversation]; and GET /agent/conversations/{conversation_id}/messages → repo.list_messages(conversation_id) returning list[Message]. Reuse the existing Conversation/Message schemas (schemas/agent.py:67-83); add thin list-wrapper response models only if the project convention requires an envelope (match neighbouring routers). Use SessionDep + ConversationRepository as in agent_chat. Scope conversations by user_id (the messages route is keyed by conversation_id which is already user-owned). Return [] for unknown user/conversation (do not 404 — matches the repo's empty-list contract). NOTE hard gate: these are new public endpoints (public-contract) — see Risks for the commit authorization env.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py -x</verify>
  <done>GET endpoints return persisted conversations for a user and ordered messages for a conversation; empty lists for unknown ids; 200 status.</done>
</task>
```

### Task 3.1 — FE history fetchers

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/lib/query/agent.ts</files>
  <action>Add typed fetchers matching Task 2.1: `fetchConversations(userId)` → GET /agent/conversations and `fetchConversationMessages(conversationId)` → GET /agent/conversations/{id}/messages, returning the existing Conversation/Message shapes. Reuse the existing api client/base-url helpers already used by ChatRequest in this file. No UI changes here.</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web typecheck</verify>
  <done>Fetchers compile and type-check; return typed Conversation[] / Message[].</done>
</task>
```

### Task 4.1 — Persist conversationId + hydrate messages on mount

```xml
<task id="4.1" wave="4">
  <files>apps/web/src/components/chat/useAgentStream.ts</files>
  <action>Make the current conversation survive reload. Persist conversationIdRef to localStorage (key e.g. `travel.conversationId`, alongside the existing `travel.userId` pattern in lib/identity): read it on init so conversationIdRef starts from storage instead of null (useAgentStream.ts:83); write it whenever it is set/updated (the first-turn mint at :131-133 and the server-echoed id at :174/:189). On mount, if a stored conversationId exists and userId is ready, call fetchConversationMessages (Task 3.1) once and hydrate `messages` (map role/content into ChatMessage) before any new turn; guard against overwriting an in-flight stream. Add a way to clear/start-new (reset ref + storage + messages) but do not build a full sidebar (Non-goal). Rule 1/2: handle empty/failed fetch gracefully (start empty, surface no error blocking new chats).</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web typecheck</verify>
  <done>Reloading the page restores the prior messages and continues the same thread on the next turn.</done>
</task>
```

## 5. Risks

- **Public-contract hard gate (Task 2.1).** New endpoints trip `hooks/risk-corroboration.sh`.
  Per memory `public-contract-hard-gate`, commit with
  `RISK_WARN_CATEGORIES="public-contract"` to downgrade the block to a warning. Lane: normal.
- **Streaming session lifecycle (Task 1.1).** Writing inside the SSE generator with the
  request-scoped session can hit a closed session. Mitigation: isolated session for the
  in-generator assistant write (already specified). This is the highest-risk task — verify the
  assistant Message actually lands after a full stream, not just user message.
- **Local Postgres availability.** Approach chosen is local Postgres; if a dev has no Postgres,
  they fall back to MemorySaver (no cross-restart memory) — documented, not blocked.
  `docker-postgres-setup` spec covers bringing one up.
- **Test DB on schema-less change.** No migration here, but per memory
  `stale-travel-db-breaks-suite-on-schema-change` the suite seeds the real DB; run the targeted
  tests, and `make test` before PR. Local LLM tests: keep `.env` aside if `OPENAI_API_KEY=test`
  breaks LLM/RAG tests (memory `env-openai-key-test-breaks-llm-tests`).

## 6. Status Log

- 2026-06-27 — Plan drafted from BE+FE investigation. Proposed; awaiting approval to execute.
- 2026-06-27 — Wave 1 complete on `feat/conversation-persistence`. Task 1.1 (`77c8a4d`) stream
  persistence + Task 1.2 (`99d0abb`) Postgres checkpointer test/docs. Verify: 6/6 targeted
  tests pass; full `tests/api/agent/`+`tests/agents/` green except 3 pre-existing
  `test_memory.py` failures (real OpenAI embeddings call — memory
  `env-openai-key-test-breaks-llm-tests`, unrelated to this diff). Note: the two tasks ran in
  parallel on one working tree → commit history is cross-contaminated (1.1's new files landed in
  1.2's commit); HEAD content is correct. Remaining waves are single-task (no parallel risk).
- 2026-06-27 — Waves 2–4 complete. Task 2.1 (`d6cfc7d`) history GET endpoints
  (public-contract gate cleared with `RISK_WARN_CATEGORIES`); Task 3.1 (`c270727`) FE history
  fetchers; Task 4.1 (`8897a8b`) FE localStorage persist + hydrate-on-mount. Verify: BE
  `tests/api/agent/` + checkpointer = **32 passed**; FE `tsc --noEmit` exit 0. All success
  criteria met. Ready for manual UI check + PR against `v3`.

## Waves

| Wave | Tasks | Parallelism | Notes |
|------|-------|-------------|-------|
| 1 | 1.1 stream persistence, 1.2 local-PG checkpointer | 2 parallel (disjoint files) | core fix + durability |
| 2 | 2.1 history endpoints | single | shares `agent.py` with 1.1 → after wave 1 |
| 3 | 3.1 FE fetchers | single | needs 2.1's endpoints to exist |
| 4 | 4.1 FE persist + hydrate | single | imports 3.1 fetchers |
