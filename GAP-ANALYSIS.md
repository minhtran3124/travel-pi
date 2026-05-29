# API Gap Analysis — Travel Planner

Chỉ xét **phần API mà agent/tool sẽ gọi** — những use case trong đề bài cần API nào,
API nào đã có, API nào còn thiếu.

> **Cập nhật 2026-05-29:** Tất cả các gap đã được implement đầy đủ —
> `GET /tips`, `GET /places/route`, `GET /cities/route`, **và nhóm `trips`**
> (`POST`/`GET`/`GET list`/`PATCH`/`DELETE`), cộng thêm
> `GET /destinations/{city}/overview` (tổng hợp 1-call cho agent). Không còn
> gap nào. Các mục "❌ Chưa có" bên dưới giữ nguyên theo lịch sử — xem ghi chú
> inline cho trạng thái hiện tại.

---

## 1. Use case → API cần dùng

### UC1 — User hỏi thời tiết hôm nay
| API cần | Trạng thái |
|---|---|
| Lấy thời tiết hiện tại + forecast theo city | ✅ `GET /weather` |

→ **Đủ.**

### UC2 — User hỏi gợi ý lộ trình (route) cho một điểm du lịch
| API cần | Trạng thái |
|---|---|
| Danh sách địa điểm theo city (lọc category, rating, recommended) | ✅ `GET /places`, `GET /places/search` |
| Chi tiết một địa điểm | ✅ `GET /places/{id}` |
| **Sinh route gợi ý** (khoảng cách/thời gian giữa 2 điểm theo travel mode) | ✅ `GET /places/route`, `GET /cities/route` |
| **Sinh itinerary nhiều ngày** (gom địa điểm theo ngày/cụm/giờ mở cửa) | ❌ **Chưa có** (sẽ nằm trong nhóm `trips`) |

→ Route giữa hai điểm đã có. Vẫn **thiếu** itinerary tổng hợp nhiều ngày — thuộc nhóm `trips` ở mục 2.

### UC3 — User yêu cầu lên lịch trình đầy đủ (flight + hotel + places + tips)
| API cần | Trạng thái |
|---|---|
| Search / book flight | ✅ `GET /flights/search`, `POST /flights/book` |
| Search / book hotel | ✅ `GET /hotels/search`, `POST /hotels/book` |
| Check địa điểm | ✅ `GET /places/search` |
| Thời tiết cho ngày đi | ✅ `GET /weather` |
| **Local tips** (đi lại, an toàn, văn hóa, ăn uống, thời điểm nên đi) | ✅ `GET /tips` |
| **Trip/Itinerary tổng hợp** — gộp flight + hotel + lịch từng ngày thành 1 object lưu được | ✅ `POST /trips` |
| Lấy lại / cập nhật một trip đã tạo | ✅ `GET`/`PATCH`/`DELETE /trips/{id}` |

---

## 2. Danh sách API còn THIẾU

> **Tất cả đã xong** — gạch ngang, giữ lại để đối chiếu lịch sử.

| # | API đề xuất | Mục đích | Use case |
|---|---|---|---|
| 1 | ~~`GET /tips?city=...`~~ ✅ đã có | Trả local tips theo city (transport, an toàn, văn hóa, ăn uống, best time to visit, ngân sách) | UC3 |
| 2 | ~~`GET /places/route`~~ ✅ đã có (`/places/route`, `/cities/route`) | Khoảng cách/thời gian giữa hai điểm theo travel mode | UC2 |
| 3 | ~~`POST /trips`~~ ✅ đã có | Tạo một trip tổng hợp (city, ngày đi/về, gắn flight booking + hotel booking + danh sách địa điểm theo ngày) | UC3 |
| 4 | ~~`GET /trips/{id}`~~ ✅ đã có (expanded: bookings + itinerary) | Lấy lại trip đã tạo | UC3 |
| 5 | ~~`PATCH /trips/{id}`~~ ✅ đã có (+ `DELETE` soft-cancel) | Cập nhật trip (thêm/bớt địa điểm, đổi booking) | UC3 |
| 6 | ~~`GET /trips`~~ ✅ đã có (search/filter/paginate) | List các trip đã tạo | UC3 |

### Ghi chú thiết kế
- **`GET /tips`** cần seed data mới (kiểu `app/data/tips.py`), tương tự cách `places.py` đang làm.
- **`GET /places/route`** có thể tận dụng `PLACES` sẵn có + `latitude/longitude` + `opening_hours` để xếp lịch — không cần dữ liệu mới.
- **`Trip`** là model mutable mới → lưu vào SQLite cùng chỗ với `bookings` (`booking_service.py` đang là state mutable duy nhất).
- Booking hiện đứng độc lập, không có `trip_id` — nếu làm Trip nên thêm liên kết.

---

## 3. Tóm tắt

| Use case | API status |
|---|---|
| UC1 — Thời tiết | ✅ Đủ |
| UC2 — Gợi ý route | ✅ `GET /places/route` + `/cities/route`; itinerary nhiều ngày → nhóm `trips` |
| UC3 — Lịch trình đầy đủ | ✅ flight/hotel/places/weather/tips + nhóm `trips` đầy đủ |

**Không còn gap.** Đã bổ sung nhóm `trips` (`POST`/`GET`/`GET list`/`PATCH`/`DELETE`)
và `GET /destinations/{city}/overview`. Xem `APIS.md` cho chi tiết.
