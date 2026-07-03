<!--
  Canonical SUMMARY.md shape. Header block is machine-read (risk-corroboration.sh + trust ledger).
  Keep the header fields present and on their own lines.
-->

# min-50-agent-stale-tool-results — Summary

Lane: normal
Confidence: medium
Reason: Hai flag được kích hoạt (hành vi agent đã có test bao phủ + thiếu bằng chứng cho đường dedup ở lượt hỏi tiếp theo); không có hard gate.
Flags: existing-behavior, weak-proof
Affects: agent tool-calling — concierge subagent (`app/agents/subagents/concierge.py`) + place search tool (`app/tools/place_tools.py::search_places` / `PlaceService`)
Input-type: change request

> `Lane` quyết định mức độ ceremony (bằng chứng cần có). `Confidence` quyết định việc có cần hỏi người dùng hay không.
> Không có hard gate; ý định rõ ràng nên PROCEED — nhưng có một design fork thật sự
> (≥2 phương án khả thi) và sẽ được giải quyết ở bước planning, kèm đề xuất.

### Intent

<!-- MIN-50, nguyên văn từ Linear issue. -->

**Tiêu đề:** Agent lặp lại tool call và trả về kết quả cũ khi người dùng hỏi "còn chỗ nào khác không?"

**Vấn đề:** Khi người dùng hỏi về chỗ ăn ngon, subagent (concierge?) gọi tool để lấy kết quả — lần đầu thì ổn. Nhưng khi người dùng hỏi tiếp "còn chỗ nào khác không?", model gọi lại tool nhưng trả về **y hệt kết quả trước đó** thay vì gợi ý chỗ mới/khác.

**Tác động:** Trải nghiệm hội thoại bị lặp lại — người dùng cảm thấy agent "không lắng nghe" câu hỏi tiếp theo và phải tự giải thích lại toàn bộ ngữ cảnh.

**Nguyên nhân nghi ngờ (cần xác nhận khi triage):**
- Tool trả về kết quả **deterministic** theo từng query (hash-based seed), nên cùng input → cùng output; tool hiện chưa có tham số để loại trừ các item đã trả về ở lượt trước.
- Model không được prompt (hoặc không có cách) để truyền "đã gợi ý A, B, C rồi" vào tool call kế tiếp (thiếu injected state / conversation memory làm tool-arg input).
- Có thể liên quan đến tool-calling orchestration trong ReAct subagent (`app/agents/`) — cần kiểm tra tool schema hiện tại trong `app/tools/` (đặc biệt domain "dining"/"destinations") và cách state/checkpointer mang theo lịch sử.

**Hướng đề xuất (thảo luận khi triage):**
1. Thêm tham số `exclude_names` / `offset`/`page` vào tool gợi ý ăn uống để agent có thể chủ động yêu cầu "kết quả khác."
2. Prompt/system instruction cho subagent: khi người dùng hỏi tiếp kiểu "chỗ khác/thêm nữa", agent phải truyền danh sách item đã gợi ý vào tool call thay vì gọi lại y hệt.
3. Cân nhắc: nếu tool đã trả đủ (N) kết quả ở lần gọi đầu, lượt sau nên trả phần còn lại của cùng result set (pagination) thay vì gọi lại tool.

**Triage TODOs:**
- Xác định tool/router cụ thể xử lý query "chỗ ăn ngon" (dining/food recommendation tool trong `app/tools/`).
- Xác định subagent nào xử lý (concierge?) và system prompt hiện tại có đề cập gì đến việc tránh lặp kết quả không.
- Viết reproduction test: hai lượt liên tiếp, assert lượt 2 không trùng lượt 1 (hoặc có truyền exclude param).

## What changed

Implemented Direction 1 end-to-end (4 tasks / 3 waves, PLAN.md):
- `PlaceService.search_places` gains `exclude_names: list[str] | None` kwarg, filtering the
  already-sorted result set by exact name match (`app/services/place_service.py`).
