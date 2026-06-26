---
slug: travel-agent
status: proposed
owner: Minh Tran
created: 2026-06-25
---

# Travel Assistant Agent — agentic multi-agent layer (LangGraph)

> Xây lớp **AI travel-assistant** trên travel-pi: không chỉ lập kế hoạch (plan) mà còn
> **trả lời, ghi chú, và cập nhật xuyên suốt chuyến đi** (long-running, stateful, đa phiên).
> Kiến trúc **agentic multi-agent**: một supervisor điều phối nhiều sub-agent biết
> *suy nghĩ → gọi tool → tự phản tỉnh/sửa sai → bàn giao cho nhau*.

## Quyết định nền (đã chốt với owner 2026-06-25)

| Hạng mục | Quyết định | Ghi chú |
|---|---|---|
| LLM provider | **Provider-agnostic, OpenAI default** | `init_chat_model()`; default `gpt-4.1` + `text-embedding-3-small`; đổi Anthropic/Gemini bằng env. **Ghi đè giả định Anthropic của `specs/llm-readiness`.** |
| Topology | **Supervisor + sub-agents agentic** | Sub-agent giao tiếp qua shared state + `Command(goto=...)`; có reflection/self-correct; HITL interrupt cho xác nhận. |
| Vector store | **pgvector** (`langchain-postgres` PGVector) | Tái dùng Postgres sẵn có; hybrid search (vector + tsvector + RRF). |
| Checkpointer | **SqliteSaver local / PostgresSaver docker** | Bám `DATABASE_URL` như engine hiện tại; fallback `MemorySaver` nếu thiếu. |
| Memory dài hạn | **PostgresStore** (pgvector semantic) | Không cần Mem0/LangMem. Namespace `("users", uid, "prefs"/"trips")`. |
| Observability | **Langfuse** `CallbackHandler` | Thay vì LangSmith như 2 repo tham khảo. |
| MCP | **`app/mcp/` để cuối** (= roadmap B11) | Nội bộ dùng `@tool` trực tiếp; chỉ expose `/mcp` khi cần client ngoài. |

## 1. Motivation

travel-pi đã có **15 domain service** (trip, place, weather, flight, hotel, booking,
expense, currency, visa, routing, destination, air_quality, climate, saved_place, tip)
nhận `Session` qua DI `get_session()` — sẵn sàng wrap thành **tool gọi trực tiếp, không HTTP
round-trip**. Phase A của `agent-platform-roadmap` đã chuẩn hoá data (POI library, itinerary
status). Đây là thời điểm hợp lý để thêm lớp agent: domain đủ giàu để tool sạch.

Tham chiếu chéo:
- `specs/llm-readiness/PLAN.md` — seam (http client, streaming, Job model, FakeLLM DI). Plan này
  **thực thi + điều chỉnh** các seam đó cho provider-agnostic.
- `specs/agent-platform-roadmap/CHECKLIST.md` Phase B — context loaders (`/trips/{id}/summary`,
  `/agent/plan`) và MCP. Agent **tiêu thụ** các tool/endpoint này; B2/B3 nên ưu tiên vì agent dùng nhiều.

## 2. Non-goals

- Không xây UI/frontend (chỉ API: `/agent/chat`, `/agent/stream`).
- Không thay đổi contract của các endpoint domain hiện có (agent chỉ *bọc* chúng).
- Không tự huấn luyện/fine-tune model; chỉ orchestration + RAG + eval.
- Không làm auth/multi-tenant thật (repo "no auth"); `user_id` truyền qua request/header, chưa enforce.
- MCP server (Phase 9) là *stretch* — làm sau khi agent lõi chạy ổn.

## 3. Success Criteria

