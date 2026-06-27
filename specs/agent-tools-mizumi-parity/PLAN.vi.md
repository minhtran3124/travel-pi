---
slug: agent-tools-mizumi-parity
status: proposed
owner: Minh Tran
created: 2026-06-27
---

# Tool agent — ngang bằng mizumi (tool chỉ đường/định tuyến)

> Lưu ý: Các khối `<task>`, lệnh `<verify>`, đường dẫn file và frontmatter `slug` được giữ nguyên
> tiếng Anh vì chúng do máy đọc/chạy. Chỉ phần diễn giải được dịch.

## 1. Động cơ

So sánh với các tool của mizumi-ai (xem `RESEARCH.md`) cho thấy repo này đã ngang hoặc hơn về
**thời tiết** và **tìm gần đây/địa điểm**, với một khác biệt có chủ đích (giữ mock/DB-first, không
dùng API Google). Lỗ hổng năng lực thực sự duy nhất: **agent chưa có tool chỉ đường/định tuyến**,
dù `app/services/routing_service.py` đã cung cấp định tuyến đường bộ OpenRouteService thật (kèm
fallback haversine offline) và đã expose qua `/places/route` và `/cities/route`.

Mục tiêu: bọc `RoutingService` có sẵn thành (các) tool agent để trợ lý trả lời được "từ A tới B bao
xa / bao lâu, đi bằng phương tiện nào?" — sao chép *ý tưởng* của mizumi, tái dùng *service* của
mình, **không** thêm phụ thuộc bên ngoài.

## 2. Không nằm trong phạm vi (non-goals)

- Không tích hợp Google Maps / Google Places (phá vỡ hợp đồng mock-first).
- Không thêm phụ thuộc bên ngoài — ORS đã nối sẵn; fallback offline đã có.
- Không stream bản đồ UI (kiểu đẩy `map_data` của mizumi) — hoãn cho tới khi web FE cần vẽ tuyến.
- Không thêm lượt LLM "humanize" thứ 2 cho mỗi tool — việc làm tự nhiên giữ tập trung ở
  `communication_style`.
- Không đổi routing service, cache, schema, hay các endpoint HTTP hiện có.

## 3. Tiêu chí thành công

- Tool `get_route` (place→place) gọi được bởi sub-agent planner và concierge.
- Tool `get_city_route` (city→city) cho câu hỏi liên thành phố kiểu "Hà Nội cách Đà Nẵng bao xa".
- Cả hai đều async (service async), đều tái dùng `session_scope()`, đều map `AppError`→`ToolException`.
- Đăng ký trong `registry.py` với `readOnly: true`, hiển thị qua `/agent/manifest`.
- Test chạy được offline (không có ORS key → đi nhánh ước lượng haversine), bộ test vẫn xanh.

## 4. Công việc (Tasks)

### Task 1.1 — Thêm tool định tuyến bọc RoutingService

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/tools/routing_tools.py</files>
  <action>Tạo routing_tools.py theo mẫu weather_tools.py (async) + place_tools.py (session_scope). Định nghĩa 2 hàm @tool async:
- get_route(origin_place_id: str, destination_place_id: str) -> dict — mở `with session_scope() as s:`, gọi `await RoutingService(s).get_place_route(origin_place_id, destination_place_id)`, trả về `dump(...)`. Docstring: giải thích trả về khoảng cách + thời lượng theo từng phương tiện (đi bộ/xe đạp/ô tô), một phương tiện gợi ý, và km đường chim bay; nhận place id hoặc mã ngắn PLC-XXXX; lưu ý place id không tồn tại hoặc không có toạ độ sẽ raise (gợi ý dùng GET /places/search). Chất lượng docstring noi theo search_places.
- get_city_route(origin_city: str, destination_city: str) -> dict — cùng dạng qua `get_city_route`; docstring lưu ý tên thành phố nhận fuzzy/chịu lỗi gõ (vd 'danang' -> 'Da Nang').
Cả hai bọc thân hàm trong `try/except AppError as e: raise ToolException(str(e)) from e`. Export `ROUTING_TOOLS = [get_route, get_city_route]`. Docstring module ghi rõ đây là wrapper cho service định tuyến ORS thật-hoặc-fallback (như weather, là một call ra ngoài thật).</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -c "from app.tools.routing_tools import ROUTING_TOOLS; print([t.name for t in ROUTING_TOOLS])"</verify>
  <done>Module import được; in ra ['get_route', 'get_city_route'].</done>
