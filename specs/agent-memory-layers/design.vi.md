---
slug: agent-memory-layers
doc: design
lang: vi
scope: P1 — background memory extraction + procedural memory injection
created: 2026-06-30
status: proposed
note: Bản tiếng Việt của design.md (bản tiếng Anh là source of truth).
---

# P1 Design — Background extraction + Procedural memory

Đóng 2 gap so với framework memory của LangChain (xem `research.md`):

1. **Background writes** — không còn phụ thuộc LLM phải tự gọi
   `save_user_preference`. Một bước chạy cuối turn sẽ tự mining exchange gần nhất.
2. **Procedural memory** — standing instructions theo từng user, persist
   cross-thread và fold vào system prompt mỗi turn qua đúng path
   `system_with_summary` đang có.

Non-goals (để sau): episodic memory, migration sang namespace có cấu trúc, RAG
scope theo user, LangSmith trace loop.

## Kiến trúc

```
START → load_context → summarize → supervisor → <sub-agent> → reflection
          │  (MỚI: load thêm procedural                        │
          │   instructions từ store)                           │ accept / END
          ▼                                                     ▼
   state.instructions ──fold──► system_with_summary       extract_memory  (MỚI)
                                                                │ ghi best-effort
                                                                ▼
                                                               END
```

- **Read path (procedural):** `load_context` nhận thêm `runtime.store`, đọc
  `get_instructions(store, user_id)`, ghi vào `state["instructions"]`.
  `system_with_summary` fold field này vào một system message dẫn đầu duy nhất.
- **Write path (background):** node terminal mới `extract_memory` chạy sau khi đã
  có câu trả lời (các nhánh accept/END của reflection route vào đây). Node dùng
  **fast LLM** để trích durable prefs + standing instructions từ exchange cuối và
  upsert vào store. Best-effort; tắt hẳn ở FAST mode.

## Các quyết định chính

### D1 — Extraction chạy ở đâu: node terminal in-graph (không async fire-and-forget)

Chọn: một node `extract_memory` in-graph, đứng trước `END`.

- **Dễ test + nhất quán với checkpointer**; mirror đúng node `summarize` đang có.
- **Latency cảm nhận ≈ 0 với streaming**: sub-agent đã stream xong token câu trả
  lời trước khi reflection/extract chạy, nên user thấy reply trước; chỉ có tín hiệu
  "turn complete" bị trễ thêm đúng 1 lần gọi fast-LLM.
- **Có gate**: bỏ qua hoàn toàn khi `allow_memory_write` = false (FAST mode → chi
  phí 0), và **best-effort** (mọi lỗi đều nuốt, không bao giờ làm hỏng turn).
- Loại bỏ: async fire-and-forget trong router/stream endpoint — latency thấp hơn
  nhưng nằm ngoài graph, cần store handle riêng, không được checkpoint, và khó
  test. Ghi lại làm optimization tương lai nếu latency thành vấn đề.

### D2 — Extractor là pure function + node wrapper mỏng (mirror summarizer)

- `memory/extractor.py`: pure `extract_memories(messages, llm) -> ExtractedMemories`.
  Gửi `[SystemMessage(prompt), HumanMessage(last_exchange)]`, parse một JSON object
  nhỏ từ reply, trả về kết quả có kiểu. **Parse phòng thủ**: bất kỳ lỗi JSON/shape
  nào → kết quả rỗng (không ghi gì). Unit-test được mà không cần graph.
- `make_extract_memory_node(llm)` trong `agents/nodes.py`: đọc
  `runtime.context.allow_memory_write` (skip nếu false), gọi `extract_memories`,
  upsert kết quả vào `runtime.store`, trả `{}` (không đổi state).

Output shape:

```json
{
  "preferences": [{"key": "diet", "text": "vegetarian"}],
  "instructions": [{"key": "language", "text": "always reply in Vietnamese"}]
}
```

`preferences` → namespace `prefs` (đang có); `instructions` → namespace
`procedural` (mới). Chỉ xét **turn user + assistant cuối cùng**, giữ prompt nhỏ và
tránh trích lại history cũ.

