---
slug: subagent-create-agent-migration
status: active (pilot-gated — scope confirmed by human)
owner: Minh Tran
created: 2026-07-06
revised: 2026-07-06 (post multi-agent review)
---

# Subagent → `create_agent` Migration (Path B, hybrid) — pilot-gated

> Đích đường dài: 5 subagent chuyển từ hand-rolled `StateGraph` (`build_subagent`) sang `create_agent`
> **nhúng làm node** trong supervisor `StateGraph` **giữ nguyên** (không phải path C). Nguồn: `specs/agent-middleware-spike/COMPARISON.md`.
>
> **Bản này đã revise sau panel review 4 persona** (architecture / feasibility / scope / adversarial).
> Thay đổi lớn: (1) sửa motivation sai logic; (2) **tách PII ship trước, không chờ migration**;
> (3) **commit chỉ tới pilot `journal` + gate**, mở rộng theo nhu cầu — KHÔNG cam kết migrate cả 5 ngay.

## 1. Motivation (đã sửa — bỏ category error)

Panel chỉ ra motivation cũ ("`create_supervisor` đã ngừng maintain") là **lỗi logic**: plan GIỮ supervisor
custom, chỉ subagent đổi — nên deprecation của supervisor không phải lý do. Motivation trung thực:

- **On-ramp năng lực có thật:** mỗi subagent trên `create_agent` mở khóa middleware ecosystem *cho chính
  nó*. Consumer cụ thể đầu tiên = **PII** (net-new, PoC PASS). Đây là lý do đủ cho một **pilot**, chưa
  phải cho migrate cả 5.
- **Bám đường maintained ở tầng subagent:** ReAct loop tay là thứ `create_agent` thay thế idiomatic.

**KHÔNG viện dẫn "velocity" trừu tượng.** Chỉ mở rộng khi có consumer middleware thật thứ 2 (khớp
DECISION.md trigger "≥2 middleware net-new"). Đến lúc đó, pilot đã trả lời mọi rủi ro kỹ thuật.

## 2. Non-goals

- **KHÔNG** chuyển supervisor sang subagents-as-tools (path C).
- **KHÔNG** cam kết migrate cả 5 trong plan này. Chỉ tới **journal pilot + STOP gate**; booking + retire v1 **ngoài committed scope**.
- **KHÔNG** đổi reflection loop, tier-gate, HITL `interrupt()`.
- **KHÔNG** "cải tiến" retry/tool-error/model-resolution — tái hiện + verify parity.
- **KHÔNG** kéo memory extraction vào graph.

## 3. Success Criteria

1. **PII ship được độc lập** (Wave A) — không phụ thuộc migration; đóng lỗ hổng bảo mật ngay.
2. Feasibility PoC (Wave 0) trả lời 4 unknown **kèm** exhaustion/streaming/parallel semantics (không chỉ "chạy được").
3. `journal` chạy qua `create_agent` với **parity** 5 behavior: retry (LLM_RETRY *propagation*), tool-error split, dynamic prompt, tool filtering, model resolution.
4. Golden parity harness phủ **tool-using + transient-error + parallel-tool + streaming** shape (không chỉ journal invoke-level).
5. Toàn bộ `tests/agents/` + `tests/memory/` xanh; `/agent/stream` verify thủ công không đổi.
6. Mixed v1/v2 là **resting state được hỗ trợ** — stall giữa chừng không phải nợ undefined.

## 4. Tasks

### Wave A — PII decoupled (ship NGAY, không chờ migration)

```xml
<task id="A.1" wave="A">
  <files>apps/api/app/agents/guardrails.py, apps/api/app/agents/graph.py, apps/api/tests/agents/test_pii_redaction.py</files>
  <action>Ship PII redaction như DECISION.md A1: một hàm/node guardrail thuần (redact email, mask credit_card,
    custom detector name/phone phối hợp MIN-53) áp pre-model trong kiến trúc HIỆN TẠI (không cần create_agent).
    Đây là issue riêng, re-intake high-risk (audit/security). Đóng lỗ hổng ngay; độc lập hoàn toàn với waves 0–3.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_pii_redaction.py -x</verify>
  <done>PII redaction live trên kiến trúc hiện tại; test xanh; KHÔNG phụ thuộc migration</done>
</task>
```

### Wave 0 — Feasibility PoC (evaluation-only, strengthened)