- `POST /agent/chat` và `GET /agent/stream` (SSE) chạy với **FakeLLM** trong test (zero network, suite xanh).
- Supervisor route đúng tới ≥3 sub-agent (planner / concierge / journal) — đo bằng eval routing ≥0.9.
- State **bền vững qua nhiều turn và nhiều phiên**: checkpointer SQLite local; thread_id = `user_{uid}_trip_{tid}`.
- Sub-agent **tự sửa sai**: ToolNode bắt `ToolException` → model retry; reflection node loop khi output không đạt.
- RAG trả POI/tip liên quan qua hybrid search (test trên fake embeddings / fixtures).
- Mọi run được trace qua Langfuse (tắt được bằng env trong test/CI).
- Eval harness offline (RAGAS faithfulness + LLM-as-judge routing) chạy `python eval/run_eval.py`,
  có ngưỡng assert; tích hợp được vào CI.
- `make test` xanh xuyên suốt; **không** phá 685 test hiện có.

## 4. Kiến trúc agent (tóm tắt)

```
                         ┌─────────────────────────────────────────────┐
  POST /agent/chat ─────▶│  load_context (trip summary + user prefs)    │
  GET  /agent/stream     └───────────────────┬─────────────────────────┘
                                             ▼
                                   ┌──────────────────┐   summarize khi >20 msg
                                   │    SUPERVISOR     │◀────────── summarize_node
                                   │ (route by intent) │
                                   └─────┬───┬───┬─────┘
              Command(goto=...)          │   │   │           (sub-agent ↔ sub-agent
                 ┌───────────────────────┘   │   └──────────────┐  qua shared state)
                 ▼                            ▼                  ▼
          ┌────────────┐             ┌────────────┐      ┌────────────┐   ┌──────────┐
          │  PLANNER   │             │ CONCIERGE  │      │  JOURNAL   │   │ BOOKING  │
          │ itinerary  │             │ Q&A + RAG  │      │ notes/upd. │   │ HITL ✋  │
          └─────┬──────┘             └─────┬──────┘      └─────┬──────┘   └────┬─────┘
                │  ToolNode (bắt ToolException → self-correct)  │              │
                ▼                            ▼                  ▼              ▼
         trip/place/flight/hotel/routing/weather  ·  RAG retriever  ·  notes/status  ·  quote→book
                 └──────────────── reflection / critic node (tự đánh giá → loop) ───────────────┘
```

- **State**: `TravelAgentState(MessagesState)` + `trip_id, user_id, status, current_flow, summary, tokens_used`
  và các field merge có `Annotated` reducer (theo mẫu mizumi `add_messages` / dedup).
- **Sub-agent** = subgraph `assistant → tools → (conditional)`; bind tool theo domain để tránh sprawl.
- **Inter-agent**: supervisor `Command(update=..., goto=member)`; sub-agent có thể `goto` supervisor/sub-agent khác.
- **Self-correct**: (1) `ToolNode` 1.x trả `ToolMessage(status="error")` cho model tự sửa; (2) `reflection_node`
  chấm draft trước khi END, loop lại assistant nếu chưa đạt (giới hạn vòng lặp).
- **HITL**: `interrupt(payload)` trong `plan_node`/booking để user duyệt itinerary/đặt chỗ; resume `Command(resume=...)`.

## 5. Cấu trúc thư mục mục tiêu

```
app/
  clients/llm.py            # init_chat_model() factory + get_llm/get_fast_llm + FakeLLM
  prompts/registry.py       # prompt versioned + active.yaml (copy pattern chat-agents)
  prompts/*.md
  agents/
    state.py                # TravelAgentState
    graph.py                # build_graph() — compile + checkpointer + store
    supervisor.py           # routing node (structured output intent)
    nodes.py                # load_context, summarize, reflection/critic, plan_node(HITL)
    subagents/planner.py concierge.py journal.py booking.py budget.py
  tools/
    registry.py             # ALL_TOOLS + get_tools_for(domain)
    trip_tools.py place_tools.py flight_tools.py hotel_tools.py
    weather_tools.py memory_tools.py
  rag/
    embeddings.py           # OpenAIEmbeddings factory + PGVector init (+ fake cho test)
    retriever.py            # hybrid_search (vector + tsvector + RRF)
    ingest.py               # chunk + embed POI/tip/guide/notes
  memory/store.py summarizer.py
  db/models/conversation.py message.py job.py
  routers/agent.py          # /agent/chat, /agent/stream (SSE), /agent/manifest
  mcp/                      # (Phase 9) MCP server expose tools ra ngoài
eval/
  datasets/*.json
  run_eval.py metrics.py    # RAGAS + LLM-as-judge + ngưỡng CI
tests/agents/ tests/tools/ tests/rag/ tests/api/agent/
```

