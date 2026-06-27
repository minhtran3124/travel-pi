# LangGraph Runtime Config — Nghiên cứu & Best Practices

> Trạng thái: nghiên cứu / tư vấn · Tạo: 2026-06-27 · Phạm vi: `apps/api/app/agents`, `tools`, `routers/agent.py`
> Nguồn tài liệu chính thống: LangGraph 1.0 official docs (Context7 `/websites/langchain_oss_python_langgraph`).

## Tóm tắt nhanh (TL;DR)

**Hỏi: Hiện tại chúng ta đã hỗ trợ RunnableConfig với LangGraph chưa?**
**Một phần.** Chúng ta đã *truyền* một config dict ở mỗi lần invoke (`configurable.thread_id`,
`recursion_limit`, `callbacks`, `metadata`) — về bản chất đây chính là `RunnableConfig`, và nó
đang hoạt động đúng để vận hành checkpointer + Langfuse tracing. Nhưng:

- Chúng ta chưa bao giờ khai báo kiểu (type) cho nó là `RunnableConfig`.
- Không node hay tool nào **đọc** `config["configurable"]`.
- Dữ liệu theo từng request ở tầng ứng dụng (`user_id`, `trip_id`) được luồn qua **graph state**,
  và việc chọn model được cố định ngay lúc build.

Trên **LangGraph 1.0** (mà chúng ta đang pin: `langgraph>=1.0,<2.0`), cách được khuyến nghị để
inject context theo từng request và không lưu bền vững là **API `Runtime` / `context_schema` mới**
— *không phải* `config["configurable"]`, và *cũng không phải* state. Chúng ta chưa dùng cách này.
Tài liệu này giải thích sự khác biệt và những gì (nếu có) nên áp dụng.

---

## 1. Hiện tại chúng ta đang làm gì

| Vấn đề | Cơ chế | Tham chiếu |
|---|---|---|
| Build graph | `StateGraph(TravelAgentState).compile(checkpointer, store)`, build một lần lúc khởi động | `app/agents/graph.py:40`, `app/core/lifespan.py:59` |
| Invoke | `graph.ainvoke(state_dict, cfg)` — `cfg` truyền theo vị trí (positional) | `app/routers/agent.py:109` |
| Nội dung `cfg` | `{"configurable": {"thread_id": ...}, "recursion_limit": ..., "callbacks": ..., "metadata": ...}` | `app/routers/agent.py:82` |
| Dữ liệu user theo request | `user_id`, `trip_id` được đặt vào **state dict ban đầu** | `app/routers/agent.py:115` |
| Trip context | Tải từ DB bên trong `load_context_node`, lưu vào `state["trip_context"]` | `app/agents/nodes.py:31` |
| Tool injection | `InjectedState("user_id")`, `InjectedStore` (không đọc config) | `app/tools/memory_tools.py:22` |
| Chọn model | Cố định theo từng node lúc build qua `get_agent_llm(agent_name)` | `app/clients/llm.py` |
| Phiên bản | `langgraph>=1.0,<2.0`, `langchain>=1.0,<2.0` | `apps/api/requirements-ai.txt` |

Chữ ký các node đều thống nhất dạng `def node(state) -> dict` — không node nào nhận `config` hay `runtime`.

---

## 2. Ba kênh (channel) trong LangGraph 1.0 (mô hình tư duy)

LangGraph tách *những gì chảy qua một lần run* thành ba kênh riêng biệt. Chọn đúng kênh là điều cốt lõi:

| Kênh | Thay đổi được? | Lưu vào checkpoint? | LLM thấy được? | Dùng cho |
|---|---|---|---|---|
| **State** | có (reducers) | **có** | chỉ các field bạn expose | messages hội thoại, kết quả tích lũy, bất cứ thứ gì agent vừa đọc *vừa ghi* qua các bước |
| **Context** (`Runtime`) | không (read-only theo run) | **không** | không | input theo request mà cố định trong suốt run: `user_id`, `org_id`, lựa chọn model, feature flags, dependency theo request |
| **Config** (`RunnableConfig`) | không | không áp dụng (cơ chế nội bộ) | không | `thread_id`, `callbacks`, `metadata`, `recursion_limit`, `tags` — bộ máy vận hành của runtime |

Hệ quả quan trọng: **`user_id` / `trip_id` đúng ra là context, không phải state.** Chúng cố định
trong suốt run và không bao giờ bị agent thay đổi — đặt chúng vào state nghĩa là chúng bị ghi vào
mọi snapshot checkpoint mà chẳng có lợi ích gì. (Đây là điểm về *độ sạch sẽ*, không phải lỗi — cách
hiện tại vẫn chạy được.)

---

## 3. API LangGraph 1.0: `Runtime` + `context_schema`

Đây là bản thay thế trong v1.0 cho pattern cũ `config_schema` + `config["configurable"]`.

### Node đọc context qua `Runtime` được inject

```python
from dataclasses import dataclass
from langgraph.graph import StateGraph, MessagesState
from langgraph.runtime import Runtime

@dataclass
class Context:
    user_id: str
    trip_id: str | None = None
    model_provider: str = "openai"

def call_model(state: MessagesState, runtime: Runtime[Context]):
    model = MODELS[runtime.context.model_provider]      # chọn model theo run
    user_id = runtime.context.user_id                   # danh tính theo run
    thread_id = runtime.execution_info.thread_id        # giá trị của framework, không phải context
    ...

builder = StateGraph(MessagesState, context_schema=Context)   # <-- khai báo context
graph = builder.compile()

# Invoke: context là kwarg hạng nhất, tách biệt khỏi config
graph.invoke(
    {"messages": [...]},
    context=Context(user_id="u_123", trip_id="t_9", model_provider="anthropic"),
    config={"configurable": {"thread_id": "conv_42"}},   # config vẫn mang thread_id
)
```

