---
slug: min-65-chatbot-intelligence
doc: high-level-design
ticket: MIN-65 — Improve chatbot intelligence: memory, reasoning & suggestion quality
created: 2026-07-12
status: proposed
related: specs/agent-memory-layers/ (P1 shipped, P2 episodic shipped), specs/min-55-shortcut-suggestions/, specs/min-58-chatbot-eval-deepeval/
---

# HLD — Chatbot Intelligence: Memory, Reasoning & Suggestion Quality

## 1. Bối cảnh & khoảng trống thực tế

MIN-65 yêu cầu 3 nhóm cải tiến. Sau khi review sâu codebase, **phần lớn hạ tầng memory
dài hạn đã ship** — thiết kế này chỉ đắp đúng chỗ còn thiếu, không xây lại.

| Yêu cầu ticket | Hiện trạng trong code | Gap |
|---|---|---|
| Long-term preference memory | ✅ `PostgresStore` + pgvector semantic index (`app/memory/store.py`), background extraction sau mỗi turn (`extraction_runner.py`), profile injection (MIN-53) | Prefs tổng quát (ngoài 3 profile key) **không auto-inject** — chỉ journal/planner thấy qua tool |
| Entity tracking trong session | ❌ Không có slot/entity state. Ngày bay, số người, điểm đến chỉ sống trong raw history + summary (lossy). PR #84 vá bằng prompt "never guess dates" | **Gap lớn nhất pillar 1** — cần structured slot state |
| Summarize hội thoại dài | ✅ `summarizer.py`: threshold 20, keep_last 5, tool-pair-safe split | Không có gap đáng kể (slots chuyển sang state sẽ hết lo summary làm rơi facts) |
| Checkpointer + memory store | ✅ `AsyncPostgresSaver` + store trong lifespan | — |
| Intent inference | Chỉ prompt-level rời rạc | Cần guardrail có hệ thống + slots làm nền |
| Multi-intent routing | ❌ Supervisor **single-hop**, structured output 1 `target_agent`; multi-intent bị prompt rule "pick one" | Cần secondary intent + dispatch |
| Hỏi đúng field thiếu | Prompt-driven, không biết chính xác field nào đã có | Slots cho phép "ask only missing" |
| Answer kèm lý do | Không có quy tắc | Prompt (communication_style) |
| Proactive suggestions | ✅ MIN-55 nhưng **map tĩnh** theo `current_flow` | Cần rule engine state-aware + cá nhân hoá |
| Ranking theo preference | ❌ Tool trả kết quả theo sort mặc định của service | Cần re-rank deterministic trong tool |
| Eval đo được | ✅ DeepEval harness (MIN-58) nhưng **single-turn only** | Cần multi-turn `run_case` + 2 metric mới |

## 2. Nghiên cứu — áp decision tree vào từng loại thông tin

