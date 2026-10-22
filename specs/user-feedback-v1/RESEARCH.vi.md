---
slug: user-feedback-v1
doc: research
lang: vi
status: complete
created: 2026-07-21
source_of_truth: false
translation_of: RESEARCH.md
---

> **Ghi chú ngôn ngữ:** Đây là bản dịch tiếng Việt. Bản tiếng Anh
> [RESEARCH.md](./RESEARCH.md) là nguồn chuẩn.

# Nghiên cứu chuyên sâu — Nền tảng Feedback Event

## Quyết định tổng quan

Travel-pi nên thêm một pipeline feedback **append-only, do product sở hữu**, không phải một learning
agent mà supervisor phải đi qua. V1 ghi nhận thumbs up/down, lý do có cấu trúc và comment tùy chọn,
gắn với đúng assistant message đã hoàn tất. V1 không ghi memory, sửa prompt hay train model.

Thay đổi quan trọng nhất không phải hai nút thumb, mà là một định danh server ổn định cho cùng câu trả
lời xuyên suốt REST, SSE, SQL history, tracing và browser. Hiện invariant này chưa tồn tại: bubble live
dùng UUID phía client, history sau reload dùng UUID trong DB, còn SSE `done` được gửi trước khi
assistant message được persist.

Nền tảng đề xuất:

```text
bắt đầu trả lời
  → server tạo agent_run_id + assistant_message_id
  → graph chạy và stream draft
  → persist nội dung cuối bằng assistant_message_id
  → SSE done / REST response trả assistant_message_id

user đánh giá câu trả lời đã hoàn tất
  → kiểm tra ownership + role + transition + idempotency
  → append FeedbackEvent bất biến vào SQL
  → trả effective feedback state
  └─ tùy chọn export async sang Langfuse score / offline eval queue
```

SQL là source of truth. Langfuse chỉ là projection tùy chọn cho evaluation và diagnostics.

## 1. Các câu hỏi đã nghiên cứu

1. Travel-pi đang persist gì, và stable answer identity bị đứt ở đâu?
2. Feedback nên liên kết với conversation, message, graph run, trace, prompt version và tool/model
   provenance thế nào?
3. Rating nên là state mutable hay evidence bất biến?
4. Retry, double-click, đổi rating và retract hoạt động ra sao?
5. JWT và anonymous identity phải enforce object ownership thế nào?
6. Dữ liệu nào thuộc product DB, Langfuse và LangGraph memory?
7. Interaction FE tối thiểu nào vừa accessible vừa hữu ích cho evaluation?
8. Cần retention, deletion, abuse và observability controls nào?

## 2. Audit backend hiện tại

### 2.1 Message có durable ID nhưng answer API bỏ qua ID đó

