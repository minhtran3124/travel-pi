---
slug: user-feedback-v1
status: active
owner: minhtran
created: 2026-07-21
---

# Feedback Event Foundation

## 1. Motivation

Create the auditable evidence layer required before travel-pi learns from user feedback. A user must
be able to rate a completed assistant answer, change or retract that rating, and optionally explain
why. The event must be tied to the exact persisted assistant message and owned conversation.

This implementation is **high-risk**: it adds a migration and changes public REST, history, and SSE
contracts. The research and design are complete, but implementation requires an explicit go-ahead.

Revised 2026-09-12: the run-provenance table this plan used to create (`agent_runs`) has existed on
`main` since PR #131/#132. The plan now links `messages` to the existing `agent_runs` (one nullable
column) and creates only `feedback_events`; see `DESIGN.md` §3.1 and §11. The feedback abuse limit
(`429`) is now an explicit deliverable of Task 3.2, using the primitive from PR #110 and the two
`feedback_rate_limit_*` settings already in `app/core/config.py`.

## 2. Non-goals

- No automatic memory write, prompt edit, fine-tuning, or supervisor-routed learning agent.
- No implicit click/book/save signal ingestion in v1.
- No admin annotation UI, automated judge, or durable analytics worker in this PR.
- No dependency on Langfuse availability for accepting product feedback.
- **Deferred from this round (2026-09-12):** the Langfuse score export and the `agent_runs.trace_id`
  column (former Task 4.1, DESIGN §9). This round is UI + API + SQL evidence only; the export is a
  projection that can be added later without touching the feedback contract.
- No change to what `agent_runs` / `agent_run_steps` record for a turn nobody rates; the metrics
  dashboard keeps reading them unchanged.
