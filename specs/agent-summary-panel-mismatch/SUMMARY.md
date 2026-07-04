<!--
  Canonical SUMMARY.md shape. Header block is machine-read (risk-corroboration.sh + trust ledger).
  Keep the header fields present and on their own lines.
-->

# agent-summary-panel-mismatch — Summary

Lane: normal
Confidence: high
Reason: Hai flag được kích hoạt (existing-behavior — sửa hành vi `search_places` đã có test; weak-proof — chưa có test khẳng định text của agent bám vào kết quả tool). Không có hard gate; nguyên nhân đã xác định trong code nên hướng sửa rõ ràng.
Flags: existing-behavior, weak-proof
Affects: agent grounding — model-facing summary của `apps/api/app/tools/place_tools.py::search_places` (chuỗi content mà LLM nhìn thấy, KHÔNG phải shape của SSE `panel` event hay REST API).
Input-type: change request

> `Lane` quyết định mức độ ceremony (bao nhiêu bằng chứng). `Confidence` quyết định việc có
> cần hỏi người dùng hay không. Hard gate ép `high-risk`. Confidence thấp hoặc hướng đi mơ hồ
> thì escalate bất kể lane — xem `rules/orchestration.md`.

### Intent

<!-- Yêu cầu gốc của user, nguyên văn tại thời điểm intake. Không diễn giải. -->

> review bug, summary in chatbox does not match with panel side info

Kèm ảnh chụp màn hình: panel **Places** ("Da Nang · cafe", 4 kết quả) liệt kê Lighthouse Coffee
Roaster, Roost Coffee Roasters, XLIII Factory Coffee Roaster, O2o First Roast — trong khi phần
text của **Travel Assistant** trong chatbox lại liệt kê 4Ps Coffee, Cong Ca Phe, The Coffee House,
Phuc Long Coffee & Tea (hai tập hoàn toàn khác nhau).

## What changed

Đã triển khai **phương án A** trên nhánh `fix/agent-summary-panel-mismatch`. `search_places`
(`apps/api/app/tools/place_tools.py`) giờ nhúng tên các place top (highest-rated first, kèm
rating) vào **chuỗi content model-facing** — cùng một `top_results` mà panel dùng — kèm chỉ dẫn
"recommend only from these by name — do not invent other places". LLM nay bám vào đúng danh sách
panel thay vì bịa chuỗi cà phê từ training data. Thêm regression test
`test_search_places_content_names_panel_places` khẳng định mọi tên trong panel đều xuất hiện
trong content. Không đổi shape của SSE `panel` event / artifact / REST API.

### Rationale

Nguyên nhân gốc đã xác nhận trong `apps/api/app/tools/place_tools.py:142-146`: khi có kết quả,
model-facing `summary` chỉ là `"{total_count}{what} place(s){where}. The full list is in the
Places panel."` — **không chứa tên place thực tế**. Tên các quán (Lighthouse, Roost, …) chỉ nằm
trong **panel artifact** (`panel_result(...)`), thứ mà LLM không đọc. Vì content không mang tên,
LLM bịa ra các chuỗi cà phê nổi tiếng từ training data (4Ps, Cong Ca Phe, …) → text lệch với panel.
Hướng sửa mặc định: đưa tên top places (đã có sẵn trong `top_results`) vào chuỗi summary để LLM
bám (ground) vào đúng dữ liệu tool trả về. Liên quan: [[min-50-agent-stale-tool-results]],
[[places-side-panel]], [[agent-summary-injection]].

### Alternatives considered

<!-- Sẽ chốt ở bước planning; ghi lại các nhánh để không mất dấu. -->

- **A (đề xuất):** Bổ sung tên top places vào model-facing `summary` của `search_places` — sửa 1
  chỗ, đúng lớp gốc, panel & text cùng nguồn `top_results`.
- **B:** Siết system prompt của concierge/subagent để cấm bịa place, buộc dùng kết quả tool — bổ
  trợ nhưng không giải quyết gốc (content vẫn thiếu tên → LLM vẫn thiếu dữ liệu để bám).
- **C:** Cả A + B.

### Deviations

- none

### Verify

<!-- Sẽ điền khi fix xong: test khẳng định content của search_places chứa tên top places. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| place tools (unit + regression) | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_place_tools.py -q` | 0 | 19 passed (incl. new `test_search_places_content_names_panel_places`) |
| flow suites | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_concierge_dedup.py tests/streaming/test_places_panel.py -q` | 0 | 4 passed |
| lint | `cd apps/api && ../../.venv/bin/ruff check app/tools/place_tools.py tests/tools/test_place_tools.py` | 0 | All checks passed |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
