---
slug: user-feedback-v1
doc: design
lang: vi
status: proposed
created: 2026-07-21
source_of_truth: false
translation_of: DESIGN.md
---

> **Ghi chú ngôn ngữ:** Đây là bản dịch tiếng Việt. Bản tiếng Anh
> [DESIGN.md](./DESIGN.md) là nguồn chuẩn.

# Thiết kế — Nền tảng Feedback Event

> **Bản sửa 2026-09-12 — dùng lại run record đã có.** Lúc viết thiết kế này (2026-07-21) chưa có
> bảng run nào. Từ đó PR #131 (`specs/agent-turn-metrics`, migration `e3b7c5d9a1f4`) đã thêm
> `agent_runs`, và PR #132 (`specs/agent-run-trace-detail`, migration `b2d9f4a7c1e8`) thêm
> `agent_run_steps` cùng cột `agent_runs.prompt_versions`. Cả hai router đã mint run id trước khi
> graph chạy và finalize row sau đó. Bản sửa này vì vậy **mở rộng** bảng đó thay vì tạo mới: §2, §3.1,
> §3.4, §4.3, §5.2, §9, §11 và §12 đổi; contract feedback (§3.2–§8, §10) giữ nguyên. Rate limit riêng
> cho feedback giờ trỏ đúng primitive đã ship ở PR #110 (`app/core/rate_limit.py`) và hai setting
> `feedback_rate_limit_*` đã có sẵn trong `app/core/config.py`.

## 1. Phạm vi và invariants

Thiết kế này thêm answer-level feedback xuyên BE→FE. Contract cố ý hẹp: thumbs up/down, reason/comment
tùy chọn, đổi, retract, reload và export cho evaluation.

Invariants bắt buộc:

1. Target là assistant message đã hoàn tất và persist, không phải conversation, client bubble, trace,
   tool call hay draft stream.
2. `assistant_message_id` do server tạo và giống nhau trong SQL history, `/agent/chat`, SSE `done` và
   hydrated FE state.
3. Không phát `done` trước khi commit assistant message thành công.
4. Chỉ owner của conversation chứa message được submit/read effective feedback.
5. Feedback event append-only, ngoại trừ privacy erasure bắt buộc.
6. Retry transport không tạo thêm logical event.
7. Feedback không phụ thuộc Langfuse và không bao giờ gọi memory extraction.
8. Provenance từ client không đáng tin; server capture lúc answer chạy.

## 2. Thiết kế component

```text
┌──────────────────────────── ANSWER PATH ────────────────────────────┐
│ Agent router (đã có)                                                │
│   mint agent_run_id, AgentRunRepository.start(status=running)       │
│   mint assistant_message_id (mới)                                   │
│      ▼                                                              │
│ LangGraph → typed SSE mapper → record_agent_run (đã có)             │
│                              → persist_assistant_turn (đổi)         │
│                              intercept done                         │
│                              persist Message(explicit id,           │
│                                              agent_run_id)          │
│                              emit done + assistant_message_id        │
│                              AgentRunRepository.finish (đã có)       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────── FEEDBACK PATH ───────────────────────────┐
│ MessageFeedback → POST /agent/feedback                              │
│   auth principal → FeedbackService                                  │
│   load Message + Conversation + AgentRun                            │
│   authorize owner + assistant role                                  │
│   validate transition + fingerprint                                 │
│   append FeedbackEvent → return effective state                     │
│      └─ best-effort async Langfuse score export                     │
└─────────────────────────────────────────────────────────────────────┘
```

Layering giữ `router → service → repository`; ORM chỉ nằm trong repository. Service sở hữu transition,
authorization và idempotency policy; repository sở hữu atomic persistence.

## 3. Data model

### 3.1 `agent_runs` (đã có) và link từ message (mới)

