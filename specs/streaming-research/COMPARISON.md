# Should `travel-pi` adopt `chat-agents`' streaming patterns?

Companion to `RESEARCH.md`. Decision-oriented. Each item: what it is, the gap, the
cost, and a verdict (✅ adopt / 🤔 conditional / ❌ skip).

---

## TL;DR verdict table

| # | Change | Effort | Verdict |
|---|---|---|---|
| 1 | Add `version="v2"` to `graph.astream(...)` | XS | ✅ Adopt |
| 2 | Typed event taxonomy + `app/streaming/` package | M–L | 🤔 Conditional on FE needs |
| 3 | Tool-call / sub-agent lifecycle events | M | 🤔 Conditional on FE needs |
| 4 | Switch to `sse-starlette` `EventSourceResponse` | S | 🤔 Conditional |
| 5 | Typed `done`/`error` terminal events (vs `[DONE]` string) | S | ✅ Adopt (small) |
| 6 | Heartbeat/ping keepalive | S | 🤔 Conditional (deploy-dependent) |
| 7 | `astream_events` v3 protocol | L | ❌ Skip (beta) |
| 8 | Budget / compression / memory-pressure telemetry | L | ❌ Skip (no need) |
| 9 | `extract.py`-style final-report guard | S | ❌ Skip (chat-shaped, not report-shaped) |

---

## 1. ✅ Add `version="v2"` — do this regardless

Our call is `graph.astream(stream_input, cfg, stream_mode="messages", subgraphs=True)`
(`agent.py:154`), unpacked as `async for ns, (chunk, _meta) in ...`. That is the **legacy
tuple form**. The docs' current recommended form is `version="v2"`, which yields a unified
`StreamPart` dict `{"type", "ns", "data"}`.

- **Why:** forward-compatibility; one consistent shape across modes; what the docs now
  document. `chat-agents` uses it everywhere.
- **Cost:** ~10 lines in `tokens()` — change the unpack to read `chunk["type"]`,
  `chunk["ns"]`, `chunk["data"]`.
- **Risk:** low, but it *does* change the iteration shape, so it needs a test pass against
  `app/core/streaming.py` + the stream router test. Treat as **normal lane**, not tiny.
- **Caveat:** confirm our installed `langgraph` version supports `version="v2"` on
  `astream` (check `apps/api/requirements.txt`). If we're on an older pin, this is a
  dependency bump first.

## 2. 🤔 Typed event taxonomy — only if the FE renders structured activity

`chat-agents` emits ~26 named JSON events; we emit raw token text + `reset`/`interrupt`.
This is the single biggest architectural difference.

- **Adopt if:** the `apps/web` chat UI is going to show tool calls in progress
  ("✈️ searching flights…"), sub-agent handoffs ("Planner → Booking"), or a HITL plan
  card. Then a typed protocol (`tool_call_started/completed`, `specialist_active`,
  `text_delta`, `message_complete`) is the right backbone and far cleaner than scraping
  raw tokens.
- **Skip if:** the FE only renders the assistant's prose answer (our memory note
  `agent-response-formatting-web-vs-whatsapp` says replies render as markdown via
  streamdown). Then the typed layer is unused complexity — violates our "simplicity first"
  rule.
- **Shape if adopted:** a *small* `app/streaming/events.py` (factory funcs returning
  `{"event","data"}`) + a thin mapper. Do **not** clone `chat-agents`' full
  `ChunkMapper` — most of its surface (deepagents `task`/`think_tool`, quant artifacts,
  `/memories/` files) is specific to their deep-research agent and irrelevant to our trip
  planner.
- **This is the open question for the user** — it depends on FE product direction, which
  is still in `/brainstorming` per memory (`monorepo-fe-phase0-state`).

## 3. 🤔 Tool-call / sub-agent lifecycle events

Subset of #2. Requires also consuming `stream_mode=["messages","updates"]` (we only use
`messages`). The `updates` mode is where tool-call starts/completions and node transitions
surface. Same conditional as #2: valuable only if the FE visualises agent activity.

## 4. 🤔 `sse-starlette` `EventSourceResponse`

We hand-roll SSE framing in `app/core/streaming.py` (`data: <text>\n\n`, `[DONE]`).
`chat-agents` uses `sse-starlette`, which gives proper `event:`/`id:`/`retry:` framing,
built-in `ping=` keepalive, and client-disconnect handling for free.

- **Pro:** less framing code to own; standard.
- **Con:** new dependency; our hand-rolled version already works and is markdown-safe
  (one `data:` per physical line). Only worth it if we also do #2 (the typed events make
  `EventSourceResponse`'s `{"event","data"}` contract pay off).
- **Verdict:** bundle with #2 if we do #2; otherwise skip.

## 5. ✅ Typed terminal `done`/`error` events

Cheap, standalone win. Replace the `data: [DONE]\n\n` *string sentinel* with a named
`event: done` (and ensure errors mid-stream emit `event: error` with a JSON code, the way
`chat-agents` does `chat.error(code=...)`). String sentinels are brittle for the FE parser;
a typed terminal is unambiguous. Low risk, no new deps. Pairs naturally with our existing
`reset`/`interrupt` named events.

## 6. 🤔 Heartbeat / keepalive

Neither repo sets a ping today. Whether we need one depends on deployment: proxies/load
balancers may cut idle SSE connections. Our long agent turns (supervisor → sub-agent →
reflection loop) can have multi-second gaps with no tokens. If we see dropped connections
in prod, add a ping (trivial with `sse-starlette` `ping=N`, or a manual `: keepalive\n\n`
comment line on a timer). Not urgent.

## 7. ❌ `astream_events` v3

Beta since LangGraph v1.2.0. Powerful (typed projections `stream.messages`, `stream.tools`),
but it's the bleeding edge and would be a rewrite of our stream loop. `chat-agents` itself
does **not** use it. Revisit when it's stable and we have a concrete need.

## 8. ❌ Budget / compression / memory-pressure telemetry

`chat-agents` tracks per-run token budgets, tiktoken-based compression detection, and peak
memory pressure because it runs unbounded deep-research agents that can blow context. Our
trip-planner turns are bounded and tool-driven. This is solving a problem we don't have —
classic speculative complexity. Skip until we observe runaway context.

## 9. ❌ `extract.py` final-report guard

`chat-agents` validates a ≥500-char final report because research produces a *document*.
Our agent produces *conversational replies*, which are legitimately short ("Booked! ✅").
A min-length guard would be actively wrong for us.

---

## Recommended sequencing (if user wants to proceed)

**Phase A — no-regret cleanups (small, do anytime):**
- #1 `version="v2"` (after confirming langgraph pin)
- #5 typed `done`/`error` terminal events

**Phase B — only after FE direction is decided (`/brainstorming` in progress):**
- #2 + #3 + #4 together: typed event package + `updates` mode + `sse-starlette`, scoped to
  ONLY the events our FE will actually render. Right-size — do not port the deep-research
  surface.

**Never (current scope):** #7, #8, #9.

---

## Open question for the user

The pivotal fork is **#2/#3**: *Will the `apps/web` chat UI render structured agent
activity (tool calls, sub-agent handoffs, HITL plan approval cards), or just stream the
assistant's markdown answer?* That single product decision determines whether ~80% of
`chat-agents`' streaming sophistication is worth porting. Until it's answered, I'd ship
Phase A and defer Phase B.
