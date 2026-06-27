# Nghiên cứu — Tool của mizumi-ai so với tool agent của travel-pi

**Ngày:** 2026-06-27
**Phạm vi:** So sánh 3 tool của chatbot mizumi-ai với các tool agent trong repo này, quyết định
nên sao chép / học hỏi / cải tiến cái nào.

Nguồn đã xem:
- `mizumi-ai/chatbot/src/agents/tools/{weather,directions,search_nearby}.py` (+ các service của chúng)
- `apps/api/app/tools/*` và `apps/api/app/services/routing_service.py` (repo này)

---

## 1. Tóm lược hai kiến trúc

| | mizumi-ai | travel-pi (repo này) |
|---|---|---|
| Framework | LangGraph, graph concierge khách sạn | LangGraph supervisor + 5 sub-agent ReAct |
| Tool trả về | `Command(update=..., goto="assistant")` — đổi state graph + UI | dict/list JSON thuần qua `dump()`; lỗi → `ToolException` |
| Nguồn dữ liệu | **API live bên ngoài** (Google Maps, Google Places, Open-Meteo) | **mock/DB-seed**, trừ Open-Meteo thật (thời tiết) + ORS thật (định tuyến) |
| Vị trí | toạ độ khách sạn được inject từ state (`origin="hotel"`) | city/place dạng text tự do, được resolve mờ (fuzzy) trong service |
| Định dạng cho LLM | theo từng tool (weather còn có lượt LLM "humanize" thứ 2 riêng) | tập trung — `build_subagent` chèn sẵn `communication_style` |
| Registry tool | không có; danh sách tool ráp theo từng node graph | `registry.py` — `TOOLS_BY_DOMAIN` + metadata MCP `readOnly`/`destructive` |

Khác biệt cốt lõi về triết lý: **mizumi gọi API bên thứ ba thật; travel-pi là backend mock theo
thiết kế** (CLAUDE.md: "mọi thứ đều giả lập trừ Open-Meteo không cần key và `/*/route`").
Ràng buộc này quyết định phần lớn các khuyến nghị bên dưới — chúng ta **không** muốn đưa thêm
phụ thuộc vào Google Maps/Places.

---

## 2. So sánh từng tool

### 2a. Thời tiết — ✅ ngang bằng, chỉ học vài điểm nhỏ

- **mizumi** `lookup_weather` (`weather.py:138`): Open-Meteo async → bộ format suy diễn mã WMO→chữ
  → **lượt LLM thứ 2** với `WEATHER_SUMMARY_PROMPT` để làm tự nhiên + gợi ý hoạt động.
- **travel-pi** `get_weather` / `get_packing` / `get_air_quality` (`weather_tools.py`): cũng dùng
  Open-Meteo thật, async, lỗi → `ToolException`. Vốn đã phong phú hơn (có packing + AQI). Việc làm
  tự nhiên hoá được xử lý một lần ở tầng agent (`communication_style`), nên lượt LLM thứ 2 của
  mizumi sẽ thừa và chậm hơn ở đây.
- **Kết luận:** giữ cái của mình. Điểm học (tuỳ chọn): "gợi ý hoạt động theo điều kiện thời tiết"
  của mizumi là điểm chạm sản phẩm hay — nhưng đó là việc của prompt, không phải của tool, và có
  thể đặt trong prompt concierge/planner thay vì thêm tool mới.

### 2b. Chỉ đường / định tuyến — ❌ THIẾU (việc cần làm thực sự duy nhất)

- **mizumi** `lookup_directions` (`directions.py:22`): Google Directions API, lối tắt
  `origin="hotel"`, trả về thời lượng/khoảng cách + link sâu Google Maps, đẩy bản đồ lên UI sớm.
- **travel-pi**: `routing_service.py` **đã có đầy đủ** — định tuyến đường bộ ORS thật với fallback
  haversine offline, cache trong tiến trình, leg theo từng phương tiện (đi bộ/xe đạp/ô tô),
  phương tiện gợi ý, resolve được cả **place** (`get_place_route`) lẫn **city** (`get_city_route`).
  Nó phục vụ `GET /places/route` và `GET /cities/route` — **nhưng chưa được bọc thành tool agent.**
  `grep routing_service app/tools/` → không có gì.
