---
slug: trip-research-deep-agent
doc: design (bản tiếng Việt của design.md v2 — bản tiếng Anh là bản gốc khi có sai khác)
created: 2026-09-18
status: proposed
depends_on: research-brief.md, ESCALATIONS.md (E001 StoreBackend · E002 BackgroundTask + poll + SSE · E003 chat + trang trip · E004 chỉ đề xuất · E005 chỉ premium · E006 tab Research), PR #219
---

# Thiết kế — trip-research-deep-agent (v2)

Đường dẫn file tính từ `apps/api/` trừ khi ghi khác.

## 0. Nguyên tắc (chủ dự án, 2026-09-18)

Dùng deep-agent harness cho mọi thứ nó đã làm được; chỉ viết code cho phần *của mình*: tool
nghiệp vụ (đã có), identity/tier/ownership, sổ sách run, và đường nối sang web. Design v1 có sáu
chỗ tự viết lại tính năng harness; v2 bỏ hết:

| v1 (tự viết lại) | v2 (tính năng harness) |
|---|---|
| methodology từng chiều nằm trong 6 prompt của registry | **Skills** (`SKILL.md` mỗi chiều, progressive disclosure) |
| dán preferences vào `system_prompt`; từ chối `memory=` | **Memory** `AGENTS.md` theo user, agent tự sửa |
| `files.py` allowlist đường dẫn ghi | **Permissions** (`deny` ghi ngoài `/research/**`, `/plan/**`, `/memory/**`) |
| `proposal.py` tự inject `HumanMessage` để retry | **Grader của RubricMiddleware có tool** (`validate_proposal` + rubric) |
| "revise" = run mới đọc lại dossier | **Thread resume**: một thread checkpoint cho mỗi dossier; revise là lượt tiếp |
| sweep đánh dấu `failed` khi restart | **Resume từ checkpoint** (`ainvoke(None, config)`), sweep chỉ là đường cùng |
| tự cắt output tool lớn | **offload large-tool-result** + `SummarizationMiddleware` có sẵn |

## 1. Vị trí trong kiến trúc

Một graph thứ hai, độc lập, dựng bằng `deepagents.create_deep_agent`, nằm trong package mới
`app/research/`. Nó dùng chung checkpointer và store tồn tại suốt process với chat graph, bind
nguyên các read-only tool của registry, ghi run vào `agent_runs`, và được khởi động từ bề mặt
agent (JWT) hoặc từ một node launcher không gọi LLM mà supervisor route tới. Chat graph và 5
specialist vẫn hand-built; đây là ngoại lệ có chủ đích mà mục *Direction* của
`techstacks/langgraph.md` đã dự liệu (wave 4 ghi lại vào đó).

```
trang trip ──POST /agent/trips/{id}/research──► router ──► ResearchService.start()
chat "research my trip" ──supervisor──► node research ──┘          │
                                                                  ▼
                                     BackgroundTask run_trip_research(run_id, ctx, turn)
                                                                  │  thread = research:{uid}:{trip}
   agent_runs / steps ◄── TurnMetricsHandler ◄── deep agent ──────┤
   progress bus       ◄── astream_events(v3) + rubric events      │
                                                                  ▼  CompositeBackend
   /skills/**  ← FilesystemBackend(app/research/skills, chỉ đọc)  │
   /memory/AGENTS.md ← StoreBackend ns ("users", uid, "research_memory")
   /research/**, /plan/** ← StoreBackend ns ("users", uid, "research", trip_id)
   còn lại (large_tool_results, conversation_history) ← StateBackend (theo thread)
```

## 2. Agent (`app/research/agent.py`)

