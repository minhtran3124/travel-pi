---
type: architecture
title: Chat widget and streaming client
description: How the web app hosts the agent — the floating ChatWidget with its compact and docked layouts and signed-out gate, the useAgentStream hook that posts to /agent/stream direct-to-origin with the Supabase token and turns typed Server-Sent Events into a streaming assistant bubble, activity trail, side panels and follow-up chips, the bespoke SSE parser and panel identity contract, human-in-the-loop resume, history hydration and legacy claim, stop/retry/regenerate semantics, smooth reveal, and the rateability rule behind message feedback.
tags: [chat, sse, streaming, react-hook, side-panel, hitl, feedback, frontend, agent-client]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-9362336b0d043069878568d7
    resource: repo://apps/web/src/components/chat/ChatSuggestions.tsx
  - id: openwiki-source-7324d3874d6656bc58be94fe
    resource: repo://apps/web/src/components/chat/ChatWidget.auth.test.tsx
  - id: openwiki-source-76dba05b878363134460cd0f
    resource: repo://apps/web/src/components/chat/ChatWidget.tsx
  - id: openwiki-source-69679c129d6bc85862830eed
    resource: repo://apps/web/src/components/chat/panel/PanelIntlProvider.tsx
  - id: openwiki-source-782846acc3078f30d8dc0691
    resource: repo://apps/web/src/components/chat/smoothReveal.ts
  - id: openwiki-source-5dd01dd1b46506c137c470f8
    resource: repo://apps/web/src/components/chat/useAgentStream.hydrate.test.tsx
  - id: openwiki-source-8aa6f6be2f4009f6ff41429f
    resource: repo://apps/web/src/components/chat/useAgentStream.stop.test.tsx
  - id: openwiki-source-c16f0bb7c468ca671f689c68
    resource: repo://apps/web/src/components/chat/useAgentStream.stream.test.tsx
  - id: openwiki-source-4c2e44b887aa4d19dc25efd6
    resource: repo://apps/web/src/components/chat/useAgentStream.ts
  - id: openwiki-source-b8300b17a1ef54fe3b13ca1b
    resource: repo://apps/web/src/lib/query/feedback.ts
  - id: openwiki-source-5c4f23451111eb43cab4a605
    resource: repo://apps/web/src/lib/stream/panel.test.ts
  - id: openwiki-source-16a43e79584a3467c9fd9286
    resource: repo://apps/web/src/lib/stream/panel.ts
  - id: openwiki-source-5635d8ee51afe5d5f9b55913
    resource: repo://apps/web/src/lib/stream/parseSSE.test.ts
  - id: openwiki-source-1dc205161e0af60f55f3e911
    resource: repo://apps/web/src/lib/stream/parseSSE.ts
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Chat widget and streaming client

The agent surface in the browser is `ChatWidget` (`apps/web/src/components/chat/ChatWidget.tsx`), mounted once in the root layout so it floats over every page, and `useAgentStream` (`useAgentStream.ts`), the hook that owns one conversation's state. The wire contract it consumes is defined by the backend's typed SSE taxonomy in [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md); `src/lib/stream/parseSSE.ts` and `src/lib/stream/panel.ts` mirror it and must be kept in lockstep.

## The widget

`ChatWidget` composes a launcher button and the `ChatPanel`, derives the active trip id from a `/trips/{id}` route and passes it to the hook, and after each completed turn invalidates the trip, items, budget and expenses queries for that trip because the agent may have changed them server-side. One boolean, `useIsCompact()` (viewport narrower than the Tailwind `sm` breakpoint), is the only responsive switch in the chat module: compact mode renders the open widget as a full-viewport sheet without the side drawer (panels are reached through inline result cards) and restores focus to the launcher on close; docked mode renders the floating panel beside a `SidePanel` drawer.

Anonymous chat was removed. Only a **confirmed** signed-out identity swaps in a sign-in prompt linking to `/auth/login` (the `loading` state still renders the panel so first paint never flashes the prompt), and in that state no `/agent/*` request is ever made (`ChatWidget.auth.test.tsx`). The drawer is wrapped in `PanelIntlProvider`, a nested `NextIntlClientProvider` fed only the `Panel` message slice for the **backend-detected** conversation language, so panel labels can differ from the cookie locale that drives the rest of the app (see [Internationalization and theming](i18n-and-theming.md)).

## The SSE parser and panel identity

`parseSSE` is a network-free async generator over a byte stream or an async iterable of strings. It buffers on the `\n\n` segment delimiter, decodes with a streaming `TextDecoder` so a multibyte character split across chunks is reassembled, maps each named event's compact JSON to a camel-cased `SSEEvent` union (`start`, `token`, `reset`, `subagent`, `tool_call`, `tool_result`, `panel`, `interrupt`, `done`, `error`), coerces missing `done` fields to null or `[]` for backward compatibility, and **skips unknown event types and malformed JSON rather than crashing**. There is no bare `data:` frame and no `[DONE]` sentinel; the backend closes the connection after `done` or `error` and the generator ends. `parseSSE.test.ts` covers all of this, including split chunks and a final undelimited segment.