</task>
```

### Task 1.2 — Đăng ký tool định tuyến vào registry

```xml
<task id="1.2" wave="2">
  <files>apps/api/app/tools/registry.py</files>
  <action>Import ROUTING_TOOLS từ app.tools.routing_tools. Thêm vào nhóm domain planner và concierge trong TOOLS_BY_DOMAIN (planner: lịch trình/hậu cần; concierge: di chuyển thực địa). Cả hai tool đều read-only — KHÔNG thêm vào _WRITE hay _DESTRUCTIVE (mặc định _meta đã đánh dấu readOnly:true). Không thay đổi gì khác.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -c "from app.tools.registry import get_tools_for, TOOL_METADATA; assert 'get_route' in [t.name for t in get_tools_for('concierge')]; assert TOOL_METADATA['get_route']['readOnly'] and not TOOL_METADATA['get_route']['destructive']; print('ok')"</verify>
  <done>get_route có mặt trong nhóm concierge + planner; metadata readOnly true, destructive false.</done>
</task>
```

### Task 1.3 — Test cho tool định tuyến (nhánh offline)

```xml
<task id="1.3" wave="2">
  <files>apps/api/tests/tools/test_routing_tools.py</files>
  <action>Thêm test dùng fixture agent_db (offline: không có ORS key, nên service đi nhánh ước lượng haversine — không có mạng). Dùng asyncio.run(tool.ainvoke({...})) vì tool là async. Bao phủ:
- get_city_route giữa hai thành phố đã seed trả về dict có key 'legs', 'recommended_mode', 'straight_line_km', 'source' == 'estimate'; legs có 3 phần tử (đi bộ/xe đạp/ô tô).
- get_route giữa hai place id đã seed hợp lệ trong cùng thành phố trả về dict cùng dạng (resolve hai place id trước bằng PlaceService hoặc search_places).
- get_route với place id không tồn tại raise ToolException.
Assert theo dạng cấu trúc, không theo khoảng cách chính xác (dữ liệu seed có thể đổi).</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/tools/test_routing_tools.py -x</verify>
  <done>Mọi test tool định tuyến pass offline.</done>
</task>
```

### Task 1.4 — Hồi quy toàn bộ bộ test tool + agent

```xml
<task id="1.4" wave="3">
  <files>apps/api/tests/tools/</files>
  <action>Chạy bộ test tool + registry để xác nhận không hồi quy do nối dây registry mới (gồm cả test manifest/registry). Không kỳ vọng đổi code; chỉ sửa nếu số lượng tool mới làm hỏng một assertion trong test_tool_registry.py.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/tools/ -q</verify>
  <done>Toàn bộ bộ test tests/tools/ xanh.</done>
</task>
```

## 5. Rủi ro

- **Tool async + `session_scope` đồng bộ**: session chỉ được dùng *trước* lệnh `await` (resolve
  endpoint); call ORS dùng httpx, không dùng session DB, nên giữ session đồng bộ xuyên qua await là
  an toàn dưới asyncio đơn luồng. Giống cách chính routing_service được cấu trúc.
- **`test_tool_registry.py` có thể assert chính xác số lượng / tập tên tool** — Task 1.4 lo việc cập nhật.
- **`.env` OPENAI_API_KEY=test** có thể làm hỏng các test LLM không liên quan ở local (xem memory) —
  giới hạn lệnh verify trong `tests/tools/`, vốn không gọi LLM.
- Cải tiến tuỳ chọn neo-theo-city cho `nearby_places` (RESEARCH §2c) **ngoài phạm vi** lần này — tách
  ra file riêng nếu muốn.

## 6. Nhật ký trạng thái

- 2026-06-27 — Dự thảo plan từ RESEARCH.md. Trạng thái: proposed (đề xuất).
