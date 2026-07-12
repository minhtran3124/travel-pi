---
slug: min-65-chatbot-intelligence
doc: detail-design
created: 2026-07-12
status: proposed
depends_on: HLD.md (quyết định phương án); nền tảng đã ship — agent-memory-layers P1/P2, agent-memory-semantic, min-53, min-55, min-58
---

# Detail Design — MIN-65

Đường dẫn file tính từ `apps/api/` trừ khi ghi khác.

## D1 — `trip_facts`: entity/slot state trong session

### Schema (`app/agents/state.py`)

```python
def merge_trip_facts(old: dict | None, new: dict | None) -> dict:
    """Reducer: giá trị mới non-None ghi đè; không bao giờ xoá fact đã biết."""
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if v is not None:
            merged[k] = v
    return merged

class TravelAgentState(MessagesState):
    ...
    trip_facts: Annotated[dict, merge_trip_facts]   # NEW
    preferences: str                                 # NEW (D2) — block text đã format
```

Key chuẩn hoá (tất cả optional): `destination`, `origin`, `start_date` (ISO),
`end_date` (ISO), `adults`, `children`, `rooms`, `budget_amount`, `budget_currency`,
`cabin_class`, `hotel_area`. Thread-scoped (checkpointer persist trong conversation);
**không** ghi vào BaseStore (per HLD §2 — per-turn slots không thuộc store).

### Injection (`system_with_summary`)

Fold thêm block (sau profile/instructions, trước summary), chỉ khi non-empty:

```
Known trip facts (already provided by the traveller — do NOT ask again;
if a required field is missing here, ask ONLY for that field):
- destination: Da Nang
- start_date: 2026-08-15 · end_date: 2026-08-20
- party: 2 adults, 1 child
```

Giữ hành vi hiện tại: cả 2 call site (`supervisor.py`, `subagents/_base.py`) đi qua
cùng hàm — không sửa call site.

### Vì sao giải quyết được gap summarizer-lossy

Facts sống trong state field, không phụ thuộc summarizer LLM "nhớ giữ". Summary chỉ còn
lo ngữ cảnh hội thoại. Không cần sửa summarizer.

## D2 — Preference auto-injection cho mọi sub-agent

`load_context_node` (`app/agents/nodes.py`) hiện load trip_context + instructions + profile.
Thêm: `search_preferences(store, user_id, limit=8)` (recency full-read, **không** query
semantic — store nhỏ, per HLD §2), **loại các `PROFILE_KEYS`** (đã có block profile riêng),
format thành block text:

```
Traveller preferences (learned from past conversations — use to personalise,
confirm before acting on stale ones):
- diet: vegetarian
- hotel_type: prefers beachfront 4-5 star
```

→ `state["preferences"]` → fold trong `system_with_summary`. Best-effort như profile
(store miss / no user → `""`). Journal tool `get_user_preferences` giữ nguyên cho truy vấn sâu.

Token cost: ≤8 dòng ngắn/turn — chấp nhận được (đúng nguyên tắc bounded full-read).

## D3 — Supervisor: slot extraction + secondary intent (một LLM call)

### Schema (`app/agents/supervisor.py`)

```python
class ExtractedSlots(BaseModel):
    """Raw mentions — verbatim text, KHÔNG tự resolve. Code sẽ normalize."""
    destination: str | None = None
    origin: str | None = None
    start_date_text: str | None = None   # vd "15/8", "tuần sau"
    end_date_text: str | None = None     # vd "20/8", "5 ngày" (duration cũng để raw)
    adults: int | None = None
    children: int | None = None
    rooms: int | None = None
    budget_text: str | None = None       # vd "khoảng 20 triệu", "$2000"
    cabin_class: str | None = None
    hotel_area: str | None = None

class SupervisorIntent(BaseModel):
    target_agent: Literal["planner","concierge","journal","booking","budget"]
    secondary_agent: Literal["planner","concierge","journal","budget"] | None = None
    language: str
    slots: ExtractedSlots | None = None
```

- `secondary_agent`: **không có `booking`** (HLD non-goal) và prompt yêu cầu ≠ `target_agent`,
  chỉ đặt khi user thực sự nêu 2 nhu cầu trong 1 câu. Nếu `target_agent == "booking"` →
  code bỏ qua secondary.
- Mọi field slots optional → không ép model bịa. Prompt: "extract ONLY what the traveller
  explicitly stated in this turn; leave null otherwise".

### Normalization trong code (node supervisor, sau LLM call)

