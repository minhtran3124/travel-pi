---
slug: user-feedback-learning
doc: research
lang: vi
status: complete
created: 2026-07-21
---

# Deep research — Học từ feedback của user trong LLM graph

## Executive answer

**Không nên tạo một specialist `learning_agent` để supervisor route qua sau mỗi câu hỏi.**
Supervisor của travel-pi nên tiếp tục làm đúng một việc: hiểu travel intent và chuyển sang
planner/concierge/journal/booking/budget. Learning là một năng lực **cross-cutting**, chạy ở hot
path cho lệnh rõ ràng như “hãy nhớ/đừng nhớ”, và chạy background cho correction hoặc tín hiệu ngầm.

**LLM không nên có toàn quyền quyết định cái gì được lưu.** Trách nhiệm đúng là:

1. Product policy định nghĩa loại dữ liệu được nhớ, scope, retention, consent và dữ liệu cấm.
2. Code/policy engine áp rule deterministic về explicit/implicit signal, confidence, conflict và
   quyền create/update/delete.
3. LLM chỉ đọc trajectory và tạo `MemoryCandidate` có cấu trúc.
4. User hoặc human reviewer quyết định case mơ hồ, nhạy cảm, và mọi thay đổi hành vi dùng chung.

Đây cũng là hướng mà LangGraph/LangMem mô tả: memory có thể được ghi trong hot path hoặc bằng một
background task; nó không bắt buộc là một agent được supervisor điều phối
([LangGraph memory overview](https://docs.langchain.com/oss/python/concepts/memory),
[LangMem concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)).

## 1. Trước hết phải tách ba nghĩa của “learn”

| Nghĩa | Ví dụ | Cập nhật ở đâu | Có tự động trong request graph? |
|---|---|---|---|
| **Per-user adaptation** | Minh thích ghế cửa sổ, ăn chay, không ở hostel | Long-term Store theo `user_id` | Có thể hot path/background |
| **Product/system improvement** | Planner thường quên hỏi số khách; prompt/tool/routing cần sửa | Trace → dataset → eval → prompt/code version mới | Không; chạy offline có gate |
| **Model-weight learning** | Fine-tune một model từ tập feedback lớn | Training pipeline riêng của model provider/team ML | Tuyệt đối không online theo từng turn |

Nếu user nói “đừng gợi ý hostel cho **tôi**”, đó là user memory. Nếu 300 users cùng complain vì
planner không giải thích trade-off, đó là evidence để sửa product/prompt sau eval. Hai luồng không
được ghi chung vào một namespace và một feedback đơn lẻ không được sửa system prompt production.

## 2. Travel-pi thực sự đang chạy thế nào

### 2.1 Answer graph không có memory agent/node ở cuối

Topology hiện tại là:

```text
START → load_context → summarize → supervisor
                                  ↓
                    planner | concierge | journal | booking | budget
                                  ↓
                           dispatch_next → reflection → END
```

`build_graph()` không đăng ký `extract_memory`; sau compile nó chỉ gắn model handle
`compiled.extract_memory_llm` để router dùng ngoài graph
([graph.py](../../apps/api/app/agents/graph.py#L122-L175)). `nodes.py` cũng ghi rõ extraction đã
chuyển sang post-turn background runner
([nodes.py](../../apps/api/app/agents/nodes.py#L1-L15)). Vì vậy câu trả lời trực tiếp cho thắc mắc
là: **supervisor không đi qua một “con agent học feedback”.**

### 2.2 Write path hiện tại là background extraction

- `/agent/chat` hoàn tất graph, persist assistant reply, rồi schedule `run_memory_extraction`
  bằng `BackgroundTasks` ([agent.py](../../apps/api/app/routers/agent.py#L357-L373)).
- `/agent/stream` drain SSE, lấy final state vào `sink`, rồi chạy `BackgroundTask` sau response
  ([agent.py](../../apps/api/app/routers/agent.py#L456-L481)).
- Runner gọi một fast LLM, nhận `preferences`, `instructions`, `episodes`, rồi upsert thẳng vào
  Store ([extraction_runner.py](../../apps/api/app/memory/extraction_runner.py#L23-L107)).
- Extractor chỉ nhìn exchange cuối cùng và parse JSON thủ công
  ([extractor.py](../../apps/api/app/memory/extractor.py#L32-L128)).
- Prompt v5 yêu cầu chỉ lấy durable signals và dùng canonical keys
  ([memory_extraction/v5.md](../../apps/api/app/prompts/memory_extraction/v5.md)).

### 2.3 Read path hiện tại

Long-term Store tách namespace theo user:

- `("users", user_id, "prefs")` — semantic facts/preferences.
- `("users", user_id, "procedural")` — standing instructions của riêng user.
- `("users", user_id, "episodes")` — outcome của trip cũ.

Store là key-addressed: cùng key thì overwrite; có semantic index trên field `text`
([store.py](../../apps/api/app/memory/store.py#L104-L216)). `load_context_node` đọc profile,
instructions và preferences vào state/prompt trước supervisor
([nodes.py](../../apps/api/app/agents/nodes.py#L86-L130)). Đây là personalization bằng external
memory, không phải model tự train lại weights.

### 2.4 Những gì code hiện tại chưa có

1. Chưa có `FeedbackEvent` chuẩn: thumbs up/down, reason, correction, accept/reject, edit,
   click/save/book/cancel chưa được lưu như evidence bất biến.
2. LLM extractor đang vừa tạo candidate vừa quyết định write; chưa có policy/verifier độc lập.
3. Memory chưa có provenance, confidence, source message/run, sensitivity, TTL hay trạng thái
   `proposed/disputed/superseded`.
4. Chỉ upsert; chưa có first-class correction/delete/forget flow và conflict resolution.
5. Prompt JSON + defensive parser không phải structured output schema; parse fail thì silent no-op.
6. FastAPI in-process background task không durable: process chết sau reply có thể mất extraction;
   turn kế tiếp quá nhanh có thể chưa thấy memory mới.
7. `allow_memory_write` hiện luôn `True` trong resolved context
   ([context.py](../../apps/api/app/agents/context.py#L89-L97)); chưa có user-facing opt-out.
8. `WORKFLOW.md` vẫn mô tả topology cũ có terminal `extract_memory`, trong khi code hiện tại đã
   chuyển background. Khi implement feature nên sửa docs cùng lúc.

## 3. So sánh các kiến trúc

| Option | Cách chạy | Ưu điểm | Vấn đề | Decision |
|---|---|---|---|---|
| A. Supervisor route sang `learning_agent` | Learning là một travel intent/sub-agent | Dễ vẽ graph | Có thể bị route miss; tăng latency; trộn domain routing với data governance | **Reject** |
| B. Terminal node trong graph | Mọi path đều qua extractor trước `END` | Deterministic, checkpoint-visible | User phải chờ thêm LLM call; interrupt/error path phức tạp | Không quay lại |
| C. Specialist tự gọi memory tool | Planner/journal tự quyết định ghi | Memory có ngay, user thấy rõ | Tool-use discretionary, policy lệch giữa agent, ảnh hưởng task chính | Chỉ dùng cho explicit command |
| D. Post-response background pipeline | Emit trajectory → extract → verify → write | Không tăng reply latency; policy tập trung; dễ batch/consolidate | Eventual consistency; cần retry/idempotency | **Default** |
| E. Hybrid C + D | Explicit hot path, implicit/background | Cân bằng immediacy và quality | Hai write path cần cùng policy/idempotency | **Recommended** |

LangMem gọi hai cơ chế này là conscious/hot-path và subconscious/background. Hot path cho update
ngay nhưng thêm latency và buộc agent multitask; background tách logic và không chặn response
([LangMem concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/),
[background quickstart](https://langchain-ai.github.io/langmem/background_quickstart/)). Memory
tool của LangMem cũng hỗ trợ create/update/delete và cho phép app giới hạn actions — thêm bằng chứng
rằng quyền write phải được policy hóa, không chỉ prompt hóa
([Memory Tools API](https://langchain-ai.github.io/langmem/reference/tools/)).

## 4. Target architecture cho travel-pi

```text
ONLINE ANSWER PATH
User turn
  → load_context (active user memories)
  → supervisor → specialist → tools → reflection → reply
  ├─ explicit "remember/correct/forget" → deterministic policy → immediate user-memory write
  └─ emit immutable trajectory + FeedbackEvent
                                      │
                                      ▼
BACKGROUND USER-MEMORY PATH
Candidate extractor (LLM, structured output)
  → deterministic policy/verifier
  → conflict + scope + sensitivity gate
  → versioned MemoryRecord in the existing LangGraph Store
  → audit metric / optional "I remembered …" notification

OFFLINE PRODUCT-LEARNING PATH
Traces + feedback events
  → sampling / human annotation / root-cause attribution
  → regression dataset
  → candidate prompt/tool/routing change
  → offline eval + A/B + approval
  → versioned deploy (never direct self-edit in production)
```

Memory pipeline là service/worker cross-cutting. Có thể implement nó bằng plain functions hoặc một
nhỏ `StateGraph` riêng nếu cần retry/branching, nhưng **không đặt nó vào danh sách specialist mà
supervisor travel route tới**.

## 5. Ai quyết định học cái gì?

### Decision stack

| Tầng | Quyết định | Không được quyết định |
|---|---|---|
| Product policy | Category, scope, consent, retention, sensitive denylist, promotion threshold | Nội dung candidate cụ thể |
| Deterministic code | Signal strength, conflict precedence, allowed operation, idempotency | Tự suy diễn meaning từ free text |
| LLM extractor | Candidate type/key/value/scope + evidence span + proposed operation | Bypass policy hoặc sửa prompt global |
| User | Confirm/correct/forget, view/edit/delete, turn personalization off | Vô tình thay đổi behavior cho mọi user |
| Human/eval gate | Ship shared procedural/prompt/tool/routing changes | Ghi preference cá nhân thay user |

Supervisor có thể đưa metadata routing (`current_flow`, specialist, tool trace) vào event để giúp
root-cause attribution, nhưng không làm memory gate.

## 6. Event và candidate model đề xuất

`FeedbackEvent` nên immutable:

```json
{
  "event_id": "fb_...",
  "user_id": "u_...",
  "trip_id": "trip_...",
  "conversation_id": "conv_...",
  "run_id": "run_...",
  "target_message_id": "msg_...",
  "node": "planner",
  "tool_call_ids": ["call_..."],
  "signal": "correction",
  "explicitness": "explicit",
  "value": "I prefer aisle, not window",
  "created_at": "...",
  "prompt_versions": {"supervisor": 6, "planner": 7},
  "model_config_version": "..."
}
```

`MemoryCandidate`/`MemoryRecord` nên có tối thiểu:

```json
{
  "kind": "preference",
  "key": "seat",
  "text": "Traveller prefers an aisle seat",
  "scope": {"level": "user", "destination": null, "travel_group": null},
  "operation": "update",
  "confidence": 0.98,
  "status": "active",
  "learned_from": "explicit_correction",
  "evidence_event_ids": ["fb_..."],
  "source_message_ids": ["msg_..."],
  "sensitivity": "normal",
  "supersedes": "memory_old_id",
  "last_confirmed_at": "...",
  "expires_at": null
}
```

Không nhất thiết phải thêm toàn bộ field vào semantic index; chỉ `text` cần embedding. Metadata dùng
cho audit, filter, conflict và UI. Profile nhỏ/canonical nên direct-key lookup; episodes mới cần
semantic search. LangGraph Store tổ chức memory bằng namespace + key và cho search cross-session
([LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence/)).

## 7. Write policy cụ thể

| Signal | Ví dụ | Action |
|---|---|---|
| Explicit remember | “Nhớ là mình ăn chay” | Upsert `prefs/diet` ngay; acknowledge |
| Explicit standing rule | “Luôn hiển thị giá bằng EUR” | Upsert user `procedural/price_currency` ngay |
| Explicit correction | “Không, mình thích aisle chứ không phải window” | New explicit wins; old record `superseded`; preserve evidence |
| Explicit forget | “Quên việc mình thích ANA đi” | Delete/tombstone exact memory; acknowledge |
| Contextual preference | “Đi với con nhỏ thì chỉ chọn khách sạn có thang máy” | Scope theo `travel_group=family`; không biến thành global rule |
| Thumb-down không reason | 👎 | Lưu feedback event; **không suy diễn** preference |
| One click/book | Chọn hotel boutique một lần | Episode/outcome evidence; chưa promote thành durable preference |
| Repeated consistent behavior | Chọn boutique 3 trip khác nhau | Tạo `proposed` candidate; confirm hoặc threshold-gated promotion |
| Silence/no click | Không bấm suggestion | Không coi là dislike; `not_observed != negative evidence` |
| Sensitive data | Passport/card/health detail | Không đưa vào semantic memory; dùng domain store phù hợp hoặc reject |

Conflict precedence đề xuất:

```text
new explicit correction
  > explicit statement
  > repeated cross-session behavior
  > one-off implicit behavior
  > model inference
```

Nếu hai facts có thể cùng đúng theo context, tách scope thay vì overwrite. Nếu scope không rõ, giữ
`disputed/proposed` và hỏi user. Không dùng float confidence của LLM như sự thật tuyệt đối; confidence
chỉ là một input cho deterministic gate.

## 8. Product-level learning từ feedback

User memory và system behavior phải có firewall. Ví dụ user nói “câu trả lời này dài quá” có thể là:

- preference cá nhân: user nhiều lần yêu cầu concise → `procedural` theo user;
- defect của product: nhiều negative traces cùng rubric → sửa communication prompt;
- lỗi dữ liệu/tool: giá sai → sửa service/tool, không sửa prompt;
- lỗi routing: supervisor chọn concierge thay vì budget → thêm routing eval/case.

Do đó offline pipeline phải attribute feedback đến `supervisor | specialist | tool | retrieval |
memory | UX`, rồi mới tạo candidate change. LangMem có prompt optimizer nhận nhiều trajectories cùng
feedback, nhưng output chỉ nên là một candidate được eval/version-control, không tự flip active
prompt ([Prompt optimization guide](https://langchain-ai.github.io/langmem/guides/optimize_memory_prompt/),
[multi-prompt optimization](https://langchain-ai.github.io/langmem/guides/optimize_compound_system/)).
LangSmith mô tả loop production trace → online monitoring → failing cases vào dataset → offline
experiment → redeploy; thumbs-down có thể được đưa vào annotation queue thay vì dùng trực tiếp làm
training truth ([evaluation lifecycle](https://docs.langchain.com/langsmith/evaluation),
[annotation queues](https://docs.langchain.com/langsmith/annotation-queues)). Travel-pi có thể áp
dụng pattern này bằng DeepEval + Langfuse hiện có, không cần adopt LangSmith.

## 9. User control và privacy

Minimum product contract nên có:

- “What I remember” — xem memory active và evidence/source giải thích được.
- Edit, forget one, clear all, disable future writes, và temporary/no-memory chat.
- Thông báo khi explicit command tạo/update/delete memory.
- Sensitive denylist; không infer protected/sensitive traits.
- Retention/expiry cho episode cũ; audit log cho write/delete; cross-user isolation tests.

OpenAI's current memory controls là một useful product precedent: user có thể xem, sửa/xóa memory,
tắt memory, và sensitive information không nên được proactively remembered nếu user không yêu cầu
([OpenAI Memory FAQ](https://help.openai.com/en/articles/8590148-personalization-and-data-controls-faq)).
Đây là pattern thiết kế, không phải tuyên bố rằng travel-pi đã đáp ứng một regulatory regime.

## 10. Evaluation gates

### User-memory quality

- Candidate precision/recall theo từng kind và explicitness.
- False-write rate, đặc biệt một-off và sensitive data.
- Correct update/delete/conflict/scope rate.
- Cross-user leakage = 0 trong adversarial tests.
- Retrieval relevance và “memory used correctly”, không chỉ “memory found”.
- User correction/forget rate sau khi memory được dùng.

### Runtime/ops

- Reply p50/p95 không tăng ở background path.
- Extraction completion, retry, dead-letter và idempotency rate.
- Eventual-consistency lag đến khi memory có thể recall.
- Cost/token per extracted candidate và per accepted memory.

### Product improvement

- Offline regression theo flow/specialist trước khi prompt/tool change được ship.
- Pairwise quality và task success, không chỉ thumbs-up tổng.
- A/B memory on/off hoặc policy version A/B với guardrail về safety/privacy.

Launch gate nên ưu tiên **precision hơn recall**: bỏ sót một preference thường chỉ làm câu trả lời ít
personalized; ghi sai một preference làm user mất trust. Mọi negative production trace quan trọng
nên trở thành regression case có thể chạy lại.

## 11. Phased roadmap

### Phase 0 — Explicit feedback foundation

- Capture immutable feedback events + trace/run/message/node/tool provenance.
- Hỗ trợ `remember`, `correct`, `forget` với canonical keys và acknowledgement.
- Không enable implicit write.

### Phase 1 — Safe background candidates (shadow mode)

- Đổi extractor sang structured schema.
- LLM tạo candidate; policy/verifier quyết định `reject/propose/activate`.
- Ghi confidence, evidence, scope, sensitivity và conflict action; chưa đưa proposed memory vào prompt.

### Phase 2 — Controlled personalization

- Enable high-confidence low-risk background writes.
- Repeated implicit signals mới được promote; ambiguous case xin confirm.
- Thêm memory management UI/API, opt-out, retention và durable worker/retry.

### Phase 3 — Offline system-learning loop

- Curate negative/positive trajectories vào DeepEval datasets.
- Root-cause attribution theo graph node/tool/prompt version.
- Generate candidate prompt changes, regression eval, human approval, versioned rollout.

### Phase 4 — Chỉ khi data đủ lớn

- Cân nhắc offline fine-tuning/ranker training nếu memory/prompt/tool fixes không đủ và consent/data
  governance cho phép. Không bao giờ update model weights từ một live user turn.

## 12. Mapping vào repo nếu triển khai

| Concern | Existing seam | Likely work |
|---|---|---|
| Candidate extraction | `memory/extractor.py` | Structured candidate schema + evidence spans |
| Central policy/write | `memory/extraction_runner.py` | Separate extractor from verifier/policy; idempotency/conflict |
| Long-term records | `memory/store.py` | Metadata, update/delete/tombstone, scoped keys |
| Scheduling | `routers/agent.py` background calls | Emit event, durable job handoff later; keep off critical path |
| Explicit hot path | memory tool/domain command | Reuse the same policy service, never a second policy |
| Feedback capture | schemas/router/service/repository + FE | New contract/schema is a separate high-risk implementation plan |
| Recall | `load_context_node`, `recall_past_trips` | Read only active, in-scope, non-expired memories |
| Offline learning | `apps/api/eval/`, Langfuse traces | Feedback datasets, node attribution, regression reports |
| User controls | `apps/web` + API | View/edit/delete/disable/temporary chat |

**Repository-specific recommendation:** keep the current hand-built `StateGraph` and existing
`BaseStore`; do not add LangMem merely to name this pattern. First harden the one existing write
seam. A new dependency is justified only if conflict/consolidation/versioning needs exceed what this
small structured policy can safely handle.

## Final decision

```text
Supervisor decides: “request này cần travel specialist nào?”
Memory extractor proposes: “exchange này có durable signal nào?”
Policy engine decides: “candidate này có được create/update/delete không?”
User/human decides: “case mơ hồ/nhạy cảm/global change có được chấp nhận không?”
Offline eval decides: “system change này có đủ tốt để deploy không?”
```

Vì vậy, câu trả lời ngắn nhất là: **không phải một con agent mà supervisor bắt buộc đi qua; nên là
một pipeline background riêng, cộng hot-path cho explicit feedback. LLM đề xuất cái cần học, còn
policy + user controls mới có quyền quyết định cái được lưu.**
