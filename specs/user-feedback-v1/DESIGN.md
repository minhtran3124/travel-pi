---
slug: user-feedback-v1
doc: design
lang: en
status: proposed
created: 2026-07-21
source_of_truth: true
---

> **Language note:** This English document is the source of truth. See
> [DESIGN.vi.md](./DESIGN.vi.md) for the Vietnamese translation.

# Design — Feedback Event Foundation

> **Revision 2026-09-12 — reuse the existing run record.** When this design was written
> (2026-07-21) there was no run table. Since then PR #131 (`specs/agent-turn-metrics`, migration
> `e3b7c5d9a1f4`) added `agent_runs` and PR #132 (`specs/agent-run-trace-detail`, migration
> `b2d9f4a7c1e8`) added `agent_run_steps` plus `agent_runs.prompt_versions`. Both routers already
> mint a run id before the graph runs and finalize the row afterwards. This revision therefore
> **extends** that table instead of creating one: §2, §3.1, §3.4, §4.3, §5.2, §9, §11 and §12
> changed; the feedback contract (§3.2–§8, §10) did not. The dedicated feedback rate limit now names
> the primitive shipped in PR #110 (`app/core/rate_limit.py`) and the two `feedback_rate_limit_*`
> settings that already exist in `app/core/config.py`.

## 1. Scope and invariants

This design adds answer-level feedback from backend to frontend. The contract is deliberately narrow:
thumbs up/down, optional reason/comment, change, retract, reload, and evaluation export.

Hard invariants:

1. A feedback target is a completed, persisted assistant message—not a conversation, client bubble,
   trace, tool call, or draft token stream.
2. `assistant_message_id` is minted by the server and is identical in SQL history, `/agent/chat`, SSE
   `done`, and hydrated FE state.
3. `done` is not emitted until the assistant message commit succeeds.
4. Only the message's conversation owner may submit or read its effective feedback.
5. Feedback events are append-only, except legally/operationally required privacy erasure.
6. A repeated transport request does not create a repeated logical event.
7. Feedback acceptance does not depend on Langfuse and never invokes memory extraction.
8. Client-supplied provenance is untrusted; the server captures it at answer time.

## 2. Component design

```text
┌──────────────────────────── ANSWER PATH ────────────────────────────┐
│ Agent router (exists today)                                         │
│   mint agent_run_id, AgentRunRepository.start(status=running)       │
│   mint assistant_message_id (new)                                   │
│      │                                                              │
│      ▼                                                              │
│ LangGraph → typed SSE mapper → record_agent_run (exists)            │
│                              → persist_assistant_turn (changed)     │
│                              intercept done                         │
│                              persist Message(explicit id,           │
│                                              agent_run_id)          │
│                              emit done + assistant_message_id        │
│                              AgentRunRepository.finish (exists)      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────── FEEDBACK PATH ───────────────────────────┐
│ MessageFeedback → POST /agent/feedback                              │
│   auth principal → FeedbackService                                  │
│   load Message + Conversation + AgentRun                            │
│   authorize owner + assistant role                                  │
│   validate transition + fingerprint                                 │
│   append FeedbackEvent                                              │
│   return effective state                                            │
│      └─ best-effort async Langfuse score export                     │
└─────────────────────────────────────────────────────────────────────┘
```

Layering follows `router → service → repository`. ORM stays in repositories. The feedback service
owns transition, authorization, and idempotency policy; the repository owns atomic persistence.

## 3. Data model

### 3.1 `agent_runs` (existing) and the message link (new)

An answer-time record is recommended instead of copying “current” configuration when feedback arrives.
That record **already exists**: `app/db/models/agent_run.py` (one row per turn or HITL resume) and
`app/db/models/agent_run_step.py` (one row per LLM call, tool call or node, in `seq` order). The
provenance this design needs maps onto them as follows; nothing here is created by this spec.