Dùng record tại answer-time thay vì copy “current config” lúc feedback đến. Record đó **đã tồn
tại**: `app/db/models/agent_run.py` (một row mỗi turn hoặc HITL resume) và
`app/db/models/agent_run_step.py` (một row mỗi LLM call, tool call hoặc node, theo `seq`). Provenance
thiết kế này cần map vào đó như sau; spec này không tạo bảng nào ở đây.

| Nhu cầu provenance (v1) | Nằm ở đâu hôm nay | Ghi chú |
|---|---|---|
| `agent_run_id` mint trước khi graph chạy | `agent_runs.id` — `routers/agent.py` mint `uuid4()` và gọi `AgentRunRepository.start` trước khi invoke graph, ở cả `/agent/chat` lẫn `/agent/stream` | Đã thỏa invariant 8 |
| `user_id`, `conversation_id`, `trip_id` | cột cùng tên | `user_id` là effective owner lúc run |
| `channel` | `agent_runs.channel` = `chat` \| `stream` | |
| loại run | `agent_runs.kind` = `turn` \| `resume` | HITL resume là row riêng |
| `status` | `agent_runs.status` = `running` \| `completed` \| `interrupted` \| `failed` | xem ghi chú status bên dưới |
| `current_flow` | `agent_runs.current_flow` | set lúc finish |
| `prompt_versions` | `agent_runs.prompt_versions` (JSON) | snapshot build-time của graph đã compile, không phải `active.yaml` lúc feedback |
| model mỗi call (`model_config`) | `agent_run_steps.model` từng LLM step, `agent_runs.by_model` tổng | thay cho cột `model_config` đề xuất |
| execution summary | `agent_run_steps` (`kind`, `node`, `tool_name`, `status`, `error_type`) | thay cho cột `execution_summary` đề xuất; args/result không được lưu theo thiết kế sẵn |
| `started_at`, `finished_at` | cột cùng tên | |

Thay đổi additive spec này thêm (một migration, §11):

| Column | Type | Quy tắc / mục đích |
|---|---|---|
| `messages.agent_run_id` | string nullable, indexed | Set lúc insert assistant reply; feedback service join message → run qua cột này. Plain string, không FK, theo convention repo (`trip_items.booking_id`, `bookings.trip_id`) |
| `agent_runs.trace_id` | string nullable | **Hoãn (2026-09-12)** cùng export ở §9; không nằm trong vòng implement đầu. Khi thêm: correlation trace, fill best-effort lúc finish khi tracing handler có; `NULL` nghĩa là "không export" |

Bỏ khỏi đề xuất gốc, kèm lý do:

- `agent_runs.assistant_message_id` — link nằm trên message. Message là target của feedback nên join
  bắt đầu từ đó; link một chiều trên row con là precedent của repo, và tránh unique constraint mà một
  turn retry (`kind=resume`, cùng conversation) sẽ va phải.
- status `abandoned` — recorder hiện có (`app/streaming/agent_run.py`) đánh dấu client disconnect là
  `failed` (`CancelledError` trong inner iterator). Status thứ năm không đem lại gì cho v1; "không
  phải `completed`" là phép thử duy nhất feedback path cần.
- `app_release` — không consumer nào của v1 cần.
- Fallback `Message.provenance` JSON — không còn ý nghĩa; bảng đã có.

**Rateable** = message có `role = assistant`, `agent_run_id` non-null, và run được link có
`status = completed`. Fallback reply sinh ra sau khi graph fail vẫn persist (§4.2); run nó link tới là
`failed`, nên **không** rateable theo quy tắc này. Đây là cố ý siết lại câu chữ cũ ở §4.2: câu trả
lời graph không sinh ra thì không có config nào để gán rating.

Ghi chú status: `AgentRunRepository.finish` ghi terminal status ở stream path từ `record_agent_run`
(sau khi SSE iterator cạn) và ở chat path từ `_finalize` của router. Feedback chỉ đọc status, không
bao giờ ghi.

### 3.2 `feedback_events`