## 6. Lane & Escalation

- **Lane: high-risk.** Lý do (nhiều hard gate cùng lúc):
  - **External deps mới** (langgraph, langchain, openai, langfuse, pgvector…) — Rule 4 "new external service dependency".
  - **Schema change**: bảng `conversations`, `messages`, `job`, checkpointer tables, pgvector extension.
  - **Public contract**: thêm endpoint `/agent/*` — chạm gate `public-contract` (xem memory `public-contract-hard-gate`).
- **Confidence: medium** — kiến trúc rõ nhưng version-pin của hệ langchain 1.x cần resolve thực tế lúc cài.
- **Escalate trước khi execute** mỗi mục có hard gate: ghi `specs/travel-agent/ESCALATIONS.md`, set
  `RISK_WARN_CATEGORIES="public-contract"` khi commit endpoint mới.
- **Rollback**: mỗi migration kèm `alembic downgrade -1`; deps revert qua `git revert <sha>`; agent layer
  tách module nên có thể gỡ router khỏi `main.py` mà không ảnh hưởng domain.

## 7. Tasks

### Phase 0 — Deps & config foundation

#### Task 0.1 — Thêm AI dependencies (resolve version cùng nhau)

```xml
<task id="0.1" wave="1">
  <files>requirements.txt, requirements-ai.txt</files>
  <action>Thêm cụm AI deps. Vì hệ langchain 1.x/langgraph 1.x dễ xung đột, tách vào requirements-ai.txt và -r vào requirements.txt. Pin: langgraph>=1.0,<2.0; langchain>=1.0,<2.0; langchain-openai>=0.3,<1.0; langchain-anthropic>=1.0,<2.0; langgraph-checkpoint-sqlite>=2.0,<3.0; langgraph-checkpoint-postgres>=2.0,<4.0; langchain-postgres>=0.0.12; pgvector>=0.3,<1.0; langfuse>=3.0,<5.0; ragas>=0.2 (dev). KHÔNG đụng pin fastapi/starlette hiện có (giữ cap <0.137). Ghi rationale vào SUMMARY (Rule 3).</action>
  <verify>uv pip install -r requirements.txt && .venv/bin/python -c "import langgraph, langchain, langchain_openai, langfuse; from langgraph.checkpoint.sqlite import SqliteSaver; print('ok')"</verify>
  <done>Cài sạch, import smoke-test pass, suite cũ vẫn xanh (chạy make test riêng).</done>
</task>
```

#### Task 0.2 — Mở rộng Settings cho LLM/agent

```xml
<task id="0.2" wave="1">
  <files>app/core/config.py, .env.example, tests/core/test_config_llm.py</files>
  <action>Thêm field: llm_provider (Literal["openai","anthropic","google"]="openai"), llm_model (default "gpt-4.1"), fast_llm_model (default "gpt-4.1-mini"), embedding_model (default "text-embedding-3-small"), openai_api_key/anthropic_api_key (str|None), langfuse_public_key/secret_key/host (str|None), langfuse_enabled (bool=False), agent_recursion_limit (int=25), summarize_threshold (int=20). Default an toàn (None/disabled) để zero-config + test không cần key. Update .env.example.</action>
  <verify>.venv/bin/python -m pytest tests/core/test_config_llm.py -x</verify>
  <done>Settings load với giá trị mặc định; provider Literal chặn giá trị sai; không field nào bắt buộc key.</done>
</task>
```

### Phase 1 — Seams: LLM client, prompts, persistence models

#### Task 1.1 — Provider-agnostic LLM client + FakeLLM

