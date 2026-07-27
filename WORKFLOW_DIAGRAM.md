# Travel Agent — Chatbot Flow Diagram

Backend agent flow. Companion to `WORKFLOW.md`, which is the authoritative text.
Render with any Mermaid-aware viewer (GitHub, VS Code Mermaid preview, mermaid.live).
Last verified: 2026-07-01; the reflection node was removed from these diagrams in #112.

> Known drift, pre-dating #112: `extract_memory` is drawn as an in-graph node with a
> "skipped in FAST" note. It is neither — it runs as a background task after the
> response (`memory/extraction_runner.py`), and modes were removed in MIN-43. Trust
> `WORKFLOW.md` where the two disagree.

---

## 1. The big picture (simple view)

One user message travels through the graph left-to-right. It **reads** long-term
memory on the way in, **does the work** in the middle, and **saves** new memory on
the way out.

```mermaid
flowchart LR
    User([User message]) --> Load

    subgraph Read["1 · Remember"]
        Load["load_context<br/>read trip + past notes"]
    end

    subgraph Route["2 · Route"]
        Sup{"supervisor<br/>which specialist?"}
    end

    subgraph Work["3 · Do the work"]
        Agent["specialist sub-agent<br/>think ⇄ call tools"]
        Disp{"dispatch_next<br/>another queued intent?"}
    end

    subgraph Write["4 · Learn"]
        Ext["extract_memory<br/>save what's durable"]
    end

    Load --> Sup --> Agent --> Disp
    Disp -->|"next queued intent"| Agent
    Disp -->|"queue empty"| Ext
    Ext --> Reply([Reply to user])

    Load -. reads .-> Store[("Long-term memory<br/>prefs · instructions · past trips")]
    Ext  -. writes .-> Store
```

**In words:**

1. **Remember** — `load_context` pulls the active trip snapshot and the user's
   standing instructions from the store, so the agent starts with context.
2. **Route** — `supervisor` reads the message and picks one specialist
   (planner / concierge / journal / booking / budget).
3. **Do the work** — the specialist runs a *think ⇄ use-tools* loop until it has an
   answer; `dispatch_next` then runs any further intent the supervisor queued for
   this turn before the turn ends.
4. **Learn** — `extract_memory` runs in the background after the turn and saves any
   durable preferences, standing instructions, and trip outcomes for next time.

---

## 2. End-to-end flow (full detail)

```mermaid
flowchart TD
    Client([Client]) -->|"POST /agent/chat"| Chat["agent_chat()<br/>routers/agent.py"]
    Client -->|"POST /agent/stream (SSE)"| Stream["agent_stream()<br/>routers/agent.py"]

    Chat --> Persist["ConversationRepository<br/>persist user turn"]
    Persist --> Invoke["graph.ainvoke(state, config)<br/>thread_id = user_trip_conv"]
    Stream --> AStream["graph.astream(stream_mode=messages)<br/>filter: sub-agent tokens only"]

    Invoke --> Graph
    AStream --> Graph

    subgraph Graph["Compiled LangGraph (built once in lifespan)"]
        direction TB
        Load["load_context<br/>trip snapshot + procedural instructions"]
        Summ["summarize<br/>compress old turns if long"]
        Sup{"supervisor<br/>structured intent → target"}
        Plan{"plan (HITL)<br/>interrupt → await approval"}
        Disp{"dispatch_next<br/>drain queued intents"}
        Ext["extract_memory<br/>background write (skipped in FAST)"]

        START((START)) --> Load --> Summ --> Sup
        Sup -->|"goto = planner"| Planner
        Sup -->|"goto = concierge"| Concierge
        Sup -->|"goto = journal"| Journal
        Sup -->|"goto = budget"| Budget
        Sup -->|"goto = booking"| Plan
        Sup -->|"unknown / tier-gated → fallback"| END((END))

        Plan -->|"approved"| Booking
        Plan -->|"rejected"| END

        Planner --> Disp
        Concierge --> Disp
        Journal --> Disp
        Booking --> Disp
        Budget --> Disp

        Disp -->|"goto = next queued specialist"| Sup
        Disp -->|"queue empty / abandoned"| Ext
        Ext --> END
    end

    Graph --> Reply["extract last message<br/>persist assistant turn"]
    Reply --> Resp([ChatResponse / SSE tokens])

    Graph -.->|"snapshot per node"| CP[("Checkpointer<br/>Postgres → MemorySaver")]
    Load -.->|"read"| ST[("Long-term Store<br/>pgvector → InMemory")]
    Ext -.->|"write"| ST
```