| Column | Type | Quy tắc / mục đích |
|---|---|---|
| `id` | string UUID PK | Cũng dùng làm provider score id |
| `schema_version` | integer | Bắt đầu `1` |
| `user_id` | string, indexed | Effective actor, derive server-side |
| `conversation_id` | string, indexed | Derive từ target message |
| `assistant_message_id` | string, indexed | Required, role assistant |
| `agent_run_id` | string nullable, indexed | Derive từ completed run |
| `action` | string | `set_rating`, `add_detail`, `retract_rating` |
| `rating` | integer nullable | `1` helpful, `-1` not helpful |
| `reason_code` | string nullable | Allowlisted taxonomy |
| `comment` | string nullable | Trim, max 500 chars |
| `source` | string | `chat_message_actions` trong v1 |
| `locale` | string nullable | Short locale allowlist, chỉ advisory |
| `client_event_id` | string UUID | Stable cho một logical UI action |
| `request_fingerprint` | string | Hash canonical accepted input |
| `supersedes_event_id` | string nullable | Prior effective event |
| `created_at` | ISO string | Immutable event time |

Constraints/indexes:

- unique `(user_id, client_event_id)`;
- index `(assistant_message_id, created_at, id)` để fold;
- index `(user_id, created_at)` cho export/erasure;
- index `(rating, created_at)` cho aggregate sampling;
- `rating IN (-1, 1)` khi non-null;
- `set_rating` cần rating và không nhận comment;
- `add_detail` cần active negative rating phù hợp và có reason hoặc comment;
- `retract_rating` không có rating/reason/comment;
- `supersedes_event_id` phải cùng user/message, enforce trong transaction.

Không copy raw request, answer, tool args hay full trace vào table này.

### 3.3 Effective feedback read model

Immutable log là authoritative; client nhận folded view:

```json
{
  "rating": "helpful",
  "reason_code": null,
  "comment_present": false,
  "rating_event_id": "...",
  "updated_at": "2026-07-21T...Z"
}
```

Fold theo `(created_at, id)`: `set_rating` thay active rating và clear detail cũ; `add_detail` enrich
current negative rating; `retract_rating` clear rating/detail; idempotent replay không đổi log. V1 có
thể fold khi query. Khi read volume lớn mới thêm projection table cập nhật transactionally.

### 3.4 Delete và claim behavior

- User/conversation erasure xóa hoặc redact free text và provider projections theo retention policy.
  Append-only là audit design, không phải lý do từ chối privacy erasure.
- Anonymous conversation claim phải update `agent_runs.user_id` và `feedback_events.user_id` cùng
  transaction với conversation reassignment. Claim path đã có — `POST /agent/conversations/claim` →
  `ConversationRepository.reassign_user` — và hiện chỉ reassign **conversations**; `agent_runs.user_id`
  đang bị bỏ lại sau mỗi lần claim. Task 2.1 mở rộng repository call đó ra ba bảng trong một
  transaction.

## 4. Answer identity contract

### 4.1 Repository change

`append_message` nhận optional explicit `message_id`. Server mint trước graph nhưng chưa insert cho đến
khi final answer hoàn tất.

```python
append_message(
    message_id=assistant_message_id,
    conversation_id=conversation_id,
    role="assistant",
    content=final_text,
)
```

Existing same-ID/same-conversation/same-content chỉ được xem là replay ở recovery path có chủ ý;
conflicting reuse là integrity error.

### 4.2 REST `/agent/chat`

Successful response thêm:

```json
{
  "conversation_id": "...",
  "assistant_message_id": "...",
  "agent_run_id": "...",
  "reply": "...",
  "current_flow": "planner"
}
```

Fallback content vẫn persist thành assistant message mang `agent_run_id` của run, nhưng run đó kết
thúc `failed` nên message **không** rateable (quy tắc §3.1); response vẫn trả `assistant_message_id`
để history và client thống nhất identity. Interrupt response có `assistant_message_id: null` và không
rateable.

### 4.3 SSE `/agent/stream`

