# Deep Comparison — 3 phương án tích hợp rubric-grader runtime (MIN-59)

**Slug:** `min-59-runtime-self-eval-loop` · **Issue:** MIN-59 · **Ngày:** 2026-07-10
**Câu hỏi:** Graft rubric-based self-eval loop vào đâu: (1) mở rộng `make_reflection_node`, (2) grader node riêng, (3) chờ migration `create_agent` + `RubricMiddleware` thật?
**Nguồn:** Explore agent (map `app/agents/`), research agent (deepagents docs/source/blog), `specs/agent-middleware-spike/` (DECISION + COMPARISON), `specs/subagent-create-agent-migration/` (PLAN status).

---

## 0. Ba phát hiện làm thay đổi bức tranh

1. **Reflection đã LÀ một LLM-judge chạy sau MỌI subagent.** `make_reflection_node`
   (`app/agents/nodes.py:120-174`) invoke LLM trên `[system, last_message]`, verdict là
   substring check `"REVISE"`, loop-back qua `Command(goto=state["current_flow"])`, bounded
   bởi `revisions >= max_revisions`. Nghĩa là **chi phí "một judge call mỗi lượt" đã được trả
   sẵn hôm nay** — câu hỏi không phải "có thêm judge không" mà là "nâng cấp judge hiện có hay
   thêm judge thứ hai".

2. **Phần tái dùng được của `RubricMiddleware` KHÔNG bị khóa vào middleware.**
   `deepagents>=0.6.5` export standalone: `GRADER_SYSTEM_PROMPT`, `GraderResponse` (Pydantic,
   per-criterion `{name, passed, gap}`), `GraderVerdict`, `RubricEvaluation` từ
   `deepagents.middleware.rubric`. Bản thân grader chỉ là một structured-output call — nhấc
   vào LangGraph node thuần được. Chỉ có *vòng lặp* (`jump_to="model"`, private state) là bị
   khóa vào `create_agent`.

3. **`RubricMiddleware` inject feedback bằng `HumanMessage`** (`name="rubric_grader"`,
   `additional_kwargs={"lc_source": "rubric_grader"}`). Repo này đã có bug đúng loại đó
   (reflection-humanmessage-language-flip — inject HumanMessage làm agent trả lời sai ngôn
   ngữ) và đã sửa bằng cách dùng `SystemMessage`. **Một literal port mang nguyên rủi ro đã
   từng trả giá.** Reflection hiện tại inject `SystemMessage("Please improve…")` — đúng bài học.

Cộng thêm bối cảnh migration: `subagent-create-agent-migration` đang **PLANNING** (high-risk,
pilot chỉ `journal`, có STOP gate, cần human confirm trước wave 1, chưa execute). Booking/concierge
— đích của MIN-59 — sẽ là những subagent migrate **cuối cùng**.

## 1. Cơ chế hiện có (điểm neo so sánh)

| Thành phần | Hiện trạng | Ref |
|---|---|---|
| Vị trí judge | Static edge `subagent → reflection` cho **cả 5** subagent; reflection route về `(*SUBAGENTS, END)` | `graph.py:137-146` |
| Verdict | Free-form, binary `"REVISE" in verdict.upper()` — không tiêu chí, không structured output | `nodes.py:151` |
| Loop bound | `revisions` counter trong state + `ctx.allow_reflection` / `ctx.max_revisions` (per-request, không rebuild graph) | `nodes.py:138-146` |
| Feedback injection | `SystemMessage` (né bug language-flip) | `nodes.py:158-170` |
| Model | `get_agent_llm("reflection")`, `reflection ∈ FAST_AGENTS` → model rẻ mặc định, override qua DB `agent_config` không cần schema change | `clients/llm.py`, `constants.py` |
| Prompt | `prompts/reflection/v1.md` qua registry (`active.yaml` per-name) | `prompts/registry.py` |
| Streaming | SSE chỉ stream token của `root ∈ SUBAGENTS`; draft bị loại được client drop qua `events.reset()` khi `msg_id` mới xuất hiện | `streaming/mapper.py:148-164` |

## 2. Bảng so sánh