- `start_date_text`/`end_date_text` → `core.dates.resolve_travel_date(raw, today(ctx.timezone))`;
  resolve fail → **drop slot** (không guess — nhất quán "never guess dates" PR #84). Duration
  ("5 ngày") khi có start_date → end = start + n-1; không có start → drop.
- `budget_text` → parse số + currency bằng regex đơn giản; fail → giữ nguyên text vào
  `budget_note`? **Không** — fail thì drop (đơn giản trước; free text vẫn nằm trong history).
- `adults/children/rooms` → int cast, drop nếu ≤0.
- `destination`/`origin` giữ raw text (fuzzy resolution đã có ở tool layer, `core/text.py`).

Command hiện tại `Command(update={current_flow, language}, goto=...)` mở rộng:
`update={..., "trip_facts": normalized, "pending_flows": [secondary] if hợp lệ else []}`.

### Prompt `prompts/supervisor/v6.md` + `active.yaml: supervisor: 6`

Nội dung thêm so với v5: (1) mô tả slots + quy tắc "verbatim only, null when unsure";
(2) quy tắc secondary: "if the message contains two distinct requests (e.g. flight AND
hotel), set target to the one that unblocks first, secondary to the other; never booking".
**Lưu ý bắt buộc** (critical pattern `supervisor-active-yaml-is-a-pointer`): tạo file v6
mới + flip pointer, không sửa v5; graph bake ở lifespan → dev cần rebuild
(`docker exec api-api-1 touch app/main.py`).

### Rủi ro routing degrade & chốt chặn

Schema phình có thể giảm chất lượng chọn `target_agent`. Chốt chặn: (a) toàn bộ field mới
optional; (b) dataset `routing.json` của eval MIN-58 chạy lại ở phase đo lường; (c) unit
test FakeLLM cho cả hai nhánh (có/không slots).

## D4 — Multi-intent dispatch: node `dispatch_next`

### State

`pending_flows: list[str]` (mặc định `[]`, supervisor ghi tối đa 1 phần tử — bound 2
intent/turn theo HLD §3.3).

### Graph (`app/agents/graph.py`, node trong `nodes.py`)

Static edge hiện tại `<sub-agent> → reflection` đổi thành `<sub-agent> → dispatch_next`:

```python
def dispatch_next(state) -> Command:
    pending = state.get("pending_flows") or []
    if pending:
        nxt, rest = pending[0], pending[1:]
        return Command(update={"current_flow": nxt, "pending_flows": rest}, goto=nxt)
    return Command(goto="reflection")
```

- Không LLM call — pure routing node.
- Reflection giữ nguyên: review **câu trả lời cuối cùng** (sau khi cả 2 intent đã chạy);
  vòng revise `goto=current_flow` → sub-agent → `dispatch_next` (pending đã rỗng) →
  reflection: không đổi hành vi revise.
- Nhánh `plan` (HITL booking) không đi qua dispatch — giữ nguyên topology cũ của nó.
- `destinations=` của supervisor Command cập nhật thêm không đổi (vẫn goto 1 sub-agent);
  thêm `dispatch_next` vào graph nodes.

Sub-agent thứ hai nhìn thấy messages của sub-agent thứ nhất trong state → tự nhiên nối
mạch ("chuyến bay đã chọn ở trên") mà không cần plumbing thêm.

## D5 — Store hygiene (tăng cường extraction, giữ tối thiểu)

1. **Timestamps**: `upsert_preference/instruction/episode` (`app/memory/store.py`) ghi thêm
   `"updated_at": datetime.now(timezone.utc).isoformat()` vào value dict (không đổi schema
   index — `text` vẫn là field được embed). Injection block D2 có thể dùng để ưu tiên
   recency khi vượt limit.
2. **Canonical keys chống key-drift**: `prompts/memory_extraction/v5.md` (+ flip
   `active.yaml`) thêm danh mục key chuẩn: `diet, hotel_type, airline, cabin_class,
   budget_band, seat, travel_pace, language, ...` + quy tắc "reuse an existing canonical
   key when the fact updates a prior one; only invent a new key for a genuinely new fact"
   → upsert key-addressed tự thành UPDATE thay vì duplicate (dạng tối giản của Mem0
   ADD/UPDATE — đủ cho scale này, per HLD §3.1).
3. **Không làm**: TTL/decay, contradiction LLM pass, versioning — premature (HLD non-goals).

## D6 — Suggestion rule engine (`app/agents/suggestions.py`)

### API — giữ tương thích 2 call site