- `search_places` tool (`app/tools/place_tools.py`) threads `exclude_names` through
  `SearchPlacesArgs` → the service call.
- New concierge prompt `v4.md` (active.yaml bumped 3→4) instructs the model to pass
  previously-suggested names as `exclude_names` on a follow-up "other places?" question.
- `tests/agents/test_concierge_dedup.py` proves a scripted `FakeLLM` tool call carrying
  `exclude_names` produces a `ToolMessage` with the excluded names absent.

19/19 tests pass across the four touched/new test files.

### Rationale

User chọn **Direction 1** (tham số `exclude_names` trên `search_places`) trong 3 hướng đã nêu ở
Alternatives — tool-level, deterministic, test được mà không cần LLM thật. PLAN.md đã soạn xong
(4 task / 3 wave): 1.1 lọc `exclude_names` trong `PlaceService.search_places`; 1.2 bump prompt
concierge lên v4 với chỉ dẫn truyền `exclude_names` khi user hỏi follow-up; 2.1 thêm field vào
`SearchPlacesArgs`/`search_places` tool (phụ thuộc 1.1); 3.1 test end-to-end chứng minh tên đã
loại trừ không xuất hiện lại trong `ToolMessage` (phụ thuộc 1.2 + 2.1).

Đính chính so với intake: `search_places` không dùng seed MD5-hash như flight/hotel — chỉ là
DB query + sort thuần, nên ràng buộc "không đổi seed algorithm" trong CLAUDE.md không áp dụng ở
đây (xác nhận qua Explore agent + đọc trực tiếp `place_service.py`).

### Alternatives considered

- **Direction 1 — tham số `exclude_names` trên `search_places`:** ở mức tool, deterministic, test được mà không cần LLM; agent truyền tên đã gợi ý trước đó để lấy kết quả mới.
- **Direction 2 — chỉ đổi prompt (chỉ dẫn concierge truyền các item đã gợi ý):** không đổi tool, nhưng phụ thuộc vào việc LLM tuân thủ và khó test deterministic.
- **Direction 3 — pagination (`offset`/`page`, trả phần còn lại của cùng set):** UX gọn nhưng thay đổi ngữ nghĩa của result set và cần thứ tự ổn định qua các lượt.
- Ràng buộc đang có: CLAUDE.md cấm thay đổi seed algorithm deterministic — filter exclude/offset chạy *sau* khi generate thì tuân thủ điều này; re-seed thì không.
- Lưu ý về injection: `search_places` dùng `@tool(args_schema=...)` tường minh; theo MIN-46 điều này **phá vỡ `InjectedState`** nếu cố auto-inject các lượt trước làm tool arg — xem `explicit-args-schema-breaks-langgraph-injection`. Truyền `exclude_names` tường minh từ LLM sẽ tránh được vấn đề này.

### Deviations

- Rule 3 — `tests/agents/test_concierge_dedup.py` imports `agent_db` directly from
  `tests.tools.conftest` (`from tests.tools.conftest import agent_db  # noqa: F401`).
  PLAN.md assumed the fixture was ambiently available, but pytest fixtures in a sibling
  directory's `conftest.py` (`tests/tools/`) are not visible to `tests/agents/` (no shared
  ancestor conftest defines it). Explicit import is the minimal fix, no new files.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Task 1.1 | `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_place_service.py -v` | 0 | 2 passed |
| Task 1.2 | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_concierge_prompt.py tests/prompts/test_registry.py -v` | 0 | 7 passed |
| Task 2.1 | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_place_tools.py -v` | 0 | 15 passed |
| Task 3.1 | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_concierge_dedup.py -v` | 0 | 1 passed |
| Success criteria | `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_place_service.py tests/prompts/test_concierge_prompt.py tests/tools/test_place_tools.py tests/agents/test_concierge_dedup.py -v` | 0 | 19 passed |

### Rollback

- `git revert <sha>`

### Harness-Delta

- không có