| Provenance need (v1 of this design) | Where it lives today | Notes |
|---|---|---|
| `agent_run_id` minted before the graph runs | `agent_runs.id` — `routers/agent.py` mints `uuid4()` and calls `AgentRunRepository.start` before invoking the graph, on both `/agent/chat` and `/agent/stream` | Already satisfies invariant 8 |
| `user_id`, `conversation_id`, `trip_id` | same-named columns | `user_id` is the effective owner at run time |
| `channel` | `agent_runs.channel` = `chat` \| `stream` | |
| run kind | `agent_runs.kind` = `turn` \| `resume` | a HITL resume is its own row |
| `status` | `agent_runs.status` = `running` \| `completed` \| `interrupted` \| `failed` | see the status note below |
| `current_flow` | `agent_runs.current_flow` | set at finish |
| `prompt_versions` | `agent_runs.prompt_versions` (JSON) | the compiled graph's build-time snapshot, not `active.yaml` at feedback time |
| model per call (`model_config`) | `agent_run_steps.model` per LLM step, `agent_runs.by_model` totals | replaces the proposed `model_config` column |
| execution summary | `agent_run_steps` (`kind`, `node`, `tool_name`, `status`, `error_type`) | replaces the proposed `execution_summary` column; no args or results are stored by construction |
| `started_at`, `finished_at` | same-named columns | |

Additive changes this spec makes (one migration, §11):

| Column | Type | Rules / purpose |
|---|---|---|
| `messages.agent_run_id` | string nullable, indexed | Set when the assistant reply is inserted; the feedback service joins message → run through it. Plain string, no FK, matching the repo convention (`trip_items.booking_id`, `bookings.trip_id`) |
| `agent_runs.trace_id` | string nullable | **Deferred (2026-09-12)** with the §9 export; not in the first implementation round. When added: provider trace correlation, filled best-effort at finish when the tracing handler exposes one; `NULL` means "do not export" |

Dropped from the original proposal, with the reason:

- `agent_runs.assistant_message_id` — the link lives on the message instead. The message is the
  feedback target, so the join starts there; a one-way link on the child row is the repo precedent,
  and it avoids a unique constraint that a retried turn (`kind=resume`, same conversation) would
  fight.
- `abandoned` status — the existing recorder (`app/streaming/agent_run.py`) marks a client
  disconnect `failed` (a `CancelledError` in the inner iterator). A fifth status buys nothing v1
  reads; "not `completed`" is the only test the feedback path makes.
- `app_release` — not needed by any v1 consumer.
- `Message.provenance` JSON fallback — moot; the table exists.

**Rateable** = the message has `role = assistant`, a non-null `agent_run_id`, and the linked run has
`status = completed`. Fallback replies produced after a graph failure are still persisted (§4.2); the
run they link to is `failed`, so they are **not** rateable under this rule. This tightens §4.2's
earlier wording deliberately: an answer the graph did not produce has no configuration to attribute
a rating to.

Status note: `AgentRunRepository.finish` writes the terminal status on the stream path from
`record_agent_run` (after the SSE iterator drains) and on the chat path from the router's
`_finalize`. Feedback reads the status; it never writes it.

### 3.2 `feedback_events`

| Column | Type | Rules / purpose |
|---|---|---|
| `id` | string UUID PK | Also used as provider score id |
| `schema_version` | integer | Starts at `1` |
| `user_id` | string, indexed | Effective actor; derived server-side |
| `conversation_id` | string, indexed | Derived from target message |
| `assistant_message_id` | string, indexed | Required target; assistant role only |
| `agent_run_id` | string nullable, indexed | Derived from completed run |
| `action` | string | `set_rating`, `add_detail`, or `retract_rating` |
| `rating` | integer nullable | `1` helpful, `-1` not helpful |
| `reason_code` | string nullable | Allowlisted taxonomy |
| `comment` | string nullable | Trimmed, max 500 characters |
| `source` | string | `chat_message_actions` in v1 |
| `locale` | string nullable | Allowlisted short locale, advisory only |
| `client_event_id` | string UUID | Stable per logical UI action |
| `request_fingerprint` | string | Hash of canonical accepted input |
| `supersedes_event_id` | string nullable | Prior effective rating/detail event |
| `created_at` | ISO string | Immutable event time |

Constraints and indexes:

- unique `(user_id, client_event_id)`;
- index `(assistant_message_id, created_at, id)` for folding;
- index `(user_id, created_at)` for export/erasure;
- index `(rating, created_at)` for aggregate sampling;
- `rating IN (-1, 1)` when non-null;
- `set_rating` requires rating and forbids comment;
- `add_detail` requires an active matching negative rating and at least reason or comment;
- `retract_rating` has no rating/reason/comment;
- `supersedes_event_id` must target the same user and message, enforced in service/repository
  transaction because SQLite/Postgres CHECK constraints cannot safely express this join.

