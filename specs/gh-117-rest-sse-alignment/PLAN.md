---
slug: gh-117-rest-sse-alignment
status: shipped
owner: opencode
created: 2026-08-07
---

# Align REST and SSE final answer on multi-intent turns

## 1. Motivation

`/agent/chat` (REST) trả lờ bị trùng lặp trên các lượt multi-intent vì nó ghép tất cả câu trả lờ của từng sub-agent. Trong khi đó `/agent/stream` (SSE) chỉ giữ lại câu trả lờ của sub-agent cuối cùng (do `reset` vô tình kích hoạt khi đổi namespace). Hai đường dẫn không đồng nhất.

Nguyên nhân gốc rễ: bộ lắp ráp câu trả lờ giả định mỗi sub-agent chỉ đóng góp một phần, nhưng thực tế mỗi sub-agent là một vòng ReAct đầy đủ, tái tạo toàn bộ câu trả lờ cho lượt.

Issue: <https://github.com/minhtran3124/travel-pi/issues/117>

## 2. Non-goals

- Không thay đổi prompt để sub-agent chỉ trả lờ một phần (sản phẩm thay đổi lớn hơn).
- Không thay đổi supervisor/ledger routing.

## 3. Success Criteria

- `/agent/chat` trả về một câu trả lờ duy nhất, không trùng lặp, cho lượt multi-intent.
- `/agent/chat` và `/agent/stream` cho cùng một lượt phải có văn bản cuối cùng giống nhau.
- Reflection revise vẫn giữ bản sửa đổi cuối cùng, loại bỏ bản nháp cũ.

## 4. Tasks

### Task 1.1 — Fix REST reply assembly (wave 1)

- **Files:** `apps/api/app/routers/agent.py`
- **Action:** Thay thế logic ghép tất cả `AIMessage` bằng logic lấy `AIMessage` cuối cùng trong lượt (sau HumanMessage gần nhất), có `content` và không có `tool_calls`. Đây là câu trả lờ cuối cùng từ sub-agent cuối hoặc bản revise cuối của reflection.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/api/agent/test_agent_chat.py::test_chat_multi_intent_turn_returns_both_subagent_answers -x`
- **Done:** Test cũ được cập nhật để phản ánh hành vi mới (chỉ còn câu trả lờ cuối cùng).

### Task 1.2 — Make SSE reset explicit on sub-agent handoff (wave 1)

- **Files:** `apps/api/app/streaming/mapper.py`
- **Action:** Phát `reset` có chủ đích khi sub-agent thay đổi (không chỉ khi `AIMessage.id` thay đổi trong cùng một sub-agent). Giữ lại `reset` cho reflection revision. Điều này làm SSE đồng ý với REST theo nguyên tắc "câu trả lờ cuối thắng".
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/api/agent/test_stream_events.py -x`
- **Done:** Các test stream hiện tại vẫn pass; reset được phát đúng khi chuyển sub-agent.

### Task 1.3 — Update multi-intent REST test expectation (wave 1)

- **Files:** `apps/api/tests/api/agent/test_agent_chat.py`
- **Action:** Sửa `test_chat_multi_intent_turn_returns_both_subagent_answers` để assert rằng reply chỉ chứa câu trả lờ của sub-agent cuối cùng, không còn câu của sub-agent đầu tiên. Đổi tên test cho phản ánh hành vi mới.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/api/agent/test_agent_chat.py::test_chat_multi_intent_turn_returns_last_subagent_answer -x`
- **Done:** Test đổi tên và pass với kỳ vọng mới.

### Task 1.4 — Add REST/SSE parity test (wave 1)

- **Files:** `apps/api/tests/api/agent/test_agent_chat.py`
- **Action:** Thêm test mới dùng cùng một `FakeLLM` script cho cả `/agent/chat` và `/agent/stream`, sau đó assert văn bản cuối cùng của hai đường dẫn bằng nhau trên một lượt multi-intent.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/api/agent/test_agent_chat.py::test_chat_and_stream_yield_same_final_answer_for_multi_intent -x`
- **Done:** Test mới pass, chứng minh hai đường dẫn đồng nhất.

### Task 1.5 — Add mapper reset-on-handoff test (wave 1)

- **Files:** `apps/api/tests/api/agent/test_stream_events.py`
- **Action:** Thêm test mới xác nhận `stream_agent_events` phát `reset` khi chuyển từ `planner` sang `concierge` trong cùng một lượt.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/api/agent/test_stream_events.py::test_mapper_emits_reset_on_subagent_handoff -x`
- **Done:** Test mới pass.

### Task 1.6 — Run full suite (wave 2)

- **Files:** all
- **Action:** Chạy toàn bộ test suite của `apps/api` để phát hiện hồi quy.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/ -q`
- **Done:** Toàn bộ test pass.

## 5. Risks

- UI SSE có thể thấy câu trả lờ của sub-agent trước bị xóa khi sub-agent sau bắt đầu. Đây là hành vi mong muốn vì mỗi sub-agent tái tạo toàn bộ câu trả lờ.
- Nếu tương lai muốn ghép các phần từ nhiều sub-agent, cần đổi cả REST và SSE cùng lúc.

## 6. Status Log

- 2026-08-07: Plan created.