```xml
<task id="0.1" wave="0">
  <files>specs/subagent-create-agent-migration/poc/embed_create_agent_poc.py</files>
  <action>Throwaway PoC (no app/ change) chứng minh, mỗi mục PASS/FAIL rõ:
    (1) create_agent nhận state_schema tương thích TravelAgentState — [feasibility đã xác nhận factory.py:815 khả thi, PoC để chốt cụ thể field summary/profile/trip_context/current_flow];
    (2) context_schema=AgentContext + middleware đọc Runtime[AgentContext] [factory.py:1443 — xác nhận allow_episodic/tier];
    (3) compiled create_agent add làm node vào StateGraph cha, checkpointer/store propagate (InjectedStore tool chạy);
    (4) **RETRY PARITY** — ModelRetryMiddleware(retry_on=_is_retryable_llm, on_failure="error") tái hiện LLM_RETRY:
        transient→retry, exhaustion→**PROPAGATE** (KHÔNG phải on_failure="continue" trả error AIMessage). Test cả nhánh cạn retry;
    (5) **STREAMING** — invoke qua .astream, xác nhận AIMessage.name=node_name + ToolCallTransformer không phá chuỗi FE mong đợi;
    (6) **PARALLEL TOOL** — 2 tool-call song song với 1 transient fail: xác nhận wrap_tool_call granularity (per-call) vs
        ToolNode-whole hiện tại; ghi rõ chênh lệch ordering ToolMessage nếu có.</action>
  <verify>cd apps/api && ../../.venv/bin/python ../../specs/subagent-create-agent-migration/poc/embed_create_agent_poc.py</verify>
  <done>6/6 mục có kết luận; FAIL nào ghi fallback. Retry propagation + streaming + parallel là gate cứng — FAIL → escalate hướng B</done>
</task>
```

### Wave 1 — Middleware set + parity harness (harness lên sớm)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/agents/subagents/middleware.py, apps/api/tests/agents/test_subagent_middleware.py</files>
  <action>Middleware tái hiện (mỗi hook unit-test): (a) dynamic prompt → override request.system_prompt =
    system_with_summary(state, ground_current_date(system)); (b) dynamic model → get_agent_llm(name) per call,
    override request.model (giữ AgentConfigCache); (c) tool filter → loại EPISODIC_TOOL_NAME khi Runtime allow_episodic=False;
    (d) retry → ModelRetryMiddleware(on_failure="error") theo PoC mục 4. Chỉ DỜI logic từ _base.py::assistant, không đổi ngữ nghĩa.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_middleware.py -x</verify>
  <done>4 middleware pass unit; parity logic với _base.py::assistant</done>
</task>
```

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/agents/subagents/tool_errors.py, apps/api/tests/agents/test_subagent_tool_errors.py</files>
  <action>Tool-error qua wrap_tool_call: (a) default _tool_error_to_message catch-all → ToolMessage; (b) split transient
    (UpstreamError, retry) vs logic (ToolException, narrowed). **graceful_fallback: chỉ tái dùng phần construct
    ToolMessage — BỎ Command(goto="assistant")** (node đó không tồn tại trong create_agent). Ghi rõ granularity retry
    đổi từ whole-ToolNode → per-call; test parallel fail. Tái dùng app.agents.retry, đừng viết lại filter.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_tool_errors.py -x</verify>
  <done>transient→retry, logic→message, parallel-fail→synthetic ToolMessage đúng thứ tự; chênh lệch ghi lại</done>
</task>
```

```xml
<task id="1.3" wave="1">
  <files>apps/api/tests/agents/test_subagent_parity.py</files>
  <action>Golden parity harness (LÊN Ở WAVE 1 để validate middleware bằng gate, không phải kỳ vọng tay). Parametrized:
    cùng TravelAgentState + FakeLLM scripted phủ **tool-call, transient error, logic error, allow_episodic on/off, PARALLEL
    tool fail**, chạy qua v1 (build_subagent) vs middleware set, assert cùng messages/tool_calls/error handling.
    Thêm 1 case **streaming** (.astream) so name-stamping. Đây là VERIFY GATE mọi wave sau.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_parity.py -x</verify>
  <done>Parity xanh cho tool-using + parallel + streaming shape; harness tái dùng cho subagent khác</done>
</task>
```

### Wave 2 — Factory v2 (song song v1)

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/subagents/_base_v2.py, apps/api/tests/agents/test_build_subagent_v2.py</files>
  <action>build_subagent_v2(name, tools, prompt, tool_fault) = create_agent(model, tools, state_schema, context_schema=
    AgentContext, middleware=[dynamic_prompt, dynamic_model, tool_filter, retry, tool_error]) trả compiled agent CÙNG
    chữ ký node như build_subagent. GIỮ build_subagent cũ song song (mixed v1/v2 = resting state hợp lệ). Chạy qua parity harness (1.3).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_build_subagent_v2.py tests/agents/test_subagent_parity.py -x</verify>
  <done>v2 compile+invoke, parity harness xanh v1 vs v2</done>
