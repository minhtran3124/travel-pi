---
slug: min-65-chatbot-intelligence
status: proposed
owner: Minh Tran
created: 2026-07-12
ticket: MIN-65
---

# MIN-65 — Chatbot Intelligence: Memory, Reasoning & Suggestion Quality

## 1. Motivation

Xem `HLD.md` §1 — 3 pillar của ticket; nền memory dài hạn đã ship, plan này đắp đúng gap:
entity/slot tracking, preference injection rộng, multi-intent routing, suggestion rule
engine + preference re-rank, và eval-first để đo được cải thiện (AC ticket).

## 2. Non-goals

Theo `HLD.md` §6: không adopt Mem0/LangMem/Letta; không LLM free-text suggestions; không
nâng reflection rubric (MIN-59); booking không làm secondary intent; không memory cho
anonymous user; không đổi public contract `/agent/*`.

## 3. Success Criteria

- User không phải lặp lại thông tin đã cung cấp trong cùng conversation (eval `memory_recall` cải thiện vs baseline).
- Preferences nhớ qua session mới (case `new_thread_at` pass).
- ≥80% câu trả lời có suggestion liên quan (deterministic layer của `suggestion_relevance`).
- Routing eval (`routing.json`) không regress sau khi supervisor schema mở rộng.
- `make test` xanh (SQLite) + `make test-docker` xanh (Postgres parity) ở cuối.

## 4. Tasks

> Wave = phase HLD: W1-2 = P0 eval-first · W3-5 = P1 memory + P2 reasoning · W6 = P3 suggestions · W7-8 = prompt pass + đo lường.
> Mọi verify chạy từ repo root trừ khi ghi khác; `PY=.venv/bin/python`, BE tests chạy trong `apps/api/`.

### Task 1.1 — Multi-turn eval harness + datasets mới

```xml
<task id="1.1" wave="1">
  <files>apps/api/eval/harness.py, apps/api/eval/loader.py, apps/api/eval/datasets/memory.json, apps/api/eval/datasets/suggestions.json, apps/api/tests/eval/test_harness_multiturn.py</files>
  <action>Mở rộng run_case hỗ trợ case shape {"turns": [...], "new_thread_at": int|null} (DESIGN D9): các turn dùng chung thread_id trên compiled graph; new_thread_at mở thread_id mới cùng user_id (cross-session, cùng store); actual_output = reply cuối; back-compat hoàn toàn với case "input" đơn. Sau invoke cuối, gọi suggestions_for_flow trên final state và gắn kết quả vào test case (field/metadata cho metric 1.2 — hiện tại là chữ ký cũ flow-only, wave 6 sẽ giàu hơn). Viết eval/datasets/memory.json (≥8 case: recall ngày/số người/điểm đến trong thread; ≥2 case cross-session preference qua new_thread_at) và suggestions.json (≥8 case phủ các flow), khai báo trong loader.load_all() với validation shape mới. Test bằng FakeLLM graph fixture như tests/agents hiện có: chung thread giữ state, new_thread_at tách thread cùng user.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_harness_multiturn.py -x -q</verify>
  <done>run_case chạy được cả case đơn lẫn multi-turn/cross-session; 2 dataset mới load + validate; tests pass, không chạm LLM thật</done>
</task>
```

### Task 1.2 — Metrics `memory_recall` + `suggestion_relevance`

```xml
<task id="1.2" wave="1">
  <files>apps/api/eval/metrics_geval.py, apps/api/eval/run_deepeval.py, apps/api/tests/eval/test_metrics_registry.py</files>
  <action>Thêm GEval factory memory_recall (rubric DESIGN D9: reuse facts đã cung cấp, không re-ask; hỏi field mới là hợp lệ) và suggestion_relevance (GEval trên label EN của suggestion keys so với ngữ cảnh) vào GEVAL_METRICS; thêm lớp deterministic cho suggestion_relevance trong run_deepeval (suggestions non-empty + key thuộc catalog — đo AC ≥80%). Nối per-case rubric filter qua LLMTestCase.metadata như MIN-58 calibration. Gotcha deepeval 4.0.7: judge-key check là eager — test registry chạy với OPENAI_API_KEY=dummy và không execute metric.</action>
  <verify>cd apps/api && OPENAI_API_KEY=dummy DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/eval/test_metrics_registry.py -x -q</verify>
  <done>2 metric mới đăng ký + filter đúng theo metadata; deterministic layer tính tỉ lệ có-suggestion; tests pass không cần key thật</done>
</task>
```

### Task 2.1 — Baseline trước khi thay đổi hành vi

