# Travel Agent — Chatbot Flow Diagram

Current backend agent flow on `feat/monorepo-fe`. Companion to `WORKFLOW.md`.
Render with any Mermaid-aware viewer (GitHub, VS Code Mermaid preview, mermaid.live).

## 1. End-to-end chatbot flow

```mermaid
flowchart TD
    Client([Client]) -->|"POST /agent/chat"| Chat["agent_chat()<br/>routers/agent.py:68"]
    Client -->|"POST /agent/stream (SSE)"| Stream["agent_stream()<br/>routers/agent.py:100"]

    Chat --> Persist["ConversationRepository<br/>persist user turn"]
    Persist --> Invoke["graph.ainvoke(state, config)<br/>thread_id = user_trip_conv"]
    Stream --> AStream["graph.astream(stream_mode=messages)<br/>filter: sub-agent tokens only"]

    Invoke --> Graph
    AStream --> Graph

    subgraph Graph["Compiled LangGraph (built once in lifespan)"]
        direction TB
        Load["load_context<br/>inject active-trip snapshot"]
        Summ["summarize<br/>compress old turns if long"]
        Sup{"supervisor<br/>structured intent → target"}
        Refl{"reflection<br/>REVISE / OK (max 1)"}

        START((START)) --> Load --> Summ --> Sup
        Sup -->|"goto = planner"| Planner
        Sup -->|"goto = concierge"| Concierge
        Sup -->|"goto = journal"| Journal
        Sup -->|"goto = booking"| Booking
        Sup -->|"goto = budget"| Budget
        Sup -->|"unknown intent → fallback"| END((END))

        Planner --> Refl
        Concierge --> Refl
        Journal --> Refl
        Booking --> Refl
        Budget --> Refl

        Refl -->|"REVISE → goto current_flow"| Sup
        Refl -->|"OK / limit reached"| END
    end

    Graph --> Reply["extract last message<br/>persist assistant turn"]
    Reply --> Resp([ChatResponse / SSE tokens])

    Graph -.->|"snapshot per node"| CP[("Checkpointer<br/>Postgres → MemorySaver")]
    Graph -.->|"prefs / facts"| ST[("Long-term Store<br/>pgvector → InMemory")]
```

## 2. Sub-agent ReAct loop (each specialist)

```mermaid
flowchart LR
    START((START)) --> Assistant["assistant<br/>llm.bind_tools(domain tools)<br/>+ system prompt + summary"]
    Assistant -->|"tools_condition:<br/>has tool_calls"| Tools["ToolNode<br/>run tools, session_scope()"]
    Tools -->|"ToolMessage<br/>(ok or status=error)"| Assistant
    Assistant -->|"no tool_calls"| END((END))
```

## 3. Sub-agent → tool-domain map

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

    C --> place
    C --> weather
    C --> rag[("RAG<br/>destination knowledge")]

    J --> trip
    J --> memory[("memory<br/>prefs store")]

    B --> flight
    B --> hotel

    Bu --> expense[expense]
    Bu --> tripbudget["get_trip_budget"]

    hotel -.->|"book_hotel<br/>⚠ destructive"| money((side effect))
```

## 4. Tool inventory by domain

| Domain | Tools |
|---|---|
| trip | `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`*, `add_itinerary_item`* |
| place | `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories` |
| flight | `search_flights` |
| hotel | `search_hotels`, `book_hotel`† |
| weather | `get_weather`, `get_packing`, `get_air_quality` |
| expense | `add_expense`*, `list_expenses`, `expense_summary` |
| memory | `save_user_preference`*, `get_user_preferences` |
| rag | `search_destination_knowledge` |

`*` write · `†` destructive