- **Kết luận:** **SAO CHÉP Ý TƯỞNG, TÁI DÙNG SERVICE CỦA MÌNH.** Hiện agent không thể trả lời "từ
  khách sạn tới cầu Rồng đi thế nào / bao xa?" dù backend làm được. Hãy bọc `RoutingService` thành
  một (hoặc hai) tool async. Không thêm phụ thuộc bên ngoài — ORS đã được nối sẵn.

### 2c. Tìm gần đây / địa điểm — ✅ ngang bằng, khác biệt là do thiết kế

- **mizumi** `search_nearby_location` / `search_places` / `find_place` (`search_nearby.py`): Google
  Places live, text tự do + enum loại địa điểm, tính khoảng cách Haversine cục bộ, thẻ gợi ý UI.
- **travel-pi**: `search_places` (lọc theo city/category/rating/price) + `nearby_places` (bán kính
  quanh một place đã biết, haversine, gần nhất trước) + `resolve_place` + `parse_nl_query` +
  `list_place_categories` (`place_tools.py`). Dựa trên DB seed, theo thiết kế.
- **Kết luận:** giữ cái của mình — dùng Google Places sẽ phá vỡ hợp đồng mock-first. Hai pattern
  đáng học với chi phí thấp:
  1. **Enum-trong-docstring**: mizumi nhét bộ từ vựng loại địa điểm hợp lệ vào docstring để LLM
     chọn đúng tham số. Chúng ta đã có bản tương đương *động* tốt hơn (tool `list_place_categories`)
     — không cần đổi, chỉ cần đảm bảo prompt planner/concierge trỏ model đến nó.
  2. **`nearby_places` chỉ neo vào một place id có sẵn.** mizumi tìm được quanh toạ độ bất kỳ. Cải
     tiến nhỏ tuỳ chọn: cho `nearby_places` neo thêm vào **city** (tâm thành phố) để hỏi "gì đó gần
     Đà Nẵng" mà không cần resolve một place cụ thể trước. Ưu tiên thấp.

---

## 3. Các pattern đáng học (xuyên suốt)

| Pattern (mizumi) | Đã có chưa? | Hành động |
|---|---|---|
| Fallback nhẹ nhàng, đúng giọng thương hiệu ở mọi nhánh lỗi | Có — `ToolException` → `ToolMessage` có thể phục hồi | không cần |
| Tính khoảng cách Haversine cục bộ (không tin API) | Có — `core/geo.haversine_km`, dùng trong routing + nearby | không cần |
| Enum-trong-docstring để giới hạn tham số LLM | Tương đương: tool `list_place_categories` | xác nhận prompt có dùng |
| Stream `map_data` lên UI sớm | Chưa (phụ thuộc FE) | hoãn — chỉ làm nếu web FE muốn vẽ bản đồ |
| Lượt LLM "humanize" thứ 2 mỗi tool | Đã làm tập trung ở tầng agent | bỏ qua (thừa) |
| API key bị commit trong `config.py:67` (lỗi của mizumi) | Không liên quan | tránh — giữ ORS key chỉ trong env |

---

## 4. Tổng hợp khuyến nghị

1. **Xây tool chỉ đường/định tuyến** bọc `RoutingService` có sẵn. Đây là lỗ hổng năng lực thực sự
   duy nhất. → PLAN.md.
2. *(tuỳ chọn, ưu tiên thấp)* Mở rộng `nearby_places` để nhận neo theo city.
3. *(chỉ prompt, không code)* Đảm bảo prompt concierge/planner hướng model tới
   `list_place_categories` và (sau khi thêm) tool định tuyến, cùng các gợi ý hoạt động theo thời tiết.

Mọi thứ còn lại đã ngang hoặc hơn mức mizumi, với khác biệt có chủ đích là travel-pi giữ
mock/DB-first và tránh phụ thuộc vào API Google.