No raw full request, answer copy, tool args, or trace content is duplicated into this table.

### 3.3 Effective feedback read model

The immutable log is authoritative; clients receive a folded view:

```json
{
  "rating": "helpful",
  "reason_code": null,
  "comment_present": false,
  "rating_event_id": "...",
  "updated_at": "2026-07-21T...Z"
}
```

Folding rules:

1. Sort by `(created_at, id)`.
2. `set_rating` replaces the active rating and clears old negative detail.
3. `add_detail` enriches only the current negative rating.
4. `retract_rating` clears rating and detail.
5. Replayed idempotent requests do not change the log.

At v1 scale, fold in a repository query. If read volume later warrants it, introduce a transactionally
updated projection table without changing event semantics.

### 3.4 Delete and claim behavior

- Conversation/user erasure deletes or redacts feedback free text and provider projections according
  to the retention policy. The privacy operation is intentionally allowed to break append-only
  history; append-only is an audit design, not a reason to violate erasure obligations.
- Anonymous conversation claim must update `agent_runs.user_id` and `feedback_events.user_id` in the
  same transaction as conversation reassignment. Otherwise the new owner can see history but not its
  feedback. The claim path exists today — `POST /agent/conversations/claim` →
  `ConversationRepository.reassign_user` — and reassigns **conversations only**; `agent_runs.user_id`
  is already left behind on every claim. Task 2.1 extends that repository call to the three tables in
  one transaction.

## 4. Answer identity contract

### 4.1 Repository change

`append_message` accepts optional explicit `message_id`. The server mints this ID before invoking the
graph but inserts no row until the answer is final.

```python
append_message(
    message_id=assistant_message_id,
    conversation_id=conversation_id,
    role="assistant",
    content=final_text,
)
```

The repository must treat an existing same-ID/same-conversation/same-content row as an idempotent
replay only in explicitly supported recovery paths; conflicting reuse is an integrity error.

### 4.2 REST `/agent/chat`

Successful response adds:

```json
{
  "conversation_id": "...",
  "assistant_message_id": "...",
  "agent_run_id": "...",
  "reply": "...",
  "trip_id": null,
  "current_flow": "planner",
  "suggestions": []
}
```

Fallback assistant content is still persisted as an assistant message carrying the run's
`agent_run_id`, but that run finishes `failed`, so the message is **not** rateable (§3.1 rule); the
response still returns its `assistant_message_id` so history and the client agree on identity.
Interrupt responses have `assistant_message_id: null` and are not rateable.

### 4.3 SSE `/agent/stream`

`start` may expose `agent_run_id` for correlation, but the FE must not enable feedback from it.
Terminal success becomes:

```text
event: done
data: {
  "conversation_id":"...",
  "assistant_message_id":"...",
  "agent_run_id":"...",
  "current_flow":"planner",
  "suggestions":[],
  "language":"vi",
  "trip_id":null
}
```

The stream today is composed as `persist_assistant_turn(record_agent_run(stream_agent_events(...)))`.
`record_agent_run` already tracks `interrupt` / `error` and finalizes the run row in its `finally`;
it is **not changed**. `persist_assistant_turn` currently yields every event first and appends the
assistant message only after the iterator is exhausted, so `done` reaches the client before the row
exists. That is the one behaviour this design changes:

```text
persist_assistant_turn (changed):
  for upstream event:
    token → accumulate and yield
    reset → clear accumulator and yield
    interrupt → yield; the done that follows an interrupt passes through with
               assistant_message_id: null (§4.2) — no row is written for an interrupted turn
    error → if accumulated text is non-empty (and code != cancelled), insert the assistant Message under the pre-minted id
            with agent_run_id = run_id (the run ends failed, so it is never rateable — same as the
            REST fallback in §4.2), then yield error unchanged; with empty text just yield
    done:
      if final text is empty: emit error{code: empty_reply}; do not yield done
      insert assistant Message under the pre-minted id, agent_run_id = run_id
      if the insert fails: emit error{code: persistence_failed}; do not yield done
      else: inject assistant_message_id + agent_run_id into the payload and yield done

record_agent_run (unchanged):
  finally → AgentRunRepository.finish(status = interrupted | failed | completed, current_flow, …)

if client disconnects before terminal:
  no Message row (the accumulator is never flushed)
  record_agent_run marks the run failed (CancelledError) — existing behaviour
```

