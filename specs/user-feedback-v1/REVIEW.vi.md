---
slug: user-feedback-v1
doc: review
lang: vi
status: supplementary
created: 2026-07-21
reviewer: independent (Claude)
source_of_truth: false
---

> **Ghi chú:** Đây là bản **review độc lập bổ sung** cho `RESEARCH.md` / `DESIGN.md` / `PLAN.md`
> (do Codex soạn). Tài liệu này **không sửa** các doc gốc — chỉ ghi lại chỗ thiếu, chỗ chưa đúng,
> và chỗ đang bỏ sót, kèm bằng chứng đã kiểm chứng trực tiếp trên code hiện tại. Các claim về
> code trong RESEARCH.md đã được verify: **tất cả đều ĐÚNG**. Phần dưới chỉ tập trung vào gap.

# Review — Feedback Event Foundation (v1)

## 0. Kết luận nhanh

Thiết kế **vững về mặt kiến trúc** và đúng ở các quyết định lớn (identity-first, SQL là source of
truth, append-only + fold, provenance-at-runtime, tách feedback khỏi memory, idempotency). Không có
lỗi kiến trúc chặn đường. Tuy nhiên có **2 gap "hợp đồng hứa nhưng không có task thực thi"** đủ sức
làm v1 sai lệch so với DoD, cùng vài chỗ under-specified và giả định hạ tầng chưa đúng thực tế repo.

Xếp theo mức độ:

| # | Vấn đề | Loại | Mức |
|---|---|---|---|
| 1 | 429 / rate-limit có trong contract nhưng không có task + repo không có hạ tầng | Gap thực thi | **Cao** |
| 2 | Anonymous-claim consistency: luồng claim đã tồn tại thật, design yêu cầu mở rộng nhưng không task nào đụng | Gap thực thi | **Cao** |
| 3 | Vòng đời `AgentRun` cho path REST `/agent/chat` bị bỏ ngỏ (thuật toán chỉ viết cho stream) | Under-spec | Trung |
| 4 | "done-after-commit": UX khi persist fail + đánh dấu `abandoned` khi client disconnect + reap row `running` treo + không được phá 2 cơ chế background memory-extraction | Rủi ro tích hợp | Trung-cao |
| 5 | Bảng `agent_runs` full-lifecycle có thể quá tầm cho v1 "chỉ thu bằng chứng" | Scope / simplicity | Trung |
| 6 | `supersedes_event_id` bị thiết kế ra nhưng fold không dùng tới | Nhất quán nội bộ | Thấp-trung |
| 7 | Retention window + owner vẫn để trống ("define before launch") | Quyết định mở | Trung |
| 8 | Danh sách metrics/counters + p95 giả định có metrics backend — repo chưa có | Giả định hạ tầng | Thấp-trung |
| 9 | Gotcha vận hành (rebuild travel.db, test-docker, e2e cần Supabase) không nằm trong plan | Vận hành | Thấp |
| 10 | Ghi chú FE (regen schema cần API sống, 34px là toàn hệ, stream bypass `/api/be`) | Vận hành FE | Thấp |
| 11 | v1 thu hẹp scope PR1 của learning research (bỏ correction/remember/forget) | Điều hòa lộ trình | Info |

---

## 1. [Cao] 429 / rate-limit: contract hứa nhưng không có task, và repo không có hạ tầng

- `DESIGN.md §5.2` liệt kê `429 — Dedicated feedback abuse limit exceeded`; `RESEARCH.md §9` yêu cầu
  "Rate-limit per effective user and per IP/device"; `§10` đếm cả `unauthorized/invalid` counters.
- **Thực tế code:** repo **không có** rate-limiting enforcement. `app/core/middleware.py:65-75` chỉ set
  header `X-RateLimit-*` **thông tin, không cưỡng chế** (`Remaining` luôn == `limit`). CLAUDE.md cũng
  ghi rõ "No auth, pagination, or rate limiting". Có `check_quota` (`agent.py:250,416`) nhưng đó là
  **quota theo ngày cho chat**, không phải abuse-limit cho feedback.