`Runtime` cũng expose `runtime.store` và `runtime.execution_info` (gồm `thread_id`), nên một node
không còn cần plumbing kiểu `InjectedStore` để truy cập store.

### Tool đọc context + state qua `ToolRuntime`

```python
from langchain.tools import ToolRuntime, tool

@tool
def get_user_info(runtime: ToolRuntime[Context, State]) -> str:
    """Tra cứu thông tin người dùng."""
    user_id = runtime.state["user_id"]          # graph state
    org_id  = runtime.context.organization_id   # context theo run, không nằm trong state
    return f"User {user_id} in org {org_id}"
```

Đây là bản kế thừa trong 1.0 cho các annotation `InjectedState` / `InjectedStore` của chúng ta.
Các annotation hiện tại vẫn chạy được; `ToolRuntime` là lựa chọn thay thế thống nhất và có kiểu rõ ràng.

### `RunnableConfig` **không** bị deprecate

`config` vẫn là kênh cho `thread_id`, `callbacks`, `metadata`, `recursion_limit`. Trong functional
API bạn vẫn có thể inject trực tiếp:

```python
from langchain_core.runnables import RunnableConfig
from langgraph.func import entrypoint

@entrypoint(checkpointer=..., store=...)
def workflow(some_input, *, store, writer, config: RunnableConfig): ...
```

Vì vậy dict `cfg` hiện tại của chúng ta là đúng và giữ nguyên. Thay đổi của 1.0 mang tính **bổ sung**:
chuyển *context ứng dụng* ra khỏi `config["configurable"]` sang `context=`, và để *cơ chế framework*
lại trong `config`.

---

## 4. Best practices (LangGraph 1.0)

1. **Kỷ luật ba kênh.** State = thay đổi được + lưu bền. Context = read-only theo run, không lưu.
   Config = cơ chế framework (`thread_id`, `callbacks`, `metadata`, `recursion_limit`). Đừng dùng
   kênh này để gánh việc của kênh kia.
2. **Context ứng dụng vào `context=`, không vào `config["configurable"]`.** `configurable` giờ dành
   cho các key của chính runtime; dữ liệu user/request thuộc về `context_schema` có kiểu.
3. **Khai báo kiểu cho context schema** (dataclass hoặc `TypedDict`) để node/tool có an toàn kiểu cả
   lúc IDE lẫn runtime trên `runtime.context.*`.
4. **Đừng lưu các hằng số vào state.** Danh tính/flag không đổi trong suốt run là context, giúp
   checkpoint gọn và snapshot có ý nghĩa.
5. **Chọn model theo runtime qua context**, không phải lúc build — *nếu* bạn cần chọn model theo từng
   request (hiện tại ta cố định theo node — ổn cho tới khi một request cần override).
6. **Giữ `config` cho tracing/threading.** `thread_id`, `callbacks` của Langfuse, `metadata`,
   `recursion_limit` giữ nguyên vị trí hiện tại — phần này đã đúng.
7. **Ưu tiên `Runtime`/`ToolRuntime` hơn `Injected*`** cho code mới — truy cập state + context + store
   một cách thống nhất và có kiểu.

---

## 5. Phân tích khoảng trống & Khuyến nghị

| Best practice | Trạng thái | Hành động |
|---|---|---|
| Truyền `config` với `thread_id`/callbacks/metadata | ✅ Đã làm | không cần |
| `RunnableConfig` có kiểu | ⚪ Hình thức | tùy chọn: annotate `cfg` |
| Context ứng dụng trong `context=` với `context_schema` | ❌ Chưa áp dụng | ứng viên refactor (xem dưới) |
| `user_id`/`trip_id` ra khỏi state lưu bền | ❌ Đang ở trong state | chuyển sang context |
| `Runtime` / `ToolRuntime` thay cho `Injected*` | ❌ Đang dùng `Injected*` | áp dụng dần cho tool mới |
| Chọn model theo request | ❌ Chỉ lúc build | chỉ áp dụng nếu có nhu cầu thực sự |

**Khuyến nghị — chỉ làm khi có lý do thúc đẩy, không làm vì bản thân nó.** Cách hiện tại (luồn qua
state + `Injected*`) vẫn hoạt động và đúng chuẩn cho LangGraph ≤0.x. API `Runtime`/`context` của 1.0
là hướng đi dài hạn sạch hơn, nhưng việc migrate chạm vào chữ ký của mọi node và cả state schema
(thuộc địa hạt Rule 4 — thay đổi hình dạng state). Trình tự đề xuất:

- **Ngay bây giờ (chi phí thấp):** khai báo kiểu `RunnableConfig` cho `cfg` ở router; tài liệu hóa mô
  hình ba kênh trong `WORKFLOW.md`. Không đổi hành vi.
- **Khi một tính năng cần đến** (ví dụ override model theo request, dependency theo request, hoặc cắt
  giảm phình to checkpoint): giới thiệu một dataclass `context_schema`, chuyển `user_id`/`trip_id` vào
  `context=`, và migrate node sang `runtime: Runtime[Context]` / tool sang `ToolRuntime`.
- **Đừng** refactor ồ ạt thuần túy vì phong cách — phạm vi ảnh hưởng rộng khắp `agents/` và `tools/`
  mà không có lợi ích nào người dùng thấy được cho tới khi một trong các lý do trên xuất hiện.

---

## 6. Tham chiếu

- Use the graph API — runtime context: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Graph API (nodes, `Runtime`, `execution_info`): https://docs.langchain.com/oss/python/langgraph/graph-api
- Workflows & agents (`ToolRuntime`): https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Functional API (inject `RunnableConfig`): https://docs.langchain.com/oss/python/langgraph/functional-api