```python
def build_research_agent(*, store, checkpointer, llm=None, grader_llm=None):
    model  = llm or get_agent_llm("trip_research")
    grader = grader_llm or get_agent_llm("trip_research_grader")
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/":   FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
            "/memory/":   StoreBackend(store=store, namespace=lambda rt: ("users", rt.context.user_id, "research_memory")),
            "/research/": StoreBackend(store=store, namespace=lambda rt: ("users", rt.context.user_id, "research", rt.context.trip_id)),
            "/plan/":     StoreBackend(store=store, namespace=lambda rt: ("users", rt.context.user_id, "research", rt.context.trip_id)),
        },
    )
    return create_deep_agent(
        model=model,
        tools=research_tools(),                       # read-only tool của registry, không tool mới
        system_prompt=registry.get("trip_research"),  # ngắn: vai trò, bố cục dossier, hợp đồng output
        skills=["/skills/"],
        memory=["/memory/AGENTS.md"],
        permissions=[
            FilesystemPermission(operations=["read"],  paths=["/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/research/**", "/plan/**", "/memory/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),   # rule khớp đầu tiên thắng
        ],
        subagents=SUBAGENTS,                          # §3
        middleware=[
            TodoListMiddleware(),
            RubricMiddleware(model=grader, tools=[validate_proposal, *fs_read_tools()], max_iterations=2,
                             on_evaluation=progress.on_rubric),
        ],
        backend=backend,
        context_schema=ResearchContext,
        state_schema=ResearchState,
        checkpointer=checkpointer,
        store=store,
        name="trip_research",
    )
```

- Đăng ký `HarnessProfile` cho instance OpenAI: `excluded_tools={"execute"}`,
  `general_purpose_subagent=disabled` (không ủy quyền vô định hướng). Đường tra cứu đã xác minh:
  profile khớp theo `ls_provider:model` của một instance `BaseChatModel`.
- `ResearchContext` (frozen dataclass): `user_id, trip_id, run_id, language, timezone`. Truyền
  qua `context=`; các namespace factory đọc nó; grader kế thừa nó.
- `ResearchState(DeepAgentState)`: `trip_id`, `user_id`, `preferences`, `language` — đúng các key
  mà tool registry inject (`search_flights`/`search_hotels` nhận `InjectedState("preferences")` và
  `("language")`; tool trip nhận `("trip_id")`). Subagent isolated nhận được các key này vì
  `state_schema` được chuyển tiếp cho subagent khai báo. `todos` là riêng từng agent.
- Dựng ở lifespan cạnh chat graph (`app.state.research_agent`), rebuild khi config generation đổi
  (cùng trigger với `resolve_travel_graph`).
- Hai hàng `agent_config` được seed: `trip_research`, `trip_research_grader` (grader thuộc
  `FAST_AGENTS`). Thiếu hàng sẽ hỏng âm thầm (bài học trong KB) nên seed là task của wave 1.

## 3. Skills, subagents, memory, rubric

**Skills (`app/research/skills/`, trong git, chỉ đọc lúc chạy):**
`dossier-format/` (bố cục file, tiêu đề, quy tắc trích dẫn "mỗi fact nêu tên tool đã sinh ra
nó"), `flights/`, `stays/`, `day-plans/`, `entry-and-season/`, `budget/`, `proposal/` (schema và
quy tắc id cho `/plan/proposal.json`). Mỗi `SKILL.md` ≤ 500 dòng, `name` = tên thư mục. Chỉ index
name+description đi vào system prompt; nội dung nạp khi kích hoạt. Subagent phải khai báo
`skills=["/skills/"]` (subagent tùy biến không kế thừa).

**Subagents (isolated, cùng instance model, mỗi cái có `TodoListMiddleware()` và `skills`):**

| tên | tool (tên trong registry, assert lúc build) | ghi |
|---|---|---|
| `flights` | `search_flights`, `resolve_date` | `/research/flights.md` |
| `stays` | `search_hotels`, `browse_hotels`, `search_places`, `nearby_places` | `/research/stays.md` |
| `days` | `search_places`, `nearby_places`, `resolve_place`, `get_route`, `get_city_route`, `get_weather`, `get_climate`, `get_air_quality` | `/research/days/day-N.md` |
| `entry_season` | `get_visa`, `get_local_tips`, `search_travel_knowledge`, `get_climate`, `get_packing` | `/research/entry-and-season.md` |
| `budget` | `get_trip_budget`, `estimate_trip_budget`, `expense_summary` | `/research/budget.md` |

