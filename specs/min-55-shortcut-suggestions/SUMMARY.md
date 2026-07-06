# min-55-shortcut-suggestions — Summary

Lane: normal
Confidence: high
Reason: Additive `suggestions` field on the agent ChatResponse envelope (public-contract) + changes to the existing chat reply flow across both apps/web and apps/api (multi-domain); no hard gate — the field is optional/backward-compatible and no new endpoint, provider, auth, or schema migration is involved.
Flags: public-contract, existing-behavior, multi-domain
Affects: apps/api ChatResponse envelope (`app/schemas/agent.py`), `/agent/chat` + `/agent/stream`; apps/web chat suggestion chips (`ChatEmptyState.tsx`, `ChatPanel.tsx`, `messages/{en,vi}.json`)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim from Linear MIN-55 (issue is the request of record). -->

Improve: Rút gọn shortcut lần chat đầu + thêm shortcut suggestion theo ngữ cảnh

**Vấn đề**
- Shortcut/suggestion ở lần chat đầu tiên hiện đang quá dài, viết dưới dạng câu hoàn chỉnh → chưa tối ưu cho việc quét nhanh và click.
- Chưa có cơ chế gợi ý shortcut cho các câu chat tiếp theo liên quan đến ngữ cảnh hội thoại hiện tại.

**Đề xuất**

1. Rút gọn shortcut ở lần chat đầu tiên
   - Không cần viết thành 1 câu hoàn chỉnh, có thể là cụm từ ngắn gọn, dễ quét (vd thay vì "Tôi muốn tìm khách sạn giá rẻ ở Đà Nẵng" → "Khách sạn Đà Nẵng 🏨" hoặc "Tìm khách sạn").
   - Ưu tiên ngắn gọn, rõ ý, dễ tap trên mobile.

2. Shortcut suggestion theo ngữ cảnh (follow-up)
   - Sau mỗi câu trả lời của bot, hệ thống nên trả về thêm 1 bộ shortcut suggestion liên quan đến ngữ cảnh vừa trao đổi, để user có thể click nhanh thay vì phải gõ tay.
   - Ví dụ: sau khi bot trả lời thông tin khách sạn → gợi ý "Xem khách sạn khác", "Đặt phòng này", "So sánh giá".

**Việc cần làm**
- Thiết kế lại nội dung/label cho bộ shortcut mở đầu (first-time chat).
- Xây dựng logic sinh shortcut suggestion động dựa trên context của câu trả lời gần nhất (theo intent/topic đang trao đổi).
- Xác định số lượng shortcut hiển thị hợp lý (vd 2-4 gợi ý) để không gây rối UI.
- Test các case cụ thể: tìm khách sạn, tìm chuyến bay, hỏi thông tin điểm đến, booking flow.

**Scope-deciding clarifications (this session):** generation mechanism = **hybrid (heuristic-by-flow now, LLM later)**; delivery = **additive `suggestions` field on `ChatResponse` + a final SSE event on `/agent/stream`**; scope = **both parts (label shortening + follow-up chips) in one branch**.

## What changed

<!-- Filled at DONE. -->

Two-part chat UX improvement: (1) shorten the four first-run welcome chips in `apps/web` to scannable phrases; (2) return 2–4 context-relevant follow-up suggestion chips after each bot reply, keyed off the agent's `current_flow` via a deterministic heuristic map, surfaced through a new optional `suggestions` field on `ChatResponse` (and a closing SSE event on the stream) and rendered by the FE below each assistant turn.

### Rationale

User chose the **hybrid** approach: ship a cheap, zero-latency heuristic (flow → curated suggestion set) first so every chat turn stays fast and free of extra LLM cost, leaving LLM-generated per-reply suggestions as a follow-up ticket. Delivery via an **additive optional field** on the existing `ChatResponse` keeps the change backward-compatible (no new endpoint, no extra round-trip).

### Alternatives considered

- **LLM-generated suggestions per turn** — most context-accurate but adds an LLM call + latency + cost to every reply and needs eval; deferred to a follow-up ticket by user decision.
- **Separate `GET /agent/suggestions` endpoint** — cleaner separation but adds a round-trip and a stronger public-contract surface (new endpoint); rejected in favor of extending `ChatResponse`.
- **Part 1 only, defer part 2** — offered; user chose to do both in one branch.

### Deviations

- none

### Verify

<!-- Filled at DONE — one row per check actually run. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| <unit / lint / build / behavior> | `<command>` | 0 | <output excerpt on fail> |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