```xml
<task id="1.1" wave="1">
  <files>app/clients/llm.py, app/core/deps.py, tests/clients/test_llm.py</files>
  <action>app/clients/llm.py: get_llm()/get_fast_llm() dùng init_chat_model(model, model_provider=settings.llm_provider). Export FakeLLM (deterministic, scriptable responses + tool-call stubs) cho test. app/core/deps.py: get_llm_client() Depends overridable (mẫu llm-readiness 3.2, tránh module-singleton footgun). KHÔNG gọi network ở import-time.</action>
  <verify>.venv/bin/python -m pytest tests/clients/test_llm.py -x</verify>
  <done>get_llm trả model đúng provider; FakeLLM override được qua dependency_overrides; không network khi import.</done>
</task>
```

#### Task 1.2 — Prompt registry (versioned + active.yaml)

```xml
<task id="1.2" wave="1">
  <files>app/prompts/registry.py, app/prompts/active.yaml, app/prompts/supervisor.v1.md, app/prompts/concierge.v1.md, tests/prompts/test_registry.py</files>
  <action>Copy pattern chat-agents: PromptRegistry quét app/prompts/*.md, load {name:{version:text}}, resolve active.yaml; registry.get(name) trả version active. Seed 2 prompt mẫu (supervisor, concierge). Singleton module-level, reload() được.</action>
  <verify>.venv/bin/python -m pytest tests/prompts/test_registry.py -x</verify>
  <done>get() trả đúng active version; version không tồn tại raise rõ ràng; reload() cập nhật.</done>
</task>
```

#### Task 1.3 — DB models: conversation, message, job (+migration)

```xml
<task id="1.3" wave="2">
  <files>app/db/models/conversation.py, app/db/models/message.py, app/db/models/job.py, app/db/models/__init__.py, app/repositories/conversation.py, alembic/versions/, tests/db/test_agent_models.py</files>
  <action>3 model kế thừa UUIDBase (UUID PK + timestamps): Conversation(user_id, trip_id?, title, domain), Message(conversation_id FK, role, content, tool_calls JSON?), Job(status enum, kind, result JSON, error text) — Job theo llm-readiness 3.1. ConversationRepository CRUD (list/create/append_message). Một migration mới (dùng ensure_column nếu cần legacy). Đăng ký vào models.__init__.</action>
  <verify>rm -f travel.db && .venv/bin/alembic upgrade head && .venv/bin/alembic check && .venv/bin/python -m pytest tests/db/test_agent_models.py -x</verify>
  <done>3 bảng migrate sạch (no drift); repo create/list/append pass; legacy-DB ALTER test (nếu có) xanh.</done>
</task>
```

### Phase 2 — Memory & checkpointer infra

#### Task 2.1 — Checkpointer (SQLite local / Postgres docker) wired in lifespan

```xml
<task id="2.1" wave="1">
  <files>app/agents/checkpointer.py, app/core/lifespan.py, tests/agents/test_checkpointer.py</files>
  <action>get_checkpointer(): chọn theo DATABASE_URL — SqliteSaver (local/test) vs AsyncPostgresSaver (postgresql://); fallback MemorySaver nếu khởi tạo lỗi (mẫu mizumi). Setup() một lần trong lifespan startup, đóng khi shutdown. Postgres path cần kwargs autocommit=True, prepare_threshold=0.</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_checkpointer.py -x</verify>
  <done>SQLite path tạo + persist + reload state theo thread_id; fallback MemorySaver khi URL lỗi; đóng sạch.</done>
</task>
```

#### Task 2.2 — Long-term memory store + summarizer

```xml
<task id="2.2" wave="2">
  <files>app/memory/store.py, app/memory/summarizer.py, tests/agents/test_memory.py</files>
  <action>store.py: wrapper PostgresStore (prod) / InMemoryStore (test) — upsert_preference/search_preferences theo namespace ("users",uid,"prefs"). summarizer.py: summarize_conversation() nén messages khi >settings.summarize_threshold (gọi get_fast_llm), trả summary + danh sách RemoveMessage. Test dùng FakeLLM + InMemoryStore.</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_memory.py -x</verify>
  <done>upsert→search trả pref đúng; summarizer nén khi vượt ngưỡng và giữ summary; zero network.</done>
</task>
```

