---
slug: min-55-shortcut-suggestions
status: shipped
owner: Minh Tran
created: 2026-07-06
---

# Chat Shortcut Rút Gọn + Follow-up Suggestions (MIN-55) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Rút gọn 4 shortcut ở màn chat đầu tiên, và sau mỗi câu trả lời của agent trả về 2–3 follow-up suggestion chip bám theo `current_flow` để user tap nhanh.

**Architecture:** Heuristic thuần trên BE (`current_flow` → danh sách *khoá gợi ý* ổn định, locale-agnostic) dùng chung cho cả `/agent/chat` (field `suggestions` trên `ChatResponse`) và stream (`done` SSE event thêm `suggestions`). FE map khoá → label/prompt đã bản địa hoá qua i18n catalog (`Chat.followups`), lưu ở state của `useAgentStream`, render bằng component `ChatSuggestions` giữa transcript và composer. Cơ chế hybrid: phase này dùng heuristic; LLM-generated để dành ticket sau, giữ nguyên chữ ký `suggestions_for_flow` nên contract không đổi.

**Tech Stack:** FastAPI + Pydantic v2 + LangGraph (BE); Next.js + next-intl + vitest (FE). Node v24 cho mọi lệnh FE.

---

## 1. Motivation

Shortcut lần đầu hiện là câu hoàn chỉnh dài, khó quét/tap trên mobile. Và sau khi bot trả lời chưa có gợi ý follow-up nào — user phải gõ tay. MIN-55 giải quyết cả hai: (1) rút gọn label mở đầu; (2) sinh 2–3 chip gợi ý theo ngữ cảnh (intent/flow) vừa trao đổi.

## 2. Non-goals

- **Không** dùng LLM để sinh suggestion ở phase này (quyết định hybrid: heuristic trước). Giữ chữ ký `suggestions_for_flow` để phase sau thay ruột.
- **Không** thêm endpoint mới (dùng field additive trên response envelope hiện có).
- **Không** đổi prompt gửi lên agent của shortcut mở đầu — chỉ rút gọn `*Label` hiển thị (giữ `*Prompt` là câu đầy đủ để agent hiểu rõ intent).
- **Không** persist suggestion vào DB (thuần dẫn xuất từ `current_flow` mỗi lượt).

## 3. Success Criteria

1. 4 shortcut mở đầu hiển thị dạng cụm ngắn (≤ ~24 ký tự, có emoji) ở cả en + vi; prompt gửi agent không đổi.
2. Sau mỗi lượt trả lời không-interrupt, FE render 2–3 chip follow-up đúng theo `current_flow`; tap chip gửi prompt tương ứng và chip biến mất khi lượt mới bắt đầu.
3. Flow không xác định / `None` / interrupt-pending → không có chip (mảng rỗng).
4. Cả `/agent/chat` (`ChatResponse.suggestions`) và `/agent/stream` (`done.suggestions`) trả cùng bộ khoá cho cùng một flow.
5. Toàn bộ test BE + FE liên quan xanh; không vỡ contract cũ (field/khoá đều additive, default rỗng).

## 4. Tasks

### Task 1.1 — BE: heuristic sinh khoá gợi ý (pure helper + tests)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/agents/suggestions.py, apps/api/tests/api/agent/test_suggestions.py</files>
  <action>Tạo helper thuần `suggestions_for_flow(current_flow: str | None) -> list[str]` map mỗi flow (planner/concierge/journal/booking/budget) sang tối đa MAX_SUGGESTIONS=3 khoá gợi ý ổn định, prefix bằng tên flow (vd "booking.otherOptions"); flow None/rỗng/không xác định → []. Viết test trước (TDD): parametrize theo `ALL_SUBAGENTS` khẳng định 1..3 khoá và mọi khoá prefix `f"{flow}."`; parametrize None/""/"unknown"/"supervisor" → []. Giữ chữ ký ổn định (phase sau thay bằng LLM).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_suggestions.py -x</verify>
  <done>Helper trả bộ khoá bounded đúng cho 5 flow, [] cho None/unknown; test xanh.</done>