Tên tool ở trên là tên read-only thật trong registry (xác minh 2026-09-18); `list_trips`, `recall_past_trips`, `get_user_preferences` và `parse_nl_query` cố ý bị loại khỏi research agent.

Agent chính: đọc `get_trip_summary` + `/memory/AGENTS.md`, ghi todos, `task()` năm subagent, đọc
file của chúng, ghi `/research/overview.md` và `/plan/proposal.json`, và cập nhật
`/memory/AGENTS.md` với những điều học được lâu dài về cách traveller này muốn được nghiên cứu
("thích boutique stay", "bỏ qua bảo tàng"). Ở lượt revise nó dùng `edit_file`, không viết lại.

**Memory:** `/memory/AGENTS.md` theo user, seed một lần (code, wave 2) từ store preference sẵn có
(`search_preferences`, định dạng như MIN-65 D2) để run đầu không "lạnh"; sau đó agent tự sở hữu.
Chỉ research agent đọc file này — chat graph không bao giờ — nên memory guard của chat vẫn là
thẩm quyền cho memory chat. Một policy hook của `StoreBackend` trên route `/memory/` chạy các quy
tắc nội dung của guard khi ghi (wave 2), để text injection không thể được lưu lại ở đó.

**Rubric (`prompts/trip_research_grader/v1.md`, kích hoạt bởi `state["rubric"]` mỗi run):**
mọi file chiều đều tồn tại và trích dẫn tool; mỗi ngày có bữa ăn và ≤ 3 hoạt động; proposal qua
`validate_proposal`; tổng tôn trọng budget trip nếu có; ngôn ngữ khớp yêu cầu.
`validate_proposal` là tool mới duy nhất, **chỉ grader dùng** (không bind cho agent): đọc
`/plan/proposal.json` qua backend và kiểm tra mọi id với DB (places, flight offers, hotels) —
"code computes" tất định, đưa cho grader làm bằng chứng. `max_iterations=2`; trạng thái cuối đọc
sau run qua `aget_state`.

## 4. Run, thread, tiến độ

- **Thread = dossier.** `thread_id = f"research:{user_id}:{trip_id}"`. Run đầu là lượt 1; mỗi
  "revise" là `HumanMessage` tiếp theo trên cùng thread, nên agent giữ ngữ cảnh và file;
  `SummarizationMiddleware` có sẵn (offload vào `/conversation_history/`) giới hạn lịch sử. Mỗi lượt
  vẫn có hàng `agent_runs` riêng (`kind="research"`, `channel="research"`, `trip_id`) cho metrics;
  `meta` của step đầu mang `{"turn": n, "revise": bool}` — không bao giờ mang text.
- **Runner** (`app/research/runner.py`, `async def`, lên lịch bằng FastAPI `BackgroundTask`):
  `async for` trên `agent.astream_events(input, version="v3", config={"configurable": {"thread_id": ...}, "callbacks": [metrics]}, context=ctx)` → phát tiến độ; bọc trong
  `asyncio.timeout(RESEARCH_TIMEOUT_S)`; luôn hoàn tất hàng run trên session tách biệt; không bao
  giờ raise ra khỏi task.
- **Resume, không restart.** Nếu process chết giữa chừng (hàng `running`, không có step kết
  thúc), `POST` tiếp theo cho trip đó resume thread checkpoint bằng `ainvoke(None, config)` dưới
  hàng run mới (`meta.resumed_from`). Sweep ở lifespan chỉ đánh dấu hàng `running` quá 30 phút là
  `interrupted`.