---

## 3. Memory lifecycle (read + write)

Long-term memory lives in one store, namespaced per user as
`("users", <user_id>, <kind>)`. Three kinds, each read and written at a different
point in the turn.

```mermaid
flowchart LR
    subgraph Turn["One turn"]
        Load["load_context"]
        Planner["planner<br/>(sub-agent)"]
        Journal["journal<br/>(sub-agent)"]
        Ext["extract_memory<br/>(background, end of turn)"]
    end

    subgraph Store["Long-term store — ('users', user_id, kind)"]
        Prefs[("prefs<br/>likes / dislikes")]
        Proc[("procedural<br/>standing instructions")]
        Epi[("episodes<br/>past-trip outcomes")]
    end

    %% reads
    Proc -->|"read at start"| Load
    Epi  -->|"recall_past_trips (tool)"| Planner

    %% writes
    Journal -->|"save_user_preference (hot path)"| Prefs
    Ext -->|"durable likes"| Prefs
    Ext -->|"standing rules"| Proc
    Ext -->|"trip outcome (approved / proposed)"| Epi
```

- **prefs** — durable likes/dislikes. Written explicitly by the journal tool
  `save_user_preference`, and in the background by `extract_memory`.
- **procedural** — standing instructions ("always book aisle seats"). Read by
  `load_context` into the system prompt; written by `extract_memory`.
- **episodes** — per-trip outcomes. Recalled by the planner via `recall_past_trips`
  so it adapts instead of planning from scratch; written by `extract_memory` with
  `outcome="approved"` when the plan passed the HITL gate, else `"proposed"`.

> `extract_memory` is **best-effort and gated**: it is skipped entirely in FAST mode
> (`allow_memory_write=False`), and any write error is swallowed so a failed
> extraction never breaks the reply.

---

## 4. Sub-agent ReAct loop (each specialist)

```mermaid
flowchart LR
    START((START)) --> Assistant["assistant<br/>llm.bind_tools(domain tools)<br/>+ system prompt + summary"]
    Assistant -->|"tools_condition:<br/>has tool_calls"| Tools["ToolNode<br/>run tools, session_scope()"]
    Tools -->|"ToolMessage<br/>(ok or status=error)"| Assistant
    Assistant -->|"no tool_calls"| END((END))
```

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
    P --> flight[flight]
    P --> hotel[hotel]
    P --> weather[weather]
    P --> routing[routing]
    P --> episodes[("episodes<br/>recall_past_trips")]

    C --> place
    C --> weather
    C --> routing
    C --> tip[tip]

    J --> trip
    J --> memory[("memory<br/>prefs store")]

    B --> flight
    B --> hotel

    Bu --> expense[expense]
    Bu --> tripbudget["get_trip_budget"]

    hotel -.->|"book_hotel<br/>⚠ destructive"| money((side effect))
```

## 6. Tool inventory by domain

| Domain | Tools |
|---|---|
| trip | `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`*, `add_itinerary_item`* |
| place | `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories` |
| flight | `search_flights` |
| hotel | `search_hotels`, `book_hotel`† |
| weather | `get_weather`, `get_packing`, `get_air_quality` |
| routing | `get_route`, `get_city_route` |
| tip | destination tips lookup |
| expense | `add_expense`*, `list_expenses`, `expense_summary` |
| memory | `save_user_preference`*, `get_user_preferences` |
| episodes | `recall_past_trips` |

`*` write · `†` destructive
