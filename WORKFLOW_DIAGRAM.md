# Travel Agent — Chatbot Flow Diagram

Current backend agent flow. Companion to `WORKFLOW.md`.
Render with any Mermaid-aware viewer (GitHub, VS Code Mermaid preview, mermaid.live).
Last verified: 2026-09-21.

---

## 1. The big picture (simple view)

One user message travels through the graph left-to-right. It **reads** long-term
memory on the way in, **does the work** in the middle, and **saves** new memory
*after* the turn, in the background.

```mermaid
flowchart LR
    User(["User message"]) --> Guard

    subgraph Read["1 · Guard + remember"]
        Guard["pii_guardrail<br/>mask card numbers"]
        Load["load_context<br/>read trip + past notes"]
        Guard --> Load
    end

    subgraph Route["2 · Route"]
        Sup{"supervisor<br/>which specialist(s)?"}
    end

    subgraph Work["3 · Do the work"]
        Agent["specialist sub-agent(s)<br/>think ⇄ call tools"]
        Refl{"reflection<br/>good enough?"}
    end

    Load --> Sup --> Agent --> Refl
    Refl -->|"needs work"| Agent
    Refl -->|"ok"| Reply(["Reply to user"])

    Reply -. "after the turn (background task)" .-> Ext["extract_memory<br/>save what's durable"]

    Load -. reads .-> Store[("Long-term memory<br/>prefs · instructions · past trips")]
    Ext  -. writes .-> Store
```

**In words:**

1. **Guard + remember** — `pii_guardrail` masks credit-card numbers, then
   `load_context` pulls the active trip snapshot plus the user's standing
   instructions, profile, and preferences from the store.
2. **Route** — `supervisor` classifies one or more intents into an ordered
   `tasks` list (planner / concierge / journal / booking / budget).
3. **Do the work** — a single-intent turn runs one specialist's *think ⇄
   use-tools* loop; a multi-intent turn fans out to parallel workers that a
   `synthesize` node merges. `reflection` may send a weak answer back once.
4. **Learn** — memory extraction runs as a **post-response background task**
   (not a graph node), saving durable preferences, standing instructions, and
   trip outcomes for next time.

---

## 2. End-to-end flow (full detail)

```mermaid
flowchart TD
    Client(["Client"]) -->|"POST /agent/chat"| Chat["agent_chat()<br/>routers/agent.py"]
    Client -->|"POST /agent/stream (SSE)"| Stream["agent_stream()<br/>routers/agent.py"]

    Chat --> Persist["ConversationRepository<br/>persist user turn"]
    Persist --> Invoke["graph.ainvoke(state, cfg, context=ctx)<br/>thread_id = user_trip_conv"]
    Stream --> AStream["graph.astream(messages + updates,<br/>subgraphs=True)"]

    Invoke --> Graph
    AStream --> Graph

    subgraph Graph["Compiled LangGraph (built once in lifespan)"]
        direction TB
        Guard["pii_guardrail<br/>mask card numbers"]
        Load["load_context<br/>trip snapshot + memory blocks"]
        Summ["summarize<br/>compress if long OR token-heavy"]
        Sup{"supervisor<br/>structured intent → tasks[]"}
        RT{"route_tasks<br/>(conditional edge)"}
        Plan{"plan (HITL)<br/>interrupt → await approval"}
        Worker["synthesis_worker × N<br/>(Send fan-out)"]
        Synth["synthesize<br/>merge worker results"]
        Refl{"reflection<br/>REVISE / OK (max 1)"}

        START(("START")) --> Guard --> Load --> Summ --> Sup --> RT
        RT -->|"no tasks / tier-gated"| END(("END"))
        RT -->|"tasks[0] = booking"| Plan
        RT -->|"single task"| Planner
        RT -->|"single task"| Concierge
        RT -->|"single task"| Journal
        RT -->|"single task"| Budget
        RT -->|"many tasks → Send × N"| Worker

        Plan -->|"approved"| Booking
        Plan -->|"rejected"| END

        Worker --> Synth

        Planner --> Refl
        Concierge --> Refl
        Journal --> Refl
        Booking --> Refl
        Budget --> Refl
        Synth --> Refl

        Refl -->|"REVISE → goto current_flow"| Planner
        Refl -->|"REVISE → goto current_flow"| Synth
        Refl -->|"OK / limit / awaiting_user / booked"| END
    end

    Graph --> Reply["extract last AIMessage<br/>persist assistant turn + agent_run"]
    Reply --> Resp(["ChatResponse / SSE tokens"])
    Reply -. "background task (skipped on interrupt)" .-> Ext["extract_memory"]

    Graph -.->|"snapshot per node"| CP[("Checkpointer<br/>Postgres → MemorySaver")]
    Load -.->|"read"| ST[("Long-term Store<br/>pgvector → InMemory")]
    Ext -.->|"write"| ST
```

> `route_tasks` is pure code: a single task goes straight to its specialist, a
> `booking` task detours through the HITL `plan` node, and two or more tasks fan
> out to parallel `synthesis_worker` instances via `Send` that converge on
> `synthesize`. A REVISE routes `goto=current_flow` (the specialist or
> `synthesize` that produced the answer) — never back to the supervisor.

---

## 3. Memory lifecycle (read + write)

Long-term memory lives in one store, namespaced per user as
`("users", <user_id>, <kind>)`. Three kinds, each read and written at a different
point in the turn. Every read passes through the store-layer poisoning guard.