`start` có thể trả `agent_run_id`, nhưng FE chưa được bật feedback từ đó. Terminal success:

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

Stream hôm nay được ghép là `persist_assistant_turn(record_agent_run(stream_agent_events(...)))`.
`record_agent_run` đã theo dõi `interrupt` / `error` và finalize run row trong `finally`; nó **không
đổi**. `persist_assistant_turn` hiện yield mọi event trước rồi mới append assistant message sau khi
iterator cạn, nên `done` tới client trước khi row tồn tại. Đó là hành vi duy nhất thiết kế này đổi:

```text
persist_assistant_turn (đổi):
  với mỗi upstream event:
    token → accumulate và yield
    reset → clear accumulator và yield
    interrupt / error → yield (record_agent_run sở hữu run status)
    done:
      nếu final text empty → error, không yield done
      insert assistant Message bằng pre-minted id, agent_run_id = run_id
      nếu insert fail → terminal persistence error, không yield done
      nếu thành công → inject assistant_message_id + agent_run_id vào payload rồi yield done

record_agent_run (không đổi):
  finally → AgentRunRepository.finish(status = interrupted | failed | completed, current_flow, …)

client disconnect trước terminal:
  không Message row (accumulator không bao giờ flush)
  record_agent_run đánh dấu run failed (CancelledError) — hành vi đã có
```

Thứ tự: message row commit khi `done` được yield; terminal status của run ghi ngay sau đó, khi outer
generator hỏi inner generator event kế tiếp và `finally` của nó chạy. Cả hai write dùng cùng
`session_factory` isolated. Feedback request rơi vào khoảng đó thấy `status = running` và nhận `404`
(§5.2); client retry cùng `client_event_id` sẽ thành công. Chấp nhận được cho v1 và rẻ hơn việc đảo
thứ tự hai wrapper best-effort.

`persist_assistant_turn` nhận thêm `run_id` và `message_id` từ router. Ở chat path (`/agent/chat`)
router đã append reply và gọi `finish` trên request session trước `session.commit()` tường minh; nó
truyền cùng hai id đó vào `append_message`, đóng gap vòng đời REST mà review đã nêu.

Như vậy `done` đổi nghĩa từ “graph mapper đã xong” thành “answer đã durable và đủ điều kiện cho action
tiếp theo”.

## 5. Feedback API

### 5.1 Endpoint

`POST /agent/feedback`. Body có `client_event_id`; `Idempotency-Key` có thể mirror cùng value, nhưng
nếu hai giá trị khác nhau thì `422`.

Set rating:

```json
{
  "client_event_id": "uuid",
  "anonymous_user_id": "optional-when-no-jwt",
  "assistant_message_id": "uuid",
  "action": "set_rating",
  "rating": "helpful",
  "locale": "vi"
}
```

`anonymous_user_id` chỉ required khi không có JWT hợp lệ và bị ignore khi authenticated, theo identity
precedence hiện tại. Đây là fallback principal có assurance yếu hơn, không phải provenance
authoritative. Detail và retract dùng cùng quy tắc.

Add negative detail:

```json
{
  "client_event_id": "uuid",
  "assistant_message_id": "uuid",
  "action": "add_detail",
  "reason_code": "incorrect",
  "comment": "Bảo tàng đóng cửa vào thứ Ba.",
  "locale": "vi"
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

Không trả actor, trace, prompt, model, fingerprint, supersession chain hay comment text.

### 5.2 Status behavior

| Status | Ý nghĩa |
|---:|---|
| `201` | Append state-changing event mới |
| `200` | Replay cùng key/fingerprint hoặc retract no-op |
| `401` | Không có JWT hợp lệ lẫn anonymous principal được hỗ trợ |
| `404` | Target unknown/foreign/non-assistant/non-completed |
| `409` | Reuse key khác fingerprint hoặc transition không hợp lệ |
| `422` | Schema/enum/length/conditional validation fail |
| `429` | Vượt feedback abuse limit |

Mọi điều kiện `404` dùng cùng response để không enumerate.

`429` do primitive sẵn có sinh ra, không viết code mới: `rate_limit(name="feedback",
limit=settings.feedback_rate_limit_max, window_seconds=settings.feedback_rate_limit_window_seconds,
subject=…)` từ `app/core/rate_limit.py`, gắn làm route dependency **trước** mọi thao tác session
(primitive raise `RuntimeError` nếu request session đã mở transaction). Hai setting đã có trong
`app/core/config.py` (mặc định 30 mỗi 60 s, override qua env) và được thêm bởi spec rate-limit
primitive đúng cho route này. Subject resolver mặc định trả `None` với caller anonymous (bỏ qua
limit), và docstring của nó nói rõ vì sao không được tin id do client gửi làm subject; feedback truyền
resolver riêng, namespace actor anonymous resolve từ body thành `anon:<anonymous_user_id>` để caller
anonymous không xoay id thoát limit lẫn không tiêu counter của user đã đăng nhập. Envelope
`RateLimitError` mang `Retry-After`, `X-RateLimit-Limit`, `-Remaining`, `-Reset` qua middleware sẵn có.

### 5.3 Service transaction

```text
resolve effective actor
normalize body + fingerprint
lookup (actor, client_event_id)
  cùng fingerprint → replay
  khác fingerprint → 409
load Message + Conversation + completed AgentRun
authorize owner, role=assistant, completed
read/lock effective feedback hiện tại
validate transition
append event với derived conversation/run
commit → schedule best-effort export → return folded state
```

Concurrent same-key race dùng savepoint, load winner, compare fingerprint rồi replay/conflict, theo
convention booking/trip hiện có.

## 6. History contract

Tránh N+1 call. Mở rộng history item theo kiểu additive:

```json
{
  "id": "assistant-message-id",
  "role": "assistant",
  "content": "...",
  "feedback": {
    "rating": "helpful",
    "reason_code": null,
    "comment_present": false,
    "rating_event_id": "...",
    "updated_at": "..."
  }
}
```

User message trả `feedback: null`. Repository bulk-load effective states cho các assistant IDs trong
history query. Dedicated conversation-feedback endpoint cũng được nếu chỉ một bulk request.

## 7. Frontend state và API design

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

`renderId` giữ ổn định cho smooth reveal/reset/resume. `serverMessageId` chỉ đến từ server history hoặc
successful `done`/REST response. Chỉ assistant + complete + server ID mới hiện feedback.

### 7.2 Mutation behavior

Tạo một `clientEventId` cho mỗi logical click và giữ qua retries. Per-message in-flight guard khiến
double-click dùng chung action; deliberate rating change tạo ID mới.

Optimistic flow: snapshot state cũ → show selected ngay, disable riêng row đó → POST → dùng canonical
server state → nếu fail rollback, announce error, retry cùng ID/payload. Không khóa chat composer hay
message khác.

## 8. Interaction design

### 8.1 Placement

```text
┌ assistant bubble ─────────────────────────────┐
│ Answer markdown…                             │
└───────────────────────────────────────────────┘
  [👍 Hữu ích] [👎 Không hữu ích]   Đã lưu ✓