Ordering: the message row is committed when `done` is yielded; the run row's terminal status is
written a moment later, when the outer generator asks the inner one for its next event and its
`finally` runs. Both writes use the same isolated `session_factory`. A feedback request that arrives
in that window sees `status = running` and gets `404` (§5.2); the client retries with the same
`client_event_id` and succeeds. That is acceptable for v1 and is cheaper than reordering two
best-effort wrappers.

Amended 2026-09-12 after the Task 3.1 review: the mapper streams a fallback `token` and then
`error` (never `done`) when the graph fails, so the `error` branch above persists that text to keep
REST and SSE history identical for the same failure; the two error codes `empty_reply` and
`persistence_failed` are the terminal codes the frontend task must recognise.

`persist_assistant_turn` gains `run_id` and `message_id` parameters from the router. On the chat
path (`/agent/chat`) the router already appends the reply and calls `finish` on the request session
before its explicit `session.commit()`; it passes the same two ids into `append_message`, which
closes the REST lifecycle gap the review raised.

This deliberately changes the meaning of `done` from “graph mapper finished” to “answer is durable
and eligible for subsequent actions.”

## 5. Feedback API

### 5.1 Endpoint

`POST /agent/feedback`

The body carries `client_event_id`; this works through `/api/be` and makes retry behavior explicit.
An `Idempotency-Key` header may mirror the same value, but having two different values is `422`.

Set rating:

```json
{
  "client_event_id": "uuid",
  "anonymous_user_id": "optional-when-no-jwt",
  "assistant_message_id": "uuid",
  "action": "set_rating",
  "rating": "helpful",
  "locale": "en"
}
```

`anonymous_user_id` is required only when no valid JWT exists and is ignored when authenticated,
matching the current agent identity precedence. It is a fallback principal with weaker assurance,
not authoritative provenance. The same rule applies to the detail and retract actions below.

Add optional negative detail:

```json
{
  "client_event_id": "uuid",
  "assistant_message_id": "uuid",
  "action": "add_detail",
  "reason_code": "incorrect",
  "comment": "The museum is closed on Tuesdays.",
  "locale": "en"
}
```

Retract:

```json
{
  "client_event_id": "uuid",
  "assistant_message_id": "uuid",
  "action": "retract_rating"
}
```

Response:

```json
{
  "feedback_event_id": "uuid",
  "assistant_message_id": "uuid",
  "effective_feedback": {
    "rating": "not_helpful",
    "reason_code": "incorrect",
    "comment_present": true,
    "rating_event_id": "uuid",
    "updated_at": "2026-07-21T...Z"
  },
  "replayed": false
}
```

The response never exposes actor, trace, prompt, model, fingerprint, internal supersession chain, or
comment text.

### 5.2 Status behavior

| Status | Meaning |
|---:|---|
| `201` | New state-changing event appended |
| `200` | Same idempotency key/fingerprint replayed, or documented retract no-op (a retract with nothing active still appends a `retract_rating` row — audit trail and key reservation — and answers `200`) |
| `401` | Neither a valid JWT nor a supported anonymous principal is available |
| `404` | Target unknown, foreign, non-assistant, non-completed, or non-rateable |
| `409` | Key reused with different fingerprint or invalid state transition |
| `422` | Schema/enum/length/conditional-field validation failed |
| `429` | Dedicated feedback abuse limit exceeded |

Do not reveal which `404` condition occurred.

The `429` is produced by the existing primitive, not new code: `rate_limit(name="feedback",
limit=settings.feedback_rate_limit_max, window_seconds=settings.feedback_rate_limit_window_seconds,
subject=…)` from `app/core/rate_limit.py`, attached as a route dependency **before** any session
work (the primitive raises `RuntimeError` if the request session already has a transaction open).
The two settings already exist in `app/core/config.py` (defaults 30 per 60 s, env-overridable) and
were added by the rate-limit primitive spec precisely for this route. The default subject resolver
returns `None` for anonymous callers (limit skipped), and its docstring says why a client-supplied
id must not be trusted as the subject; feedback passes its own resolver that namespaces the
body-resolved anonymous actor as `anon:<anonymous_user_id>` so an anonymous caller can neither rotate
out of the limit nor exhaust an authenticated user's counter. The `RateLimitError` envelope carries
`Retry-After`, `X-RateLimit-Limit`, `-Remaining`, `-Reset` via the existing middleware.