</task>
```

Nội dung `app/agents/suggestions.py`:

```python
"""Context-aware follow-up suggestion keys, keyed off the agent's current_flow.

Deterministic heuristic (MIN-55, phase 1): each sub-agent flow maps to a small,
curated set of follow-up suggestion *keys*. Keys are locale-agnostic stable
identifiers; the web client resolves them to localized chip labels/prompts via
its i18n catalog (apps/web/messages/*.json -> Chat.followups). Returns [] for an
unknown/None flow so the client renders no chips.

A future phase may swap this map for LLM-generated suggestions; keep the
`suggestions_for_flow` signature stable so callers (router + stream mapper) and
the response contract do not change.
"""

from __future__ import annotations

#: Max chips surfaced per turn (keep the UI uncluttered — MIN-55).
MAX_SUGGESTIONS = 3

_FLOW_SUGGESTIONS: dict[str, list[str]] = {
    "planner": ["planner.addDay", "planner.adjustBudget", "planner.findStay"],
    "concierge": [
        "concierge.nearbyPlaces",
        "concierge.checkWeather",
        "concierge.getThere",
    ],
    "journal": ["journal.addNote", "journal.viewTimeline", "journal.tripSummary"],
    "booking": ["booking.otherOptions", "booking.bookThis", "booking.comparePrices"],
    "budget": ["budget.addExpense", "budget.remaining", "budget.breakdown"],
}


def suggestions_for_flow(current_flow: str | None) -> list[str]:
    """Return up to MAX_SUGGESTIONS follow-up suggestion keys for a flow.

    :param current_flow: The sub-agent the supervisor last routed to
        (``planner|concierge|journal|booking|budget``) or ``None``.
    :return: A list of stable suggestion keys, or ``[]`` when the flow is
        unknown/``None``.
    """
    if not current_flow:
        return []
    return _FLOW_SUGGESTIONS.get(current_flow, [])[:MAX_SUGGESTIONS]
```

Test `tests/api/agent/test_suggestions.py`:

```python
import pytest

from app.agents.constants import ALL_SUBAGENTS
from app.agents.suggestions import MAX_SUGGESTIONS, suggestions_for_flow


@pytest.mark.parametrize("flow", ALL_SUBAGENTS)
def test_known_flow_returns_bounded_prefixed_keys(flow):
    keys = suggestions_for_flow(flow)
    assert 1 <= len(keys) <= MAX_SUGGESTIONS
    assert all(k.startswith(f"{flow}.") for k in keys)


@pytest.mark.parametrize("flow", [None, "", "unknown", "supervisor"])
def test_unknown_or_none_flow_returns_empty(flow):
    assert suggestions_for_flow(flow) == []
```

> Lưu ý: `ALL_SUBAGENTS` sống ở `app/agents/constants.py:23`. Nếu tuple đó chứa tên nào chưa có trong `_FLOW_SUGGESTIONS`, test sẽ đỏ ngay — đó là guard cố ý để hai bên không lệch.

---

### Task 1.2 — FE: rút gọn label mở đầu + thêm i18n catalog follow-ups

```xml
<task id="1.2" wave="1">
  <files>apps/web/messages/en.json, apps/web/messages/vi.json</files>
  <action>(Part 1) Rút gọn 4 giá trị `Chat.suggestions.*Label` thành cụm ngắn dễ tap (kèm emoji), GIỮ NGUYÊN các `*Prompt`. (Part 2) Thêm nhánh `Chat.followups` với 5 flow × 3 khoá, mỗi khoá có `{ "label", "prompt" }` — khoá phải khớp 1:1 với `_FLOW_SUGGESTIONS` ở Task 1.1 (planner/concierge/journal/booking/budget). Dịch song song en + vi, cùng cấu trúc khoá.</action>
  <verify>cd apps/web && node -e "['en','vi'].forEach(l=>{const m=require('./messages/'+l+'.json').Chat;const f=m.followups;['planner.addDay','planner.adjustBudget','planner.findStay','concierge.nearbyPlaces','concierge.checkWeather','concierge.getThere','journal.addNote','journal.viewTimeline','journal.tripSummary','booking.otherOptions','booking.bookThis','booking.comparePrices','budget.addExpense','budget.remaining','budget.breakdown'].forEach(k=>{const[a,b]=k.split('.');if(!f[a]||!f[a][b]||!f[a][b].label||!f[a][b].prompt)throw new Error(l+' missing '+k);});if(m.suggestions.planWeekendLabel.length>28)throw new Error(l+' label too long');});console.log('ok')"</verify>
  <done>4 label mở đầu ngắn gọn (giữ prompt); 15 khoá followups có đủ label+prompt ở cả en+vi; verify in "ok".</done>