</task>
```

### Wave 3 — Pilot `journal` + STOP gate

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/agents/subagents/journal.py, apps/api/app/agents/graph.py</files>
  <action>Trỏ journal sang build_subagent_v2. Supervisor/edges/reflection/HITL GIỮ NGUYÊN — đổi một node builder.
    Verify full tests/agents + tests/memory + **/agent/stream thủ công** (journal flow) không đổi.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ tests/memory/ -x</verify>
  <done>journal qua create_agent, mọi test xanh, parity xanh, streaming không đổi. **STOP — human review kết quả pilot.**</done>
</task>
```

### ⛔ STOP GATE (sau Wave 3)

Không tự động sang subagent khác. Đánh giá pilot: parity có giữ end-to-end? Streaming FE ổn? Chi phí/rủi ro
thực so dự đoán? **Chỉ mở rộng khi có consumer middleware thật thứ 2** (DECISION trigger). Nếu không → dừng ở
journal, coi như đã de-risk hướng B cho tương lai, mọi subagent khác ở v1 (resting state hợp lệ).

### Wave 4+ — Expand-on-demand (KHÔNG committed, để tham chiếu)

- planner / budget / concierge: migrate **từng cái khi nó nhận middleware thật**, mỗi cái qua parity gate.
- booking: **cuối cùng, chỉ khi cần** — kề HITL interrupt, rủi ro cao nhất, zero middleware consumer hiện tại.
- retire `build_subagent` + rename `_base_v2`→`_base`: **chỉ khi cả 5 đã độc lập earn migration.** Task riêng.

## 5. Waves

| Wave | Tasks | Song song? | Gate | Committed? |
|---|---|---|---|---|
| **A** | A.1 PII decoupled | single | full test | ✅ (issue riêng, ship trước/song song) |
| **0** | 0.1 feasibility PoC (6 mục) | single | **STOP+human nếu retry/stream/parallel FAIL** | ✅ |
| **1** | 1.1 middleware, 1.2 tool-error, 1.3 parity harness | 3 song song (file rời) | parity + unit | ✅ |
| **2** | 2.1 factory v2 | single | parity harness v1↔v2 | ✅ |
| **3** | 3.1 pilot journal | single | **⛔ STOP GATE + human-confirm** | ✅ |
| 4+ | expand planner/budget/concierge/booking, retire v1 | on-demand | parity mỗi cái | ❌ **không committed** |

## 6. Risks (post-review)

- **R1 — state/context tương thích** → *giảm mạnh*: feasibility xác nhận `create_agent` nhận state_schema+context_schema (factory.py:815,1443). PoC 0.1(1,2) chốt cụ thể. Fallback "context qua state" bị bác (persist vào checkpointer = regression) → nếu context_schema fail thì **escalate**, không âm thầm fallback.
- **R2 — retry KHÔNG có ở node create_agent** (factory.py:1502) → phải dùng ModelRetryMiddleware **on_failure="error"** để PROPAGATE (default "continue" trả error AIMessage = khác parity). Gate cứng ở PoC 0.1(4).
- **R3 — parity drift ngầm** (structured-output/message-trim nội bộ create_agent) → harness 1.3 phủ tool/parallel/**streaming**; migrate từng cái.
- **R3b — streaming surface** (AIMessage.name stamp, ToolCallTransformer) chỉ lộ qua /agent/stream → verify thủ công ở Wave 3 + case streaming ở 1.3.
- **R4 — parallel tool granularity** (concierge): wrap_tool_call per-call vs ToolNode-whole; graceful_fallback Command(goto) bỏ → chỉ giữ ToolMessage. Test parallel-fail ở 1.2/1.3.
- **R5 — API 1.x churn** → pin chặt, theo changelog.
- **R6 — YAGNI / over-migration** (panel) → mitigated bằng STOP gate: chỉ pilot, mở rộng theo nhu cầu.

## 7. Status Log

- 2026-07-06 — PLAN proposed (path B, full-5).
- 2026-07-06 — **Revised sau panel review 4 persona.** Sửa motivation (category error); tách PII (Wave A, ship trước);
  commit chỉ tới journal pilot + STOP gate; strengthen PoC (retry-propagation/streaming/parallel); parity harness lên Wave 1;
  booking + retire-v1 ra khỏi committed scope. Feasibility xác nhận state/context khả thi (factory.py:815,1443); retry phải
  qua middleware on_failure="error" (factory.py:1502).
- 2026-07-06 — **Scope CONFIRMED bởi human: pilot-gated.** Committed = Wave A (PII) + Wave 0–3 (PoC → middleware+parity →
  v2 factory → journal pilot → STOP). Wave 4+ expand-on-demand. Sẵn sàng execute; mỗi wave re-intake khi thực thi.