### Phase 3 — Tools (wrap domain services)

> Mỗi task bọc 1 nhóm domain thành `@tool` với Pydantic args_schema; gọi service trực tiếp qua session
> factory; raise `ToolException` cho lỗi service (để model self-correct). File rời nhau → song song wave 1.

#### Task 3.1 — Trip & itinerary tools

```xml
<task id="3.1" wave="1">
  <files>app/tools/trip_tools.py, tests/tools/test_trip_tools.py</files>
  <action>Tools: get_trip_summary, get_day_plan, add_place_to_trip, update_itinerary_status, save_day_note. Bọc TripService; args_schema Pydantic; docstring súc tích (LLM thấy schema này). Lỗi service → ToolException.</action>
  <verify>.venv/bin/python -m pytest tests/tools/test_trip_tools.py -x</verify>
  <done>Mỗi tool gọi service đúng + trả dict serializable; ToolException khi service raise.</done>
</task>
```

#### Task 3.2 — Place & POI tools

```xml
<task id="3.2" wave="1">
  <files>app/tools/place_tools.py, tests/tools/test_place_tools.py</files>
  <action>Tools: search_places, nearby_places, resolve_place, parse_nl_query. Bọc PlaceService + parse_nl_query sẵn có.</action>
  <verify>.venv/bin/python -m pytest tests/tools/test_place_tools.py -x</verify>
  <done>Tool trả list place serializable; city không rõ → count 0 (không raise) đúng convention repo.</done>
</task>
```

#### Task 3.3 — Flight/hotel/booking tools

```xml
<task id="3.3" wave="1">
  <files>app/tools/flight_tools.py, app/tools/hotel_tools.py, tests/tools/test_booking_tools.py</files>
  <action>Tools: search_flights, search_hotels, get_hotel_availability, và (nếu roadmap B5 có) quote_* /book_*. Booking tool đánh dấu destructive trong metadata để supervisor/HITL gate.</action>
  <verify>.venv/bin/python -m pytest tests/tools/test_booking_tools.py -x</verify>
  <done>Search tools deterministic (theo seed MD5 hiện có); book tool yêu cầu cờ confirm.</done>
</task>
```

#### Task 3.4 — Weather/info + memory tools + registry

```xml
<task id="3.4" wave="2">
  <files>app/tools/weather_tools.py, app/tools/memory_tools.py, app/tools/registry.py, tests/tools/test_registry.py</files>
  <action>weather_tools: get_weather, get_packing, get_air_quality (async). memory_tools: save_user_preference, get_user_preferences (gọi memory/store). registry.py: ALL_TOOLS + get_tools_for(domain) trả nhóm tool theo sub-agent (chống sprawl). Mỗi tool kèm metadata readOnly/destructive (chuẩn roadmap B1).</action>
  <verify>.venv/bin/python -m pytest tests/tools/test_registry.py -x</verify>
  <done>get_tools_for("planner"/"concierge"/...) trả đúng nhóm; metadata annotation đầy đủ.</done>
</task>
```

### Phase 4 — RAG (pgvector)

#### Task 4.1 — Embeddings + vector store init (+ fake)

```xml
<task id="4.1" wave="1">
  <files>app/rag/embeddings.py, alembic/versions/, tests/rag/test_embeddings.py</files>
  <action>embeddings.py: get_embeddings() = OpenAIEmbeddings(model=settings.embedding_model) (prod) / FakeEmbeddings deterministic (test). get_vector_store() = PGVector(connection=DATABASE_URL, collection_name="travel_pois") khi Postgres; test dùng in-memory/fake. Migration tạo extension pgvector + collection tables CHỈ khi Postgres (skip SQLite). Document rõ: RAG yêu cầu Postgres (docker).</action>
  <verify>.venv/bin/python -m pytest tests/rag/test_embeddings.py -x</verify>
  <done>FakeEmbeddings trả vector ổn định; get_vector_store chọn đúng theo DATABASE_URL; test không cần Postgres/network.</done>
</task>
```