### 5.3 Service transaction

```text
resolve effective actor
normalize body and compute fingerprint
lookup event by (actor, client_event_id)
  found + same fingerprint → replay
  found + different fingerprint → 409
load target Message joined to Conversation and completed AgentRun
authorize owner, role=assistant, completed
lock/read current effective feedback
validate action transition
append event with derived conversation/run values
commit
schedule best-effort export
return folded state
```

Concurrent same-key insert races recover by rolling back to a savepoint, loading the winner, comparing
fingerprints, and replaying or conflicting—matching existing booking/trip repository conventions.

## 6. History contract

Avoid one request per message. Extend the ownership-scoped history item additively:

```json
{
  "id": "assistant-message-id",
  "conversation_id": "...",
  "role": "assistant",
  "content": "...",
  "created_at": "...",
  "feedback": {
    "rating": "helpful",
    "reason_code": null,
    "comment_present": false,
    "rating_event_id": "...",
    "updated_at": "..."
  }
}
```

User messages return `feedback: null`. The repository performs a bulk effective-state lookup for the
assistant message IDs returned by the history query. An alternative dedicated conversation-feedback
endpoint is acceptable if it remains one bulk request; N+1 message calls are not.

## 7. Frontend state and API design

### 7.1 Message state

```ts
interface ChatMessage {
  renderId: string;
  serverMessageId: string | null;
  role: "user" | "assistant";
  content: string;
  delivery: "streaming" | "complete" | "interrupted" | "failed";
  feedback: EffectiveFeedback | null;
}
```

- Client `renderId` remains stable through smooth reveal/reset/resume.
- `serverMessageId` is assigned only from server history or successful SSE `done`/REST response.
- Feedback controls render only for assistant + complete + server ID.
- Partial, interrupted, failed, empty, and typing states never show feedback.

### 7.2 Mutation behavior

Create one `clientEventId` per logical click and retain it for retries. Use a per-message in-flight
guard so double-clicks share the action rather than minting two events. A deliberate rating change
mints a new ID.

Optimistic algorithm:

1. Snapshot prior effective state.
2. Show selected/retracted state immediately and disable only that message's controls.
3. POST with the retained client event ID.
4. Replace optimistic state with canonical server state.
5. On failure, roll back, announce error, and offer retry using the same ID/payload.

Do not globally disable the chat composer or other messages while feedback saves.

## 8. Interaction design

### 8.1 Placement

```text
┌ assistant bubble ─────────────────────────────┐
│ Answer markdown…                             │
└───────────────────────────────────────────────┘
  [👍 Helpful] [👎 Not helpful]   Saved ✓
```

Controls sit below the assistant bubble and align with its left edge. They remain visible on touch;
they are not hover-only. The row wraps inside the current narrow chat panel.

Use ink/neutral styling by default. Departure Lime may indicate selected state because it is an
active selection, but selection must also have icon/text/border/`aria-pressed`; never use color alone.

### 8.2 Helpful flow

1. User activates Helpful.
2. Rating saves immediately.
3. Button becomes pressed; polite status says “Feedback saved.”
4. Activating the pressed button retracts; activating Not helpful replaces it.

### 8.3 Not-helpful flow

1. User activates Not helpful; rating saves immediately.
2. Button becomes pressed and a small “Tell us more” affordance opens the reusable modal.
3. User may choose one reason, enter up to 500 characters, Save, Skip, or close.
4. Closing never retracts the already-saved thumb.
5. Saving detail creates a separate immutable detail event linked to the active negative rating.

Reason choices are single-select in v1 to keep aggregation unambiguous. “Other” may be paired with an
optional comment; prose is never required.

### 8.4 Accessibility

