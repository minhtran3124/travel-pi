---
slug: memory-extraction-background
created: 2026-07-04
owner: Minh Tran
---

# Memory Extraction → Background — Intake

Lane: normal
Confidence: high
Reason: Đưa `extract_memory` (LLM call cuối lượt) ra khỏi critical path bằng FastAPI background task — chạm existing tested behavior của agent graph (flag 8) + rework test (flag 9); không hard gate.
Flags: existing-behavior, weak-proof
Affects: agent graph (`app/agents/graph.py`, `nodes.py`), agent routers (`app/routers/agent.py`) — no public-contract change (response shape của `/agent/chat`, `/agent/stream` giữ nguyên)
Input-type: Change request (maintenance / latency)
Route: /writing-plans → /using-git-worktrees → /subagent-driven-development
Escalate: no

## Intent

> check https://www.langchain.com/blog/running-subagents-in-the-background
> xem thử có thể áp dụng cho việc chạy agent extract ko?
>
> (follow-up) **dung background task**

User muốn đưa node `extract_memory` chạy nền để không thêm latency vào cuối mỗi lượt.
Đã đánh giá: cơ chế Agent Protocol trong blog là over-engineering cho một side-effect
fire-and-forget; user chọn hướng **FastAPI background task** gọn nhẹ trong stack hiện có.

## Rationale

`extract_memory` là node cuối trước `END` (`graph.py:141-155`): mỗi lượt (non-FAST) tốn
thêm 1 LLM call `extract_memories` trước khi `graph.ainvoke`/stream hoàn tất. Node này
best-effort, nuốt mọi lỗi, `return {}` — không có giá trị trả về cho graph. Vì vậy có thể
gỡ khỏi graph và schedule sau khi response đã gửi.

Phạm vi thay đổi:
- Tách logic node → service `run_extraction(...)` dùng chung.
- `nodes.py`: reflection 3 chỗ `goto="extract_memory"` → `END`; bỏ `make_extract_memory_node`.
- `graph.py`: bỏ node + edge; `destinations=(*SUBAGENTS, END)`; bỏ `pick("extract_memory")`.
- `constants.py`: cân nhắc giữ/gỡ `"extract_memory"` khỏi `FAST_AGENTS`.
- `routers/agent.py`: `/chat` schedule qua `BackgroundTasks` (skip khi `interrupt_pending`);
  `/stream` schedule sau khi stream xong, lấy final state qua `graph.get_state(cfg)`.

## Alternatives

- **Agent Protocol async subagents (blog)** — bác bỏ: task-queue + separate deployed agents
  quá nặng cho fire-and-forget memory write; repo là raw LangGraph in-process, không dùng
  LangGraph Platform.
- **Giữ node, defer trong graph** — bác bỏ: LangGraph node vẫn được await; không thoát critical path.

## Open design question (giải quyết ở PLAN)

Runner nền resolve model `extract_memory` thế nào để **test vẫn hermetic** (hiện FakeLLM
inject qua `build_graph(llm=, fast_llm=)`)? Ứng viên: stash resolved extract-llm lên
`app.state` lúc build graph, hoặc expose resolver. Plan agent phải đọc `tests/conftest`
+ cách test lấy graph/store trước khi chốt.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Full suite | `cd apps/api && make test` (`.env` aside) | 0 | 1237 passed |
| Runner unit | `pytest tests/memory/test_extraction_runner.py -x` | 0 | 6 passed |
| Graph rewire | `pytest tests/agents/test_depth_toggles.py tests/agents/test_supervisor.py -x` | 0 | reflection→END |
| /chat bg task | `pytest tests/api/agent/test_agent_chat.py -x` | 0 | 12 passed (skip on interrupt) |
| /stream bg task | `pytest tests/api/agent/test_stream_persistence.py -x` | 0 | 6 passed |

### Rollback

- `git revert 8dee139 170dbeb 104b406 7cd6471` (waves 4→1), hoặc bỏ branch `feat/memory-extraction-background` (chưa merge).
