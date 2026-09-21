---
type: architecture
title: Agent chat endpoints, SSE streaming and side panels
description: The /agent REST surface (chat, stream, conversations, messages, manifest, claim, feedback), how a turn is set up before the graph runs, the typed Server-Sent Events taxonomy and the mapper that turns a LangGraph stream into it with de-duplication and drafts reset, side-panel artifacts and their localization, the persistence and run-recording wrappers, follow-up suggestions, and the failure and interrupt semantics a client can rely on.
tags: [sse, streaming, api, agent-endpoints, side-panel, persistence, suggestions, feedback, conversations]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-21f28c5be11ee9c6a18ea317
    resource: repo://apps/api/app/agents/suggestions.py
  - id: openwiki-source-0c11d3874f7202bbad8fddd7
    resource: repo://apps/api/app/core/streaming.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-1105be9b06d6d56a1f393fc7
    resource: repo://apps/api/app/services/feedback_service.py
  - id: openwiki-source-4a48f560e453efb55fe6af89
    resource: repo://apps/api/app/streaming/events.py
  - id: openwiki-source-76708c8400c5eff5125d4ccf
    resource: repo://apps/api/app/streaming/mapper.py
  - id: openwiki-source-5137402db7c3517e50238553
    resource: repo://apps/api/app/streaming/panel_localizer.py
  - id: openwiki-source-68af6ca698f22da67eb8c45a
    resource: repo://apps/api/app/streaming/panels/__init__.py
  - id: openwiki-source-d886b0e2cf9ea2fb691bad02
    resource: repo://apps/api/app/streaming/panels/base.py
  - id: openwiki-source-2f79ae2dd4825875b9e2e004
    resource: repo://apps/api/app/streaming/panels/hotels.py
  - id: openwiki-source-34203d1d5a997b4fa276444b
    resource: repo://apps/api/app/streaming/persistence.py
  - id: openwiki-source-53aa9f1963cc8720d5032ebb
    resource: repo://apps/api/app/tools/_base.py
  - id: openwiki-source-dd5930e7d3226b663bbde1a2
    resource: repo://apps/api/tests/streaming/test_mapper_tool_event_dedup.py
  - id: openwiki-source-0ed23c817010895ceb640eb0
    resource: repo://apps/api/tests/streaming/test_panel_localizer.py
  - id: openwiki-source-43e63165547a23cadd26e5ac
    resource: repo://apps/api/tests/streaming/test_persistence.py
  - id: openwiki-source-44a3b1409223fa52f93ba58d
    resource: repo://apps/api/tests/streaming/test_synthesize_stream_chunks.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Agent chat endpoints, SSE streaming and side panels

`apps/api/app/routers/agent.py` is the HTTP boundary of the agent. Every route requires a verified Supabase bearer token (see [Authentication and user tiers](../concepts/auth-and-tiers.md)); the graph itself is described in [Agent graph and supervisor routing](graph-and-supervisor.md).

## Routes

| Route | Purpose |
|---|---|
| `POST /agent/chat` | One turn (or an interrupt resume), reply returned as JSON with usage and suggestions |
| `POST /agent/stream` | Same input, reply streamed as typed SSE events |
| `GET /agent/conversations` | The caller's conversations, newest first; a legacy `user_id` query param is ignored |
| `GET /agent/conversations/{id}/messages` | Message history plus pending-interrupt state, feedback and rateability per assistant message |
| `GET /agent/manifest` | Specialist names and every registry tool with its read-only/destructive flags |
| `POST /agent/conversations/claim` | Reassign anonymous conversations to the signed-in account |
| `POST /agent/feedback` | Thumbs feedback on an assistant message (`routers/feedback.py`) |

`ChatRequest` carries `message`, optional `trip_id`, `conversation_id`, `timezone`, a `retry` flag and `resume` (the HITL decision). `ChatResponse` returns `conversation_id`, `assistant_message_id`, `agent_run_id`, `reply`, `trip_id`, `current_flow`, `suggestions`, `interrupt_pending`/`interrupt_payload` and a `usage` block.