- **Không task nào** trong `PLAN.md` thực thi rate-limit. `Task 2.1` chỉ nói "auth/anonymous identity".
  → `429` sẽ không bao giờ trả về ⇒ contract sai sự thật, và "abuse limit" trong threat model (§10) là
  khoảng trống mở cho spam feedback (đặc biệt với anonymous id do client tự khai).
- **Đề xuất:** chọn 1 trong 2, và ghi rõ:
  - **(a) Descope cho v1:** bỏ `429` khỏi contract, thay bằng "abuse-limit là follow-up", tái dùng
    `check_quota` để chặn thô nếu cần.
  - **(b) Làm thật:** thêm 1 task riêng cho cơ chế rate-limit (per-user + per-IP), quyết định
    dependency (slowapi? tự viết bằng bảng đếm?) — đây là **cross-cutting mới**, không nên nhét ẩn
    vào task feedback service.

## 2. [Cao] Anonymous-claim consistency: luồng claim đã có thật nhưng plan không mở rộng nó

- `DESIGN.md §3.4` yêu cầu: khi claim hội thoại ẩn danh phải cập nhật `agent_runs.user_id` **và**
  `feedback_events.user_id` **trong cùng transaction** với việc reassign conversation.
- **Thực tế code:** luồng claim **đã tồn tại** — endpoint claim ở `app/routers/agent.py:595-607` gọi
  `ConversationRepository.reassign_user(from_user_id=anon, to_user_id=sub)` (`conversation.py:75-90`),
  và **chỉ reassign bảng `conversations`**. Có sẵn cả guard `ForbiddenError` khi source là account đã
  đăng ký (`agent.py:599-601`).