#### Task 4.2 — Ingest pipeline + hybrid retriever

```xml
<task id="4.2" wave="2">
  <files>app/rag/ingest.py, app/rag/retriever.py, scripts/ingest_rag.py, tests/rag/test_retriever.py</files>
  <action>ingest.py: chunk (RecursiveCharacterTextSplitter 400/50) + embed POI/tip/destination guide từ app/data; serialize record→template string (không embed JSON thô); metadata city/category. retriever.py: hybrid_search(query, filters) = pgvector cosine ∪ tsvector full-text, hợp nhất bằng RRF; luôn metadata pre-filter. scripts/ingest_rag.py CLI. Test trên FakeEmbeddings + fixtures in-memory.</action>
  <verify>.venv/bin/python -m pytest tests/rag/test_retriever.py -x</verify>
  <done>Ingest chunk đúng; hybrid_search trả kết quả lọc theo metadata; RRF hợp nhất 2 nguồn (test với fake).</done>
</task>
```

### Phase 5 — Agent graph (lõi)

#### Task 5.1 — State + sub-agent factory

```xml
<task id="5.1" wave="1">
  <files>app/agents/state.py, app/agents/subagents/_base.py, tests/agents/test_state.py</files>
  <action>state.py: TravelAgentState(MessagesState) + trip_id,user_id,status,current_flow,summary,tokens_used + reducer Annotated cho field gộp. _base.py: build_subagent(name, tools, prompt_key) → subgraph assistant→tools với llm.bind_tools, ToolNode bắt ToolException, tools_condition route. Giữ nhỏ + serializable (đây là contract Postgres-serialize).</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_state.py -x</verify>
  <done>State khởi tạo/merge đúng; build_subagent compile được subgraph chạy với FakeLLM (1 vòng tool).</done>
</task>
```

#### Task 5.2 — Specialist sub-agents

```xml
<task id="5.2" wave="2">
  <files>app/agents/subagents/planner.py, app/agents/subagents/concierge.py, app/agents/subagents/journal.py, app/agents/subagents/booking.py, app/agents/subagents/budget.py, tests/agents/test_subagents.py</files>
  <action>Mỗi sub-agent = build_subagent với nhóm tool tương ứng (planner: trip/place/flight/hotel/routing; concierge: place/weather/visa/currency + RAG retriever tool; journal: save_day_note/update_itinerary_status/memory; booking: quote/book + HITL; budget: expense/balance). Concierge nhận RAG retriever làm tool. Booking dùng interrupt() để xác nhận trước khi book.</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_subagents.py -x</verify>
  <done>Mỗi sub-agent chạy độc lập với FakeLLM: gọi đúng nhóm tool; booking interrupt trước book.</done>
</task>
```

#### Task 5.3 — Supervisor + cross-cutting nodes

```xml
<task id="5.3" wave="3">
  <files>app/agents/supervisor.py, app/agents/nodes.py, tests/agents/test_supervisor.py</files>
  <action>supervisor.py: llm.with_structured_output(SupervisorIntent{target_agent,language}) → Command(update={current_flow}, goto=member); fallback message khi intent unknown. nodes.py: load_context_node (nạp trip summary + user prefs vào system prompt), summarize_node (dùng summarizer), reflection_node (chấm draft, loop lại assistant nếu chưa đạt, có giới hạn vòng), plan_node (HITL interrupt cho itinerary).</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_supervisor.py -x</verify>
  <done>Supervisor route đúng target theo FakeLLM intent; reflection loop dừng theo giới hạn; load_context inject prefs.</done>
</task>
```

#### Task 5.4 — Compile graph (build_graph)