- Native `<button type="button">`, stable accessible names, `aria-pressed`, visible focus ring.
- Enter/Space work through native semantics.
- 40–44px hit area and spacing; glyph may remain 16–18px.
- `aria-live="polite"` for saving/saved/error/retracted; do not move focus for background success.
- Modal uses visible title, focus trap, Escape, close/cancel, and focus restore.
- Reason group uses native radios and a `<fieldset>/<legend>` or equivalent accessible group.
- Textarea has visible label, optional hint, remaining count, and programmatic error association.
- English and Vietnamese strings are complete; no hard-coded panel labels.
- Reduced-motion users receive no celebratory animation requirement.

### 8.5 UI states

| State | Controls | Status |
|---|---|---|
| Streaming/interrupt/failed | hidden | none |
| Eligible, unrated | both unpressed | optional “Rate this answer” label |
| Saving | optimistic pressed; local disabled | “Saving…” |
| Saved helpful | helpful pressed | “Feedback saved” |
| Saved negative | negative pressed + details affordance | “Feedback saved” |
| Save failed | rolled back; retry enabled | localized error |
| Retracted | both unpressed | “Feedback removed” |
| Reloaded | server effective state | no stale success toast |

## 9. Observability export

**Deferred (2026-09-12):** the first implementation round is UI + API + SQL evidence only; the
service keeps an `export_hook` seam that is a no-op. The section stays as the contract for the
follow-up. Ordering caveat for that follow-up: the hook is scheduled as a Starlette background task,
and the request session's teardown commit runs **after** background tasks (see
`docs/solutions` background-task deadlock note), so a real exporter must either commit explicitly
before scheduling or read the event through its own session, never the request session.

After local commit, enqueue best-effort export:

- score ID = feedback event ID;
- target = `agent_runs.trace_id` when non-null; when it is null the export is skipped and counted,
  never guessed. `app/agents/observability.py` does not expose a trace id today, so Task 2.2 first
  verifies whether the Langfuse handler in use can return one (or accept a seeded id derived from
  `agent_run_id`); if neither holds, `trace_id` stays null in v1 and export is a documented no-op;
- name = `response_rating`;
- value = boolean/numeric mapping of `+1/-1`;
- comment = minimized optional reason/comment subject to provider policy;
- metadata/tags = event schema version and source, not user-supplied provenance.

Exporter failure increments a metric and is retryable; it never changes the API result. Because the
current background mechanism is not durable, the first implementation may be best-effort only, but
the SQL event remains available for a later reconciliation worker.

## 10. Security and privacy threat model

| Threat | Control |
|---|---|
| Attacker rates another user's UUID | Join message→conversation and compare effective owner every time |
| User rates own user-message ID | Require `role=assistant` and completed run |
| Spoofed trace/model/flow | Do not accept those fields from client |
| Duplicate click/network retry | Stable client event ID + unique actor/key + fingerprint |
| Same key reused for different payload | `409`, no state change |
| Comment XSS | Store normalized text; render text-only; never inject HTML |
| Oversized/spam payload | 500-char bound, schema limit, dedicated rate limit |
| Sensitive text leaks to logs/metrics | Never log bodies/comments; structured low-cardinality metrics only |
| Provider outage or purge | SQL remains authoritative; async projection |
| Anonymous ID theft | Document weak assurance, abuse limits; plan signed anonymous session |
| Config attribution drift | Snapshot at run time, not feedback time |
| Feedback changes memory unexpectedly | No call/import edge from feedback service to memory runner/store |

## 11. Migration and rollout

One migration, descending from the current single Alembic head `b8e4c1f7a305`
(`add_bookings_trip_id`; verify with `alembic heads` at implementation time) and written in
`batch_alter_table` form like that migration so SQLite and Postgres behave the same. Upgrade:

1. `messages.agent_run_id` — nullable string + index `ix_messages_agent_run_id`;
2. `feedback_events` table with the constraints and indexes of §3.2.

(`agent_runs.trace_id` is deferred with the §9 export and gets its own additive migration later.)

Downgrade drops `feedback_events` first, then the column. `agent_runs` and `agent_run_steps`
themselves are **not** touched by either direction; they belong to migrations `e3b7c5d9a1f4` and
`b2d9f4a7c1e8`. Test both directions the way `tests/db/test_bookings_trip_id_migration.py` does
(upgrade, assert, downgrade, assert), and add the two new columns to the exact-column-set assertion
in `tests/test_db_models.py`.

