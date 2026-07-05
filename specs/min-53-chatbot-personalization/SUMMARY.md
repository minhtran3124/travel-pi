# min-53-chatbot-personalization — Summary

Lane: normal
Confidence: high
Reason: Changes existing agent conversation behavior (soft-prompt questions) around sensitive personal data (name/gender/travel-group) with LLM-driven behavior that is hard to prove deterministically — 3 flags, no hard gate. Scope locked with user: prompt + memory-preferences approach (no schema), ask at suggestion-time.
Flags: audit/security (PII — gender), existing behavior, weak proof
Affects: agent prompts (supervisor/concierge system prompts + communication_style), memory store preferences namespace, TravelAgentState — no public API contract change
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-53 verbatim (Vietnamese, from the Linear ticket). Oracle for /intent-review. -->

Improve: Chatbot chủ động hỏi thông tin cá nhân hóa (tên, giới tính, nhóm đi cùng) để giao tiếp và gợi ý phù hợp hơn

## Mục tiêu

Cải thiện agentic chatbot workflow để cá nhân hóa trải nghiệm giao tiếp và gợi ý (suggestion) phù hợp hơn với từng user.

## Đề xuất

* **Tên user**: hỏi nhẹ nhàng (không bắt buộc) để xưng hô tự nhiên hơn trong hội thoại.
* **Giới tính**: hỏi nhẹ nhàng để điều chỉnh cách xưng hô/giao tiếp cho phù hợp.
* **Nhóm đi cùng / số lượng người**: hỏi nhẹ nhàng loại hình chuyến đi, ví dụ:
  * Gia đình có trẻ nhỏ
  * Couple
  * Solo
  * Nhóm bạn (friends)
  * Số lượng người cụ thể

## Lý do

Thông tin này giúp agent đưa ra suggestion phù hợp hơn (vd: khách sạn có khu vui chơi trẻ em cho gia đình, phòng romantic cho couple, hostel/social space cho solo/friends...).

## Việc cần làm

* Thiết kế các câu hỏi "soft prompt" tự nhiên, không gây khó chịu, không bắt buộc trả lời.
* Xác định thời điểm phù hợp trong flow để hỏi (đầu hội thoại hay khi bắt đầu tìm kiếm gợi ý).
* Lưu các thông tin này vào context/state của session để tái sử dụng cho các suggestion sau.
* Đảm bảo user có thể bỏ qua (skip) các câu hỏi này mà không bị chặn luồng chính.

## What changed

The travel agent now personalizes address + suggestions via three reserved memory-store preference keys (`name`, `gender`, `travel_group`) — no schema, no migration. **Ask:** concierge (v8) and planner (v5) prompts gained a "Personalize before suggesting" section — a single, optional, skippable soft question about trip company at suggestion-time, plus an optional gentle name ask; gender is never asked directly (PII-safe, requester-confirmed). **Capture:** memory_extraction (v3) prompt captures the three reserved keys when volunteered (extractor already parses free-form `{key,text}` — no code change). **Reuse:** `get_profile()` (`store.py`) reads the keys, `load_context_node` folds them into the new `TravelAgentState.profile` field, and `system_with_summary` injects a "Traveller profile:" block into the single leading system message every turn (supervisor + all sub-agents). Cross-session (rides existing prefs store).

### Rationale

Existing infra already fits: `app/memory/store.py` holds per-user, cross-session **preferences** (`upsert_preference`, addressable by `(namespace, key)`, semantically searchable) and the background `extraction_runner` already captures preferences from conversation. `TravelAgentState.instructions` already folds per-user standing directives into the leading system prompt. So the lightest credible path is prompt-engineering the soft prompts + wiring personalization preferences into retrieval/injection — not new schema. This keeps the change reversible and off any hard gate.

### Alternatives considered

- **Prompt + memory-preferences (CHOSEN — user-confirmed)** — soft-prompt guidance in agent system prompts; capture name/gender/group via existing preference extraction → memory store preferences; inject into system prompt for suggestions. No schema, no migration. Soft prompt fires **at suggestion-time** (before concierge/planner emits hotel/activity suggestions), not at conversation open. Must be optional + skippable without blocking the main flow.
- **Structured personalization slots** — dedicated profile fields on `TravelAgentState` and/or a new profile namespace with explicit slot-filling. Heavier; would touch data model and could re-trigger to high-risk. Rejected: existing preference infra already fits.

### Deviations

- Rule 1 — Guarded `get_profile` against a non-string preference `text` (a malformed reserved key no longer poisons the whole loop / drops all valid keys). Found by final correctness review. `apps/api/app/memory/store.py`. Commit `dc58563`.

### Escalation resolution (intent review)

The final intent review (blind to PLAN) flagged that the verbatim MIN-53 proposal asks to softly request **name** and **gender**, whereas the built prompts asked only trip-company. Surfaced to the requester (both were planner-time narrowings, not explicitly signed off):

- **Name** → requester chose to ADD a gentle, optional, skippable name ask (concierge v8 / planner v5). Commit `c00eaa6`.
- **Gender** → requester CONFIRMED keeping "never ask directly" (PII-safe); gender captured/used only if volunteered. No code change; recorded here + in CHANGELOG. See `ESCALATIONS.md`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Blast-radius suite (agents+memory+prompts) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents tests/memory tests/prompts -q` | 0 | 168 passed (store profile, state fold, injection, prompt smoke, no-regression) |
| Store helper (task 1.1) | `pytest tests/memory/test_store_profile.py -x` | 0 | 4 passed incl. order + non-string-text guard |
| State fold (task 1.2) | `pytest tests/agents/test_state_system_prompt.py -x` | 0 | 10 passed (6 pre-existing + 4 new) |
| Profile injection (task 2.1) | `pytest tests/agents/test_profile_injection.py -x` | 0 | 2 passed + procedural no-regression 3 passed |
| Lint | `ruff check app/memory/store.py app/agents/state.py app/agents/nodes.py app/prompts` | 0 | clean |
| Full suite (SQLite/Postgres) | `make test` / `pytest -q` | 2 | ⚠️ NOT a regression — 544 errors are `psycopg.OperationalError: 127.0.0.1:5433 refused` (dev Postgres container down; lifespan/checkpointer needs it). Diff touches no DB/config. Re-run green after `docker compose up -d db`. |

### Rollback

- Revert code + prompts: `git revert c00eaa6 dc58563 651d984 bf7c452 18b2964 7fbf53c ace1c75` (or drop the branch / close the PR). No migration to undo (no schema change). Prompt versions revert cleanly by restoring `active.yaml` to concierge:7 / planner:4 / memory_extraction:2.

### Harness-Delta

- none