`panel.ts` declares the typed payloads for the six panel kinds (`route`, `places`, `weather`, `air_quality`, `flights`, `hotels`) and, more importantly, **panel identity**: `panelKey(panel)` is `kind:category_key` for a places panel and the bare `kind` otherwise. The canonical, never-localized `category_key` is preferred over the display `category` so a mid-conversation language switch cannot split one category into two tabs. Both the drawer and each message upsert panels by that key, so a re-emitted panel (reflection re-runs a tool under a fresh call id) replaces its card instead of duplicating it, while distinct places categories stay as separate cards.

## The streaming hook

`useAgentStream` posts `ChatRequest` bodies (`message`, `trip_id`, `conversation_id`, `retry`, `timezone` from the browser's `Intl` settings, or `resume`) to `${streamBaseUrl()}/agent/stream`, **directly at the backend origin** with the Supabase bearer header, bypassing the buffering Next.js proxy. Its rules:

- **One turn at a time.** A synchronous `inFlightRef` blocks a second `send`/`resume` in the same tick (React state updates too late), and sends are refused while an interrupt is pending or the identity is not ready.
- **Conversation continuity.** The client mints a conversation id on the first turn and persists it in `localStorage` under `travel.conversationId`; the backend accepts a client-supplied id and keys the thread on it, and `start`/`interrupt` events re-pin whatever id the server echoes.
- **Rendering.** Each `send` appends a user bubble and an empty assistant bubble. `token` text is not appended directly but queued into a **smooth reveal** controller (`smoothReveal.ts`) that drains at about 40 characters per second via `requestAnimationFrame`, speeding up so it never lags more than about six seconds behind the wire and continuing after the stream ends. `reset` blanks the bubble and drops buffered text (a superseded draft) but keeps the turn's activity and panels, since the work still happened.
- **Activity trail.** `subagent` sets the active specialist; `tool_call` appends a running step attributed to it; `tool_result` flips the step to `ok` or `error`. The UI resolves raw tool names to localized labels.
- **Panels** are upserted by key both into the flat drawer list and into the streaming message's own `panels`, and their `language` (also carried by `done`) becomes `panelLanguage`, defaulting to `en` and changing only when an event supplies one.
- **Terminal handling.** `done` records the follow-up suggestion keys and the persisted `assistantMessageId`; a `429` becomes a quota error, an in-band `error` event or a stream that produced no tokens becomes a visible error (there is deliberately no `/agent/chat` fallback that would mask streaming failures), and partial tokens already rendered are kept. Every turn stamps `elapsedMs` when it ends.
- **Human-in-the-loop.** An `interrupt` event stores `{ conversationId, payload }` and the UI shows an approve/reject prompt; `resume(approved)` posts `{ resume: { approved } }` and streams the continuation into the **same** assistant bubble. Approval has no reply line on the server (it would be wiped by the booking hand-off `reset`), so the hook records a synthetic `plan_approved` activity step instead. `onTurnComplete` is deferred until the interrupt is resolved.
- **Stop, retry, regenerate, new conversation.** `stop()` aborts the request and marks it deliberate, so the finally-block still settles the turn: content gets a "stopped" note or placeholder and the persisted id is dropped, making a stopped turn unrateable even if `done` had already arrived; the unmount abort leaves state untouched. `canRetry` is true when the last message is an unanswered user turn (a reload mid-stream); `retry()` re-sends it with `retry: true` so the backend does not save a duplicate question, and `regenerate()` drops the last answer and re-runs the question the same way. `newConversation()` clears the reveal buffer, storage and messages.

## Hydration and the legacy claim

Once the identity is `signed-in`, a one-shot effect (guarded against Strict Mode double invocation) first claims any pre-auth anonymous history: if `localStorage` still holds the legacy `travel.userId`, it posts the claim, drops the key on success or on a `403` (the id belongs to a registered account), and keeps the key with a soft error on any other failure so the next open retries. It then hydrates the stored conversation from `GET /agent/conversations/{id}/messages`. Only rows the server marks `rateable` receive a `serverMessageId` and their effective feedback; a pending interrupt is rehydrated so `resume` has a target bubble, adding an empty assistant bubble if the interrupt fired before any tokens and never marking the interrupted turn rateable. Both steps fail silently so a new chat is never blocked (`useAgentStream.hydrate.test.tsx`).

## Suggestions and feedback

`ChatSuggestions` renders the locale-agnostic keys from `done` as chips whose label and prompt come from the `Chat.followups.*` message catalog; clicking a chip sends its prompt, and suggestions are cleared at the start of the next send. Message feedback is filed against `serverMessageId`, whose presence is the single "complete and rateable" signal: it is assigned only from history or a successful `done`, never on streaming, interrupted, stopped or failed turns. `useSubmitFeedback` mints one `client_event_id` per logical action (the body field is the idempotency key, not a header), shares an in-flight promise per message so a double-click is one action, and replays the same id on retry so the server answers with the existing event.
