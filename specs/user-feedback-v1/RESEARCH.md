---
slug: user-feedback-v1
doc: research
lang: en
status: complete
created: 2026-07-21
source_of_truth: true
---

> **Language note:** This English document is the source of truth. See
> [RESEARCH.vi.md](./RESEARCH.vi.md) for the Vietnamese translation.

# Deep research — Feedback Event Foundation

## Executive decision

Travel-pi should add a **product-owned, append-only feedback event pipeline**, not a learning agent
that the supervisor visits. V1 captures thumbs up/down, an optional structured reason, and an
optional comment against the exact completed assistant message. It does not write memory, edit a
prompt, or train a model.

The most important change is not the thumb buttons. It is establishing one stable server identity for
an assistant answer across REST, SSE, SQL history, tracing, and the browser. Today that invariant does
not exist: live bubbles use client UUIDs while reloaded messages use database UUIDs, and the streaming
`done` event is emitted before the assistant message is persisted.

The recommended foundation is:

```text
answer starts
  → server mints agent_run_id + assistant_message_id
  → graph runs and streams draft content
  → final content persists under assistant_message_id
  → SSE done / REST response exposes assistant_message_id

user rates completed answer
  → ownership + role + transition + idempotency checks
  → append immutable FeedbackEvent in SQL
  → return effective feedback state
  └─ optional async export to Langfuse score / offline eval queue
```

SQL is the system of record. Langfuse is an optional projection for evaluation and diagnostics.

## 1. Questions researched

1. What does travel-pi persist today, and where does stable answer identity break?
2. How should feedback relate to conversations, messages, graph runs, traces, prompt versions, and
   model/tool provenance?
3. Should a rating be mutable state or immutable evidence?
4. How do retries, double-clicks, rating changes, and retractions behave?
5. How should JWT and anonymous identity enforce object ownership?
6. What belongs in the product database versus Langfuse or LangGraph memory?
7. What is the smallest accessible FE interaction that remains useful for evaluation?
8. What retention, deletion, abuse, and observability controls are required?

## 2. Current backend audit

### 2.1 Messages have durable IDs, but answer APIs discard them