</task>
```

Ví dụ rút gọn `Chat.suggestions.*Label` (en / vi) — chỉ đổi Label:

| Khoá | Label mới (en) | Label mới (vi) |
|---|---|---|
| planWeekend | `Weekend in Tokyo 🗾` | `Cuối tuần ở Tokyo 🗾` |
| findCoffee | `Coffee nearby ☕` | `Cà phê gần đây ☕` |
| checkWeather | `Weather in Bali ⛅` | `Thời tiết Bali ⛅` |
| checkBudget | `My budget 💰` | `Ngân sách 💰` |

Thêm nhánh `Chat.followups` (đặt cạnh `Chat.suggestions`). Mẫu (en) — dịch tương ứng cho vi:

```json
"followups": {
  "planner": {
    "addDay": { "label": "Add a day ➕", "prompt": "Add another day to this itinerary" },
    "adjustBudget": { "label": "Adjust budget 💰", "prompt": "Adjust this plan to fit my budget" },
    "findStay": { "label": "Find a stay 🏨", "prompt": "Find places to stay for this trip" }
  },
  "concierge": {
    "nearbyPlaces": { "label": "More nearby 📍", "prompt": "Show me other places nearby" },
    "checkWeather": { "label": "Weather ⛅", "prompt": "What's the weather there right now?" },
    "getThere": { "label": "How to get there 🧭", "prompt": "How do I get there?" }
  },
  "journal": {
    "addNote": { "label": "Add a note 📝", "prompt": "Add a note to my trip journal" },
    "viewTimeline": { "label": "Timeline 🗒️", "prompt": "Show my trip timeline" },
    "tripSummary": { "label": "Trip summary ✨", "prompt": "Summarize my trip so far" }
  },
  "booking": {
    "otherOptions": { "label": "Other options 🔁", "prompt": "Show me other options" },
    "bookThis": { "label": "Book this ✅", "prompt": "Book this one" },
    "comparePrices": { "label": "Compare prices ⚖️", "prompt": "Compare the prices" }
  },
  "budget": {
    "addExpense": { "label": "Add expense ➕", "prompt": "Add an expense to my budget" },
    "remaining": { "label": "Remaining 💵", "prompt": "How much budget do I have left?" },
    "breakdown": { "label": "Breakdown 📊", "prompt": "Show me the budget breakdown" }
  }
}
```

> Copy có thể tinh chỉnh sau; điều bắt buộc là **tập khoá** khớp Task 1.1. Không đổi `next-intl` schema/loader.

---

### Task 2.1 — BE: field `suggestions` trên ChatResponse + /agent/chat

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/schemas/agent.py, apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_agent_chat.py</files>
  <action>Thêm `suggestions: list[str] = Field(default_factory=list)` vào `ChatResponse` (giữ backward-compat). Trong `agent_chat` (routers/agent.py): import `suggestions_for_flow`; ở nhánh thành công tính `suggestions = [] if interrupt_pending else suggestions_for_flow(result.get("current_flow"))` và truyền vào `ChatResponse`; nhánh error (line ~229) và interrupt truyền `suggestions=[]`. Thêm test: 1 lượt trả về flow đã biết → `response.json()["suggestions"]` không rỗng và mọi khoá prefix theo flow; lượt interrupt/không-flow → `[]`.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -x</verify>
  <done>ChatResponse có suggestions; /agent/chat trả bộ khoá đúng theo flow, [] khi interrupt/None; test xanh.</done>
</task>
```