Rollout:

1. Deploy migration and BE identity fields; FE ignores additive fields.
2. Verify REST/SSE/history ID equality and `done-after-commit` metrics.
3. Deploy hidden FE code and internal-feature flag.
4. Enable internal cohort; inspect error, duplicate, unauthorized, comment, and coverage metrics.
5. Ramp percentage gradually; retain kill switch for UI and export independently.
6. Backfill is unnecessary: old messages may be rateable if an ownership-valid assistant message
   exists, but run provenance is nullable. Product may instead hide feedback for pre-release messages.

Recommended v1 policy: hide controls for messages without an `agent_run_id`; this avoids mixing fully
attributed new events with historical answers of unknown configuration.

Rollback:

- Disable FE flag first.
- Disable export independently.
- Roll back BE only after clients no longer require new fields.
- Keep tables during operational rollback to avoid evidence loss; use migration downgrade only when
  explicitly accepting data deletion after backup.

## 12. Test matrix

### Backend

- REST normal, fallback, interrupt: correct nullable/non-null message/run IDs; the fallback reply is
  persisted with `agent_run_id` set and its run `failed`, and is refused with `404` when rated.
- SSE token/reset/done: final text persists once, `messages.agent_run_id` equals the run started by
  the router, and the ID matches history.
- SSE persistence failure: no `done`; terminal error; no feedback-capable ID.
- Disconnect: no empty message; run status is `failed` (existing recorder), not `completed`.
- `agent_runs` / `agent_run_steps` rows are byte-identical to today's for a turn nobody rates (the
  existing `tests/api/agent/test_agent_runs*.py` and trace-detail tests stay green unchanged).
- `429` after `feedback_rate_limit_max` events in one window, for an authenticated and for an
  `anon:`-namespaced subject; the counter increments on a rejected (`404`/`409`) request too.
- Assistant ownership happy path for JWT and supported anonymous identity.
- Foreign, unknown, user-role, incomplete-run target: identical `404`.
- Same key/same body replay, same key/different body conflict, concurrent race recovery.
- Set, replace, detail, retract, stale/no-op retract, invalid transition.
- Reason enum, action-dependent fields, whitespace normalization, 500-char Unicode boundary.
- Langfuse disabled/outage: local success unchanged.
- Feedback submission never calls memory extraction/store.
- Anonymous claim updates conversations, runs, and events together (`reassign_user` extended; a
  claim on a conversation with no feedback still moves its `agent_runs` rows).
- Erasure removes/redacts local text and queues provider deletion.
- Migration upgrade/downgrade and model parity on SQLite/Postgres.

### Frontend

- SSE parser accepts `assistant_message_id`/`agent_run_id` and ignores unknown additive fields.
- `send`, `resume`, and `retry` map terminal IDs to the correct render bubble.
- Hydration preserves server ID and effective feedback.
- No controls on user, streaming, empty, interrupted, or failed messages.
- Helpful save/retract; negative save/change; optional detail/skip/close.
- Double-click and retry reuse client event ID; deliberate new action uses a new ID.
- Optimistic rollback and localized retry do not block chat.
- Keyboard, focus, `aria-pressed`, live announcements, dialog focus restore, touch target.
- Narrow/mobile wrapping, both locales, long translated strings, reduced motion.
- Comment renders safely as text and respects trim/length/error rules.

### End-to-end acceptance

1. Send a message; capture SSE server message ID.
2. Reload; history message ID is identical.
3. Rate helpful; reload; pressed state remains.
4. Change to not helpful, add reason, reload; effective state and details flag remain.
5. Retract; reload; neither thumb is selected.
6. Replay each request; event count does not grow.
7. Attempt another user's ID; response does not reveal existence and state is unchanged.
8. Disable Langfuse; repeat flow successfully.

## 13. Definition of done

- All invariants in section 1 are enforced by tests.
- OpenAPI is regenerated; SSE mirror is updated in the same change.
- No raw feedback text appears in logs, traces by default, or memory.
- SQL feedback remains available when tracing is off.
- UI state survives reload and is accessible in English and Vietnamese.
- Rollout, rollback, retention owner/window, erasure behavior, and metrics dashboards are documented.
- Memory-candidate or product-learning work remains a separate, gated follow-up.