## Setting up a turn (both endpoints)

The two endpoints share the same preamble, in this order:

1. Resolve the `AgentContext` (tier from the users table, reflection toggle, validated client timezone; see [Agent state, runtime context and reply language](state-context-and-language.md)).
2. **Quota check** raises `429` for a free user over the daily turn limit *before any work or bytes* (see [Rate limiting and quotas](../concepts/rate-limiting-and-quotas.md)).
3. `ensure_conversation` resolves or creates the conversation row **before** the graph runs, so a message can never be orphaned and the thread id is stable.
4. A run id and an **assistant message id are minted up front**, so the response, the stored row, the history endpoint and feedback all name the same message. An `agent_runs` row is started (see [Observability, turn metrics and cost](observability-and-metrics.md)).
5. The user message is PII-redacted and appended to the conversation (the stream skips this on `retry`, since the row already exists), and the session is **committed before the graph runs** so a tool's own session scope or the isolated streaming session can write; on SQLite an uncommitted request session would otherwise lock the database.
6. A resume request becomes `Command(resume=...)`; otherwise the turn input carries the message, user id, account email and, only if supplied, the trip id.

The JSON endpoint then awaits `graph.ainvoke`, picks the reply as the last content-bearing, non-tool-calling `AIMessage` after this turn's human message, persists it, schedules background memory extraction only when no interrupt is pending, and returns. If the graph run raises, it returns a localized fallback reply instead of a 500 and persists it so history stays consistent; the run is marked `failed`, which makes the message unrateable.

## The SSE pipeline