```python
def suggestions_for_flow(
    current_flow: str | None,
    *,
    trip_facts: dict | None = None,
    profile: dict | None = None,
    preferences: str = "",
) -> list[str]:   # vẫn trả list i18n key, MAX 3
```

- `routers/agent.py:306` (non-stream): có final state → truyền đủ tham số.
- `streaming/mapper.py:246` (done SSE): dùng cùng cơ chế sink/final-state như
  `run_memory_extraction_from_stream` để lấy trip_facts/profile lúc drain; nếu điểm build
  done-event không chạm được final state → fallback gọi với `current_flow` như cũ
  (degrade về hành vi MIN-55, không vỡ). Chi tiết chốt lúc implement (ghi trong PLAN).

### Rule engine

Bảng rule có thứ tự (specific → generic), lấy key đầu tiên match cho đến đủ 3;
fallback cuối = map tĩnh `_FLOW_SUGGESTIONS` hiện tại (bảo toàn AC "≥80% có suggestion" —
không bao giờ ít hơn hiện trạng):

| Điều kiện (ví dụ) | Key gợi ý |
|---|---|
| flow=booking & vừa book flight & chưa có hotel trong trip_facts | `book_hotel_next` |
| flow=booking & vừa book hotel | `transport_to_hotel`, `activities_near_destination` |
| trip_facts.start_date trong ≤14 ngày | `weather_before_trip`, `packing_tips` |
| profile.travel_group == family | `family_activities` |
| preferences chứa budget signal / flow=budget | `budget_check` |
| trip_facts.destination có & flow=concierge | `local_tips_destination` |
| (fallback) | map tĩnh theo flow như MIN-55 |

Key mới (~8) cần entry `Chat.followups.<key>.{label,prompt}` trong
`apps/web/messages/en.json` + `vi.json` (FE `ChatSuggestions.tsx` resolve động — không sửa
component). Interrupt-pending vẫn suppress như cũ.

Deterministic → unit test thuần không cần LLM.

## D7 — Preference-aware re-rank trong tools

### `app/tools/_ranking.py` (mới)

```python
def rank_by_preference(items: list[T], preferences: str, extractors: ...) -> tuple[list[T], list[str]]
    """Stable sort: điểm boost = số preference keyword khớp attribute của item.
    Trả (items đã xếp, matched_reasons) — reasons để tool đưa vào summary string."""
```

- Matcher keyword deterministic (lowercase, có fold diacritics qua `core/text.py`):
  hotel — star ("5 sao"/"5-star"), khu vực ("beach", "gần biển"), type; flight — airline
  name, khung giờ ("morning"/"sáng", "evening"/"tối") map vào departure hour.
  Prefs là free text → matcher keyword là trade-off chấp nhận cho v1 (ghi rõ limitation).
- **Stable sort** trên kết quả deterministic của service → không phá quy tắc "same query
  = same result" (cùng user + cùng prefs → vẫn deterministic).

### Wiring

`search_hotels`/`browse_hotels` (`tools/hotel_tools.py`), `search_flights`
(`tools/flight_tools.py`): nhận `preferences: Annotated[str, InjectedState("preferences")]`
— **inline Annotated, KHÔNG dùng `args_schema=`** (gotcha đã ghi:
`explicit-args-schema-breaks-langgraph-injection`). Re-rank trước khi build summary +
`panel_result`; khi có match, summary string nối: `"Đã ưu tiên theo sở thích: <reasons>"`
→ vừa là ranking vừa là "reason đi kèm" (AC pillar 3). Panel giữ thứ tự đã re-rank.

## D8 — Prompt quality pass (một task, một giọng văn)

| Prompt | Version mới | Nội dung thêm |
|---|---|---|
| `communication_style` | v6 (active 5→6) | "Every recommendation carries a one-line reason tied to the traveller's stated facts or preferences ('vì bạn đi cùng trẻ nhỏ…'). List answers end with the single most relevant next step." |
| `concierge` | v10 | Intent inference: chủ động nêu ngụ ý theo mùa/thời tiết/sự kiện ("tháng 7 là mùa cao điểm — nên đặt sớm"); ask-only-missing đối chiếu Known trip facts |
| `planner` | v8 | Ask-only-missing; default-with-confirm ("mặc định 2 người lớn — xác nhận giúp mình?") chỉ cho field không bắt buộc bởi tool signature |
| `booking` | v7 | Ask-only-missing (tool args vẫn là hard gate — không nới) |

Tất cả: file version mới + flip `active.yaml` (không sửa file cũ); nhớ graph-rebuild khi dev.

