# Roadmap: Chuẩn hóa dữ liệu → MCP / Agent layer

> Nguồn ý tưởng: deep-review hai repo `mauriceboe/TREK` và `itskovacs/trip` (2026-06-18).
> Thứ tự bắt buộc: **Phase A (chuẩn hóa dữ liệu) làm trước**, **Phase B (MCP/agent tools) làm sau**.
> Lý do: MCP tools chỉ phơi bày domain ra ngoài — nếu domain còn nghèo/chưa chuẩn hóa thì tool sẽ
> phải "vá" và sau này đổi schema sẽ phá vỡ tool. Làm domain giàu + ổn định trước, tool mới sạch.

**Quy ước thực thi:** mỗi mục lớn (A1, B3, …) là một feature riêng → chạy `/feature-intake` →
PLAN → TDD → review (spec + quality + correctness + intent) → PR vào `v2`. Cross-reference với
`AGENT_IMPROVEMENTS.md` ghi trong ngoặc `[#n]`.

Legend: ⬜ chưa làm · 🔶 đang làm · ✅ xong · ⏸ tạm hoãn

---

## PHASE A — Chuẩn hóa & làm giàu dữ liệu (LÀM TRƯỚC)

### A0. ✅ Kỷ luật migration (nền tảng cho mọi mục Phase A) — DONE (`feat/migration-helper`)
- [x] Helper dùng chung `app/crud/_migrations.py`: `ensure_column` + `ensure_unique_partial_index`.
- [x] `crud/trip.py` + `crud/booking.py` `init_db` dùng helper (behavior-identical, full suite xanh).
- [x] Test trên DB cũ (ALTER path) — `tests/test_migrations.py`.
- [ ] (Quy ước tiếp theo) Mỗi mục Phase A sau PHẢI dùng `ensure_column` + thêm test legacy-DB.
- *Spec:* `specs/migration-helper/`. *Lane:* normal + migration waiver.

### A1. ✅ Thư viện POI tái sử dụng — places là entity hạng-nhất (M2M với trips) [#1] — DONE (`feat/poi-library`)
> Option A: catalog giữ nguyên + `saved_places` (mutable, soft-delete) + `trip_place_link` M2M. Saved CRUD + favorite/visited SET idempotent + dedup-by-distance + shortlist add/list/remove + `TripDetail.places`. Specs: `specs/poi-library/`. 594 tests.
> Ý tưởng cốt lõi từ `trip`: place tồn tại độc lập, được link vào nhiều trip qua bảng join,
> thay vì nhúng cứng trong `trip_items`.
- [ ] Quyết định mô hình: giữ `data/places.py` (seed tĩnh) làm catalog gốc, thêm bảng `saved_places`
      (place do user/agent lưu) — hoặc hợp nhất. Ghi quyết định vào SUMMARY (Rationale/Alternatives).
- [ ] Bảng join `trip_place_link` (trip_id, place_id, …) — M2M.
- [ ] `trip_items` tham chiếu `place_id` (đã có) → cho phép 1 place xuất hiện ở nhiều trip/ngày.
- [ ] CRUD + service: `link_place_to_trip`, `list_trip_places`, `unlink`.
- [ ] Trường POI giàu hơn cho saved place: `favorite`, `visited`, `links: list[str]`, `duration`.
- *Phụ thuộc:* A0. *Công sức:* Trung bình (schema + trips service). *Giá trị:* Cao nhất (nền cho `/agent/plan`).

### A2. ⬜ Place categories có màu/icon (phân loại do người dùng định nghĩa)
- [ ] Bảng `categories` (name, color, icon) — hoặc enum mở rộng nếu muốn giữ tĩnh.
- [ ] `place.category_id` (hiện đang là string `category`) — cân nhắc giữ string để không phá `PlaceCategory` enum hiện có; chỉ thêm `color`/`icon` metadata.
- [ ] Endpoint `GET /places/categories` (đã có) → trả thêm color/icon.
- *Phụ thuộc:* A1 (nếu gắn vào saved place). *Công sức:* Thấp-TB.

### A3. ⬜ Enum `status` cho itinerary item (`pending | booked | constraint | optional`) [#1]
> Một trường — agent diễn đạt được phần kế hoạch mềm vs cứng và ràng buộc bắt buộc.
- [ ] Thêm `TripItemStatus` enum vào `app/enums.py`.
- [ ] Thêm field `status` vào `TripItem` schema + cột `status` + migration.
- [ ] Cập nhật day-plan: hiển thị status; gap-detection có thể bỏ qua `optional`.
- [ ] Test: tạo item với từng status, default = `pending`.
- *Phụ thuộc:* A0. *Công sức:* Thấp. *Giá trị:* Cao (ngữ nghĩa lập kế hoạch cho agent).

### A4. ⬜ Ngày "trôi nổi"/chưa lên lịch (date của day cho phép null, sort `nulls_last`)
> Cho phép draft itinerary trước khi chốt ngày.
- [ ] Cho phép `TripDay`/day-plan có `date = None`; sắp xếp null xuống cuối.
- [ ] Điều chỉnh `day-plan` để xử lý ngày chưa có date (không tính travel-time/weather khi thiếu date).
- [ ] Test ordering + day-plan với ngày null.
- *Phụ thuộc:* mô hình day hiện tại. *Công sức:* Thấp-TB.