```mermaid
flowchart LR
    subgraph Turn["One turn"]
        Load["load_context"]
        Planner["planner<br/>(sub-agent)"]
        Journal["journal<br/>(sub-agent)"]
        Ext["extract_memory<br/>(background, after the turn)"]
    end

    subgraph Store["Long-term store — ('users', user_id, kind)"]
        Prefs[("prefs<br/>likes / dislikes")]
        Proc[("procedural<br/>standing instructions")]
        Epi[("episodes<br/>past-trip outcomes")]
    end

    %% reads
    Proc -->|"read at start (all rows)"| Load
    Prefs -->|"read at start (all non-profile + profile)"| Load
    Epi  -->|"recall_past_trips (tool, top 3)"| Planner

    %% writes
    Journal -->|"save_user_preference (hot path)"| Prefs
    Ext -->|"durable likes"| Prefs
    Ext -->|"standing rules"| Proc
    Ext -->|"trip outcome (approved / proposed)"| Epi
```

- **prefs** — durable likes/dislikes. Written explicitly by the journal tool
  `save_user_preference`, and in the background by `extract_memory`. Read whole
  by `load_context` (no cap since PR #218); reserved keys `name`/`gender`/
  `travel_group` form the profile block.
- **procedural** — standing instructions ("always book aisle seats"). All rows
  read by `load_context` into the system prompt; written by `extract_memory`
  under a 6-key canonical allowlist.
- **episodes** — per-trip outcomes. Recalled by the planner via
  `recall_past_trips` (top 3) so it adapts instead of planning from scratch;
  written by `extract_memory` with `outcome="approved"` when the plan passed the
  HITL gate, else `"proposed"`.

> `extract_memory` is a **post-response background task**, not a graph node. It
> is skipped when `allow_memory_write=False` or a HITL interrupt is pending, and
> any write error is swallowed so a failed extraction never breaks the reply.
> On read, each row is checked by `memory/guard.py` and stamped with a
> month-granularity `(recorded …)` age marker (`format_age`, PR #216).

---

## 4. Sub-agent ReAct loop (each specialist)

```mermaid
flowchart LR
    START(("START")) --> Assistant["assistant<br/>llm.bind_tools(domain tools)<br/>+ system prompt + memory + date"]
    Assistant -->|"tools_condition:<br/>has tool_calls"| Tools["ToolNode<br/>run tools, session_scope()"]
    Tools -->|"ToolMessage<br/>(ok or status=error)"| Assistant
    Assistant -->|"no tool_calls"| END(("END"))
```

Every specialist also binds the private `needs_clarification` tool (not in the
public manifest / MCP surface); calling it sets `awaiting_user=True` and
reflection ends the turn early.

## 5. Sub-agent → tool-domain map

```mermaid
flowchart LR
    Sup{{supervisor}}

    Sup --> P[planner]
    Sup --> C[concierge]
    Sup --> J[journal]
    Sup --> B[booking]
    Sup --> Bu[budget]

    P --> trip[trip]
    P --> place[place]
    P --> flightS["flight search"]
    P --> hotelA["hotel availability"]
    P --> weather[weather]
    P --> climate[climate]
    P --> routing[routing]
    P --> date[date]
    P --> episodes[("episodes<br/>recall_past_trips")]

    C --> place
    C --> weather
    C --> climate
    C --> routing
    C --> tip[tip]
    C --> visa[visa]
    C --> hotelBrowse["hotel browse + availability"]
    C --> knowledge["travel-knowledge RAG"]
    C --> date

    J --> trip
    J --> memory[("memory<br/>prefs store")]

    B --> flight["flight search + book"]
    B --> hotel["hotel search + book"]
    B --> cancel["cancel flight / hotel"]
    B --> date

    Bu --> expense[expense]
    Bu --> tripbudget["trip budget<br/>read / set / estimate"]

    flight -.->|"book_flight<br/>⚠ destructive"| money((side effect))
    hotel -.->|"book_hotel<br/>⚠ destructive"| money
    cancel -.->|"⚠ destructive"| money
```

## 6. Tool inventory by domain

Source of truth: `tools/registry.py` (`TOOLS_BY_DOMAIN`). Every tool declares an
explicit `args_schema` that also declares its injected args (PR #204).

| Domain | Tools |
|---|---|
| trip | `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `list_trips`, `add_place_to_trip`*, `add_itinerary_item`*, `create_trip`*, `set_trip_budget`*, `estimate_trip_budget` |
| place | `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories` |
| flight | `search_flights`, `book_flight`† |
| hotel | `search_hotels`, `browse_hotels`, `book_hotel`† |
| booking | `cancel_flight`†, `cancel_hotel`† |
| weather | `get_weather`, `get_packing`, `get_air_quality` |
| climate | `get_climate` |
| routing | `get_route`, `get_city_route` |
| tip | `get_local_tips` |
| visa | `get_visa` |
| knowledge (RAG) | `search_travel_knowledge` |
| expense | `add_expense`*, `list_expenses`, `expense_summary` |
| memory | `save_user_preference`*, `get_user_preferences` |
| episodes | `recall_past_trips` |
| date | `resolve_date` |
| _private_ | `needs_clarification` (not registered in the manifest / MCP surface) |

`*` write · `†` destructive. `list_trips` is served in-agent but excluded from
the MCP surface (its injected `user_id` would become caller-supplied); MCP also
omits destructive tools and any tool needing an injected `store`/`tool_call_id`.