| Chiều | (1) Mở rộng reflection node | (2) Grader node riêng (hotel/booking) | (3) Chờ migration → `RubricMiddleware` |
|---|---|---|---|
| **Marginal latency/cost khi `satisfied`** | ✅✅ ~0 — nâng cấp call judge ĐÃ tồn tại thành structured rubric call | ⚠️ +1 LLM call/lượt hotel-booking **nếu chạy cạnh reflection**; ✅ ~0 nếu grader *thay* reflection cho flow được grade | ⚠️ +1 call bên trong subagent, reflection vẫn chạy sau → judge kép nếu không tắt bớt |
| **Blast radius** | ⚠️ Sửa node battle-tested chạy trên CẢ 5 subagent — bug rubric-dispatch ảnh hưởng mọi flow | ✅ Cô lập: node mới + rewire 2 edge (booking, concierge); 3 subagent còn lại không đổi | ❌ Gated sau high-risk migration cả harness |
| **Tách bạch concern** | ❌ Trộn "critique tổng quát" với "rubric per-task" trong 1 node; toggle `allow_reflection` gate cả hai | ✅ Grading tách khỏi critique; toggle/config/metrics độc lập | ✅ Middleware đúng nghĩa, upstream maintain |
| **Đo lường A/B (yêu cầu #5-6 của issue)** | ⚠️ Metrics rubric lẫn với metrics reflection sẵn có; khó quy delta | ✅ Bật/tắt per-flow sạch; latency/cost/quality delta đo trực tiếp | ✅ `on_evaluation` callback + stream events có sẵn |
| **Structured verdict per-criterion** | Tự viết (có thể import `GraderResponse` của deepagents) | Import `GraderResponse`/`GRADER_SYSTEM_PROMPT` standalone — semantics upstream, không cần middleware | ✅ Có sẵn trọn gói |
| **Rủi ro regression hành vi đã tuned** | ⚠️ Trung — đổi prompt + parsing của node đang chạy prod trên mọi lượt | ✅ Thấp — reflection giữ nguyên cho flow không grade | ❌ Cao nhất — kế thừa toàn bộ rủi ro parity của migration (5 behavior battle-tested) |
| **Bug language-flip** | ✅ Kế thừa fix SystemMessage sẵn có | ✅ Tự kiểm soát injection (dùng SystemMessage) | ❌ Upstream inject `HumanMessage` — rủi ro đã biết, phải patch/wrap |
| **Tương tác 2 vòng lặp** | ✅ Một loop duy nhất, một cap duy nhất | ⚠️ Phải quyết: grader thay reflection cho flow grade (khuyến nghị) hay cần cap tổng hợp | ❌ Loop middleware (trong subagent) + loop reflection (ngoài graph) chồng nhau — cần thiết kế lại tầng |
| **Timeline** | ✅ Ngay | ✅ Ngay | ❌ Sau pilot `journal` + STOP gate + migrate booking/concierge (cuối hàng) — nhiều tuần/tháng |
| **Forward-compat với path B** | ⚠️ Logic rubric nằm trong node dùng chung, tách ra sau tốn công | ✅ Rubric prompt + `GraderResponse` schema chuyển thẳng vào `RubricMiddleware` khi migration đến booking/concierge | ✅ Là đích |
| **API stability** | ✅ Không phụ thuộc mới | ⚠️ Phụ thuộc `deepagents>=0.6.5` (beta) **chỉ nếu** import schema; tự định nghĩa Pydantic tương đương cũng được | ❌ Beta + `create_agent` middleware runtime còn trẻ |
| **Đúng đề bài MIN-59** ("scope 1-2 sub-agent rủi ro cao") | ⚠️ Về cấu trúc là toàn agent (dispatch nội bộ theo `current_flow`) | ✅✅ Đúng nguyên văn đề xuất của issue | ⚠️ Middleware gắn per-agent — được, nhưng sau migration |

## 3. Phân tích từng phương án

### (1) Mở rộng `make_reflection_node`

**Ưu:** rẻ nhất về latency (nâng cấp call sẵn có, không thêm call); một loop/một cap; kế thừa
mọi cơ chế đã tuned (SystemMessage injection, SSE reset, revisions counter, per-request toggle).

**Nhược (mang tính quyết định):** node này chạy trên **mọi** subagent — đưa rubric-dispatch
(`if current_flow in RUBRICS`) vào giữa một node battle-tested nghĩa là mọi flow đều đi qua code
mới; regression ở đây là regression toàn agent. Trộn hai concern làm hỏng chính mục tiêu của
prototype: **đo lường** — không tách được "delta do rubric" khỏi "reflection vốn có", và
`allow_reflection` không còn ngữ nghĩa sạch. Issue yêu cầu benchmark with/without → cần một
công tắc độc lập, phương án này không cho điều đó một cách tự nhiên.

### (2) Grader node riêng, scoped hotel/booking — **khuyến nghị**

**Thiết kế then chốt:** grader **thay thế** reflection cho flow được grade (rewire
`booking → grader`, `concierge → grader`; grader route `(booking|concierge, reflection?, END)`),
KHÔNG chạy cạnh reflection — nhờ đó marginal cost khi `satisfied` ≈ 0 so với hiện tại (vẫn một
judge call, chỉ là judge tốt hơn). Ba subagent còn lại giữ nguyên `→ reflection`.

**Ưu:** đúng nguyên văn scope đề xuất của MIN-59; blast radius nhỏ và cô lập; A/B sạch (toggle
per-flow qua `AgentContext`, giống pattern `allow_reflection`); model rẻ qua DB config có sẵn
(thêm `"grader"` vào `AGENT_CONFIG_NODES` + `FAST_AGENTS` — không schema change); rubric prompt
per-flow theo đúng pattern registry (`prompts/grader_booking/v1.md`…); có thể mượn semantics
upstream (`GraderResponse` per-criterion, 5 verdict) mà không đụng middleware; khi path B
migration tới booking/concierge, rubric + schema chuyển thẳng vào `RubricMiddleware` — đây là
**cầu nối** sang path B, giống vai trò PII guardrail trong DECISION A1.

**Nhược:** thêm surface graph (1 node + rewire 2 edge + destinations); phải quyết định rõ
grader-thay-reflection (nếu để cả hai thì +1 call và cần cap tổng); một ít wiring (constants,
agent_config seed, prompt dirs). Tất cả đều là chi phí một lần, kiểm soát được.

### (3) Chờ migration → `RubricMiddleware` literal

**Ưu:** đúng pattern upstream nhất; per-criterion grading + observability có sẵn; không tự
maintain vòng lặp; là trạng thái cuối theo verdict path B.

**Nhược (loại ở thời điểm này):** bị khóa sau migration high-risk mới ở giai đoạn PLANNING với
pilot là `journal` — booking/concierge (đích MIN-59) migrate cuối → prototype trễ vô hạn định;
upstream inject `HumanMessage` = rủi ro language-flip đã biết; loop middleware nằm *trong*
subagent trong khi reflection loop nằm *ngoài* — chồng hai judge nếu không thiết kế lại;
DECISION.md của spike đã kết luận DEFER cho chính lớp quyết định này. **Không phải "không bao
giờ" — là "chưa phải bây giờ":** phương án (2) giữ cửa mở để hội tụ về (3) khi migration đến nơi.

## 4. Rủi ro chung cần xử lý ở mọi phương án (đưa vào PLAN)

1. **Injection role:** feedback per-criterion phải là `SystemMessage` (bài học
   language-flip) — không copy nguyên `HumanMessage` của upstream.
2. **Cap tổng:** grader `max_iterations` (đề xuất 2 theo issue) phải chia sẻ/nhất quán với
   `revisions` để tổng số vòng lặp mọi loại bị chặn cứng.
3. **Streaming:** draft bị loại đã được client drop qua `events.reset()` (msg_id mới) — grader
   node đặt tên ngoài `SUBAGENTS` sẽ tự động không stream; verify lại với vòng revise.
4. **Grader verdict `grader_error`:** lỗi grader phải fail-open (giữ answer gốc, log) — không
   được chặn reply của user vì judge hỏng.
5. **Đo lường:** benchmark latency/cost + quality delta trên bộ eval MIN-58 (đã có baseline
   calibrated, PR #81) with/without toggle — đây là deliverable chính của prototype, không
   phải code.

## 5. Verdict

**Phương án (2) — grader node riêng, thay thế reflection cho flow hotel/booking.** Nó là điểm
duy nhất thỏa đồng thời: đúng scope đề bài, đo A/B sạch (mục đích tồn tại của prototype), blast
radius nhỏ, marginal cost ≈ 0 khi satisfied, né bug đã biết, và là cầu nối tự nhiên sang
`RubricMiddleware` khi path B migration chạm tới booking/concierge.

Phương án (1) chỉ nên chọn nếu ưu tiên tuyệt đối là "ít file đụng nhất" và chấp nhận đo lường
nhiễu. Phương án (3) là đích hội tụ dài hạn, không phải điểm khởi đầu của prototype này.

---

# Phụ lục A — Phương án 3 "đúng chuẩn từ đầu": phân tích toàn diện

**Câu hỏi:** nếu chấp nhận đi trọn con đường chuẩn (path B migration → `RubricMiddleware` literal)
ngay từ đầu thì nó trông như thế nào — chuỗi phụ thuộc, khối lượng, rủi ro, và cái giá thật?

## A.1 Insight đảo chiều: MIN-59 chính là "consumer thứ 2" mà migration đang chờ

STOP gate của `subagent-create-agent-migration/PLAN.md` ghi rõ: *"Chỉ mở rộng khi có consumer
middleware thật thứ 2 (DECISION trigger)"* — PII là consumer #1. **`RubricMiddleware` là một
consumer middleware net-new chính danh** → chọn phương án 3 không phải "chờ vô hạn định" mà là
**MIN-59 tự trở thành lý do kéo migration mở rộng**. Đây là steelman mạnh nhất của phương án 3:
hai effort hợp nhất thành một câu chuyện kiến trúc nhất quán.

Nhưng nó cũng lộ ra nghịch lý cốt lõi (xem A.5): MIN-59 là **prototype để đo xem runtime
self-eval có đáng không** — dùng nó làm lý do mở rộng migration nghĩa là **trả giá kiến trúc
trước khi có số liệu** mà chính issue yêu cầu.

## A.2 Chuỗi phụ thuộc đầy đủ (route map "đúng chuẩn")

```
[Committed sẵn — PLAN active, chưa execute]
Wave 0   PoC 6 mục (state_schema, context_schema, embed-as-node,
         RETRY PROPAGATION, STREAMING, PARALLEL TOOL)      ← gate cứng, FAIL → escalate
Wave 1   middleware set (dynamic prompt/model, tool filter, retry)
         + tool_errors wrap_tool_call + GOLDEN PARITY HARNESS   (3 task song song)
Wave 2   build_subagent_v2 (create_agent, v1 song song)
Wave 3   pilot journal → ⛔ STOP GATE + human review

[Uncommitted — Wave 4+, MIN-59 kích hoạt bằng tư cách consumer #2]
Wave 4   migrate concierge (R4: parallel-tool granularity — subagent NHIỀU tool nhất)
Wave 5   migrate booking (PLAN: "cuối cùng, chỉ khi cần — kề HITL interrupt,
         rủi ro cao nhất") — nếu MIN-59 giữ scope booking

[MIN-59 thật sự bắt đầu]
Wave 6   attach RubricMiddleware:
         - dep mới deepagents>=0.6.5 (beta)
         - TravelAgentState/state input thêm kênh `rubric`; supervisor inject
           rubric per-flow trước Command(goto=subagent) (không rubric = no-op)
         - PATCH HumanMessage injection → SystemMessage (bug language-flip đã biết)
         - grader model: construction-time → wire vào AgentConfigCache + graph rebuild
         - map on_evaluation + rubric_evaluation_start/end vào typed SSE stream
         - tắt/route reflection cho flow được grade (judge kép) + cap tổng hợp
Wave 7   FakeLLM scripted cho grader verdicts + parity/streaming verify
Wave 8   đo latency/cost/quality trên bộ eval MIN-58 → báo cáo trade-off (deliverable gốc)
```

**Khối lượng:** ~10–12 task parity-gated qua ~7 wave, **2 human gate** (STOP sau pilot; confirm
mở rộng sang booking), phần lớn ở **high-risk lane** (migration SUMMARY đã classify high-risk với
5 flags). So với phương án 2: ~4–5 task, normal lane, 1 wave chain.

## A.3 Rủi ro kỹ thuật RIÊNG của đường chuẩn (không tồn tại ở phương án 2)

| # | Rủi ro | Chi tiết |
|---|---|---|
| A | **Grader token leak vào SSE** | Grader của middleware chạy BÊN TRONG node subagent → chunk của nó mang namespace node `root ∈ SUBAGENTS` → nguy cơ stream verdict/critique ra user. Mapper hiện lọc theo root node (`mapper.py:148`); phải lọc thêm theo `name="rubric_grader"`/`lc_source` hoặc metadata tag. Phương án 2 miễn nhiễm (grader là node riêng ngoài SUBAGENTS). **Phải thêm vào PoC.** |
| B | **HumanMessage injection** | Upstream inject `HumanMessage(name="rubric_grader")` — đúng class gây bug language-flip đã trả giá. Buộc subclass/patch → ngay cả "literal port" cũng không còn literal. |
| C | **Judge kép 2 tầng** | Loop middleware nằm TRONG subagent; reflection judge nằm NGOÀI ở graph. Không tắt reflection cho flow grade thì mỗi lượt booking = 2 judge call + 2 loop độc lập (cap 3 × cap max_revisions). |
| D | **Booking kề HITL `interrupt()`** | PLAN gọi đây là migration rủi ro nhất trong cả harness. `jump_to="model"` re-run cả tool loop — tương tác với plan-approval gate của booking phải chứng minh an toàn (guarded action có thể bị re-run?). |
| E | **Beta churn kép** | deepagents 0.6.x beta + middleware runtime langchain 1.x còn trẻ (R5 của PLAN) — hai lớp API chưa ổn định chồng lên nhau. |
| F | **Concierge R4** | Parallel-tool granularity (wrap_tool_call per-call vs ToolNode-whole) — concierge là subagent nhiều tool + có geocode dedup; parity khó nhất sau booking. |

## A.4 Cái được thật sự nếu đi đường chuẩn

1. **Loop semantics upstream-maintained** — không tự nuôi vòng lặp grader; fix + cải tiến
   (grader-with-tools, judge bằng evidence) chảy về miễn phí.
2. **Observability trọn gói** — `on_evaluation`, custom stream events, `_rubric_evaluations`
   history per-criterion.
3. **Câu chuyện kiến trúc nhất quán** — PII (consumer #1) + Rubric (consumer #2) đúng trigger
   DECISION; migration mở rộng "earned", không speculative; onion composability cho middleware
   tương lai (tool-selector, guardrails).
4. **Không nợ chuyển đổi** — phương án 2 sẽ có một khoản nợ "chuyển node → middleware" khi
   migration đến nơi (dù đã thiết kế convergent thì vẫn là một lần rework).

## A.5 Nghịch lý prototype-trước-hay-đầu-tư-trước (điểm quyết định)

MIN-59 nguyên văn: *"prototype → đo latency/cost/quality → **viết báo cáo trade-off để quyết
định có mở rộng không**"*. Tức là số liệu đứng TRƯỚC quyết định đầu tư.

Phương án 3 đảo ngược thứ tự đó: đầu tư ~7 wave high-risk (bao gồm migration booking — thứ
PLAN gọi là rủi ro nhất) **trước khi biết** runtime self-eval có đáng bật hay không. Nếu báo cáo
kết luận "latency/cost không đáng" → toàn bộ Wave 4–6 đã trả giá cho một feature bị tắt. Migration
vẫn còn giá trị độc lập theo verdict path B — nhưng DECISION.md đã chốt nguyên tắc *expand theo
consumer demand thật*, và "demand" ở đây chưa được chứng minh — chứng minh nó chính là việc của MIN-59.

**Kết luận trung thực:** "đúng chuẩn từ đầu" chỉ hợp lý khi coi migration là mục tiêu tự thân
(đằng nào cũng làm, MIN-59 là dịp) VÀ chấp nhận deliverable đo lường của MIN-59 lùi sau ~7 wave.
Nếu mục tiêu là trả lời câu hỏi của MIN-59 nhanh và rẻ → phương án 2 (thiết kế convergent: verdict
names + GraderResponse schema + rubric trong prompt registry + grader model qua agent_config)
rồi hội tụ về middleware khi Wave 4+ tự nó được kích hoạt.

## A.6 Biến thể 3-lite đáng cân nhắc (nếu vẫn muốn chuẩn-từ-đầu)

Giảm giá của đường chuẩn bằng cách **thu hẹp đích migration theo đúng scope hẹp nhất của issue**:

- Giữ nguyên Wave 0–3 committed (PoC → harness → v2 → pilot journal → STOP) — đằng nào cũng phải đi.
- Wave 4 chỉ migrate **concierge** (hotel search — read-only, không mutation), **bỏ booking** khỏi
  scope MIN-59 (issue tự đề xuất biến thể "hotel search only").
- Attach RubricMiddleware (đã patch HumanMessage) chỉ trên concierge; đo trên hotel-search flows
  của bộ eval MIN-58.
- Booking giữ v1 + không rubric cho tới khi báo cáo dương tính → tránh hoàn toàn rủi ro D.

Vẫn đắt hơn phương án 2 đáng kể (~8–9 task, 2 human gate, R4 concierge còn nguyên, rủi ro A/B/C/E
còn nguyên) nhưng là phiên bản "đúng chuẩn" rẻ nhất có thể bảo vệ được.