Sửa `ChatResponse` (schemas/agent.py:49):

```python
class ChatResponse(AppBaseModel):
    """The agent's reply for one turn."""

    conversation_id: str
    reply: str
    current_flow: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    interrupt_pending: bool = False
    interrupt_payload: dict | None = None
```

Trong `routers/agent.py`: thêm import `from app.agents.suggestions import suggestions_for_flow`. Return thành công (≈272):

```python
    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        current_flow=result.get("current_flow"),
        suggestions=(
            [] if interrupt_pending else suggestions_for_flow(result.get("current_flow"))
        ),
        interrupt_pending=interrupt_pending,
        interrupt_payload=interrupt_payload,
    )
```

Nhánh error (≈229) thêm `suggestions=[]`.

> Test có thể dùng FakeLLM/monkeypatch để ép `current_flow`. Xem cách `test_agent_chat.py` hiện dựng graph/response; nếu ép flow khó, có thể test trực tiếp việc `ChatResponse(..., suggestions=suggestions_for_flow("booking"))` serialize đúng + 1 integration khẳng định key `suggestions` tồn tại trong body (kiểu list). Ưu tiên tái dùng fixture sẵn có, không hit network.

---

### Task 2.2 — BE: thêm `suggestions` vào `done` SSE event

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/streaming/events.py, apps/api/app/streaming/mapper.py, apps/api/tests/api/agent/test_stream_events.py</files>
  <action>Đổi `events.done` nhận thêm kwarg bắt buộc `suggestions: list[str]` và đưa vào payload `{conversation_id, current_flow, suggestions}`; cập nhật docstring taxonomy (dòng ~21). Trong `mapper.py` (≈194) tính `suggestions = [] if interrupts else suggestions_for_flow(current_flow)` rồi truyền vào `events.done`; import helper. Thêm/điều chỉnh test khẳng định payload `done` chứa `suggestions` (list) — không rỗng khi có flow, `[]` khi interrupt/None.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/api/agent/test_streaming_sse.py -x</verify>
  <done>done event mang suggestions đúng ngữ cảnh; caller duy nhất (mapper) đã cập nhật; test streaming xanh.</done>
</task>
```

`events.py` — `done`:

```python
def done(
    *, conversation_id: str, current_flow: str | None, suggestions: list[str]
) -> TypedSSEEvent:
    return _event(
        "done",
        {
            "conversation_id": conversation_id,
            "current_flow": current_flow,
            "suggestions": suggestions,
        },
    )
```

`mapper.py` (≈194-195):

```python
        current_flow = state.values.get("current_flow") if state else None
        suggestions = [] if interrupts else suggestions_for_flow(current_flow)
        yield events.done(
            conversation_id=conversation_id,
            current_flow=current_flow,
            suggestions=suggestions,
        )
```

Thêm import `from app.agents.suggestions import suggestions_for_flow` ở đầu `mapper.py`. Cập nhật comment taxonomy `done` trong `events.py` docstring: `{conversation_id, current_flow, suggestions}`.

---

### Task 3.1 — FE: parse `suggestions` trong `done` event

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/lib/stream/parseSSE.ts, apps/web/src/lib/stream/parseSSE.test.ts</files>
  <action>Thêm `suggestions: string[]` vào interface `SSEDoneEvent`; trong `parseSegment` case "done" đọc `Array.isArray(data.suggestions) ? data.suggestions.map(String) : []`. Cập nhật comment wire-contract (dòng ~13) cho done. Thêm test: segment `event: done` với `suggestions:["booking.bookThis"]` → parse ra mảng đúng; done không có field → `[]`.</action>
  <verify>cd apps/web && pnpm test src/lib/stream/parseSSE.test.ts</verify>
  <done>SSEDoneEvent có suggestions; parser trả mảng khoá (rỗng khi thiếu/không hợp lệ); test xanh.</done>
</task>
```