```xml
<task id="2.1" wave="2">
  <files>specs/min-65-chatbot-intelligence/BASELINE.md</files>
  <action>Chạy eval mới trên code hiện tại để có mốc so sánh: theo memory repo (eval-harness-bypasses-db-config-and-context) — chạy TRONG container api, configure agent_config + reload_from_db trước, cần OPENAI_API_KEY judge thật. Ghi BASELINE.md: bảng score memory_recall / suggestion_relevance (+ routing hiện hành), lệnh chạy chính xác, ngày chạy. Kỳ vọng baseline thấp ở memory_recall (chưa có trip_facts) — đó là mốc đo cải thiện. Nếu không có key: ghi documented-skip + lệnh để user chạy, KHÔNG silent-pass.</action>
  <verify>test -s specs/min-65-chatbot-intelligence/BASELINE.md</verify>
  <done>BASELINE.md có score thật hoặc documented-skip kèm lệnh tái chạy</done>
</task>
```

### Task 3.1 — State foundation: `trip_facts`, `preferences`, `pending_flows`

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/agents/state.py, apps/api/tests/agents/test_trip_facts.py</files>
  <action>Thêm vào TravelAgentState: trip_facts (Annotated[dict, merge_trip_facts] — reducer DESIGN D1: non-None ghi đè, không xoá), preferences: str, pending_flows: list[str]. system_with_summary fold thêm 2 block theo đúng thứ tự và wording DESIGN D1/D2 ("Known trip facts — do NOT ask again…", "Traveller preferences…"); mọi field rỗng → trả base không đổi (giữ hành vi hiện tại cho user mới). Không sửa call site (supervisor/_base đi qua cùng hàm). Test: reducer merge các nhánh; fold đúng nội dung/thứ tự; rỗng → identity.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_trip_facts.py -x -q</verify>
  <done>3 field mới + reducer + injection block hoạt động; toàn bộ test agents hiện có vẫn xanh (chạy tests/agents -q nếu nghi ngờ)</done>
</task>
```

### Task 4.1 — Supervisor: slot extraction + secondary intent (prompt v6)

```xml
<task id="4.1" wave="4">
  <files>apps/api/app/agents/supervisor.py, apps/api/app/prompts/supervisor/v6.md, apps/api/app/prompts/active.yaml, apps/api/tests/agents/test_supervisor_slots.py</files>
  <action>Mở rộng SupervisorIntent theo DESIGN D3: ExtractedSlots (raw verbatim, all-optional) + secondary_agent (Literal không có booking) + slots. Sau LLM call, normalize trong code: date qua core.dates.resolve_travel_date với today(ctx.timezone) — fail thì DROP (never guess); duration cần start_date; int cast adults/children/rooms; budget regex đơn giản; destination/origin giữ raw. Command update thêm trip_facts=normalized và pending_flows=[secondary] (bỏ secondary khi target là booking hoặc trùng target). Tạo prompts/supervisor/v6.md MỚI (copy v5 + quy tắc slots verbatim-or-null + quy tắc secondary) và flip active.yaml supervisor: 6 — KHÔNG sửa v5 (critical pattern supervisor-active-yaml-is-a-pointer). Test FakeLLM: slots resolve đúng/drop đúng, secondary hợp lệ → pending_flows, booking → secondary bị bỏ, routing cũ không đổi khi slots null.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_slots.py -x -q</verify>
  <done>Supervisor 1 LLM call trả routing + slots; normalization thuần code có test; active.yaml trỏ v6</done>
</task>
```

### Task 4.2 — Preference auto-injection tại `load_context`

```xml
<task id="4.2" wave="4">
  <files>apps/api/app/agents/nodes.py, apps/api/tests/agents/test_preferences_injection.py</files>
  <action>load_context_node đọc thêm search_preferences(store, user_id, limit=8) (recency full-read, không query semantic — DESIGN D2), LOẠI các PROFILE_KEYS (đã có block profile), format block "Traveller preferences…" → state["preferences"]. Best-effort như profile: store miss / no user_id / lỗi → "". Test: prefs trong store → block đúng nội dung, profile keys bị loại, store rỗng → "", lỗi store không raise.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_preferences_injection.py -x -q</verify>
  <done>Mọi sub-agent thấy preferences qua system message mỗi turn; user mới không đổi hành vi</done>