- **Progress bus** (`app/research/progress.py`): trong process, `run_id → (ring buffer, queues)`;
  event được suy ra chứ không tự soạn: `run.tool_calls` (tên tool + trạng thái; với
  `write_file`/`edit_file` chỉ lấy path), `run.subagents` (tên, trạng thái), `values.todos` (giai
  đoạn), rubric `on_evaluation` (lần lặp, kết quả), trạng thái kết thúc. Không có text tin nhắn,
  không có tool args.
- **SSE** `GET /agent/research/{run_id}/stream`: live từ bus khi có, nếu không thì snapshot từ
  `agent_run_steps` + index file, poll lại mỗi 2 giây tới khi kết thúc.

## 5. Hợp đồng công khai (bề mặt agent, JWT, premium)

| Method | Path | Ghi chú |
|---|---|---|
| POST | `/agent/trips/{trip_id}/research` | `{instruction?, language?}` → 202 `{run_id, thread_turn}`; 403 không phải chủ / không premium; 409 đang chạy; 429 `research_start` 3 lần/ngày/user. Gọi lần đầu = lượt 1, các lần sau trên cùng trip = lượt revise. |
| GET | `/agent/trips/{trip_id}/research` | tóm tắt run mới nhất (status, turn, files, proposal_ready) hoặc 404 |
| GET | `/agent/research/{run_id}` | status + giai đoạn (todos) + tóm tắt step + index file |
| GET | `/agent/research/{run_id}/stream` | SSE (§4) |
| GET | `/agent/research/{run_id}/files/{path:path}` | nội dung qua `backend.download_files` |
| PUT | `/agent/research/{run_id}/files/{path:path}` | user sửa qua `backend.upload_files`; backend đánh giá cùng bộ permission, nên không cần allowlist riêng |

`CurrentUserDep` + `require_premium`; ownership `trip.user_id == user.id` (`X-User-Id` của REST
chính là Supabase id). Router mỏng; `ResearchService` sở hữu các kiểm tra và sổ sách run.

## 6. Lối vào từ chat

`SupervisorIntent.target_agent` + `_Target` thêm `"research"`; prompt supervisor **v14** ("research
/ lên kế hoạch cả chuyến đi chuyên sâu → research; tìm kiếm thuần ở lại planner; cần trip đang
hoạt động"). `ALL_SUBAGENTS` thêm `"research"`; `PREMIUM_ONLY_SUBAGENTS` thêm `"research"` (free
tier nhận thông báo premium sẵn có qua `allowed_subagents`). Node mới **`research`** (đặt tên như
một specialist để dây `for name in SUBAGENTS` và destinations của reflection đã có bao trùm nó;
không gọi LLM): không có `trip_id` → `awaiting_user` + `system_reply("research_needs_trip")`; có thì
`ResearchService.start` (`session_scope()` riêng), trả lời `system_reply("research_started")`,
`current_flow="research"`. Key gợi ý `research.view_progress`, `research.start` (+ i18n en/vi).
Eval: routing goldens `research-*` en/vi dưới capability `routing` sẵn có (xem §12).

## 7. Trang trip (apps/web)

**Tab Research** (E006), khóa kèm gợi ý nâng cấp với free tier. Trạng thái trống → "Research this
trip"; tiến độ live (`useResearchStream(runId)` qua `streamBaseUrl()` với JWT; parser ở
`lib/stream/research.ts` phản chiếu `streaming/research_events.py`); cây file + trình xem markdown;
sửa inline (PUT); ô "Revise" (POST kèm instruction); panel proposal với "Apply to trip" gọi các REST
endpoint sẵn có (`POST /trips/{id}/items`, thêm shortlist) qua REST client với `X-User-Id`, mỗi item
một request, tóm tắt lỗi từng phần. Chạy `gen:api` sau khi BE xong.

## 8. Dữ liệu và an toàn