- No per-IP or per-device limiting for anonymous callers beyond the `anon:` namespace (deferred with
  the rate-limit primitive's own backlog).

## Global Constraints

- **Layering:** `router → service → repository`; ORM only in repositories; the feedback service owns
  authorization, transition and idempotency policy.
- **Existing run record is reused, not replaced:** `AgentRunRepository.start` / `finish` keep their
  call sites and semantics; a task may add a keyword parameter with a default, never change an
  existing one. `tests/api/agent/test_agent_runs.py` and `test_agent_run_steps_wiring.py` must stay
  green **without edits** through every wave.
- **Schema delta is exactly:** `messages.agent_run_id` (nullable, indexed) and the `feedback_events`
  table — one Alembic migration off head `b8e4c1f7a305`, written
  with `batch_alter_table`, with a real downgrade. Plain string ids, no FK constraints (repo
  convention).
- **Rateable rule (single definition, in the service):** message `role = assistant`, non-null
  `agent_run_id`, linked run `status = completed`. Every other case is the same non-enumerating `404`.
- **Append-only:** `feedback_events` rows are never updated or deleted by product code; effective
  state is a fold ordered by `(created_at, id)`.
- **No feedback → memory edge:** nothing under `app/services/feedback*` or `app/routers/feedback.py`
  may import from `app/agents/memory*` or the store; an import-graph test pins it.
- **No bodies in logs:** comments and free text never reach `logger.*`, metrics labels, or Langfuse
  by default.
- **Both databases:** every new test that touches the schema runs on the SQLite suite and is
  expected to pass on the Postgres Docker suite (`make test-docker`) before the branch finishes.
- **Rate limit before any session work:** the `rate_limit(...)` dependency is listed before
  `SessionDep` on the feedback route; `enforce_rate_limit` raises if the session already has a
  transaction open.
- **Verify commands** are single, pipe-free, under 60 s, run from the repo root with a leading
  `cd apps/api &&` / `cd apps/web &&`. Backend rows that change shared behaviour run their enclosing
  test directory, not only the task's new file (lesson from `close-product-loop-s1`).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The migration adds `messages.agent_run_id` and `feedback_events`, and its downgrade removes exactly those | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_feedback_events_migration.py -q` | exit 0 |
| SC-2 | ORM column sets for `messages` and `feedback_events` match the migration | `cd apps/api && ../../.venv/bin/python -m pytest tests/test_db_models.py -q` | exit 0 |
| SC-3 | Set, replace, detail, retract fold to the documented effective state; a replayed `(user_id, client_event_id)` appends nothing | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_feedback_repository.py -q` | exit 0 |
| SC-4 | A conversation claim moves `conversations`, `agent_runs` and `feedback_events` rows for the anonymous id in one transaction | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_conversation_reassign.py -q` | exit 0 |
| SC-5 | `/agent/chat`, SSE `done` and reloaded history carry the same `assistant_message_id`; on the stream path `done` is not yielded until the message row is committed; the row's `agent_run_id` equals the run the router started | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py tests/api/agent/test_stream_events.py tests/streaming/test_persistence.py -q` | exit 0 |
| SC-6 | `POST /agent/feedback` returns `201`/`200`/`404`/`409`/`422` per DESIGN §5.2; a foreign, user-role, unknown, or `failed`-run target all return an identical `404` body | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_feedback.py -q` | exit 0 |
| SC-7 | The `feedback_rate_limit_max + 1`-th request in one window from the same subject returns `429` with `Retry-After`; an `anon:` subject and an authenticated subject count separately; a `404`-rejected request still increments the counter | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_feedback_rate_limit.py -q` | exit 0 |
| SC-8 | Existing run-metrics behaviour is unchanged: the agent_runs and step-wiring tests pass with no edits to those files | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_runs.py tests/api/agent/test_agent_run_steps_wiring.py -q` | exit 0 |
| SC-9 | No import path leads from the feedback service or router to the memory runner or store | `cd apps/api && ../../.venv/bin/python -m pytest tests/architecture/test_feedback_no_memory_edge.py -q` | exit 0 |
| SC-10 | The SSE parser accepts `assistant_message_id` / `agent_run_id` on `done` and ignores unknown additive fields; the regenerated OpenAPI types compile | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/stream/parseSSE.test.ts` | exit 0 |
| SC-11 | Feedback controls render only for complete assistant messages with a server id; helpful / not-helpful / detail / retract / retry flows update `aria-pressed` and the live region as DESIGN §8.5 lists | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/MessageFeedback.test.tsx src/components/chat/MessageList.render.test.tsx` | exit 0 |
| SC-12 | Every new UI string exists in both locales | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/messages.parity.test.ts` | exit 0 |
| SC-13 | Frontend type-checks against the regenerated schema | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit` | exit 0 |
| SC-14 | Backend lint is clean | `cd apps/api && ../../.venv/bin/ruff check app` | exit 0 |
| SC-15 | The end-to-end spec is collectable (it runs only with e2e credentials; see §5 Risks) | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec playwright test --list playwright/chat-feedback.spec.ts` | exit 0 |

## 4. Tasks

### Task 1.1 — Schema: link column, feedback_events, migration (wave 1)

- **Files:** apps/api/app/db/models/message.py, apps/api/app/db/models/feedback_event.py, apps/api/app/db/models/__init__.py, apps/api/app/enums.py, apps/api/alembic/versions/<revision>_add_feedback_events.py, apps/api/tests/db/test_feedback_events_migration.py, apps/api/tests/test_db_models.py
- **Action:** Add `Message.agent_run_id` (nullable string, index `ix_messages_agent_run_id`). Add the `FeedbackEvent` model exactly as DESIGN
  §3.2 (columns, unique `(user_id, client_event_id)`, the three indexes, `rating IN (-1, 1)` check)
  and typed enums for `action`, `rating`, `reason_code`, `source`. Write one Alembic migration off
  head `b8e4c1f7a305` in `batch_alter_table` form (mirror
  `b8e4c1f7a305_add_bookings_trip_id.py`), with a downgrade that drops `feedback_events` first, then
  the column. Do not touch `agent_runs` or `agent_run_steps` otherwise. Update the exact
  column-set assertions in `tests/test_db_models.py` (a `messages` check and a new one for
  `feedback_events`), and write the upgrade→assert→downgrade→assert round trip modelled on
  `tests/db/test_bookings_trip_id_migration.py`.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes: Alembic head b8e4c1f7a305 and the existing AgentRun and Message models (on main). Produces: `feedback_event.py`, `<revision>_add_feedback_events.py`, `messages.agent_run_id`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_feedback_events_migration.py tests/test_db_models.py tests/db -q -p no:randomly`
- **Done:** Both tests pass; `alembic heads` prints exactly one head; `alembic downgrade -1` then
  `upgrade head` on a fresh SQLite file leaves `feedback_events` and the column present.

### Task 2.1 — Repositories: feedback log, message link on append, three-table claim (wave 2)

- **Files:** apps/api/app/repositories/feedback.py, apps/api/app/repositories/conversation.py, apps/api/app/schemas/feedback.py, apps/api/tests/db/test_feedback_repository.py, apps/api/tests/db/test_conversation_reassign.py
- **Action:** `FeedbackRepository`: `find_by_client_event(user_id, client_event_id)`,
  `append(event)` with savepoint recovery on the unique-key race (load the winner, return it), and
  `effective_for(message_ids)` — one query, folded per DESIGN §3.3 ordering `(created_at, id)`, no
  N+1. `ConversationRepository.append_message` gains optional `message_id` and `agent_run_id`
  keyword parameters (defaults `None`, so every existing caller is unchanged); add
  `get_message_for_feedback(message_id)` returning message + conversation owner + linked run
  status in one query. Extend `reassign_user(from_user_id, to_user_id)` to update
  `agent_runs.user_id` and `feedback_events.user_id` in the same transaction as conversations and
  return the conversation count as before (the claim route needs no change). Pydantic schemas for
  the request/response/effective-state shapes of DESIGN §5.1 and §3.3.
- **Criteria:** SC-3, SC-4
- **Interfaces:** Consumes: `feedback_event.py`, `messages.agent_run_id`. Produces: `repositories/feedback.py`, `schemas/feedback.py`, `append_message`, `reassign_user`, `get_message_for_feedback`, `effective_for`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/db -q -p no:randomly`
- **Done:** Fold cases (set, replace, detail, retract, stale retract, replay) match DESIGN §3.3;
  reassign moves rows in all three tables and a conversation with no feedback still moves its runs;
  the existing conversation-repository tests pass unchanged.

### Task 3.1 — Answer identity on REST, SSE and history (wave 3)

- **Files:** apps/api/app/routers/agent.py, apps/api/app/streaming/persistence.py, apps/api/app/streaming/events.py, apps/api/app/schemas/agent.py, apps/api/tests/api/agent/test_agent_chat.py, apps/api/tests/api/agent/test_stream_events.py, apps/api/tests/streaming/test_persistence.py
- **Action:** Mint `assistant_message_id = str(uuid4())` next to the existing `run_id` in both
  routes. Chat path: pass `message_id` and `agent_run_id=run_id` into the existing `append_message`
  call; add `assistant_message_id` and `agent_run_id` to `ChatResponse` (`null` message id on an
  interrupt). Stream path: `persist_assistant_turn` gains `run_id` and `message_id`; on `done` it
  inserts the message **before** yielding, injects both ids into the `done` payload, and on an
  empty text or insert failure emits the terminal error and never yields `done`
  (DESIGN §4.3). `record_agent_run` is not edited. History items gain an additive `feedback` field
  populated by `FeedbackRepository.effective_for` in one bulk call (`null` for user messages).
- **Criteria:** SC-5, SC-8
- **Interfaces:** Consumes: `append_message`, `effective_for`. Produces: `ChatResponse.assistant_message_id`, `done.assistant_message_id`, `history.feedback` (all in `schemas/agent.py`).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent tests/streaming -q -p no:randomly`
- **Done:** REST, SSE and history return one id per answer; a stream test proves the message row
  exists when `done` arrives; `test_agent_runs.py` and `test_agent_run_steps_wiring.py` pass with no
  diff.

### Task 3.2 — Feedback service, `POST /agent/feedback`, abuse limit (wave 3)

- **Files:** apps/api/app/services/feedback_service.py, apps/api/app/routers/feedback.py, apps/api/app/main.py, apps/api/tests/api/agent/test_feedback.py, apps/api/tests/api/agent/test_feedback_rate_limit.py, apps/api/tests/architecture/test_feedback_no_memory_edge.py
- **Action:** `FeedbackService` implements DESIGN §5.3: resolve the effective actor (JWT, else
  `anonymous_user_id` with the agent endpoints' precedence), normalise and fingerprint, replay or
  `409` on the `(actor, client_event_id)` key, load the target via `get_message_for_feedback`,
  apply the rateable rule from Global Constraints (every failure is the same `404` body), validate
  the transition, append, commit, then schedule the best-effort export hook (a no-op in this round; export is deferred, see §2).
  Route `POST /agent/feedback` in a new router registered in `main.py`, with the dependency order
  `rate_limit(name="feedback", limit=settings.feedback_rate_limit_max,
  window_seconds=settings.feedback_rate_limit_window_seconds, subject=feedback_subject)` **first**,
  then session and auth. `feedback_subject` returns `auth_user.id` when authenticated, else
  `f"anon:{body.anonymous_user_id}"` when present, else `None` (limit skipped, route then answers
  `401`). Tests: contract statuses, identical `404` bodies for foreign / user-role / unknown /
  `failed`-run targets, same-key replay vs conflict, concurrent race, the `429` cases of SC-7, and an
  import-graph test that walks `app.services.feedback_service` and `app.routers.feedback` and fails
  on any module under `app.agents.memory` or the store.
- **Criteria:** SC-6, SC-7, SC-9
- **Interfaces:** Consumes: `repositories/feedback.py`, `get_message_for_feedback`, `schemas/feedback.py`, plus the rate-limit primitive and the two feedback_rate_limit settings already on main. Produces: `services/feedback_service.py`, `routers/feedback.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_feedback.py tests/api/agent/test_feedback_rate_limit.py tests/architecture/test_feedback_no_memory_edge.py -q`
- **Done:** All three files pass; `curl` of the route without a body returns the shared `422`
  envelope; the OpenAPI document lists `POST /agent/feedback` with `429` in its responses.

### Task 4.1 — Regenerate and mirror the contracts on the web (wave 4)

- **Files:** apps/web/src/lib/api/schema.d.ts, apps/web/src/lib/query/feedback.ts, apps/web/src/lib/api/keys.ts, apps/web/src/lib/stream/parseSSE.ts, apps/web/src/lib/stream/parseSSE.test.ts
- **Action:** Regenerate `schema.d.ts` with `pnpm gen:api` against the running API (never hand-edit).
  Add a `useSubmitFeedback` mutation over `POST /agent/feedback` that keeps one `clientEventId` per
  logical action across retries and a per-message in-flight guard (DESIGN §7.2). Mirror
  `assistant_message_id` / `agent_run_id` on the bespoke SSE `done` type and prove unknown additive
  fields are ignored.
- **Criteria:** SC-10, SC-13
- **Interfaces:** Consumes: `routers/feedback.py`, `done.assistant_message_id` (through the regenerated OpenAPI document). Produces: `lib/query/feedback.ts`, `useSubmitFeedback`, `parseSSE.ts`.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/stream/parseSSE.test.ts src/lib/query`
- **Done:** Parser tests pass; `tsc --noEmit` is clean against the regenerated schema.

### Task 5.1 — Accessible bilingual feedback controls (wave 5)

- **Files:** apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/MessageList.tsx, apps/web/src/components/chat/MessageFeedback.tsx, apps/web/src/components/chat/FeedbackDialog.tsx, apps/web/src/components/chat/MessageList.render.test.tsx, apps/web/src/components/chat/MessageFeedback.test.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Assign `serverMessageId` only from history or a successful `done` / REST response; show
  `MessageFeedback` only for assistant + complete + server id. Two native buttons with
  `aria-pressed`, a polite live region, the reason/comment modal for the negative path reusing
  `Modal` and `Textarea`, optimistic update with rollback and retry on the same `clientEventId`, and
  reloaded effective state from the history `feedback` field. Every string in both locales.
- **Criteria:** SC-11, SC-12
- **Interfaces:** Consumes: `useSubmitFeedback`, `parseSSE.ts`, `history.feedback`. Produces: `MessageFeedback.tsx`, `FeedbackDialog.tsx`.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/MessageList.render.test.tsx src/components/chat/MessageFeedback.test.tsx src/messages.parity.test.ts`
- **Done:** Mouse, keyboard, screen-reader, English/Vietnamese, error, retry, replace, retract,
  streaming and history cases pass; no controls on user, streaming, interrupted or failed messages.

### Task 6.1 — End-to-end and record (wave 6)

- **Files:** apps/web/playwright/chat-feedback.spec.ts, specs/user-feedback-v1/SUMMARY.md
- **Action:** Playwright spec following `playwright/booking-smoke.spec.ts` conventions (auth setup
  project, storage state, skips without `E2E_USER_*`): send a message, capture the SSE message id,
  reload and compare, rate helpful, reload, change to not helpful with a reason, retract, replay a
  request and assert the event count does not grow (via `GET` history `feedback`), then attempt
  another user's id. Record only commands actually run in `SUMMARY.md` `### Verify`, one row per SC,
  and fill `### Not auto-verified` (Postgres run, browser UAT).
- **Criteria:** SC-14, SC-15
- **Interfaces:** Consumes: `MessageFeedback.tsx`, `routers/feedback.py`. Produces: `chat-feedback.spec.ts`, `SUMMARY.md`.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec playwright test --list playwright/chat-feedback.spec.ts`
- **Done:** The spec is listed; `ruff check app` is clean; every SC row in `SUMMARY.md` cites a
  command that was run with its exit code.

## 5. Risks

- **Identity split:** authenticated JWT and anonymous body identity must resolve exactly as the
  current agent endpoints do; object ownership is checked via message → conversation → owner.
- **Write-order window:** on the stream path the message row is committed at `done` but the run
  row turns `completed` a moment later (DESIGN §4.3). A feedback request in that window gets `404`
  and the client retries with the same key. Accepted for v1; a test pins the retry succeeding.
- **Migration on a long-lived database:** both suites build from migrations on a fresh file, so a
  dev Postgres that is behind will fail every feedback write with a column error exactly as
  `close-product-loop-s1` saw for `bookings.trip_id`. `alembic upgrade head` must run on deploy.
- **Rate-limit dependency order:** the primitive raises `RuntimeError` if the request session has
  already begun a transaction; the route must list the limiter before any session-using dependency.
- **Privacy:** free text can contain PII; cap length, keep it out of logs, define deletion/retention,
  and do not copy raw comments into semantic memory.
- **E2E in CI runs as a free user** with no tier row (see `close-product-loop-s1` SUMMARY); feedback
  has no tier gate, so the spec is meaningful there, but it still needs the e2e secrets.

## 6. Status Log

- 2026-07-21 — Deep BE/FE research and bilingual design completed; implementation not started.
- 2026-09-12 — Plan re-based on the `agent_runs` / `agent_run_steps` tables that shipped in PR
  #131/#132: schema delta reduced to two nullable columns plus `feedback_events`; waves reordered so
  schema (1) → repositories (2) → identity + API/rate limit (3) → web (4–5) → e2e (6); Langfuse export + `trace_id` deferred;
  the `429` abuse limit is now Task 3.2's deliverable over the PR #110 primitive; Success Criteria
  table and Global Constraints added per `rules/plan-format.md`. Still `proposed`.