The stream endpoint returns `sse_response(persist_assistant_turn(record_agent_run(stream_agent_events(...))), background=memory extraction)`: three nested async generators, each passing every event through unchanged while adding one responsibility, wrapped by `app/core/streaming.py`, which serializes `TypedSSEEvent`s as `event: <name>\ndata: <json>\n\n`, sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`, and runs the background task only after the body drains. The persistence and run-recording wrappers use an **isolated session factory bound to the request session's engine** (not `str(url)`, which masks the password) because the request-scoped session may be torn down mid-stream.

### Event taxonomy (`app/streaming/events.py`)

`start{conversation_id}` → any of `subagent{name}`, `token{content}`, `reset{}`, `tool_call{id,name,args_preview,subagent}`, `tool_result{id,status}`, `panel{tool_call_id,kind,data,language}` → optionally `interrupt{conversation_id,payload}` → `done{conversation_id,assistant_message_id,agent_run_id,current_flow,suggestions,language,trip_id,usage}` or `error{code,message}`. Tool argument previews are truncated to 200 characters. `done` is the durability signal: its ids are filled in only after the reply row is committed.

### The mapper (`app/streaming/mapper.py`)

`stream_agent_events` drives `graph.astream` with `stream_mode=["messages","updates"]` and `subgraphs=True`. Token deltas come from `messages` mode; completed messages, and therefore tool calls and results (the token chunks only carry partial tool-call fragments), come from `updates` mode. Rules the client can rely on:

- **A specialist handoff emits `subagent` and, if tokens were already streamed, `reset`**, so the client and the persistence accumulator discard the superseded draft. A reflection revision within the same specialist is detected as a new message id and also emits `reset`.
- **Only user-facing prose streams**: chunks from synthesis workers and their inner specialists are suppressed; the top-level `synthesize` answer streams and is de-duplicated by message id (not "first chunk only", which would ship a one-character reply). Terminal supervisor and `plan` messages never stream via `messages` mode, so the mapper surfaces them from `updates` as a `token`, which is why an unknown-intent, tier-gated or cancelled-booking turn still shows an explanation instead of a blank bubble.
- **Tool events are emitted once per tool call id.** The same `ToolMessage` is seen twice per turn (subgraph `tools` node and parent specialist node), and a subgraph update replays the whole thread history, so the mapper seeds its seen-sets from the pre-turn checkpoint's message and tool-call ids. `tests/streaming/test_mapper_tool_event_dedup.py` pins that history is never replayed as new events.
- **Panels precede their `tool_result` pill.** A tool declared with `response_format="content_and_artifact"` (weather, air quality, hotel search, flights, places, route) returns a `{kind, data}` artifact via `panel_result`; the mapper localizes it and emits `panel` before `tool_result`.
- **Language is seeded from the checkpoint** before the loop so a resume turn, which skips the supervisor, still tags its panels and `done` with the persisted language, and is updated the moment a node persists a new value.
- After the stream drains the mapper reads the graph snapshot: a pending interrupt becomes an `interrupt` event and suppresses suggestions, the final values are written into the sink the memory-extraction background task reads, metrics are closed and priced inside a guarded block, and `done` is emitted with `current_flow`, suggestions, language, trip id and usage.
- On failure, a `cancelled` client disconnect emits `error{code: cancelled}` and re-raises; any other exception emits a localized fallback `token` if nothing was streamed yet (so the bubble is never empty) followed by `error{code: internal}`.

### Persistence wrapper (`app/streaming/persistence.py`)

`persist_assistant_turn` accumulates `token` content, clears it on `reset`, and on `done` writes the text under the pre-minted message id before yielding `done` with the ids injected. An empty reply or a failed insert yields `done` with a null message id; an interrupted turn saves the draft for history but also reports a null id, because that turn is not rateable. A terminal `error` with accumulated text persists it (history parity with the JSON fallback) unless the code is `cancelled`, in which case nothing is written. `tests/streaming/test_persistence.py` covers each branch. `record_agent_run` closes the `agent_runs` row with a status derived from the events (see the observability page).

## Side panels and localization

Each panel kind is a module under `app/streaming/panels/` that defines its payload model and self-registers a `PanelSpec` at import; registering the same kind twice raises, and `panel_result` raises `UnknownPanelKind` (deliberately neither `ValueError` nor `AppError`, so a mistyped kind cannot be swallowed as a recoverable tool error). Registered kinds today: `weather`, `air_quality`, `flights`, `hotels`, `places`, `route`.

`localize_panel` is registry-driven: English (or any unsupported code) is an identity no-op, while `vi` **deep-copies** the payload and dispatches to the kind's `localize_vi`, so the English payload persisted in the checkpoint is never mutated. Localizers swap bounded vocabularies (weather descriptions, place categories, hotel amenities) through lookup tables that tests check for parity with the seeded English sources; free-text descriptions pass through untouched. The frontend side of this is described in [Chat widget and streaming client](../frontend/chat-and-streaming-client.md).

## Follow-up suggestions

`suggestions_for_flow` (`app/agents/suggestions.py`) returns up to three **locale-agnostic keys** that the web client resolves to localized chips. An ordered rule table runs first using `trip_facts`, the traveller profile and preferences (booking handoff nudges, trip starting within 14 days, family signals, budget-conscious signals, concierge with a known destination), then the static per-flow catalog backfills so a bare call with only `current_flow` reproduces the static behaviour exactly. Unknown or missing flows return an empty list; the profile lookup is best-effort.

## History, claiming and feedback

The messages endpoint is ownership-scoped: an unknown or non-owned conversation returns an empty list without confirming existence. It reads the checkpoint (through an optional graph dependency that degrades to "no interrupt" when the graph is unavailable) to report a pending HITL interrupt, folds effective feedback in one bulk query, and marks each assistant message `rateable` using the single rule in `feedback_service`: assistant role linked to a run whose status is `completed`. Claiming reassigns conversations from an anonymous id to the caller and returns `403` if the source id belongs to a registered account, preventing history theft. Feedback submission is rate-limited per subject and idempotent per fingerprint; see [Rate limiting and quotas](../concepts/rate-limiting-and-quotas.md).