Không migration. `agent_runs` tiếp tục chỉ giữ cấu trúc; dossier, memory và lịch sử nằm trong
store / checkpointer. `instruction` đi qua bộ redaction PII sẵn có trước khi thành `HumanMessage`.
Text dossier không bao giờ đi vào chat graph. Kế toán chi phí qua `TurnMetricsHandler` theo run;
trần cứng: `RESEARCH_TIMEOUT_S=600`, rubric `max_iterations=2`, `recursion_limit` agent 150
(deepagents mặc định 9 999 — ta override qua `.with_config`), subagent `recursion_limit` 60.

## 9. Kiểm thử

Offline (`FakeLLM`, `InMemoryStore`, `MemorySaver`): build với thư mục skills thật; lượt kịch bản:
todos → `task(flights)` → subagent `write_file` → agent chính `write_file` proposal → grader gọi
`validate_proposal` (id sai một lần) → sửa → satisfied; permissions từ chối ghi vào `/skills/x`;
lượt thứ hai trên cùng thread sửa thay vì viết lại; runner hoàn tất khi timeout; thứ tự bus; route
202/403(chủ)/403(premium)/409/429; đường SSE snapshot; node launcher; routing của supervisor. Biến
thể Postgres: round-trip `StoreBackend` trên `PostgresStore` + resume checkpoint. Smoke có key
`eval/research_smoke.py` (không CI): một run thật trên trip đã seed → file tồn tại, proposal hợp lệ,
chi phí ≤ trần.

## 10. Waves (đầu vào cho writing-plans)

1. Dependency (`deepagents>=0.7.15,<0.8`) · `app/research/{context,state,tools,agent}.py` · thư mục skills · prompt `trip_research` v1 + grader v1 · seed hàng agent_config · test build/lượt offline.
2. `runner.py`, `progress.py`, `service.py` (start/status/latest/resume), seed memory + policy hook, nối lifespan, sweep, test.
3. Route + `research_events.py` + parser FE + rate limit + test.
4. Lối vào chat (supervisor v14, node `research`, guard reflection, tier gate, gợi ý, i18n, eval goldens) + đoạn ngoại lệ trong `techstacks/langgraph.md`.
5. Tab Research + luồng apply + `gen:api` · script smoke có key · bật mặc định `research_enabled`.

Wave 1–3 ship với `research_enabled=false`, nên sản phẩm chat không bị chạm cho tới khi wave 4 được review.

## 11. Phương án đã cân nhắc

- `response_format=Proposal` (structured output có kiểu) thay vì agent ghi `/plan/proposal.json`:
  có kiểu miễn phí, nhưng proposal sẽ không còn là file agent `edit_file` được ở lượt revise và
  user đọc được trong cây; giữ làm phương án dự phòng nếu đường file tỏ ra mong manh.
- Tiến độ chỉ bằng poll DB: giữ làm đường fallback, không phải đường duy nhất.
- Bind write tool với `interrupt_on` / `permissions mode="interrupt"`: E004 từ chối cho v1; harness
  hỗ trợ sau này mà không cần thiết kế lại.
- Một namespace theo user với trip trong path: từ chối (`ls/glob/grep` quét cả namespace).

## 12. Cam kết không thay thế và phạm vi ảnh hưởng (yêu cầu của chủ dự án, 2026-09-18)

**Mục tiêu nhắc lại:** thêm năng lực deep-agent research *bên cạnh* sản phẩm hiện có. Mọi thứ đang
chạy hôm nay không đổi hành vi; tính năng là bổ sung và tắt được.

### 12.1 Chạm vào đâu, chạm thế nào