### D3 — Store: tổng quát hoá namespace, thêm helper procedural (back-compat)

`memory/store.py`:

- `_namespace(user_id, kind)` → `("users", user_id, kind)`; giữ `_prefs_namespace`
  gọi lại helper này để các entry prefs cũ không đổi.
- Thêm `upsert_instruction(store, user_id, key, value)` và
  `get_instructions(store, user_id, *, query=None, limit=10)` cho kind
  `"procedural"`. Value giữ shape `{"text": ...}` để semantic index tiếp tục chạy.
  `upsert_preference` / `search_preferences` đang có giữ nguyên.

### D4 — Procedural injection qua `system_with_summary` đang có

- `agents/state.py`: thêm `instructions: str` vào `TravelAgentState`;
  `system_with_summary` fold field này **trước** summary:
  `"Standing traveller instructions:\n{instructions}"`. Trả `base` nguyên vẹn khi
  cả ba field đều rỗng (user mới không đổi hành vi).
- `agents/nodes.py`: `load_context_node(state, runtime)` (thêm param `runtime` để
  LangGraph inject) đọc `runtime.store`, gọi `get_instructions`, join các text, trả
  `{"instructions": ...}`. Best-effort; thiếu store / không có user → `{}`.

### D5 — Context gate: `allow_memory_write`

`agents/context.py`:

- Thêm `allow_memory_write: bool = True` vào `AgentContext`.
- `_MODE_POLICY`: FAST → `False`; BALANCED / DEEP → `True`.
- `resolve_agent_context` truyền qua. **Không gate theo tier** — memory là một UX
  differentiator rẻ; free user vẫn giữ. (Quyết định product: xác nhận trước khi
  wiring kiểu D.1; mặc định để bật.)

### D6 — Wiring graph (gọn)

`agents/graph.py`:

- Thêm node `extract_memory`: `make_extract_memory_node(pick("extract_memory"))`,
  tier fast, static edge `extract_memory → END`.
- `agents/nodes.py` reflection: hai nhánh `Command(goto=END)` (accept + no-revision)
  đổi thành `Command(goto="extract_memory")`. Nhánh REVISE loop-back giữ nguyên.
  `plan` huỷ giữ `goto=END` (không có gì để trích khi huỷ).

### D7 — Prompt

- `prompts/memory_extraction/v1.md` — yêu cầu model emit đúng JSON shape, chỉ trích
  tín hiệu **durable** (preference ổn định, standing instructions), bỏ qua chi tiết
  trip 1 lần, và trả array rỗng khi không có gì đủ tiêu chuẩn.
- `prompts/active.yaml` — thêm `memory_extraction: 1`.

## Rủi ro & giảm thiểu

- **Latency** — thêm 1 lần gọi fast-LLM mỗi non-FAST turn. Giảm thiểu bằng streaming
  (câu trả lời đã hiện) + skip ở FAST mode. Nếu vẫn vướng → chuyển sang async (nhánh
  bị loại ở D1).
- **Extraction rác làm bẩn memory** — parse JSON phòng thủ + prompt "durable only" +
  upsert theo `key` (ghi đè, không append) giới hạn blast radius.
- **Provider-agnostic / tests** — `extract_memories` là pure và chạy bằng FakeLLM;
  fake trả JSON canned chứng minh path ghi, fake trả rỗng chứng minh path no-op.

## Test matrix (proof)

| Hành vi | Check |
|---|---|
| store: upsert + recall instruction | `tests/memory/test_store_instructions.py` |
| extractor: JSON hợp lệ → kết quả có kiểu | `tests/memory/test_extractor.py` (FakeLLM) |
| extractor: rác/rỗng → kết quả rỗng (không raise) | same |
| node: ghi prefs + instructions vào store | `tests/agents/test_memory_extraction.py` |
| node: `allow_memory_write=False` → không gọi LLM, không ghi | same |
| injection: instructions trong store → xuất hiện trong system prompt | `tests/agents/test_procedural_injection.py` |
| context: FAST → `allow_memory_write=False`; BALANCED/DEEP → True | `tests/agents/test_context_*.py` |