### A5. ⬜ Annotation booking theo ngày (type enum: flight/car/hotel/activity/generic + reference)
> Lớp "đã đặt gì trong ngày" nhẹ, tách khỏi `bookings` giao dịch hiện có.
- [ ] Quyết định: tái dùng `trip_item.booking_id` link tới booking thật, HAY thêm `TripBooking` nhẹ
      (label, type, reference, notes) theo từng ngày. Ghi rõ trade-off trong SUMMARY.
- [ ] Schema + CRUD + serializer.
- *Phụ thuộc:* A1. *Công sức:* TB.

### A6. ⬜ Chia chi phí: `paid_by` + `GET /trips/{id}/balance` [#12]
> Rollup ai-nợ-ai, bổ sung cho budget rollup đã có.
- [ ] Thêm `paid_by` vào trip item (ai trả).
- [ ] Service tính net balance theo member → `{member: net_amount}`.
- [ ] (Tùy chọn) thuật toán settlement greedy "ai trả ai" (ý tưởng từ TREK).
- [ ] Test: nhiều item, nhiều người trả, kiểm tra tổng = 0.
- *Phụ thuộc:* mô hình member (A1/A5 nếu cần member). *Công sức:* Thấp-TB.

### A7. ⬜ Packing list + checklist thành sub-resource có cấu trúc
> Nâng từ chuỗi phẳng (packing hiện tại) lên item query/tick được: `{text, qty, category, packed}`.
- [ ] Schema `TripPackingItem` / `TripChecklistItem` + CRUD.
- [ ] Nối với gợi ý packing đã có (`/weather/packing`) → seed list tự động.
- [ ] Endpoints CRUD dưới `/trips/{id}/packing`, `/trips/{id}/checklist`.
- *Phụ thuộc:* A0. *Công sức:* TB.

### A8. ⬜ Trường free-text: `notes` (trip + per-day) và `archival_review` (retro sau chuyến)
> Bề mặt "trí nhớ"/tổng kết cho agent.
- [ ] Thêm `notes` cho trip (nếu chưa) và cho từng day; `archival_review` cho trip.
- [ ] Migration + serializer + test.
- *Phụ thuộc:* A0. *Công sức:* Thấp.

### A9. ⬜ Provider ABC cho weather / routing / geocode (refactor chuẩn hóa)
> Một interface thay-thế-được, có trường `source`, helper `_request`/cache dùng chung.
- [ ] `BaseProvider` ABC; `weather_service` & `routing_service` kế thừa.
- [ ] Gom logic cache + degrade (offline haversine, source flag) vào base.
- [ ] Không đổi contract API; chỉ refactor — test hiện có phải xanh.
- *Phụ thuộc:* không (độc lập). *Công sức:* TB. *Lưu ý:* refactor → review kỹ, không phá behavior.

**🚩 Cổng chuyển phase:** chỉ bắt đầu Phase B khi A1 + A3 (tối thiểu) đã merge — đây là 2 thứ
MCP/agent layer phụ thuộc nhiều nhất.

---

## PHASE B — Agent & MCP layer (LÀM SAU)

### B1. ⬜ Metadata annotation cho mọi route (readOnly/destructive/idempotent/openWorld) [#4]
> Chuẩn MCP từ TREK — client biết call nào nguy hiểm.
- [ ] Định nghĩa annotation (vd dict trong decorator/registry) cho từng route.
- [ ] Phơi bày trong `/agent/manifest` (B4) và trong MCP tool registration (B11).
- *Phụ thuộc:* không (nhưng hữu ích nhất sau khi route ổn định). *Công sức:* Thấp.

### B2. ⬜ Context loader `GET /trips/{id}/summary` (nửa-đọc của `/agent/plan`)
> `get_trip_summary` của TREK: một call trả snapshot denormalize (days, places, budget rollup,
> gaps, bookings, status). Mình đã có các mảnh — chỉ cần ghép.
- [ ] Compose từ trip detail + day-plan + budget + gaps + (A1 places, A3 status, A6 balance).
- [ ] Test: 1 trip đầy đủ → 1 response đủ ngữ cảnh.
- *Phụ thuộc:* A1, A3, A6. *Công sức:* Thấp-TB. *Giá trị:* Cao.

### B3. ⬜ `POST /agent/plan` — endpoint composite [#3]
> Gộp 5+ call: top flights + hotels + places + weather summary + tips trong 1 response.
- [ ] Input `{origin, destination, start_date, end_date, adults, preferences?}`.
- [ ] Compose từ các service hiện có; trả về context mạch lạc cho agent.
- *Phụ thuộc:* B2 (chia sẻ shape summary). *Công sức:* TB.