| Bề mặt | Loại thay đổi | Rào chắn |
|---|---|---|
| `requirements-ai.txt` | **thêm** `deepagents` (kéo `langsmith` 0.9→0.12) | cùng gate với PR #219: full suite ×2 interpreter, Docker suite, so sánh eval-smoke với baseline |
| `app/research/**`, `app/research/skills/**`, `prompts/trip_research*/v1.md` | **mới** | package cô lập; chỉ lifespan, router và node launcher import nó |
| `app/agents/supervisor.py` `_Target`, `SupervisorIntent`, prompt **v14** | **sửa (enum routing + phiên bản prompt mới)** | v13 vẫn trên đĩa; v14 = v13 + một rule + hai ví dụ; routing goldens của mọi capability hiện có chạy lại và phải không đổi; fallback unknown-target đã có sẵn |
| `app/agents/constants.py` `ALL_SUBAGENTS` + `PREMIUM_ONLY_SUBAGENTS` | **thêm** `"research"` | graph nối `for name in SUBAGENTS: add_edge(name, "reflection")` và `reflection.destinations=(*SUBAGENTS, ...)`, nên node launcher **đặt tên `research`** và đăng ký như specialist; free tier loại nó qua đường `allowed_subagents` sẵn có |
| `app/agents/graph.py` | **thêm** một node `research` | không edge hiện có nào đổi |
| `app/agents/nodes.py` reflection | **thêm** guard cùng hình dạng `_booking_committed_this_turn` (`_research_started_this_turn`) để REVISE không khởi động job lần nữa | guard hiện có không đổi |
| `app/agents/suggestions.py`, `apps/web/messages/*.json` | **thêm** key | key hiện có không đổi |
| `app/db/seed.py` | **thêm** hai hàng `agent_config` | seed idempotent; hàng hiện có không đổi |
| `app/core/lifespan.py` | **thêm** `app.state.research_agent` | build lỗi được bắt và log; khởi động chat graph không bị ảnh hưởng; route research trả 503 |
| `app/streaming/research_events.py`, `apps/web/src/lib/stream/research.ts` | **mới** | taxonomy SSE của chat và parser không đổi; parser chat vốn bỏ qua event lạ |
| `app/routers/research.py` | **mới**, dưới `/agent/...` | không route hiện có nào đổi; `/agent/manifest` và MCP không đổi vì `validate_proposal` nằm ở `app/research/`, **không** ở `tools/registry.py` |
| `tools/registry.py`, 5 specialist, `plan_node`, memory extraction, `pii_guardrail`, summarize, `route_tasks` | **không chạm** | khẳng định bằng danh sách "file không đổi" trong plan + `blast-radius-check.sh` |
| store / checkpointer | **namespace / thread id mới** (`("users", uid, "research", trip)`, `("users", uid, "research_memory")`, `research:{uid}:{trip}`) | tách rời `prefs/procedural/episodes` và thread id của chat; `_search_kind` và memory guard không được gọi cho chúng |
| `agent_runs` | **giá trị hàng mới** `kind="research"`, `channel="research"` | không đổi schema; dashboard liệt kê như mọi run |
| eval | **thêm** routing goldens `research-*` dưới capability `routing` sẵn có | không đổi TAXONOMY (capability mới sẽ làm lệch `eval-compare` với baseline đã commit) |
| `techstacks/langgraph.md` | **thêm** một đoạn | chỉ tài liệu |
| web | **mới**: tab Research + hook + parser | các tab hiện có và chat widget không đổi |

### 12.2 Công tắc tắt

`settings.research_enabled` (mặc định **true** khi đã ship, **false** trong wave 1–4): khi false,
router research trả 404, node launcher trả lời `system_reply("research_unavailable")`, tab web ẩn, và
lifespan bỏ qua việc build research agent. Gạt cờ không bao giờ chạm chat graph.

### 12.3 Nghĩa vụ chứng minh mang vào PLAN.md

- SC: full BE suite pass với **cùng số lượng** như `main` trước tính năng (test bổ sung chỉ cộng thêm).
- SC: kết quả eval-smoke theo capability bằng baseline (routing goldens của planner/concierge/journal/booking/budget không đổi dưới v14).
- SC: tên `ALL_TOOLS`, `/agent/manifest` và danh sách tool MCP giống hệt từng byte trước/sau.
- SC: với `research_enabled=false` toàn bộ bề mặt mới vô hình (route 404, tab ẩn) và suite chat xanh.
- SC: launcher không bao giờ khởi động job thứ hai trong cùng lượt (test guard reflection).