</task>
```

### Task 5.1 — Multi-intent dispatch node + graph rewire

```xml
<task id="5.1" wave="5">
  <files>apps/api/app/agents/graph.py, apps/api/app/agents/nodes.py, apps/api/tests/agents/test_multi_intent_routing.py</files>
  <action>Thêm node dispatch_next (DESIGN D4, pure code không LLM): pending_flows non-empty → Command(update={current_flow: next, pending_flows: rest}, goto=next); rỗng → goto reflection. Rewire static edge của cả 5 sub-agent: sub-agent → dispatch_next (thay vì → reflection). Nhánh plan/HITL giữ nguyên topology. Test với FakeLLM graph: (a) 2 intent chạy đúng thứ tự rồi mới reflection, sub-agent 2 thấy messages của sub-agent 1; (b) single intent → thẳng reflection (hành vi cũ); (c) reflection REVISE loop-back qua dispatch_next không lặp vô hạn (pending đã rỗng).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py -x -q</verify>
  <done>Query đa ý định được xử lý tuần tự trong 1 turn, tối đa 2 sub-agent; hành vi single-intent và revise không đổi</done>
</task>
```

### Task 5.2 — Store hygiene: `updated_at` + canonical keys (extraction v5)

```xml
<task id="5.2" wave="5">
  <files>apps/api/app/memory/store.py, apps/api/app/prompts/memory_extraction/v5.md, apps/api/app/prompts/active.yaml, apps/api/tests/memory/test_store_timestamps.py</files>
  <action>upsert_preference/upsert_instruction/upsert_episode ghi thêm updated_at (UTC ISO — dùng datetime.now(timezone.utc), không utcnow()) vào value dict; đọc back-compat với value cũ không có field; KHÔNG đổi index config (text vẫn là field embed). Tạo prompts/memory_extraction/v5.md (copy v4 + danh mục canonical keys DESIGN D5 + quy tắc reuse-key-on-update), flip active.yaml memory_extraction: 5. Test: upsert ghi timestamp, get/search đọc được record cũ lẫn mới; extractor test mở rộng với FakeLLM trả canonical key.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_store_timestamps.py tests/memory/test_extractor.py -x -q</verify>
  <done>Value có updated_at, back-compat; prompt v5 active; key-drift giảm qua canonical vocabulary</done>
</task>
```

### Task 6.1 — Suggestion rule engine + FE i18n keys

```xml
<task id="6.1" wave="6">
  <files>apps/api/app/agents/suggestions.py, apps/api/app/routers/agent.py, apps/api/app/streaming/mapper.py, apps/web/messages/en.json, apps/web/messages/vi.json, apps/api/tests/agents/test_suggestions_engine.py</files>
  <action>Thay _FLOW_SUGGESTIONS tĩnh bằng rule engine DESIGN D6: signature suggestions_for_flow(current_flow, *, trip_facts=None, profile=None, preferences="") trả list key MAX 3, bảng rule ordered specific→generic, fallback cuối là map tĩnh hiện tại (không bao giờ ít suggestion hơn hiện trạng). Catalog thêm ~8 key (book_hotel_next, transport_to_hotel, activities_near_destination, weather_before_trip, packing_tips, family_activities, budget_check, local_tips_destination) + entry Chat.followups.<key>.{label,prompt} trong CẢ en.json và vi.json (FE resolve động, không sửa component). Non-stream: routers/agent.py truyền final state. Stream: lấy trip_facts/profile lúc drain theo cùng cơ chế sink như run_memory_extraction_from_stream; nếu điểm build done-event không chạm được final state → fallback flow-only (degrade an toàn về MIN-55). Giữ suppress khi interrupt pending. Test: từng rule, fallback, MAX 3, key luôn thuộc catalog.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_suggestions_engine.py -x -q && node -e "const en=require('/Users/minhtran/Documents/minhtran3124/developer/travel-pi/apps/web/messages/en.json'),vi=require('/Users/minhtran/Documents/minhtran3124/developer/travel-pi/apps/web/messages/vi.json');for(const k of ['book_hotel_next','transport_to_hotel','activities_near_destination','weather_before_trip','packing_tips','family_activities','budget_check','local_tips_destination']){if(!en.Chat.followups[k]||!vi.Chat.followups[k])throw new Error(k)};console.log('i18n ok')"</verify>
  <done>Suggestions state-aware + cá nhân hoá theo profile/prefs; cả 2 locale đủ key; contract ChatResponse.suggestions không đổi</done>