### B4. ⬜ `GET /agent/manifest` + enum endpoints + scopes [#4]
> Manifest "agent-flavored" + tài liệu capability tier kiểu `domain:action` (từ TREK).
- [ ] Manifest viết tay: mô tả tool, "when to use / when NOT", ví dụ input.
- [ ] Enum endpoints: `/agent/airlines`, `/agent/amenities`, `/agent/tip-categories`.
- [ ] Khai báo scopes (`trips:write` ⊃ `trips:read`; `list_*`/`summary` luôn khả dụng).
- *Phụ thuộc:* B1. *Công sức:* TB.

### B5. ⬜ Quote-then-book qua trạng thái `pending → confirmed` [#2]
> Reservation tạo ở `pending`, agent show cho user, rồi `confirm` (mẫu TREK).
- [ ] `POST /flights/quote` & `/hotels/quote` → `quote_id` + giá khóa, trạng thái `pending`.
- [ ] `book` chấp nhận `quote_id` hoặc params; chuyển `pending → confirmed`.
- [ ] Tái dùng soft-cancel/idempotency đã có.
- *Phụ thuộc:* không bắt buộc Phase A. *Công sức:* TB.

### B6. ⬜ Activity booking — places trở nên đặt-được [#15]
> `POST /places/{id}/book` → loại booking thứ ba `activity`, mock availability theo id+datetime.
- [ ] BookingType `ACTIVITY`; deterministic availability như hotels.
- *Phụ thuộc:* A1 (place model). *Công sức:* TB.

### B7. ⬜ Resolver place đa hình URL/NL (`q` nhận free-text hoặc Maps link) [#10]
> Mở rộng NL search đã có; auto-gán category (ý tưởng `token_google_search` của `trip`).
- [ ] Một endpoint nhận free-text / URL / coords → place chuẩn hóa + category.
- [ ] URL Maps có thể stub deterministic (đúng tinh thần mock).
- *Phụ thuộc:* A1, A2. *Công sức:* TB.

### B8. ⬜ Xuất lịch `.ics` (iCalendar) cho itinerary + reservations
> Serializer thuần trên dữ liệu trip/day sẵn có — tiện ích thực tế cao.
- [ ] `GET /trips/{id}/export.ics`; service `export_trip_ics`.
- *Phụ thuộc:* day-plan (+ A4). *Công sức:* Thấp.

### B9. ⬜ Import places từ URL + batch ops [#Tier1.3]
> `import_places_from_url`, và `POST /bookings/batch` (all-or-nothing/partial) — dùng mẫu
> `asyncio.Semaphore(4)` + `gather(return_exceptions=True)` của `trip`.
- [ ] Import: dán list Maps → POI có cấu trúc (stub deterministic).
- [ ] Batch bookings với idempotency key per item.
- *Phụ thuộc:* A1, B5. *Công sức:* TB.

### B10. ⬜ `copy_trip` — nhân bản itinerary (reset packing/checklist)
> "Lên kế hoạch giống chuyến trước nhưng cho Lisbon."
- [ ] `POST /trips/{id}/copy`; deep-copy days/items/places link, reset trạng thái booking.
- *Phụ thuộc:* A1, A7. *Công sức:* Thấp-TB.

### B11. ⬜ MCP server wrapper — Resources vs Tools, compound tools, prompts [#5]
> Hạng mục lớn nhất; gói gọn mọi thứ trên thành MCP cho Claude/Agent SDK.
- [ ] Module `app/mcp/` (hoặc `mcp_server.py`) phơi bày endpoint hữu ích nhất làm MCP tools.
- [ ] **Resources (read-only)** map các GET (`trip://trips/{id}/summary`, `/budget`, `/categories`).
- [ ] **Tools (read-write)** map các POST/PUT/DELETE, tên `verb_noun` snake_case, mô tả 1 câu mệnh lệnh,
      delete ghi rõ "Cannot be undone."
- [ ] **Annotations** (B1) gắn vào từng tool.
- [ ] **Compound tools** (vd `create_and_assign_place`) — atomic + ghi rõ "when NOT to use".
- [ ] **Prompts** dựng-sẵn: `trip-summary`, `packing-list`, `budget-overview`.
- [ ] (Tùy chọn) scope enforcement theo B4.
- *Phụ thuộc:* phần lớn Phase A + B1/B2/B4. *Công sức:* Cao. *Để cuối cùng.*

---

## Thứ tự đề xuất (rút gọn)

1. **A0 → A1 → A3** (nền + POI library + status) — mở khóa cổng chuyển phase.
2. A4, A6, A8 (nhanh, giá trị tốt) song song/sau A1.
3. A2, A5, A7, A9 (làm giàu thêm; A9 refactor làm khi rảnh).
4. **🚩 Cổng:** A1+A3 merged → sang Phase B.
5. **B1 → B2 → B3** (annotations + summary + /agent/plan) — gói đòn bẩy cao nhất.
6. B4, B5, B6, B7, B8 (manifest, quote-then-book, activity, resolver, ics).
7. B9, B10 (import/batch, copy).
8. **B11 MCP wrapper — cuối cùng**, gói tất cả ra MCP.

## Status Log
- 2026-06-18 — Checklist khởi tạo từ deep-review TREK + trip. Tất cả mục: ⬜ chưa làm.