Theo bài [Choosing the Right AI Agent Memory Strategy — A Decision Tree Approach](https://machinelearningmastery.com/choosing-the-right-ai-agent-memory-strategy-a-decision-tree-approach/)
(4 loại memory: working / semantic / episodic / procedural; 5 câu hỏi: persist qua turn? →
qua session? → fact hay event? → retrieval kiểu gì? → có learned procedure?), chạy tree
**riêng cho từng loại thông tin** của travel assistant:

| Loại thông tin | Persist? | Qua session? | Fact/Event | Memory type | Trong repo |
|---|---|---|---|---|---|
| Slot chuyến đi đang bàn (ngày, điểm đến, số người, budget) | qua turn | **không** (theo conversation) | fact tạm | **Working memory** → `TravelAgentState` field, checkpointer persist theo thread | **THÊM MỚI** (`trip_facts`) |
| Sở thích bền (hạng ghế, loại khách sạn, airline, budget band) | có | **có** | fact ổn định | **Semantic** → store `prefs` namespace | Đã có; **mở rộng injection** |
| Profile (name/gender/travel_group) | có | có | fact ổn định | Semantic (keyed read, không vector) | Đã có (MIN-53) |
| Standing instructions ("luôn trả lời tiếng Việt") | có | có | fact ổn định | **Procedural** → `procedural` namespace, inject mỗi turn | Đã có (P1) |
| Chuyến đi quá khứ + outcome | có | có | **event** | **Episodic** → `episodes` namespace + `recall_past_trips` | Đã có (P2) |
| Learned workflow của agent | — | — | — | Procedural (prompt-rewriting) | **Bỏ qua** — chưa cần |

Retrieval policy (câu hỏi 4 của tree + nghiên cứu LangMem/Mem0): profile + prefs là store
**nhỏ, bounded** → **full-read & inject** mỗi turn thắng vector search (không tốn embedding,
không recall-miss, deterministic). `store.search()` semantic chỉ dành cho episodes (đã đúng
như vậy). Đây là nguyên tắc "memory là một nguồn context cạnh tranh context window — chỉ
retrieve khi cải thiện câu trả lời".

### Nguồn tham khảo chính

- LangGraph long-term memory / LangMem (hot-path vs background writes): [docs.langchain.com/oss/python/langchain/long-term-memory](https://docs.langchain.com/oss/python/langchain/long-term-memory), [langchain-ai.github.io/langmem](https://langchain-ai.github.io/langmem/)
- Mem0 (single-pass extraction, ADD/UPDATE/DELETE conflict ops, hybrid retrieval): [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- MemGPT/Letta (core-memory always-in-context + archival cold storage): [leoniemonigatti.com/blog/memgpt](https://www.leoniemonigatti.com/blog/memgpt.html)
- Generative Agents (importance tagging at write time), MemoryBank (Ebbinghaus decay), A-MEM ([arxiv 2502.12110](https://arxiv.org/abs/2502.12110)), HippoRAG ([arxiv 2405.14831](https://arxiv.org/abs/2405.14831)), survey "Memory in the Age of AI Agents" ([arxiv 2512.13564](https://arxiv.org/pdf/2512.13564))
- Entity/slot tracking: state-schema fields cho thread hiện tại, store cho cross-thread facts — không nhét per-turn slots vào BaseStore

## 3. Lựa chọn phương án (options → quyết định)

### 3.1 Memory framework: build-on-existing vs adopt thư viện

| Option | Ưu | Nhược | Quyết định |
|---|---|---|---|
| **A. Xây tiếp trên BaseStore + state hiện có** | Tận dụng toàn bộ P1/P2 đã ship; zero dependency mới; FakeLLM-testable | Tự lo dedup/conflict (giữ mức tối thiểu) | ✅ **CHỌN** |
| B. Adopt Mem0 | Conflict-resolution + dedup battle-tested (LoCoMo 92.5) | Hệ memory thứ 2 song song checkpointer/store; external service; quá tầm cho mock-backend | ❌ |
| C. Adopt LangMem SDK | Chính chủ LangChain | Pre-1.0 (0.0.30), cadence chậm; những gì cần (profile, background extraction) repo đã tự có tương đương | ❌ |
| D. Letta/MemGPT | Paged memory hay | Commercial runtime, thay cả kiến trúc agent | ❌ |

### 3.2 Entity/slot extraction: ở đâu?

| Option | Ưu | Nhược | Quyết định |
|---|---|---|---|
| A. Node extraction riêng mỗi turn | Tách bạch | +1 LLM call/turn (latency + cost) | ❌ |
| **B. Gộp vào structured output của supervisor** | **Zero LLM call thêm** — supervisor đã gọi `with_structured_output`; đã thấy full context | Schema supervisor phình → risk routing kém (mitigate: field optional + routing eval có sẵn) | ✅ **CHỌN** |
| C. Tool `record_trip_facts` cho sub-agent | Agent chủ động | LLM-discretionary — đúng cái gap P1 từng phải sửa | ❌ |

Nguyên tắc `llm-parses-code-computes` (critical pattern của repo): supervisor chỉ trả
**raw text** slot (vd. "tuần sau", "15/8"); **code** normalize (date qua `core/dates`,
số qua int cast). Không để LLM tự tính ISO date.

### 3.3 Multi-intent routing

| Option | Ưu | Nhược | Quyết định |
|---|---|---|---|
| A. Sub-agent → supervisor re-entry (vòng lặp đầy đủ) | Tổng quát N intent | Vòng lặp không bound rõ; +1 supervisor LLM call mỗi hop | ❌ |
| **B. Supervisor trả `secondary_agent` (tối đa 2 intent/turn) + node `dispatch_next`** | Bounded, deterministic, zero LLM call thêm; reflection vẫn review câu trả lời cuối | Chỉ 2 intent/lượt (đủ cho "hotel + flight") | ✅ **CHỌN** |
| C. Handoff tools giữa sub-agents | Chuẩn swarm | Đổi topology lớn, khó test, ngoài scope | ❌ |

### 3.4 Suggestions: rule engine vs LLM-generated

| Option | Ưu | Nhược | Quyết định |
|---|---|---|---|
| **A. Rule engine state-aware trên catalog key mở rộng** | Deterministic, testable, giữ nguyên contract FE (i18n key), zero latency | Kém "sáng tạo" hơn LLM | ✅ **CHỌN** (v1) |
| B. LLM sinh suggestion free-text | Linh hoạt | Đổi contract FE (mất i18n key), +1 LLM call, khó eval ổn định | ❌ (ghi nhận là bước sau nếu rule engine chạm trần) |

### 3.5 Ranking kết quả theo preference

Chọn **deterministic re-rank trong tool** (stable-sort boost theo preference match) trước khi
build summary + `panel_result` — giữ nguyên tính deterministic của mock backend, testable,
không thêm LLM call. LLM re-rank bị loại (cost/latency, phá determinism).

## 4. Kiến trúc tổng thể (sau thay đổi)

```
POST /agent/chat|stream
 → AgentContext (tier, tz, allow_*)
 → graph:
    load_context ── trip_context + instructions + profile
    │                + preferences (NEW: full-read prefs → inject)
    summarize ────── như cũ (slots đã an toàn trong state)
    supervisor ───── SupervisorIntent{target, SECONDARY?, SLOTS raw}   (NEW)
    │                code normalize slots → state.trip_facts (merge reducer)
    ▼
    sub-agent ────── system msg = base + profile + preferences + instructions
    │                + trip_facts ("Known trip facts — do NOT re-ask") + summary
    │                tools: re-rank hotels/flights theo preferences (NEW)
    ▼
    dispatch_next ── còn pending intent? → sub-agent kế tiếp : reflection   (NEW)
    ▼
    reflection ───── như cũ → END
 → suggestions_for_flow(flow, trip_facts, profile, preferences)  (NEW: rule engine)
 → BACKGROUND: run_memory_extraction (thêm updated_at + canonical keys)  (tăng cường)
```

**Điểm mấu chốt:** mọi thay đổi đều nằm trên seam có sẵn — `system_with_summary` (injection),
`SupervisorIntent` (structured output), static edge sub-agent→reflection (dispatch),
`suggestions_for_flow` (2 call sites), `content_and_artifact` tools (re-rank).

## 5. Phased delivery & mapping Acceptance Criteria

| Phase | Nội dung | AC ticket |
|---|---|---|
| **P0 — Eval first** | Multi-turn `run_case`, dataset `memory.json` + `suggestions.json`, metric `memory_recall` + `suggestion_relevance`, chạy **baseline** | "thêm metric trước khi implement" |
| **P1 — Memory** | `trip_facts` state + supervisor slot extraction + preference auto-injection + store hygiene (updated_at, canonical keys) | "không lặp lại thông tin trong session"; "prefs nhớ qua session" |
| **P2 — Reasoning** | `secondary_agent` + `dispatch_next` (multi-intent); prompt guardrails: intent inference, ask-only-missing, default-with-confirm | routing đa ý định; hỏi đúng field thiếu |
| **P3 — Suggestions** | Rule engine + catalog mở rộng + FE i18n keys; preference re-rank trong hotel/flight tools; communication_style "reason with every recommendation" | "≥80% câu trả lời có suggestion"; ranking theo preference; lý do đi kèm |
| **P4 — Đo lường** | Re-run eval vs baseline, ghi RESULTS | "đo bằng eval hiện có" |

Có thể tách P1/P2/P3 thành 3 sub-issue Linear đúng như ticket gợi ý — PLAN.md đánh wave
tương ứng để cắt được ở ranh giới phase.

## 6. Non-goals

- Không adopt Mem0 / LangMem / Letta; không graph-memory, không Ebbinghaus decay, không A-MEM.
- Không LLM-generated free-text suggestions (giữ contract i18n key với FE).
- Không nâng reflection rubric (thuộc MIN-59).
- Không cho `booking` làm secondary intent (HITL interrupt phức tạp — booking luôn là intent đơn).
- Không memory cho anonymous user (giữ gate `user_id` hiện tại).
- Không đổi public contract `/agent/chat`, `/agent/stream` (shape `ChatResponse.suggestions` giữ nguyên — vẫn là list key).