`Message` already inherits a random UUID primary key, but stores only conversation, role, content,
and tool calls ([message.py](../../apps/api/app/db/models/message.py#L9-L17)). The repository returns
the created `Message` ([conversation.py](../../apps/api/app/repositories/conversation.py#L104-L123)),
yet `/agent/chat` discards that return value in both the normal and fallback answer paths
([agent.py](../../apps/api/app/routers/agent.py#L278-L308),
[agent.py](../../apps/api/app/routers/agent.py#L344-L359)). `ChatResponse` therefore has no assistant
message ID ([agent.py](../../apps/api/app/schemas/agent.py#L55-L77)).

### 2.2 Streaming currently emits success before persistence

The mapper emits terminal `done` with conversation/flow/suggestions/language/trip but no message ID
([events.py](../../apps/api/app/streaming/events.py#L90-L107)). The persistence wrapper passes every
event through unchanged and appends the assistant message only after the upstream iterator is fully
exhausted ([persistence.py](../../apps/api/app/streaming/persistence.py#L32-L80)). Consequently:

- the browser can receive `done` for content that later fails to persist;
- `done` cannot contain the new database message ID;
- a rating created immediately after `done` has no authoritative target;
- abandoned streams correctly have no assistant row, but this is implicit rather than modeled.

The wrapper already handles `reset`, so it is the correct seam to intercept terminal success,
persist the final accumulated content, then emit a rewritten `done` carrying the server message ID.

### 2.3 Ownership exists for history reads, but creation has a sharp edge

Authenticated calls use the JWT subject and ignore a spoofed fallback ID; anonymous calls use the
client-supplied ID ([agent.py](../../apps/api/app/routers/agent.py#L87-L98)). History reads join through
the conversation owner and return an empty result for foreign/unknown conversations
([agent.py](../../apps/api/app/routers/agent.py#L514-L546)).

However, `ensure_conversation` accepts an existing client-selected conversation ID without verifying
that its row belongs to the caller ([conversation.py](../../apps/api/app/repositories/conversation.py#L36-L68)).
The feedback endpoint must not inherit that behavior. OWASP requires an object-level authorization
check for every endpoint that receives an object ID; an unpredictable UUID is not authorization
([OWASP BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)).

### 2.4 Tracing cannot currently correlate a rating to one answer

Langfuse metadata currently records only user and trip/session tags
([observability.py](../../apps/api/app/agents/observability.py#L78-L92)). It does not snapshot
conversation, response message, graph run, specialist/tool outcome, model, prompt version, or release.
Prompt versions and model configuration can change later, so looking up “current” values when a user
rates an old message is incorrect. Provenance must be captured when the answer runs.

### 2.5 Feedback and memory are independent

Memory extraction already runs as a post-response task on every completed answer
([agent.py](../../apps/api/app/routers/agent.py#L360-L373),
[agent.py](../../apps/api/app/routers/agent.py#L456-L481)). The new feedback endpoint must not call it.
A thumbs-down says “this answer was not useful”; it does not reliably mean “store the opposite as a
durable preference.” This separation is the central safety gate inherited from
[the broader feedback-learning research](../user-feedback-learning/RESEARCH.md).

## 3. Current frontend audit

### 3.1 Live and hydrated messages use different identity sources

`ChatMessage.id` is a client-generated render UUID during live streaming
([useAgentStream.ts](../../apps/web/src/components/chat/useAgentStream.ts#L44-L51),
[useAgentStream.ts](../../apps/web/src/components/chat/useAgentStream.ts#L283-L297)). After reload,
history maps the backend message ID into that same property
([useAgentStream.ts](../../apps/web/src/components/chat/useAgentStream.ts#L204-L219)). A live rating
would therefore target an ID that the backend has never seen.

The FE needs separate `renderId` and nullable `serverMessageId`, plus delivery state. Feedback is
eligible only when delivery is `complete` and `serverMessageId` is present.

### 3.2 Three completion paths must share the same contract

`send`, `resume`, and `retry` each parse `done` separately. All three must set the server message ID;
otherwise interrupted/resumed or retried turns behave differently. The bespoke SSE type mirror also
must be changed with the backend, because it is not generated from OpenAPI
([parseSSE.ts](../../apps/web/src/lib/stream/parseSSE.ts#L90-L117)).

### 3.3 Existing UI seams are sufficient

Assistant bubbles render in `MessageList` and already sit outside user content markdown
([MessageList.tsx](../../apps/web/src/components/chat/MessageList.tsx#L40-L73)). Feedback controls
should sit below the assistant bubble, not inside markdown. The existing `Modal` already handles
focus entry, Tab trapping, Escape, and focus restoration
([Modal.tsx](../../apps/web/src/components/ui/Modal.tsx#L16-L89)). English/Vietnamese copy belongs
under the existing `Chat` namespaces.

The generic icon button is 34px, while WCAG 2.2 Level AA requires at least a 24×24 CSS-pixel target
or sufficient spacing; 44×44 is the enhanced target recommendation
([W3C target-size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum),
[W3C target-size enhanced](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced)). For
this compact, touch-heavy chat surface, use a 40–44px hit area even if the glyph remains small.

## 4. External evidence and implications

### Feedback is an evaluation record tied to execution

LangSmith attaches user feedback to a trace/root or child run, allowing a specific application step
to be evaluated ([LangSmith feedback guide](https://docs.langchain.com/langsmith/attach-user-feedback),
[feedback format](https://docs.langchain.com/langsmith/feedback-data-format)). Langfuse represents
end-user feedback as typed scores attached to a trace, observation, session, or dataset run, with an
optional comment ([Langfuse scores](https://langfuse.com/docs/evaluation/scores/overview),
[score data model](https://langfuse.com/docs/evaluation/scores/data-model)).

Implication: keep `assistant_message_id` as the product identity and `agent_run_id`/nullable
`trace_id` as diagnostic provenance. A provider trace ID is not a replacement for a product record.
LangChain permits a run identifier to be supplied in `RunnableConfig`, while Langfuse supports
predetermined/deterministic trace identifiers for distributed correlation
([RunnableConfig reference](https://reference.langchain.com/python/langchain-core/runnables/config/RunnableConfig),
[Langfuse trace IDs](https://langfuse.com/docs/observability/features/trace-ids-and-distributed-tracing)).
This supports minting correlation IDs at answer start rather than trying to recover them when
feedback arrives.

### Idempotency is request identity, not deduplication by content

The IETF `Idempotency-Key` work-in-progress specifies retry-safe POST/PATCH behavior: a key must not
be reused for a different payload, a server may fingerprint payloads, completed retries replay the
prior result, and concurrent duplicates need explicit handling
([IETF draft](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header)).

Implication: one client event UUID survives network retries. The same actor/key/fingerprint returns
the original event; the same actor/key with another payload is `409`. Changing up→down creates a new
key and a new event. Do not generate a fresh key inside generic middleware on every retry.

### Privacy applies to “Tell us more” text

Purpose limitation, data minimization, and storage limitation require collecting only what is needed
and retaining it only as long as needed
([European Commission GDPR principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en)).
Langfuse retention is separately configurable, and provider deletion must be considered alongside
local deletion ([Langfuse retention](https://langfuse.com/docs/administration/data-retention),
[Langfuse deletion](https://langfuse.com/docs/administration/data-deletion)).

Implication: reason codes are preferred over prose; comment is optional and bounded; raw text is not
logged or copied into memory; retention and erasure cover both SQL and exported scores/traces.

### Toggle semantics must be explicit

WAI's button pattern requires accessible names and supports two-state buttons using `aria-pressed`;
Enter and Space activate a focused button, and the accessible label should remain stable as pressed
state changes ([WAI button pattern](https://www.w3.org/WAI/ARIA/apg/patterns/button/)). A modal must
move focus inside, trap focus, close on Escape, and restore focus
([WAI modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)).

Implication: “Helpful” and “Not helpful” stay the labels; `aria-pressed` expresses selection. A polite
live region announces saved/error/retracted state. The negative-details dialog is optional and never
blocks recording the rating.

## 5. Architecture alternatives

| Decision | Option | Benefit | Failure mode | Choice |
|---|---|---|---|---|
| System of record | Langfuse only | Fast setup | Feedback unavailable/coupled to provider outage and retention | Reject |
| System of record | SQL + async Langfuse projection | Product ownership, provider-independent | Requires export seam | **Choose** |
| Rating history | Mutable row | Simple current-state read | Loses changes/retractions and retry audit | Reject |
| Rating history | Append-only events + folded effective state | Auditable and reversible | Read model is slightly richer | **Choose** |
| Provenance | Copy current config when feedback arrives | Simple | Historically wrong | Reject |
| Provenance | Capture run snapshot at answer time | Exact attribution | Adds run lifecycle | **Choose** |
| Stream identity | Pre-insert empty message | ID exists early | Aborted streams pollute history | Reject |
| Stream identity | Pre-mint ID, insert final message before `done` | Stable ID without empty rows | Wrapper ordering change | **Choose** |
| UI details | Require a reason before saving downvote | Richer data | High abandonment and coerced text | Reject |
| UI details | Save thumb immediately; details optional | Low friction | Some sparse events | **Choose** |
| V1 learning | Feedback directly writes memory | Immediate adaptation | Misinterprets quality signal; unsafe | Reject |
| V1 learning | Evidence only, offline/shadow consumers later | Auditable | Delays learning rollout | **Choose** |

## 6. Recommended v1 signal semantics

V1 supports one rating dimension:

- `helpful` (`+1`)
- `not_helpful` (`-1`)
- `retract` (no active rating)

Negative details are optional reason codes:

- `incorrect`
- `irrelevant`
- `outdated`
- `did_not_follow_request`
- `tool_or_data_problem`
- `unsafe_or_inappropriate`
- `other`

An optional comment is qualitative evidence, not an instruction to memory. Corrections,
remember/forget commands, implicit clicks/bookings, and admin annotations should use later typed
event schemas rather than overloading the v1 thumbs contract.

## 7. Identity, authorization, and anonymous users

The authorization path is:

```text
JWT subject or anonymous principal
  → assistant_message_id
  → Message must exist and role == assistant
  → Message.conversation_id
  → Conversation.user_id must equal effective actor
```

Unknown messages, user messages, foreign messages, and foreign conversations return the same
non-enumerating `404`. An optional `anonymous_user_id` is only the existing fallback principal when
no JWT exists; it is never trusted as answer provenance. The request does not accept authoritative
`conversation_id`, trace, flow, model, or prompt fields; the server derives them.

Authenticated feedback has strong account ownership. The current anonymous ID is client-asserted, so
it is weaker. V1 may preserve the existing anonymous product behavior, but it must document that
assurance gap, apply abuse limits, and transactionally reassign feedback/run ownership when anonymous
conversations are claimed. A future signed anonymous session is the proper hardening path.

## 8. Idempotency and event-state model

Each user action has a stable `client_event_id` (or explicit `Idempotency-Key`) retained across
retries. The server stores a canonical request fingerprint.

| Situation | Result |
|---|---|
| First valid action | `201`, append event |
| Same actor + key + fingerprint | replay original `200`, no new event |
| Same actor + key + different fingerprint | `409` |
| Concurrent same-key actions | one wins; loser replays winner |
| Helpful → not helpful | new `set` event supersedes current event |
| Current rating → retract | new `retract` event supersedes current event |
| Retract with no current rating | `409 invalid_transition` or documented idempotent no-op; choose one and test |

Recommendation: make `retract` without an active rating a replay-safe no-op response, because UI
state can be stale across tabs. Preserve the submitted event only when it changes effective state.

## 9. Privacy, retention, and abuse controls

- Cap comment length at 500 Unicode characters for v1; trim outer whitespace and reject control
  characters. Render as text only.
- Never log comment bodies, raw request bodies, tool arguments, or corrections.
- Keep structured reason separate from free text for analytics and minimization.
- Rate-limit per effective user and per IP/device for anonymous callers. Existing informational rate
  headers are not enforcement. OWASP treats unrestricted resource consumption as an API risk and
  recommends explicit request and rate limits
  ([OWASP API4](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/)).
- Define a product retention window before launch. On user/conversation erasure, delete or redact
  identifiable feedback and request provider deletion; retain only genuinely anonymized aggregates
  when lawful.
- Do not store feedback comment text in LangGraph semantic memory.
- Avoid raw full-trace duplication in the feedback table; reference the run and store only an
  allowlisted provenance snapshot.

## 10. Evaluation and observability handoff

The event foundation enables, but does not itself execute, product learning:

```text
SQL feedback event
  ├─ dashboard: rating/reason/coverage trends
  ├─ best-effort Langfuse score linked by trace/run
  └─ sampled negative trajectories → human annotation → regression dataset
                                           ↓
                               prompt/tool/routing candidate
                                           ↓
                               offline eval + approval + rollout
```

Langfuse scores can support user feedback, human annotations, automated judges, and later analytics
([Langfuse evaluation overview](https://langfuse.com/docs/evaluation/overview)). Export the stable
feedback event ID as the provider score ID so retries update/replay rather than duplicate.

Track accepted/retracted/replayed/conflicted/unauthorized/invalid/export-failed counters; feedback
POST p95; rating coverage per completed assistant message; negative reason completion; rating-change
rate; export lag; and results segmented by captured app release/model/prompt/flow. Never put comment
content in metric labels or logs.

## 11. Most important changes, ranked

1. **Fix answer identity and stream ordering.** Without this, all later feedback is untrustworthy.
2. **Enforce message-level ownership and assistant role.** UUIDs alone do not prevent IDOR/BOLA.
3. **Persist immutable, idempotent SQL evidence.** Do not make Langfuse or memory authoritative.
4. **Capture provenance at run time.** Later “current config” lookup corrupts attribution.
5. **Separate effective UI state from immutable history.** Users can change/retract without erasing
   evidence.
6. **Make negative details optional and accessible.** Low-friction signal first, richer context second.
7. **Keep v1 disconnected from memory.** Evidence quality must be measured before learning is enabled.

## 12. Delivery recommendation

Implement in the six waves in [PLAN.md](./PLAN.md): stable identity; run/feedback persistence;
ownership-safe API; optional observability export; contract mirroring and accessible bilingual UI;
then cross-layer tests and rollout evidence.

Ship dark first with database/API and no visible buttons. Validate identity, ownership, idempotency,
and persistence metrics. Enable controls for an internal cohort, then a small percentage, then all
users. Do not begin memory-candidate work until event quality, privacy controls, and evaluation
sampling have been reviewed.

## Final answer to the original question

The supervisor should not route through a feedback-learning agent. The supervisor continues to select
the travel specialist. The feedback foundation records immutable evidence outside the answer graph;
later background/offline pipelines may turn that evidence into memory candidates or product changes
under deterministic policy, evaluation, and human/user controls.