`Message` đã có UUID primary key, nhưng chỉ lưu conversation, role, content và tool calls
([message.py](../../apps/api/app/db/models/message.py#L9-L17)). Repository trả về `Message` vừa tạo
([conversation.py](../../apps/api/app/repositories/conversation.py#L104-L123)), nhưng `/agent/chat`
bỏ return value ở cả normal và fallback path
([agent.py](../../apps/api/app/routers/agent.py#L278-L308),
[agent.py](../../apps/api/app/routers/agent.py#L344-L359)). Vì vậy `ChatResponse` chưa có assistant
message ID ([agent.py](../../apps/api/app/schemas/agent.py#L55-L77)).

### 2.2 Streaming đang báo thành công trước persistence

Mapper phát `done` với conversation/flow/suggestions/language/trip nhưng không có message ID
([events.py](../../apps/api/app/streaming/events.py#L90-L107)). Persistence wrapper pass-through mọi
event rồi chỉ append assistant message sau khi upstream iterator kết thúc hoàn toàn
([persistence.py](../../apps/api/app/streaming/persistence.py#L32-L80)). Hệ quả:

- browser có thể nhận `done` nhưng bước persist sau đó thất bại;
- `done` không thể chứa database message ID mới;
- rating ngay sau `done` không có target chuẩn;
- abandoned stream không tạo assistant row, nhưng semantics này chưa được model hóa rõ.

Wrapper đã xử lý `reset`, nên đây là seam đúng để chặn terminal success, persist final content rồi phát
lại `done` có server message ID.

### 2.3 History có ownership check, nhưng creation có sharp edge

Request authenticated dùng JWT subject và bỏ fallback ID giả mạo; anonymous dùng ID phía client
([agent.py](../../apps/api/app/routers/agent.py#L87-L98)). History kiểm tra conversation owner và trả
empty cho foreign/unknown conversation ([agent.py](../../apps/api/app/routers/agent.py#L514-L546)).

Tuy nhiên, `ensure_conversation` chấp nhận conversation ID do client chọn mà không xác minh owner của
row đã tồn tại ([conversation.py](../../apps/api/app/repositories/conversation.py#L36-L68)). Feedback
endpoint không được kế thừa hành vi này. OWASP yêu cầu object-level authorization cho mọi endpoint
nhận object ID; UUID khó đoán không phải authorization
([OWASP BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)).

### 2.4 Tracing chưa correlate được rating với đúng một answer

Langfuse metadata mới chỉ có user và trip/session
([observability.py](../../apps/api/app/agents/observability.py#L78-L92)). Chưa snapshot conversation,
response message, graph run, specialist/tool outcome, model, prompt version hay release. Prompt/model
có thể đổi về sau, nên lấy “current config” lúc user rate message cũ là sai. Provenance phải được chụp
ngay khi answer chạy.

### 2.5 Feedback độc lập với memory

Memory extraction đang chạy post-response trên mọi completed answer
([agent.py](../../apps/api/app/routers/agent.py#L360-L373),
[agent.py](../../apps/api/app/routers/agent.py#L456-L481)). Feedback endpoint mới không được gọi nó.
Thumbs-down nghĩa là “câu trả lời này không hữu ích”, không đáng tin để suy ra “hãy lưu điều ngược lại
thành preference lâu dài”. Đây là safety gate cốt lõi từ
[nghiên cứu feedback-learning tổng quát](../user-feedback-learning/RESEARCH.md).

## 3. Audit frontend hiện tại

### 3.1 Live và hydrated message dùng hai nguồn identity khác nhau

`ChatMessage.id` là UUID render do client tạo trong live stream
([useAgentStream.ts](../../apps/web/src/components/chat/useAgentStream.ts#L44-L51),
[useAgentStream.ts](../../apps/web/src/components/chat/useAgentStream.ts#L283-L297)). Sau reload,
history map backend message ID vào cùng property
([useAgentStream.ts](../../apps/web/src/components/chat/useAgentStream.ts#L204-L219)). Rating live vì
thế sẽ gửi một ID mà backend chưa từng biết.

FE cần tách `renderId` và `serverMessageId` nullable, kèm delivery state. Chỉ message `complete` có
`serverMessageId` mới được feedback.

### 3.2 Ba completion path phải dùng cùng contract

`send`, `resume` và `retry` parse `done` ở ba nhánh riêng. Cả ba phải set server message ID. Bespoke
SSE mirror cũng phải đổi đồng thời với BE vì không được generate từ OpenAPI
([parseSSE.ts](../../apps/web/src/lib/stream/parseSSE.ts#L90-L117)).

### 3.3 UI seam hiện tại đã đủ

Assistant bubble render trong `MessageList`, tách khỏi markdown do user/model tạo
([MessageList.tsx](../../apps/web/src/components/chat/MessageList.tsx#L40-L73)). Controls nên nằm dưới
bubble, không nằm trong markdown. `Modal` hiện có đã xử lý focus entry, Tab trap, Escape và focus
restore ([Modal.tsx](../../apps/web/src/components/ui/Modal.tsx#L16-L89)). Copy en/vi nằm trong
namespace `Chat` hiện hữu.

Icon button chung rộng 34px, trong khi WCAG 2.2 AA yêu cầu target tối thiểu 24×24 CSS px hoặc spacing
đủ; 44×44 là mức enhanced
([W3C target-size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum),
[W3C target-size enhanced](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced)). Với chat
compact dùng nhiều trên touch, nên dùng hit area 40–44px dù glyph vẫn nhỏ.

## 4. Evidence bên ngoài và hệ quả thiết kế

### Feedback là evaluation record gắn với execution

LangSmith gắn feedback vào trace/root hoặc child run
([LangSmith feedback guide](https://docs.langchain.com/langsmith/attach-user-feedback),
[feedback format](https://docs.langchain.com/langsmith/feedback-data-format)). Langfuse model hóa
end-user feedback thành typed score gắn với trace, observation, session hoặc dataset run, có comment
tùy chọn ([Langfuse scores](https://langfuse.com/docs/evaluation/scores/overview),
[score data model](https://langfuse.com/docs/evaluation/scores/data-model)).

Hệ quả: `assistant_message_id` là product identity; `agent_run_id`/`trace_id` nullable là diagnostic
provenance. Provider trace ID không thay thế product record.
LangChain cho phép truyền run identifier qua `RunnableConfig`, còn Langfuse hỗ trợ
predetermined/deterministic trace identifiers cho distributed correlation
([RunnableConfig reference](https://reference.langchain.com/python/langchain-core/runnables/config/RunnableConfig),
[Langfuse trace IDs](https://langfuse.com/docs/observability/features/trace-ids-and-distributed-tracing)).
Vì vậy nên mint correlation IDs lúc answer bắt đầu thay vì cố tìm lại khi feedback đến.

### Idempotency là request identity, không phải dedup theo content

IETF `Idempotency-Key` draft mô tả POST/PATCH retry-safe: key không được tái dùng cho payload khác,
server có thể fingerprint payload, completed retry trả prior result, concurrent duplicate phải được xử
lý rõ ([IETF draft](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header)).

Hệ quả: một client event UUID phải sống qua network retry. Cùng actor/key/fingerprint trả event cũ;
cùng actor/key với payload khác trả `409`. Đổi up→down tạo key và event mới. Không được để generic
middleware tự tạo key mới ở mỗi lần retry.

### Privacy áp dụng cho text “Cho chúng tôi biết thêm”

Purpose limitation, data minimization và storage limitation yêu cầu chỉ thu thập và giữ dữ liệu cần
thiết ([European Commission GDPR principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en)).
Retention và deletion phía Langfuse cũng phải được quản lý riêng
([Langfuse retention](https://langfuse.com/docs/administration/data-retention),
[Langfuse deletion](https://langfuse.com/docs/administration/data-deletion)).

Hệ quả: ưu tiên reason code hơn prose; comment optional và bounded; raw text không vào log/memory;
retention và erasure bao phủ SQL lẫn exported score/trace.

### Toggle semantics phải rõ

WAI yêu cầu button có accessible name, hỗ trợ `aria-pressed`, Enter/Space và label ổn định
([WAI button pattern](https://www.w3.org/WAI/ARIA/apg/patterns/button/)). Modal phải đưa focus vào
trong, trap focus, đóng bằng Escape và trả focus
([WAI modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)).

Hệ quả: label “Hữu ích” và “Không hữu ích” không đổi; `aria-pressed` biểu diễn selection. Polite live
region báo saved/error/retracted. Negative-details dialog là tùy chọn và không chặn việc lưu rating.

## 5. So sánh phương án kiến trúc

| Quyết định | Phương án | Lợi ích | Rủi ro | Chọn |
|---|---|---|---|---|
| Source of truth | Chỉ Langfuse | Setup nhanh | Coupled với outage/retention provider | Loại |
| Source of truth | SQL + Langfuse projection async | Product sở hữu | Cần export seam | **Chọn** |
| Rating history | Mutable row | Đọc đơn giản | Mất lịch sử đổi/retract | Loại |
| Rating history | Append-only + folded state | Audit và reversible | Read model phức tạp hơn chút | **Chọn** |
| Provenance | Lấy current config lúc feedback | Đơn giản | Sai lịch sử | Loại |
| Provenance | Snapshot lúc answer | Attribution chính xác | Thêm run lifecycle | **Chọn** |
| Stream identity | Insert empty message sớm | Có ID sớm | Pollute history khi abort | Loại |
| Stream identity | Mint ID sớm, insert final trước `done` | Stable, không row rỗng | Đổi ordering | **Chọn** |
| Negative detail | Bắt buộc reason | Dữ liệu giàu | Tăng abandonment | Loại |
| Negative detail | Lưu thumb ngay, detail optional | Ít friction | Một số event sparse | **Chọn** |
| Learning V1 | Ghi memory trực tiếp | Adapt nhanh | Hiểu sai signal | Loại |
| Learning V1 | Evidence only | Audit được | Learning đến sau | **Chọn** |

## 6. Semantics signal đề xuất cho v1

V1 chỉ có một rating dimension: `helpful` (+1), `not_helpful` (-1), và `retract` (không active
rating). Negative reason optional gồm `incorrect`, `irrelevant`, `outdated`,
`did_not_follow_request`, `tool_or_data_problem`, `unsafe_or_inappropriate`, `other`.

Comment optional là qualitative evidence, không phải instruction cho memory. Correction,
remember/forget, implicit click/booking và admin annotation nên dùng typed event sau này, không nhồi
vào thumbs contract v1.

## 7. Identity, authorization và anonymous user

```text
JWT subject hoặc anonymous principal
  → assistant_message_id
  → Message tồn tại và role == assistant
  → Message.conversation_id
  → Conversation.user_id == effective actor
```

Unknown, user-role, foreign hoặc incomplete message đều trả cùng `404` không enumerate. Optional
`anonymous_user_id` chỉ là fallback principal hiện có khi không có JWT, không phải provenance đáng
tin. Request không được gửi `conversation_id`, trace, flow, model hay prompt như field authoritative.

Authenticated feedback có ownership mạnh. Anonymous ID hiện do client tự khai nên assurance yếu hơn.
V1 có thể giữ behavior anonymous hiện tại nhưng phải document gap, rate-limit abuse và reassign
feedback/run cùng transaction khi claim conversation. Signed anonymous session là hướng hardening.

## 8. Idempotency và event-state model

Mỗi logical action có `client_event_id` ổn định qua retries và server lưu canonical fingerprint.

| Tình huống | Kết quả |
|---|---|
| Action hợp lệ đầu tiên | `201`, append event |
| Cùng actor + key + fingerprint | replay `200`, không event mới |
| Cùng actor + key + fingerprint khác | `409` |
| Concurrent cùng key | một winner; loser replay winner |
| Helpful → not helpful | event `set` mới supersede event hiện tại |
| Rating hiện tại → retract | event `retract` mới supersede event hiện tại |

Khuyến nghị: retract khi không còn active rating trả idempotent no-op, vì UI state có thể stale giữa
nhiều tab. Chỉ persist event khi effective state thực sự thay đổi.

## 9. Privacy, retention và abuse controls

- Comment tối đa 500 Unicode chars, trim ngoài, reject control chars và render text-only.
- Không log comment, raw body, tool args hay correction.
- Tách structured reason khỏi free text.
- Rate-limit theo effective user và IP/device cho anonymous. OWASP coi unrestricted resource
  consumption là API risk và khuyến nghị request/rate limits rõ ràng
  ([OWASP API4](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/)).
- Chốt retention trước launch; erasure phải xử lý SQL lẫn provider projection.
- Không ghi comment vào LangGraph semantic memory.
- Không copy full trace; chỉ reference run và allowlisted provenance snapshot.

## 10. Evaluation và observability handoff

```text
SQL feedback event
  ├─ dashboard rating/reason/coverage
  ├─ Langfuse score best-effort theo trace/run
  └─ sampled negative trajectories → human annotation → regression dataset
                                           ↓
                               prompt/tool/routing candidate
                                           ↓
                               offline eval + approval + rollout
```

Langfuse hỗ trợ user feedback, human annotation, automated judge và analytics
([Langfuse evaluation overview](https://langfuse.com/docs/evaluation/overview)). Dùng feedback event ID
làm provider score ID để retry không duplicate.

Theo dõi accepted/retracted/replayed/conflicted/unauthorized/invalid/export-failed, p95 POST, coverage
trên completed answer, reason completion, rating-change rate và export lag. Không đưa comment vào metric
label hay log.

## 11. Các thay đổi quan trọng nhất theo thứ tự

1. Sửa answer identity và stream ordering.
2. Enforce message-level ownership và assistant role.
3. Persist SQL evidence bất biến, idempotent.
4. Capture provenance ngay lúc run.
5. Tách effective UI state khỏi immutable history.
6. Negative detail optional và accessible.
7. Giữ V1 hoàn toàn tách khỏi memory.

## 12. Khuyến nghị delivery

Triển khai theo sáu wave trong [PLAN.md](./PLAN.md): stable identity; run/feedback persistence;
ownership-safe API; optional observability export; contract mirror + accessible bilingual UI; rồi test
xuyên layer và rollout evidence.

Ship dark trước với DB/API nhưng chưa hiện buttons. Xác minh identity, ownership, idempotency và
persistence metrics. Sau đó bật internal cohort, small percentage, rồi toàn bộ. Không bắt đầu
memory-candidate cho đến khi review chất lượng event, privacy controls và evaluation sampling.

## Trả lời cuối cho câu hỏi ban đầu

Supervisor không nên route qua feedback-learning agent. Supervisor tiếp tục chọn travel specialist.
Feedback foundation ghi immutable evidence bên ngoài answer graph; background/offline pipeline về sau
mới biến evidence thành memory candidate hoặc product change, qua deterministic policy, evaluation và
user/human control.