- **Hệ quả nếu bỏ sót:** sau khi user đăng ký và claim, họ **thấy được history hội thoại cũ nhưng
  feedback/run của những message đó vẫn mang `user_id` ẩn danh** ⇒ đúng như design cảnh báo ("see
  history but not its feedback"), và tệ hơn: các bản ghi feedback đó **mồ côi chủ**, ảnh hưởng cả
  ownership check lẫn erasure.
- **Gap trong plan:** không task nào liệt kê sửa endpoint claim / `reassign_user`. `Task 1.2` (repo)
  không có `conversation.py`; `Task 2.1` có `agent.py` nhưng Action không nhắc claim.
- **Đề xuất:** thêm rõ vào một task: mở rộng `reassign_user` (hoặc endpoint claim) để reassign
  `agent_runs` + `feedback_events` cùng transaction, kèm test "claim cập nhật cả conversations, runs,
  events cùng lúc" (test này đã có trong `DESIGN.md §12` nhưng thiếu điểm neo thực thi).

## 3. [Trung] Vòng đời `AgentRun` cho path REST `/agent/chat` bị bỏ ngỏ

- Component diagram (`DESIGN.md §2`) và thuật toán persistence (`§4.3`) **chỉ viết cho SSE stream**
  (persistence wrapper intercept `done`). Nhưng path REST không stream `/agent/chat`
  (`agent.py:278-308` success, `344-359` fallback) cũng cần: pre-mint id → chạy graph → persist
  message dưới id đó → **tạo + finalize `AgentRun`**.
- `Task 2.1` nói "Integrate the answer-time run lifecycle" và có đụng `agent.py`, nhưng **không có
  thuật toán** cho nhánh non-stream (khi nào tạo run `running`, khi nào finalize `completed`/`failed`,
  fallback path đánh dấu ra sao). `§4.2` chỉ mô tả *response shape*, không mô tả *lifecycle*.
- **Rủi ro:** hai path stream/non-stream dễ lệch nhau (một path có run provenance, path kia không), làm
  hỏng chính cái invariant "mọi completed answer có agent_run_id" mà rollout dựa vào để gate UI.
- **Đề xuất:** viết thuật toán run-lifecycle cho `/agent/chat` ngang hàng với block `§4.3`, gồm cả
  nhánh fallback (graph fail nhưng vẫn persist assistant message → run `failed` nhưng rateable).

## 4. [Trung-cao] "done-after-commit": UX lỗi persist, disconnect, và tương tác với memory-extraction

Đây là thay đổi **rủi ro nhất** của v1 (đổi ngữ nghĩa `done`). Ba điểm chưa được xử lý đủ:

1. **UX khi answer đã stream xong nhưng commit fail.** Hiện tại (đã verify `persistence.py:51-81`):
   `done` phát *trước*, persist chạy *sau* khi iterator cạn, và **lỗi DB bị nuốt (chỉ log)**. Design
   mới lật thành persist-trước-done ⇒ một câu trả lời user *đã thấy stream đầy đủ* giờ có thể kết bằng
   **error thay vì done**. Design (`§4.3`) thừa nhận nhưng **không nói FE làm gì với đoạn text đã hiện**
   (giữ hay bỏ?), và user thấy gì. Cần định nghĩa rõ ở FE state machine (`§7`/`§8.5` mới có
   streaming/interrupt/failed = hidden, nhưng thiếu case "đã stream full rồi mới failed").

2. **Đánh dấu run `abandoned` khi client disconnect.** Hiện tại disconnect ⇒ vòng `async for` bị cắt ⇒
   **reply mất im lặng** (block persist sau vòng lặp không chạy — đã verify). Design nói "mark run
   abandoned best-effort", nhưng khi generator bị `CancelledError`/`GeneratorExit`, việc ghi DB trong
   `finally` là **khó và dễ hỏng** (session có thể đã đóng). Ngoài ra **không có reaper/TTL** cho các
   row `running` bị treo khi best-effort thất bại ⇒ bảng `agent_runs` tích tụ rác `running`.

3. **Không được phá memory-extraction.** Đã verify: extraction chạy **hai cơ chế khác nhau** —
   `/chat` dùng FastAPI `BackgroundTasks.add_task` (`agent.py:364-373`), `/stream` dùng Starlette
   `BackgroundTask` truyền vào `sse_response(...)` (`agent.py:456-482`). Dời điểm persist vào trong
   stream wrapper phải đảm bảo **cả hai trigger** vẫn nhận đúng assistant message đã persist. Design
   không phân tích tương tác này.

- **Đề xuất:** bổ sung mục "failure & disconnect semantics" nêu rõ: (i) FE hiển thị gì khi post-stream
  persist fail; (ii) chiến lược mark `abandoned` (và chấp nhận best-effort tới đâu) + cần reaper hay
  không; (iii) xác nhận thứ tự persist mới không đổi hành vi của cả hai background extraction path.

## 5. [Trung] `agent_runs` full-lifecycle có thể quá tầm cho v1 "chỉ thu bằng chứng"

- Mục tiêu v1 (Non-goals) là **thu bằng chứng, chưa learning**. Nhưng thiết kế đưa vào một bảng
  `agent_runs` với **5 status** (`running/completed/interrupted/failed/abandoned`), kéo theo lifecycle,
  reaping, và consistency lúc claim (điểm #2, #4). Chính `DESIGN.md §3.1` đã tự nêu fallback:
  provenance tạm sống trong cột `Message.provenance` JSON.
- Rollout (`§11`) lại **gate UI theo sự tồn tại của `agent_run_id`** ⇒ cả bảng trở thành load-bearing
  cho v1, không còn là "optional nice-to-have".
- Theo `rules/behavior.md §2 (Simplicity First)`: nên **quyết định có chủ đích** table-now vs
  JSON-now-table-later, thay vì mặc định chọn bản nặng. Nếu chọn JSON-now: v1 gọn hơn nhiều, vẫn giữ
  được `assistant_message_id` + snapshot provenance tại answer-time; đẩy bảng `agent_runs` (và toàn bộ
  lifecycle/reaper) sang PR2 khi thực sự cần failure-analytics.
- **Đề xuất:** thêm 1 dòng quyết định rõ ràng trong DESIGN/PLAN (không để mập mờ "may temporarily").

## 6. [Thấp-trung] `supersedes_event_id` được thiết kế nhưng fold không dùng

- `DESIGN.md §3.2` có cột `supersedes_event_id`, nhưng `§3.3` fold **chỉ sort theo `(created_at, id)`**,
  không đi theo chain supersede. ⇒ cột này thành **dead weight** cho read-model.
- Điểm kỹ thuật: `created_at` là **ISO string** (`app/db/base.py:52-53` `datetime.now(timezone.utc)
  .isoformat()`), và `isoformat()` **bỏ microseconds khi = 0** (độ dài biến thiên). Với offset cố định
  `+00:00`, so sánh chuỗi vẫn đơn điệu theo thời gian cho các mốc **khác nhau** — nên trường hợp thường
  ngày (click cách nhau) fold đúng. Rủi ro chỉ ở **tie thật sự cùng-microsecond**: khi đó tiebreak rơi
  về `id` = **UUID ngẫu nhiên, không theo thời gian** ⇒ "latest wins" có thể chọn nhầm. Xác suất với
  feedback do người bấm là cực thấp, nên đây là **robustness/consistency**, không phải bug chặn.
- **Đề xuất:** hoặc (a) fold **theo chain `supersedes_event_id`** để thứ tự tất định, hoặc (b) bỏ cột
  đó cho gọn và ghi chú fold thuần theo timestamp. Đừng để cả hai cùng tồn tại mà mâu thuẫn.

## 7. [Trung] Retention window + owner vẫn để trống

- `RESEARCH.md §9` và `DESIGN.md §13 (DoD)` yêu cầu "retention owner/window documented", nhưng **không
  đề xuất giá trị cụ thể** — chỉ "define before launch". Đây là **quyết định sản phẩm còn mở**: DoD
  không thể đạt nếu chưa chốt. Cần người chủ + con số (ví dụ: comment text giữ N ngày, aggregate vô
  thời hạn) trước khi bật controls. Nêu ra để không trôi tuột.

## 8. [Thấp-trung] Metrics/observability giả định backend chưa tồn tại

- `RESEARCH.md §10` liệt kê nhiều counter (accepted/retracted/replayed/conflicted/unauthorized/…),
  `feedback POST p95`, `export lag`, phân tách theo release/model/prompt/flow.
- **Thực tế:** repo dùng `logging.getLogger` + middleware header thông tin; **không có** Prometheus/
  statsd/metrics registry (`rg prometheus|statsd` không ra). ⇒ danh sách metric là **nguyện vọng**, chưa
  có nơi để "track".
- **Đề xuất:** hoặc thu hẹp về **structured log fields** (low-cardinality, không chứa comment) mà một
  log pipeline có thể tổng hợp sau, hoặc đánh dấu rõ phần dashboard là follow-up, không phải DoD của PR
  này.

## 9. [Thấp] Gotcha vận hành không nằm trong plan (sẽ cắn khi execute)

- Thêm 2 bảng + migration ⇒ **phải rebuild `travel.db`** hoặc cả suite fail (lifespan seed DB thật,
  `create_all` không thêm cột) — xem memory `stale-travel-db-breaks-suite-on-schema-change`.
- Migration phải chạy `make test-docker` để kiểm **parity SQLite/Postgres** (không chỉ SQLite).
- `Task 4.1` verify là `npm run test:e2e` (Playwright): cần **Supabase env dummy** để Next dev server
  chạy (memory `env-supabase-required-for-web-dev-server`) và Playwright ở máy này hay lỗi
  (`playwright-mcp-broken-use-node24-script`). Verify này khó xanh trong môi trường hiện tại — nên có
  phương án fallback (script node24) hoặc hạ e2e xuống "manual acceptance".
- **Đề xuất:** thêm các bước này vào phần rollout/verify của PLAN để người execute không vấp.

## 10. [Thấp] Ghi chú FE cần chính xác hơn

- `pnpm gen:api` regen `schema.d.ts` bằng cách trỏ tới `http://localhost:8000/openapi.json` ⇒ **cần API
  sống có sẵn endpoint feedback** mới regen được. `Task 3.1` (wave 4) phụ thuộc BE (wave 3) đã deploy/
  chạy — đúng thứ tự, nhưng nên nói rõ "API phải chạy khi regen".
- Vấn đề **target-size 34px là toàn hệ**: không chỉ `Button size="icon"` mà cả `Field.tsx`/`Select`
  dùng `h-[34px]`. Nếu chỉ nâng nút feedback lên 40–44px thì **lệch với phần còn lại của hệ**. Cần
  quyết định: nâng riêng cho chat feedback (chấp nhận ngoại lệ có chủ đích) hay không đụng.
- **Stream bypass proxy:** SSE đi thẳng origin (`client.ts:74 streamBaseUrl()`), còn `POST
  /agent/feedback` sẽ đi qua `/api/be` (`client.ts:51`). Hai base path khác nhau — không sai, nhưng
  `DESIGN.md §5.1` nói "works through `/api/be`" nên nêu rõ điểm bất đối xứng này để không nhầm khi test.

## 11. [Info] Điều hòa lộ trình với `user-feedback-learning`

- `user-feedback-learning/RESEARCH.md` mô tả **PR 1** gồm cả `comment/correction/remember/forget`.
  `user-feedback-v1` **thu hẹp** còn `helpful/not_helpful/retract` + optional reason/comment, đẩy
  correction/remember/forget sang "later typed schemas".
- Đây là **thu hẹp hợp lý** (an toàn hơn, đúng tinh thần "evidence-only"), và **khớp** với `PR 3` của
  learning (explicit remember/correct/forget). Không phải lỗi — nhưng nên **ghi 1 dòng** trong v1 rằng
  "v1 = PR1 đã re-scope, remember/forget nằm ở PR3" để lộ trình hai doc không đọc thấy mâu thuẫn.

---

## 12. Những chỗ thiết kế đã làm ĐÚNG (không cần đụng)

Để cân bằng — các quyết định sau đã verify là đúng và nên giữ nguyên:

- **SQL là source of truth, Langfuse chỉ là projection** — đúng, tránh coupling vào provider.
- **Append-only + fold effective state** — đúng, giữ được lịch sử sửa/rút.
- **Provenance snapshot tại answer-time** — đúng; tra "current config" khi feedback tới sẽ sai lịch sử.
- **Tách feedback khỏi memory-extraction** — đúng và là safety gate cốt lõi kế thừa từ learning.
- **Idempotency tái dùng convention có thật:** `booking.py:101-111` và `trip.py:123-135` đã dùng
  `begin_nested()` savepoint + bắt `IntegrityError` + đọc winner qua `get_by_idempotency_key`. Design
  viện dẫn đúng, có thể tái dùng ngay (lưu ý: `ConversationRepository` **chưa** có pattern này).
- **Ownership qua message → conversation → owner, 404 không liệt kê** — đúng chuẩn OWASP BOLA; và đã
  verify lỗ hổng `ensure_conversation` (`conversation.py:36-68`) là thật nên feedback **không được**
  kế thừa hành vi đó.
- **Accessibility (aria-pressed, focus trap Modal, live region, target-size)** — đúng hướng; `Modal.tsx`
  đã có focus entry/trap/Escape/restore (chỉ thiếu `aria-labelledby` nối `<h2>`).

## 13. Việc nên làm tiếp (đề xuất)

1. Chốt #1 (429) và #2 (claim consistency) **trước khi execute** — đây là 2 gap contract/data thật sự.
2. Bổ sung thuật toán lifecycle cho path REST (#3) và "failure & disconnect semantics" (#4) vào DESIGN.
3. Ra quyết định có chủ đích `agent_runs` table-now vs `Message.provenance` JSON-now (#5).
4. Làm rõ fold: dùng chain hay drop `supersedes_event_id` (#6).
5. Chốt retention window/owner (#7) và hạ metrics xuống structured-log hoặc đánh dấu follow-up (#8).
6. Thêm các bước vận hành (#9) và ghi chú FE (#10) vào PLAN.
7. Thêm 1 dòng điều hòa lộ trình (#11).