## D9 — Eval trước, đo sau (MIN-58 harness)

### Multi-turn harness (`eval/harness.py`)

`run_case` thêm hỗ trợ shape mới (back-compat với `input` đơn):

```jsonc
{
  "turns": ["Tìm khách sạn Đà Nẵng 15-20/8, 2 người lớn 1 trẻ em", "Còn vé máy bay thì sao?"],
  "new_thread_at": null,        // hoặc index — turn đó mở thread_id MỚI, cùng user_id (cross-session)
  "metrics": ["memory_recall"]
}
```

- Cùng `thread_id` cho các turn (trừ `new_thread_at` → thread mới, cùng user, cùng store —
  đo "prefs nhớ qua session"). `actual_output` = reply cuối.
- Suggestions: graph không tự sinh → harness gọi `suggestions_for_flow(final_state...)`
  sau invoke, gắn vào test case (retrieval-free, deterministic).

### Metrics (`eval/metrics_geval.py` + `run_deepeval.py`)

- `memory_recall` (GEval): "assistant reuses facts the traveller already provided (dates,
  party, destination, prefs) and does NOT re-ask for them; asking for a genuinely new
  field is fine."
- `suggestion_relevance`: 2 lớp — deterministic (suggestions non-empty + key thuộc catalog;
  đo AC ≥80%) + GEval relevance (label EN của key có liên quan ngữ cảnh không).
- Datasets mới `eval/datasets/memory.json`, `suggestions.json`; đăng ký trong `loader.load_all()`;
  per-case rubric filter qua `metadata` như MIN-58 calibration.

### Vận hành

Baseline chạy **trước** wave implement (P0), re-run ở P4 → RESULTS.md so delta. Lưu ý đã
ghi trong memory repo: eval bypass DB config → chạy trong container, cần key judge thật;
không có key → documented-skip, không silent-pass.

## Test matrix (proof)

| Behavior | Check |
|---|---|
| reducer merge: mới ghi đè, None không xoá | `tests/agents/test_trip_facts.py` |
| system_with_summary fold trip_facts/preferences; rỗng → base không đổi | same |
| supervisor: slots verbatim → normalize (date resolve, int cast, drop-on-fail) | `tests/agents/test_supervisor_slots.py` (FakeLLM) |
| supervisor: secondary hợp lệ → pending_flows; booking primary → secondary bị bỏ | same |
| load_context: prefs → block (loại PROFILE_KEYS); store miss → "" | `tests/agents/test_preferences_injection.py` |
| dispatch_next: pending → goto kế tiếp đúng thứ tự; rỗng → reflection; revise loop không vỡ | `tests/agents/test_multi_intent_routing.py` |
| store: upsert ghi updated_at; back-compat value cũ không có field | `tests/memory/test_store_timestamps.py` |
| extractor v5: canonical key reuse (FakeLLM) | `tests/memory/test_extractor.py` mở rộng |
| suggestions: từng rule + fallback + MAX 3 + key ∈ catalog | `tests/agents/test_suggestions_engine.py` |
| ranking: boost đúng, stable sort, no-prefs → thứ tự nguyên trạng, reasons đúng | `tests/tools/test_preference_ranking.py` |
| tools: injection `preferences` không lộ vào model schema | same |
| eval: multi-turn cùng thread; new_thread_at tách thread cùng user | `tests/eval/test_harness_multiturn.py` (FakeLLM) |
| prompts mới load được qua registry + active.yaml trỏ đúng | registry check trong verify task |

## Risks & mitigations

- **Routing degrade vì schema phình** → optional fields, routing eval re-run, FakeLLM tests (D3).
- **Slot normalize sai ngày** → tái dùng `core/dates` (đã có suite riêng + nguyên tắc raise-don't-guess); fail → drop.
- **Trip facts cũ khi user đổi chuyến** ("thôi, đi Huế đi") → giá trị mới ghi đè theo reducer; số người/ngày cũ có thể sót — prompt "Known trip facts" kèm "confirm if the traveller appears to have changed plans". Chấp nhận residual risk v1.
- **Streaming path không lấy được final state cho suggestions** → fallback flow-only (degrade về MIN-55, không vỡ contract).
- **Keyword matcher rank sai** → chỉ boost (không lọc bỏ), stable sort giữ thứ tự gốc trong nhóm cùng điểm.
- **Hook risk-corroboration**: không endpoint mới, không đổi shape response; diff prompt/test có chữ "session"/xoá assert có thể false-positive → xử lý theo memory đã ghi (`RISK_WARN_CATEGORIES` khi cần).