```xml
<task id="5.4" wave="4">
  <files>app/agents/graph.py, tests/agents/test_graph.py</files>
  <action>build_graph(): StateGraph(TravelAgentState); add load_context, supervisor, summarize, reflection + 5 sub-agent subgraph; conditional edges START→load_context→(summarize?)→supervisor→member→(reflection)→END; compile(checkpointer=get_checkpointer(), store=get_store()). Cache compiled graph (lru_cache) nhưng checkpointer/store lấy từ lifespan.</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_graph.py -x</verify>
  <done>Graph compile; e2e với FakeLLM: 1 message → route → tool → reflection → trả lời; state persist qua 2 turn cùng thread_id.</done>
</task>
```

### Phase 6 — API surface

#### Task 6.1 — Agent router (/agent/chat, /agent/stream, /agent/manifest)

```xml
<task id="6.1" wave="1">
  <files>app/routers/agent.py, app/schemas/agent.py, app/main.py, tests/api/agent/test_agent_chat.py</files>
  <action>POST /agent/chat {message,user_id,trip_id?}→graph.ainvoke(config thread_id+callbacks). GET /agent/stream→StreamingResponse SSE (dùng app/core/streaming.py từ llm-readiness 1.2; stream_mode="messages"). GET /agent/manifest→mô tả tool + readOnly/destructive (roadmap B4). Lưu conversation/message qua repository sau mỗi turn. Đăng ký router trong main.py. CHẠM gate public-contract → escalate + RISK_WARN_CATEGORIES khi commit.</action>
  <verify>.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -x</verify>
  <done>chat trả body với FakeLLM (override get_llm_client); stream phát ≥2 SSE event + terminal; manifest liệt kê tool + annotation.</done>
</task>
```

### Phase 7 — Observability (Langfuse)

#### Task 7.1 — Langfuse callback wiring

```xml
<task id="7.1" wave="1">
  <files>app/agents/observability.py, app/routers/agent.py, tests/agents/test_observability.py</files>
  <action>build_langfuse_handler(user_id, session_id=trip_id, tags) → CallbackHandler (langfuse>=3: from langfuse.langchain import CallbackHandler). Trả None khi langfuse_enabled=False (test/CI default). Gắn vào config["callbacks"] trong agent router. KHÔNG fail khi thiếu key.</action>
  <verify>.venv/bin/python -m pytest tests/agents/test_observability.py -x</verify>
  <done>handler None khi disabled; khi enabled build đúng với session_id=trip_id; agent vẫn chạy khi handler None.</done>
</task>
```

### Phase 8 — Evaluation

#### Task 8.1 — Eval harness (RAGAS + LLM-as-judge + CI gate)

```xml
<task id="8.1" wave="1">
  <files>eval/datasets/routing.json, eval/datasets/rag.json, eval/metrics.py, eval/run_eval.py, tests/eval/test_eval_smoke.py</files>
  <action>datasets: cặp (input, expected) cho routing intent + RAG faithfulness. metrics.py: wrapper RAGAS (faithfulness, answer_relevancy, context_recall) + LLM-as-judge routing accuracy (mẫu mizumi DeepEval/OpenEvals). run_eval.py: chạy dataset qua graph (FakeLLM hoặc model thật theo env), in summary, assert ngưỡng (routing≥0.9, faithfulness≥0.85), exit code cho CI. test_eval_smoke chạy với FakeLLM để CI nhanh.</action>
  <verify>.venv/bin/python -m pytest tests/eval/test_eval_smoke.py -x</verify>
  <done>run_eval chạy với FakeLLM, in pass-rate, exit 0 khi đạt ngưỡng / exit 1 khi không; smoke test xanh.</done>
</task>
```

### Phase 9 — MCP server (stretch, = roadmap B11)

#### Task 9.1 — MCP server expose tools

