# Deep Comparison — Giữ custom StateGraph vs Chuyển hết sang `create_agent`

**Slug:** `agent-middleware-spike` · **Issue:** MIN-61 · **Ngày:** 2026-07-06
**Câu hỏi:** Bỏ qua chi phí/số file refactor — **lợi ích thực chất** khác nhau ra sao, và **đường dài** cách nào tốt hơn?
**Nguồn:** LangChain 1.x docs (Context7), map codebase `app/agents/` (Explore agent).

---

## 0. "2 cách" thực ra là 3 — và điểm mấu chốt nằm ở đây

Câu hỏi đặt ra "giữa 2 cách", nhưng phân tích trung thực cho thấy có **3 kiến trúc**, không phải 2:

| | Kiến trúc | Supervisor (routing) | Subagent (ReAct loop) |
|---|---|---|---|
| **A** | **Giữ nguyên** custom | Custom `StateGraph` + `Command(goto)` | Hand-rolled `build_subagent` |
| **B** | **Hybrid** (đề xuất) | Custom `StateGraph` + `Command(goto)` **giữ nguyên** | `create_agent` nhúng làm node |
| **C** | **Full** create_agent | `create_agent` + subagents-as-tools (LLM routing) | `create_agent` |

Docs 1.x **cho phép nhúng** `create_agent` làm node trong `StateGraph` lớn hơn ("integrate the agent as
a node or subgraph, all middleware hooks continue to function"). → **B tồn tại và được hỗ trợ chính
thức.** Đây là điểm quyết định: bạn KHÔNG phải chọn giữa "middleware ecosystem" và "deterministic
orchestration" — B lấy cả hai.

## 1. Bảng so sánh lợi ích thực chất (bỏ qua chi phí refactor)

| Chiều | A — Giữ custom | B — Hybrid (subagent→create_agent) | C — Full (supervisor-as-tools) |
|---|---|---|---|
| **Năng lực net-new** (PII, guardrails, tool-selector, context-editing, call-limit, model-fallback) | Mỗi cái = node/code tự viết + tự maintain | ✅ **Một dòng middleware, upstream maintain.** Lợi ích lớn nhất | ✅ Như B |
| **Tái dùng cross-cutting** | Copy-paste qua `_base.py`/`nodes.py`, dễ drift | ✅ Viết 1 lần dạng middleware có thứ tự (onion), áp cho cả 5 subagent | ✅ Như B |
| **Bám upstream / maintenance** | ❌ Ngoài đường maintained (`create_supervisor` đã bỏ; hand-rolled = pattern cũ) | ✅ Subagent trên đường LangChain đầu tư; fix + middleware mới chảy về | ✅✅ Toàn bộ trên đường maintained |
| **Orchestration tất định** (routing, reflection loop, HITL gate) | ✅✅ Toàn quyền: `Command(goto)`, reflection bounded, `interrupt()` giữa node | ✅ **Giữ nguyên** — supervisor vẫn là graph | ❌ **Routing do LLM quyết** (gọi subagent qua tool) — mất tính tất định |
| **Deep agents stack** (SubAgentMiddleware, Filesystem, Todo, planning) | ❌ Không cắm được vào graph tay | ⚠️ Cắm được ở tầng subagent | ✅ Cắm wholesale |
| **Behavior battle-tested** (retry, tool-error split PR#55, summarizer PR#58) | ✅ Đã tuned + test | ⚠️ Phải tái hiện dạng middleware + verify parity | ⚠️ Như B, cộng rủi ro routing |
| **Lock-in / API churn** | ✅ Không (tự sở hữu loop) | ⚠️ Middleware API còn trẻ (1.x), đang tiến hóa | ❌ Phụ thuộc sâu nhất vào API trẻ |
| **Model/provider flexibility** | ✅ `get_agent_llm` + DB config (mạnh) | ⚠️ `wrap_model_call` dynamic model — làm lại được | ⚠️ Như B |
| **Tính tất định cho luồng booking** (tier gate, plan-approval trước booking) | ✅✅ Graph đảm bảo thứ tự | ✅ Giữ ở supervisor graph | ❌ LLM có thể route sai thứ tự |

## 2. Cái gì map được, cái gì không (fairness check)

**Gần như MỌI thứ đều biểu diễn được trên stack mới** (không phải rào cản kỹ thuật):

- Node-level `retry_policy=LLM_RETRY` → `ModelRetryMiddleware` / `wrap_model_call` retry (per-subagent).
- `interrupt()` HITL plan→booking → `HumanInTheLoopMiddleware(interrupt_on=...)` — thậm chí gọn hơn.
- Dynamic prompt `system_with_summary` → `wrap_model_call` (docs có mẫu inject state vào prompt).
- Tool filtering theo `AgentContext.allow_episodic` → `wrap_model_call` override `ModelRequest.tools`.
- Split tool-error (transient vs logic) → `wrap_tool_call` middleware.
- Per-request state → middleware `state_schema` mở rộng `AgentState` + `can_jump_to`/`jump_to` short-circuit.

**Cái KHÔNG map sạch sang C (mất khi bỏ supervisor graph):**

- **Reflection loop bounded** (`nodes.py` revise ≤ max_revisions, route về `current_flow`) — là cấu trúc
  graph, không phải concern của 1 agent. Ở C phải mô phỏng bằng LLM/tool → kém tất định.
- **`Command(goto)` routing tất định** theo intent + tier gate. Ở C, supervisor "quyết định" qua tool
  call → phi tất định, khó đảm bảo (rủi ro cho luồng booking cần thứ tự cứng).
- **Shared checkpointer/store propagate** vào nested subgraph (đang "miễn phí" nhờ compile 1 lần).

→ Đây chính là lý do **B > C** cho app này: reflection + tier-gate + plan-approval là **graph-shaped,
tất định**, không nên đổi lấy LLM-routing.

## 3. Verdict đường dài

**Ignoring cost, đường dài: B (hybrid) là tốt nhất — và nó tốt hơn A.**

Lý do cốt lõi (đã đổi trọng số so với DECISION.md ban đầu, vốn nặng về chi phí near-term):

1. **Bám đường upstream.** `create_supervisor` đã ngừng maintain; hand-rolled supervisor là pattern
   LangChain đang rời bỏ. Ở lại A nghĩa là ngày càng bơi ngược dòng — mỗi năng lực mới (guardrails,
   context-editing, deep agents) là công tự viết, trong khi B nhận "miễn phí".
2. **Tốc độ năng lực.** Lợi ích thật KHÔNG phải "gọn code" — mà là **velocity**: thêm một guardrail /
   tool-selector / call-limit ở B là 1 dòng; ở A là một node + test + maintain.
3. **Giữ được thế mạnh tất định.** B **không** hy sinh orchestration tất định (supervisor vẫn là graph).
   Đó là điều C đánh mất và là lý do "chuyển qua HẾT create_agent" (C) **không** phải đích đến.

**Khi nào A vẫn hợp lý:** nếu agent đứng yên về tính năng (không thêm cross-cutting concern mới) →
A "đủ tốt", vì mọi thứ đang battle-tested; migration chỉ thêm rủi ro mà không mở khóa giá trị. Verdict
đường dài giả định app **tiếp tục thêm** năng lực (PII, guardrails, HITL mở rộng… — đúng quỹ đạo hiện tại).

**Không phải đích đến:** C (bỏ supervisor graph, subagents-as-tools). Đổi tính tất định lấy sự đồng nhất
là bước lùi độ tin cậy cho luồng booking cần thứ tự cứng.

## 4. Đường đi khuyến nghị (nếu chọn B — vẫn nên sequence để giảm rủi ro)

> Câu hỏi bảo bỏ qua chi phí; nhưng "đường dài tốt hơn" ≠ "làm một phát". B đạt được **tăng dần**:

1. **Pilot 1 subagent** ít rủi ro nhất (`journal`: không booking, ít tool) → `create_agent`, nhúng làm
   node, verify parity (retry, tool-error, prompt).
2. **Ship PII** như middleware **trên node đã migrate đó** (thay vì hàm thủ công) — biến A1 của DECISION
   thành cầu nối tự nhiên sang B.
3. Mở rộng dần các subagent còn lại; supervisor graph + reflection + HITL **giữ nguyên** suốt quá trình.
4. Chỉ cân nhắc C nếu tương lai routing tất định không còn quan trọng (khó xảy ra với booking).

## 5. Ảnh hưởng tới DECISION.md

DECISION.md (DEFER toàn bộ fork) đúng ở trục **near-term cost/risk**. Khi **bỏ trục đó** theo yêu cầu,
verdict đường dài đảo sang: **B là đích kiến trúc đúng.** Hai kết luận không mâu thuẫn — chúng trả lời
2 câu hỏi khác nhau (near-term "làm gì tiếp" vs long-term "kiến trúc đúng là gì"). Hòa giải: **hướng B
làm đích, đi bằng các bước nhỏ, mỗi bước re-intake; PII là bước 1 và là cầu nối.**