</task>
```

### Task 6.2 — Preference-aware re-rank trong hotel/flight tools

```xml
<task id="6.2" wave="6">
  <files>apps/api/app/tools/_ranking.py, apps/api/app/tools/hotel_tools.py, apps/api/app/tools/flight_tools.py, apps/api/tests/tools/test_preference_ranking.py</files>
  <action>Tạo tools/_ranking.py: rank_by_preference(items, preferences, ...) -> (ranked, reasons) — keyword matcher deterministic (fold diacritics qua core/text), STABLE sort boost-only (không lọc bỏ item nào) theo DESIGN D7: hotel (star/khu vực/type), flight (airline, khung giờ sáng/tối theo departure hour). Wire vào search_hotels/browse_hotels/search_flights: nhận preferences qua Annotated[str, InjectedState("preferences")] — inline Annotated, TUYỆT ĐỐI không dùng @tool(args_schema=) (gotcha explicit-args-schema-breaks-langgraph-injection); re-rank trước khi build summary + panel_result; có match → summary nối "Đã ưu tiên theo sở thích: <reasons>". Test: boost đúng, stable, prefs rỗng → thứ tự nguyên trạng, injected arg không lộ vào model schema, determinism giữ nguyên với cùng input+prefs.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_preference_ranking.py -x -q</verify>
  <done>Kết quả hotel/flight xếp theo preference đã học, panel + summary nhất quán, deterministic</done>
</task>
```

### Task 7.1 — Prompt quality pass (reasons, intent inference, ask-only-missing)

```xml
<task id="7.1" wave="7">
  <files>apps/api/app/prompts/communication_style/v6.md, apps/api/app/prompts/concierge/v10.md, apps/api/app/prompts/planner/v8.md, apps/api/app/prompts/booking/v7.md, apps/api/app/prompts/active.yaml</files>
  <action>Một task một giọng văn (DESIGN D8): communication_style v6 — mọi recommendation kèm 1 dòng lý do gắn với facts/preferences của traveller, kết thúc list-answer bằng next step liên quan nhất; concierge v10 — intent inference chủ động (mùa cao điểm/thời tiết/sự kiện), ask-only-missing đối chiếu Known trip facts; planner v8 — ask-only-missing + default-with-confirm cho field không bị tool signature bắt buộc; booking v7 — ask-only-missing, tool args vẫn là hard gate. Tất cả tạo FILE MỚI + flip active.yaml, không sửa version cũ. Cẩn trọng ngôn ngữ: không hardcode tagline/nội dung tiếng Việt vào prompt (gotcha MIN-60 language-mixing).</action>
  <verify>cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'reason' in registry.get('communication_style').lower(); [registry.get(n) for n in ('supervisor','concierge','planner','booking','memory_extraction')]; print('prompts ok')"</verify>
  <done>4 prompt version mới active, registry load sạch; guardrail quality phủ cả 5 đường trả lời</done>
</task>
```

### Task 8.1 — Đo lường: re-run eval vs baseline + RESULTS

```xml
<task id="8.1" wave="8">
  <files>specs/min-65-chatbot-intelligence/RESULTS.md</files>
  <action>Chạy lại toàn bộ eval (memory, suggestions, routing, và các dataset MIN-58 cũ) cùng điều kiện với 2.1 (trong container, key thật); ghi RESULTS.md: bảng delta vs BASELINE.md từng metric, đạt/không đạt AC (memory_recall cải thiện, suggestion ≥80%, routing không regress), phân tích ngắn case fail. Chạy full make test (SQLite) và make test-docker (Postgres parity — nhớ gotcha docker-py312 + stale travel.db sau schema-less change vẫn nên mktemp DB). Không có key → documented-skip như 2.1.</action>
  <verify>test -s specs/min-65-chatbot-intelligence/RESULTS.md && cd apps/api && ../../.venv/bin/python -m pytest tests/agents tests/memory -q</verify>
  <done>RESULTS.md có delta thật vs baseline; suite agents+memory xanh; AC ticket được đánh giá tường minh từng mục</done>
</task>
```

## 5. Risks

Chi tiết tại `DESIGN.md` §Risks. Tóm tắt: routing degrade do schema supervisor phình
(mitigate: optional fields + routing eval); slot normalize sai (tái dùng `core/dates`,
drop-on-fail); streaming path không lấy được final state cho suggestions (fallback
flow-only); keyword ranking thô (boost-only, không lọc); hook risk-corroboration
false-positive trên từ `session`/xoá assert trong test refactor (dùng
`RISK_WARN_CATEGORIES` đúng cách khi bị chặn). Prompt mới → dev phải rebuild graph
(`docker exec api-api-1 touch app/main.py`) khi verify tay.

## 6. Status Log

- 2026-07-12 — Plan drafted (HLD.md + DESIGN.md + PLAN.md). Chưa execute.
