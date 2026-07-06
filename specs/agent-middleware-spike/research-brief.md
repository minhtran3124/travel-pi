# Research Brief — LangChain Agent Middleware ↔ agent harness hiện tại

**Slug:** `agent-middleware-spike` · **Issue:** MIN-61 · **Lane:** normal · **Ngày:** 2026-07-06
**Nguồn:** LangChain 1.x docs qua Context7 (`/websites/langchain`, `docs.langchain.com/oss/.../middleware`), đọc code `app/agents/`.

---

## Câu hỏi then chốt (pivot) & câu trả lời

> **Middleware chạy được trong custom `StateGraph`, hay chỉ trong `create_agent`?**

**Trả lời dứt khoát: chỉ trong `create_agent`.** Trích docs (đã fetch):

> *"Middleware in LangChain is **not a separate runtime**; its hooks run inside the compiled
> LangGraph that `create_agent` returns. The entire agent, including its middleware, can be
> integrated into a larger `StateGraph` as a node or subgraph, with all middleware hooks
> continuing to function."*

Hệ quả cho codebase này:

- **KHÔNG** thể gắn `AgentMiddleware` hook (`before_model` / `wrap_model_call` / `wrap_tool_call` /
  `after_model` …) trực tiếp lên các node của một `StateGraph` tự dựng.
- **CÓ** thể build một agent bằng `create_agent(..., middleware=[...])` rồi nhúng agent đó như một
  **node/subgraph** vào supervisor `StateGraph` hiện tại — middleware vẫn chạy bên trong node đó.
- → Muốn có middleware cho subagents, phải **build subagent bằng `create_agent`** (không phải
  hand-rolled loop). Đây chính là "fork lớn" issue đã cảnh báo.

## Xác nhận API ở version đang pin

`apps/api/requirements-ai.txt`: `langchain>=1.0,<2.0`, `langgraph>=1.0,<2.0` → API middleware **có sẵn**,
không cần nâng cấp. Import paths (docs 1.x):

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware, PIIMiddleware, before_model, wrap_model_call,
    AgentState, ModelRequest, ModelResponse,
)
```

`PIIMiddleware` xác nhận có thật, chữ ký: `PIIMiddleware(pii_type, *, strategy="redact"|"mask"|"block",
detector=<regex tùy chọn>, apply_to_input=True)`. Built-in types: `email`, `credit_card`, `api_key`, …
Custom qua `detector=r"..."`.

## Kiến trúc hiện tại (đã đọc code, không suy đoán)

Subagent được dựng bởi **một factory chung** `build_subagent()` trong
`app/agents/subagents/_base.py` — **hand-rolled ReAct `StateGraph`**, KHÔNG dùng
`create_agent`/`create_react_agent`:

```
StateGraph(TravelAgentState, context_schema=AgentContext)
  assistant (node, retry_policy=LLM_RETRY)  →  bind_tools + invoke
  tools     (ToolNode, handle_tool_errors=_tool_error_to_message | tool_fault)
  assistant --tools_condition--> tools --> assistant | END
```

`assistant` node gói **5 hành vi cố ý** — đây là "chi phí ẩn" khi migrate sang `create_agent`:

| # | Hành vi hiện tại (`_base.py`) | Map sang middleware/`create_agent` | Ghi chú |
|---|---|---|---|
| 1 | **Deferred model resolution** — `resolve_model(None)` gọi *trong* node mỗi request (MIN-43 D1) | `wrap_model_call` (dynamic model) hoặc callable model | Rewrite, không phải drop-in |
| 2 | **Dynamic prompt** — `system_with_summary(state, ground_current_date(system))` per-turn | `wrap_model_call` / dynamic-prompt hook | Map sạch — **đây là candidate #2** |
| 3 | **Episodic tool filtering** — `active_tools` lọc theo `ctx.allow_episodic` | `wrap_model_call` (`ModelRequest.tools`) hoặc `LLMToolSelectorMiddleware` | Cần dynamic tools |
| 4 | **Tool-error → message** — `_tool_error_to_message`, `ToolFaultPolicy` (PR #55) | `wrap_tool_call` + built-in error handling | Battle-tested — rủi ro regression |
| 5 | **Node-level `RetryPolicy`** — `LLM_RETRY` trên node assistant | `ModelRetryMiddleware` (khác cơ chế) | **Non-goal**: KHÔNG thay RetryPolicy |

**Kết luận chi phí migrate:** blast radius *code* gọn (một hàm `build_subagent`), nhưng **rủi ro
hành vi cao** — 5 behavior đã battle-tested phải tái hiện dưới dạng middleware và verify parity trên
cả 5 subagent + wiring supervisor. Va chạm trực tiếp với 2 non-goal (RetryPolicy #5, và gián tiếp
memory). → Đây là **refactor trung bình, rủi ro trung-cao**, không phải "bật một flag".

## Phát hiện chiến lược quan trọng nhất

**Giá trị #1 (PIIMiddleware) bị *khóa cứng* vào fork `create_agent`.** Không có `create_agent` →
không có bất kỳ middleware nào, kể cả PII. NHƯNG **năng lực PII redaction/masking không cần
middleware để tồn tại** — nó có thể là một hàm thuần chạy pre-model trong `assistant` node hiện tại
(hoặc một node `guardrail` riêng trên cạnh `load_context → …`). → **Tách được lỗ hổng bảo mật khỏi
cuộc refactor lớn**: ship PII handling "thủ công" (idiomatic với kiến trúc hiện tại) mà không phải
migrate. Đây là insight quyết định cho DECISION.md.

## PoC path (2 lựa chọn, đều evaluation-only — không đụng `app/`)

- **(A) Faithful** — throwaway script dựng `create_agent(model=FakeLLM|real, middleware=[PIIMiddleware("email", strategy="redact", apply_to_input=True)])`, invoke với input chứa email → xác nhận redaction ở version đang pin. Chứng minh API, KHÔNG chứng minh tích hợp vào supervisor.
- **(B) Manual-equivalent** — hàm `redact_pii(text)` (regex email/phone) áp trong một node thử → chứng minh năng lực PII *không cần* `create_agent`, đúng hướng ship thật.

→ DECISION.md đề xuất PoC (A) để chốt API + (B) như hình mẫu đường ship thật.