```xml
<task id="9.1" wave="1">
  <files>app/mcp/server.py, app/mcp/__init__.py, tests/mcp/test_mcp_server.py</files>
  <action>Dùng tool registry (Phase 3) làm nguồn: expose read-only GET làm MCP Resources, read-write làm Tools (verb_noun, mô tả mệnh lệnh, delete ghi "Cannot be undone"), gắn annotation từ registry. Mount /mcp (transport http). Chỉ làm sau khi agent lõi ổn. Tham chiếu roadmap B11.</action>
  <verify>.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -x</verify>
  <done>MCP server liệt kê đúng tools/resources với annotation; smoke call 1 read-only tool trả kết quả.</done>
</task>
```

## 8. Bảng waves (thứ tự thực thi)

| Phase | Mục tiêu | Tasks | Song song |
|---|---|---|---|
| 0 | Deps + config | 0.1, 0.2 | 2 (file rời) |
| 1 | LLM client, prompts, models | 1.1, 1.2 ‖ 1.3 | wave1: 1.1+1.2; wave2: 1.3 |
| 2 | Checkpointer + memory | 2.1 ‖ 2.2 | tuần tự nhẹ |
| 3 | Tools | 3.1, 3.2, 3.3 ‖ 3.4 | wave1: 3.1-3.3; wave2: 3.4 (registry cần tools) |
| 4 | RAG | 4.1 → 4.2 | tuần tự |
| 5 | Agent graph | 5.1 → 5.2 → 5.3 → 5.4 | tuần tự (phụ thuộc dọc) |
| 6 | API | 6.1 | single |
| 7 | Langfuse | 7.1 | single |
| 8 | Eval | 8.1 | single |
| 9 | MCP (stretch) | 9.1 | single |

**Đề xuất chia PR:** Phase 0+1 (1 PR nền), Phase 2+3 (1 PR), Phase 4 (1 PR RAG), Phase 5 (1 PR core agent),
Phase 6+7 (1 PR API+trace), Phase 8 (1 PR eval), Phase 9 (PR riêng, sau).

## 9. Risks

- **Version hell của langchain 1.x/langgraph 1.x** — resolve cùng nhau ở 0.1; nếu xung đột với pin
  fastapi/pydantic hiện có → escalate, không tự nới pin fastapi.
- **Postgres-only cho RAG + AsyncPostgresSaver** — local SQLite không chạy pgvector. Test phải dùng
  fake embeddings + SqliteSaver; tài liệu hoá rõ RAG cần docker. (Liên quan memory `docker-py312-vs-local-py314`.)
- **Schema change** (conversations/messages/job + checkpointer + pgvector) — rebuild `travel.db` sau migration
  (memory `stale-travel-db-breaks-suite-on-schema-change`); kèm downgrade.
- **Public-contract gate** — `/agent/*` là endpoint mới → memory `public-contract-hard-gate`:
  set `RISK_WARN_CATEGORIES="public-contract"` khi commit Phase 6/9.
- **Test phải zero-network** — mọi LLM/embedding call trong test dùng Fake; CI không có API key.
- **Token cost runtime** — sub-agent dùng fast model (gpt-4.1-mini) cho việc rẻ; supervisor/reflection nhẹ.
- **ruff-on-edit strip import** (memory) — thêm import + usage cùng lúc; chạy `ruff --select F821` trước test.

## 10. Status Log

- 2026-06-25 — Plan khởi tạo từ deep-review travel-pi + 2 codebase tham khảo (chat-agents, mizumi) +
  research best-practice (LangGraph 1.x, pgvector RAG, Langfuse, RAGAS). Quyết định nền chốt với owner.
  Tất cả task: ⬜ proposed.
- 2026-06-25 — **Phases 0–9 ✅ shipped** on branch `feat/travel-agent-foundation` (off v3), one commit
  per phase. Full SQLite suite 843 passed; alembic no drift; ruff clean. Cross-engine (Postgres/py3.12)
  via `make test-docker`. See SUMMARY.md `### Verify`. Notable: langgraph-checkpoint-sqlite/postgres
  bumped to 3.x (2.x runtime break); langchain-text-splitters + mcp added; pgvector migration probes
  availability (no-op on stock Postgres). RAG/Postgres-store are Postgres-only; tests use in-memory fakes.
