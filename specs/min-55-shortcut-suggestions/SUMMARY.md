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

- Rule 1 — Task 3.1 updated a pre-existing `parseSSE` `done` deep-equality test to include `suggestions: []` (the parser now always emits the field). Required, in-file. Commit `1817e1d`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| BE heuristic unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_suggestions.py -x` | 0 | 9 passed |
| BE /agent/chat | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -q` | 0 | 15 passed |
| BE done SSE event | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/api/agent/test_streaming_sse.py -x` | 0 | 24 passed |
| FE parseSSE | `cd apps/web && pnpm test src/lib/stream/parseSSE.test.ts` | 0 | 21 passed |
| FE ChatSuggestions | `cd apps/web && pnpm test src/components/chat/ChatSuggestions.test.tsx` | 0 | 3 passed |
| FE useAgentStream | `cd apps/web && pnpm test src/components/chat/useAgentStream.stream.test.tsx` | 0 | 5 passed |
| FE chat suite + typecheck | `cd apps/web && pnpm test src/components/chat && pnpm exec tsc --noEmit` | 0 | 33 tests; tsc clean |

### Correctness Review

- `/correctness-review` (BASE `1603309`..HEAD `80e8634`, finder model sonnet, FIND stage): ✅ no correctness defects. Traced agent_chat happy + interrupt-pending; stream happy + interrupt→resume + retry + exception; parseSSE done with absent/null/non-array/valid; ChatSuggestions render/click; ChatPanel visibility guard. Confirmed the single required `events.done` caller updated; both `suggestions_for_flow` imports present (guards `formatter-strips-unused-import` regression). No findings → no SCORE/fix loop needed.

### Intent Findings

- advisory (`drift`, behaviorally-equivalent) — Intent to-do "Test các case cụ thể: tìm khách sạn, tìm chuyến bay, hỏi thông tin điểm đến, booking flow." E2E coverage: destination-info (`test_chat_returns_flow_scoped_suggestions`) + booking/interrupt (`test_chat_returns_no_suggestions_when_interrupt_pending`); hotel-search + flight-search scenarios covered only structurally via the flow-generic unit test (`test_known_flow_returns_bounded_prefixed_keys` over all 5 `ALL_SUBAGENTS`). Mechanism is flow-generic so those scenarios behave identically to the tested flows. Routing: **advisory / follow-up** — add 2 literal e2e cases (hotel→planner/concierge, flight→booking) in a later commit; non-blocking for ship.

### Rollback

- Revert the feature range: `git revert --no-commit 8eba8fc^..80e8634 && git commit` (or drop the branch — it is unmerged, off `v3`).

### Harness-Delta

- backlog (→ `/compound`) — Parallel wave subagents committing to the SHARED git index race: two Wave-2 agents' `git add`+`commit` interleaved, entangling both diffs into one commit and leaving one task's files uncommitted; the pre-commit hook also auto-staged a sibling task's files. Mitigations that worked: from Wave 3 on, subagents implement + verify only (no commit) and the controller serializes commits with explicit pathspecs. Corroborates existing `wave-shared-file-partition` learning; the new angle is the **commit/index** contention (not just file/type overlap). Worth a `docs/solutions/harness/` note.