```

Controls nằm dưới bubble, align mép trái, luôn visible trên touch và wrap trong chat panel hẹp. Default
dùng ink/neutral. Departure Lime được dùng cho selected state nhưng phải kèm icon/text/border và
`aria-pressed`, không dựa vào màu đơn thuần.

### 8.2 Helpful flow

Activate Helpful → save ngay → button pressed + polite “Đã lưu feedback”. Activate lại để retract;
activate Not helpful để replace.

### 8.3 Not-helpful flow

Activate Not helpful → save rating ngay → button pressed + mở affordance “Cho chúng tôi biết thêm”.
User chọn một reason, nhập tối đa 500 chars, Save/Skip/close. Đóng dialog không retract thumb đã lưu.
Save detail tạo immutable detail event riêng liên kết active negative rating. Reason single-select để
aggregation rõ; prose không bắt buộc.

### 8.4 Accessibility

- Native button, stable accessible name, `aria-pressed`, focus ring.
- Enter/Space theo native semantics; hit area 40–44px.
- `aria-live="polite"` cho saving/saved/error/retracted, không move focus khi success.
- Modal có title, focus trap, Escape, cancel/close, focus restore.
- Reason dùng native radios + fieldset/legend hoặc group tương đương.
- Textarea có visible label, optional hint, counter và error association.
- Đủ strings en/vi, không hard-code; reduced motion không cần celebration animation.

### 8.5 UI states

| State | Controls | Status |
|---|---|---|
| Streaming/interrupt/failed | hidden | none |
| Eligible, unrated | cả hai unpressed | optional label |
| Saving | optimistic pressed; local disabled | “Đang lưu…” |
| Saved helpful | helpful pressed | “Đã lưu feedback” |
| Saved negative | negative pressed + details | “Đã lưu feedback” |
| Save failed | rollback; retry enabled | localized error |
| Retracted | cả hai unpressed | “Đã gỡ feedback” |
| Reloaded | server effective state | không toast cũ |

## 9. Observability export

**Hoãn (2026-09-12):** vòng implement đầu chỉ gồm UI + API + bằng chứng SQL; service giữ seam
`export_hook` là no-op. Mục này giữ nguyên làm contract cho vòng sau.

Sau local commit, enqueue best-effort export:

- score ID = feedback event ID;
- target = `agent_runs.trace_id` khi non-null; khi null thì bỏ qua export và đếm, không bao giờ
  đoán. `app/agents/observability.py` hôm nay không expose trace id, nên Task 2.2 trước hết verify
  Langfuse handler đang dùng có trả trace id không (hoặc nhận id seed từ `agent_run_id`); nếu cả hai
  đều không, `trace_id` giữ null ở v1 và export là no-op có document;
- name = `response_rating`;
- value = boolean/numeric map từ `+1/-1`;
- comment = minimized optional reason/comment theo provider policy;
- metadata = schema version/source, không provenance do user gửi.

Exporter failure chỉ tăng metric và retry được; không đổi API result. Background task v1 có thể
best-effort, nhưng SQL event cho phép reconciliation worker về sau.

## 10. Security và privacy threat model

| Threat | Control |
|---|---|
| Rate UUID của user khác | Join message→conversation và so owner mỗi lần |
| Rate user message | Require assistant role + completed run |
| Spoof trace/model/flow | Không nhận fields này từ client |
| Double-click/retry | Stable client ID + unique actor/key + fingerprint |
| Cùng key, payload khác | `409`, không đổi state |
| Comment XSS | Normalize text, render text-only |
| Payload lớn/spam | 500-char limit + dedicated rate limit |
| Leak text vào log/metric | Không log body/comment; metric low-cardinality |
| Provider outage/purge | SQL authoritative, projection async |
| Anonymous ID theft | Document gap, abuse limit, signed session roadmap |
| Config drift | Snapshot lúc run |
| Feedback ghi memory | Không có call/import edge từ feedback sang memory |

## 11. Migration và rollout

Một migration, đi từ single Alembic head hiện tại `b8e4c1f7a305` (`add_bookings_trip_id`; verify
bằng `alembic heads` lúc implement) và viết theo dạng `batch_alter_table` như migration đó để SQLite
và Postgres hành xử giống nhau. Upgrade:

1. `messages.agent_run_id` — string nullable + index `ix_messages_agent_run_id`;
2. bảng `feedback_events` với constraints/indexes ở §3.2.

(`agent_runs.trace_id` hoãn cùng export §9, sẽ có migration additive riêng sau.)

Downgrade drop `feedback_events` trước, rồi cột. Bản thân `agent_runs` và `agent_run_steps`
**không** bị đụng ở cả hai chiều; chúng thuộc migration `e3b7c5d9a1f4` và `b2d9f4a7c1e8`. Test cả hai
chiều theo cách `tests/db/test_bookings_trip_id_migration.py` làm (upgrade, assert, downgrade,
assert), và thêm hai cột mới vào assertion exact-column-set trong `tests/test_db_models.py`.

Rollout:

1. Deploy migration + BE identity fields; FE cũ ignore additive fields.
2. Verify ID equality REST/SSE/history và `done-after-commit`.
3. Deploy FE ẩn sau internal flag.
4. Enable internal cohort, inspect error/duplicate/unauthorized/comment/coverage.
5. Ramp dần; UI và export có kill switch riêng.
6. Không bắt buộc backfill. Khuyến nghị chỉ hiện controls cho message có `agent_run_id` để tránh trộn
   fully-attributed event với historical answer không rõ config.

Rollback: tắt FE flag trước, tắt export riêng, chỉ rollback BE sau khi client không cần fields mới.
Trong operational rollback nên giữ tables để không mất evidence; downgrade migration chỉ dùng khi đã
backup và chấp nhận xóa dữ liệu.

## 12. Test matrix

### Backend

- REST normal/fallback/interrupt trả đúng nullable/non-null IDs; fallback reply persist với
  `agent_run_id` và run `failed`, bị từ chối `404` khi rate.
- SSE token/reset/done persist final text một lần, `messages.agent_run_id` bằng run router đã start,
  ID khớp history.
- Persistence fail không phát `done`; disconnect không tạo empty message, run status là `failed`
  (recorder sẵn có), không phải `completed`.
- Row `agent_runs` / `agent_run_steps` giống hệt hôm nay với turn không ai rate (các test
  `tests/api/agent/test_agent_runs*.py` và trace-detail vẫn xanh không đổi).
- `429` sau `feedback_rate_limit_max` event trong một window, với subject authenticated lẫn
  `anon:`-namespaced; counter tăng cả khi request bị từ chối (`404`/`409`).
- JWT/anonymous happy path; foreign/unknown/user-role/incomplete đều cùng `404`.
- Replay/conflict/concurrent race; set/replace/detail/retract/no-op/invalid transition.
- Enum, conditional fields, trim, Unicode 500-char boundary.
- Langfuse off/outage vẫn local success; feedback không gọi memory.
- Claim update conversation/run/event cùng transaction (`reassign_user` mở rộng; claim một
  conversation chưa có feedback vẫn chuyển row `agent_runs` của nó); erasure xử lý local/provider.
- Migration upgrade/downgrade và model parity SQLite/Postgres.

### Frontend

- SSE parser nhận message/run IDs; `send`/`resume`/`retry` map đúng bubble.
- Hydration giữ server ID và feedback state.
- Không controls ở user/streaming/empty/interrupted/failed.
- Save/retract/change/detail/skip/close; double-click/retry giữ ID.
- Optimistic rollback không block chat; keyboard/focus/aria/live/dialog/touch đều đúng.
- Mobile/narrow, en/vi, long strings, reduced motion và text-only comment an toàn.

### End-to-end acceptance

1. Send message, capture SSE message ID; reload thấy cùng ID.
2. Rate helpful; reload vẫn pressed.
3. Đổi not helpful, thêm reason; reload giữ effective state.
4. Retract; reload không thumb nào selected.
5. Replay request không tăng event count.
6. Dùng ID user khác không lộ existence và không đổi state.
7. Tắt Langfuse, flow vẫn thành công.

## 13. Definition of done

- Mọi invariant section 1 có test enforce.
- OpenAPI được regenerate và SSE mirror đổi trong cùng change.
- Raw feedback text không vào log, trace mặc định hay memory.
- SQL feedback vẫn dùng được khi tracing off.
- UI state survive reload và accessible bằng tiếng Anh/Việt.
- Rollout, rollback, retention owner/window, erasure và metrics được document.
- Memory-candidate/product-learning vẫn là follow-up tách riêng có gate.