Sửa `SSEDoneEvent` + case:

```ts
export interface SSEDoneEvent {
  type: "done";
  conversationId: string;
  currentFlow: string | null;
  suggestions: string[];
}
```

```ts
    case "done":
      return {
        type: "done",
        conversationId: String(data.conversation_id ?? ""),
        currentFlow: data.current_flow == null ? null : String(data.current_flow),
        suggestions: Array.isArray(data.suggestions)
          ? data.suggestions.map(String)
          : [],
      };
```

---

### Task 3.2 — FE: component `ChatSuggestions` (chip render + i18n map)

```xml
<task id="3.2" wave="3">
  <files>apps/web/src/components/chat/ChatSuggestions.tsx, apps/web/src/components/chat/ChatSuggestions.test.tsx</files>
  <action>Tạo component thuần nhận `{ suggestions: string[]; onPick: (text:string)=>void; disabled?: boolean }`. Map mỗi khoá → `{ label: t(\`followups.${key}.label\`), prompt: t(\`followups.${key}.prompt\`) }` qua `useTranslations("Chat")`, lọc bỏ khoá không có bản dịch (guard drift) rồi render hàng pill wrap; click gọi `onPick(prompt)`; trả null khi rỗng. Test bằng NextIntlClientProvider (theo mẫu MessageList.render.test.tsx): render 2 khoá → thấy label; click → onPick nhận đúng prompt; khoá lạ bị bỏ.</action>
  <verify>cd apps/web && pnpm test src/components/chat/ChatSuggestions.test.tsx</verify>
  <done>Chip render label bản địa hoá, click gửi prompt, khoá không xác định bị lọc; test xanh.</done>
</task>
```

Nội dung `ChatSuggestions.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";

export interface ChatSuggestionsProps {
  suggestions: string[];
  onPick: (text: string) => void;
  disabled?: boolean;
}

/**
 * Context-aware follow-up chips shown after an assistant turn. Keys come from the
 * backend heuristic (keyed off current_flow); labels/prompts are resolved here via
 * the Chat.followups i18n catalog. Unknown keys (BE/FE drift) are filtered out.
 */
export function ChatSuggestions({
  suggestions,
  onPick,
  disabled,
}: ChatSuggestionsProps) {
  const t = useTranslations("Chat");
  const items = suggestions
    .filter((key) => t.has(`followups.${key}.label`))
    .map((key) => ({
      key,
      label: t(`followups.${key}.label`),
      prompt: t(`followups.${key}.prompt`),
    }));

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-sm border-t border-line bg-panel-raised px-lg py-sm">
      {items.map((s) => (
        <button
          key={s.key}
          type="button"
          disabled={disabled}
          onClick={() => onPick(s.prompt)}
          className="rounded-pill border border-line bg-panel px-md py-1 text-xs font-medium text-ink transition duration-150 hover:-translate-y-0.5 hover:border-faint hover:bg-lime-soft active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
```

> **Kiểm chứng `t.has`:** next-intl expose `t.has(key)` — xác nhận version qua context7 (`resolve-library-id` "next-intl" → `query-docs` "does useTranslations t.has exist") hoặc grep usage sẵn có. Nếu version không có `.has`, thay guard bằng một `Set` khoá hợp lệ tĩnh (mirror của catalog) trong file này; test khoá-lạ ở trên sẽ bắt lỗi nếu guard sai.

---

### Task 4.1 — FE: `useAgentStream` tiêu thụ `done.suggestions`

```xml
<task id="4.1" wave="4">
  <files>apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/useAgentStream.stream.test.tsx</files>
  <action>Thêm state `suggestions: string[]` (khởi tạo []). Expose `suggestions` trong interface `UseAgentStream` + return. Clear `setSuggestions([])` ở đầu `send`, `retry`, `resume`, và trong `newConversation`. Trong CẢ ba vòng lặp SSE (send/retry/resume) thêm `case "done": setSuggestions(event.suggestions); break;` (thay cho việc rơi vào default). Thêm test: feed một stream kết thúc bằng done có suggestions → hook expose đúng mảng; lượt send mới clear về [].</action>
  <verify>cd apps/web && pnpm test src/components/chat/useAgentStream.stream.test.tsx</verify>
  <done>Hook lưu & expose suggestions từ done, clear khi bắt đầu lượt/hội thoại mới; test xanh.</done>
</task>
```

Điểm sửa chính trong `useAgentStream.ts`:

- Khai báo state cạnh `panels`: `const [suggestions, setSuggestions] = useState<string[]>([]);`
- Trong `UseAgentStream` (interface) thêm: `suggestions: string[];` (kèm doc ngắn).
- Đầu `send` (sau `setError(null)` / trước `setMessages`), đầu `retry`, đầu `resume`: `setSuggestions([]);`
- Trong `newConversation`: thêm `setSuggestions([]);`
- Ba vòng `for await ... switch(event.type)` (send, resume, retry): thêm nhánh

```ts
            case "done":
              setSuggestions(event.suggestions);
              break;
```

- Return object thêm `suggestions,`.

> `done` hiện rơi vào `default` (no-op) ở cả 3 vòng — thêm nhánh riêng, không xoá nhánh nào khác. `setSuggestions` ổn định (setState) nên không cần thêm vào deps.

---

### Task 5.1 — FE: render `ChatSuggestions` trong `ChatPanel` + kiểm thử FE tổng

```xml
<task id="5.1" wave="5">
  <files>apps/web/src/components/chat/ChatPanel.tsx</files>
  <action>Destructure `suggestions` từ `stream`. Render `<ChatSuggestions suggestions={suggestions} onPick={send} disabled={inputBlocked} />` chỉ khi `messages.length > 0 && !isStreaming && interrupt === null && suggestions.length > 0`, đặt NGAY TRÊN khối interrupt/composer (dưới MessageList/canRetry/panels). Import component.</action>
  <verify>cd apps/web && pnpm test src/components/chat && pnpm typecheck</verify>
  <done>Chip follow-up hiện dưới transcript sau lượt trả lời (ẩn khi đang stream/interrupt/rỗng); typecheck + test chat xanh.</done>
</task>
```

Trong `ChatPanel.tsx`: thêm `import { ChatSuggestions } from "./ChatSuggestions";`, thêm `suggestions` vào destructure của `stream`, và chèn trước block `{interrupt !== null ? (...) : (<ChatComposer .../>)}`:

```tsx
      {messages.length > 0 && !isStreaming && interrupt === null && suggestions.length > 0 ? (
        <ChatSuggestions suggestions={suggestions} onPick={send} disabled={inputBlocked} />
      ) : null}
```

> Nếu `pnpm typecheck` không tồn tại, dùng `pnpm exec tsc --noEmit` (xác nhận script trong `apps/web/package.json`). Chạy mọi lệnh FE với Node v24 (`export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`).

## 5. Risks

- **Drift khoá BE↔FE:** tập khoá `_FLOW_SUGGESTIONS` (1.1) phải khớp `Chat.followups` (1.2). Guard hai đầu: test 1.1 ép prefix theo flow; `ChatSuggestions` lọc khoá không có bản dịch nên khoá thừa của BE không làm vỡ UI (chỉ không hiển thị).
- **`t.has` theo version next-intl:** xem note ở Task 3.2 — fallback bằng Set tĩnh nếu thiếu.
- **OpenAPI types (`schema.d.ts`) của FE:** FE dùng SSE nên KHÔNG tiêu thụ `ChatResponse.suggestions`; không cần regen ngay. Nếu về sau FE gọi `/agent/chat`, chạy script generate types. Ngoài scope lần này.
- **Commit-time public-contract gate:** field mới trên `ChatResponse` có thể khiến `risk-corroboration.sh` cảnh báo `public-contract`. Là mở rộng field (không phải endpoint mới) nên thường chỉ warn; nếu bị chặn → `RISK_WARN_CATEGORIES="public-contract"` (memory `public-contract-hard-gate`).
- **env `OPENAI_API_KEY=test`** làm đỏ test LLM cục bộ (memory) — các test của MIN-55 thuần, không hit LLM, nhưng nếu chạy full suite thì để `.env` sang một bên.

## 6. Status Log

- 2026-07-06 — Plan drafted (proposed). Lane normal, confidence high (SUMMARY.md). Waves 1→5, 8 tasks.
- 2026-07-07 — Wave 1 done. 1.1 `8eba8fc` (heuristic + tests, 9 pass); 1.2 `88cd795` (welcome labels + followups i18n, verify ok). Independent review ✅ spec+quality; cross-contract BE↔en↔vi = 15 keys, zero drift.
- 2026-07-07 — Final gates ✅. /correctness-review 0 findings; /intent-review 1 advisory → resolved by e2e hotel/flight tests `b62ae5f` (both route to planner). Full targeted suite: 50 BE + 62 FE pass.
- 2026-07-07 — shipped via `feat/min-55-shortcut-suggestions` (PR pending).
- 2026-07-07 — Wave 5 done. 5.1 `0704fb8` (ChatPanel renders ChatSuggestions, guarded on completed-turn/non-empty; 33 chat tests pass, tsc --noEmit exit 0). All 8 tasks implemented; per-task spec+quality reviews ✅. Next: final /correctness-review + /intent-review over whole diff.
- 2026-07-07 — Wave 4 done. 4.1 `c45435b` (useAgentStream consumes done.suggestions across all 3 SSE loops + clears on send/retry/resume/newConversation, 5 pass). Review ✅ all 5 spec points; no no-op loop; tests genuine.
- 2026-07-07 — Wave 3 done. 3.1 `1817e1d` (parseSSE done.suggestions, 21 pass); 3.2 `4c63b88` (ChatSuggestions component, 3 pass). Implement-only + serial controller commits (no race). Review ✅ both; click sends prompt not label; no t.has; tokens real; 24 tests.
- 2026-07-07 — Wave 2 done. 2.1 `006b5ec` (ChatResponse.suggestions + /agent/chat, 15 pass); 2.2 `55a52d6` (done SSE event suggestions, 24 pass). Concurrent-git race entangled commits mid-wave; controller untangled (2.1 re-committed clean). Review ✅ both tasks, tree clean, all events.done callers updated, 35 tests. Harness-Delta (backlog): parallel subagents committing to shared index race — from Wave 3, implement-only + controller serializes commits.

## 7. Wave Map

| Wave | Tasks | Song song | Ghi chú phụ thuộc |
|------|-------|-----------|-------------------|
| 1 | 1.1 BE heuristic, 1.2 i18n | 2 | file rời nhau (app/agents vs messages) |
| 2 | 2.1 ChatResponse+/chat, 2.2 done SSE | 2 | đều import helper của 1.1; file rời nhau |
| 3 | 3.1 parseSSE done, 3.2 ChatSuggestions | 2 | 3.1←shape của 2.2; 3.2←catalog của 1.2 |
| 4 | 4.1 useAgentStream | 1 | ←type của 3.1 |
| 5 | 5.1 ChatPanel + FE e2e | 1 | ←3.2 + 4.1 |
