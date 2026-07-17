---
slug: agentic-chatbot
type: research-brief
status: research
owner: Minh Tran
created: 2026-07-17
---

# Research Brief — Making the Chatbot More Agentic

Two-pass deep research (2026-07-17): (A) full map of the current agent implementation,
(B) current (2025–2026) agentic patterns for LangGraph + FastAPI + Next.js. This brief
reconciles the two into prioritized, non-duplicating upgrade paths.

## 1. Where the agent stands today

**Architecture:** LangGraph supervisor → 5 ReAct sub-agents (planner/concierge/journal/
budget + HITL-gated booking) → reflection → END. Built once in `core/lifespan.py`; turn
flow in `apps/api/app/agents/graph.py:122-166`. Structured `SupervisorIntent` routing with
"LLM parses, code computes" slot normalization. Postgres checkpointer (threads) + a real
**three-layer long-term memory** already in place (`memory/`: prefs / procedural
instructions / episodes in `PostgresStore`+pgvector, background extraction via
`memory/extraction_runner.py`). ~30 registry tools (`tools/registry.py`), 4 destructive
(`book_flight`, `book_hotel`, `cancel_flight`, `cancel_hotel`). SSE event taxonomy already
streams sub-agent + tool activity + panels to the FE; MCP re-exposes the registry.

**How agentic is it?** Reactive, single-turn, bounded:

| Gap | Evidence |
|---|---|
| No upfront multi-step planning | routing is one-shot; `dispatch_next` (`agents/nodes.py:233`) queues at most **one** secondary intent, never `booking` |
| No initiative between turns | only memory extraction runs post-turn in background; no scheduled/event-driven agent runs |
| Shallow reflection | `reflection/v1.md` = binary REVISE/OK, fast model, no rubric, max 1 revision, same sub-agent re-run — cannot re-route or verify against state |
| Coarse HITL | one `interrupt()` gates *entry to the booking sub-agent* (`nodes.py:202`), not individual tool calls; no undo/compensation path |
| Heuristic suggestions | `agents/suggestions.py` deterministic rule table (LLM replacement already spec'd — see §4) |
| Unverified memory writes | `extract_memory` persists parsed LLM JSON; dedup = key overwrite only; no consolidation/decay |
| No parallel work | sub-agents run strictly sequentially; no fan-out for independent searches |

## 2. Pattern landscape (2025–2026, sourced)

- **Plan-as-state beats plan-and-execute graphs** — deepagents-style `write_todos` tool +
  todo ledger in graph state; replan = rewrite todos, no separate replanner node.
- **Tiered HITL** — LangChain 1.x `HumanInTheLoopMiddleware`: per-tool `interrupt_on`
  (approve/edit/reject). Practitioner rule: interrupt **only** irreversible high-blast
  actions; reversible writes get **preview + undo** (compensating tools) instead.
- **Ambient agents** — cron/event-triggered graph runs on dedicated thread_ids, surfacing
  via notify/question/review. Production travel apps (Mindtrip Stays, Expedia, Booking)
  ship price monitoring + trip-timeline nudges this way.
- **Tool-grounded verification** — CRITIC/VerifiAgent-style: critics call tools and run
  deterministic checks (budget arithmetic, date overlap) rather than judging prose;
  Agent-as-a-Judge for offline evals.
- **Orchestration** — supervisor remains the production default; collapse sub-agents that
  share context; LangGraph `Send` API for parallel fan-out; ephemeral task-subagents for
  context isolation.
- **Agentic UX** — streamed plan checklist, per-tool status, interruptible runs, artifact/
  canvas panels (AG-UI protocol or hand-rolled SSE — ours already covers most events).
- **API direction:** LangGraph/LangChain 1.x (GA Oct 2025) moved agent ergonomics to
  **middleware** (`create_agent` + middleware stack) — prefer that surface when upgrading.

## 3. Prioritized upgrade paths

Ordered by leverage ÷ effort, each anchored to an existing seam.

### P1 — Plan-as-state task ledger (the core "more agentic" unlock)
Generalize `dispatch_next` from "one queued secondary intent" to a real task queue.
`state.py:64` already types `pending_flows`; add a `todos` state key + a supervisor-writable
plan (`write_todos`-style tool or structured output extension of `SupervisorIntent`).
Sub-agents execute items; `dispatch_next` pops until done or budget hit. Enables
"plan my Tokyo weekend" → search flights → check weather → build itinerary → summarize,
in one turn. *Seam:* `agents/nodes.py:233`, `agents/state.py`, supervisor prompt v7.

### P2 — Tiered HITL + undo (unlocks autonomy safely)
Reclassify the tool registry into read / write / destructive tiers (metadata already exists:
`_DESTRUCTIVE`/`_WRITE` in `registry.py`). Reads auto-execute; reversible writes
(`add_expense`, `add_place_to_trip`, `add_itinerary_item`) execute with a visible
**undo affordance** (compensating tools — most CRUD deletes already exist as services);
only cancellations/payments keep blocking `interrupt()`. Move the interrupt from
route-entry (`plan_node`) to per-tool. *Seam:* wrap destructive ToolNode calls with
`interrupt()`; FE `InterruptPrompt.tsx` already handles approve/reject.

### P3 — Tool-grounded reflection (feeds spec min-59)
Replace the binary REVISE/OK with: (1) **deterministic state checks first** — itinerary vs
budget, date overlaps, orphaned bookings (cheap, no LLM); (2) a structured rubric verdict
that can **re-route** (not just re-run) and cite which check failed. `max_revisions` is
already context-driven. Wire recorded conversations + deepeval (`apps/api/eval/`) into a
regression suite. *Seam:* `make_reflection_node` (`nodes.py:151`), `reflection/v2.md`.
**Do not duplicate:** `specs/min-59-runtime-self-eval-loop` — this path should land as
input to that spec.

### P4 — Proactive "trip sentinel" (ambient agency, high visibility)
Scheduled background graph runs on a dedicated thread per trip: price re-check on
shortlisted flights/hotels (deterministic search makes diffs trivial), pre-trip checklist
N days out, weather alert before departure. Surface via a notifications table + SSE/panel
or suggestion chips on next open. *Seam:* the `BackgroundTasks` pattern in
`routers/agent.py` (already used for memory extraction) + APScheduler; trips have dates,
`trip-value-layer` (shipped) gives gaps/booking linkage to reason over.

### P5 — Parallel fan-out for planning
Use LangGraph `Send` to run flight + hotel + weather searches concurrently when the plan
requires all three (P1's ledger tells us). Cuts perceived latency where the agent does the
most work. *Seam:* `build_graph` (`graph.py:135`); panels already merge by kind.

### P6 — Memory hardening (infra exists, trust doesn't)
Add verification/consolidation to the single write path (`extraction_runner.py`):
dedup-by-similarity, contradiction resolution (new pref supersedes old), decay/expiry for
stale episodes. No new storage needed. *Seam:* `run_memory_extraction`.

### P7 — Agentic UX: plan visibility
Stream the P1 todo ledger as a new SSE event (`plan` or extend `subagent`); FE renders a
live checklist with per-item status; add a stop button (checkpointer makes interrupt/resume
free). *Seam:* `streaming/events.py` + `mapper.py`; FE `useAgentStream.ts` already upserts
typed events. **Contract note:** SSE event changes must mirror into
`apps/web/src/lib/stream/` (lockstep invariant, `techstacks/frontend.md`).

## 4. Existing specs — do not duplicate

| Spec | Status | Overlap handling |
|---|---|---|
| `llm-chat-suggestions` | high-risk, not shipped | Suggestions stay out of scope here; P1's ledger can later feed it richer context |
| `min-59-runtime-self-eval-loop` | planned | P3 lands *as input to* it, not beside it |
| `min-58-chatbot-eval-deepeval` | in repo (`eval/`) | P3's regression suite builds on it |
| `trip-value-layer` | shipped | P4 consumes its gaps/booking linkage |
| `web-content-enrichment` | design | New concierge tool only; orthogonal |
| `min-65-chatbot-intelligence` | partly shipped | P1 is its natural continuation (`dispatch_next` → ledger) |

## 5. Risks / constraints

- **Latency & cost:** P1/P5 add LLM roundtrips per turn — keep the ledger on the fast
  model, cap ledger length, respect `agent_recursion_limit=25` (raise deliberately).
- **Prompt changes are pointer-gated:** supervisor behavior lives in versioned prompts
  (`prompts/<name>/vN.md` + `active.yaml`); graph is baked at lifespan startup — no hot
  reload (`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`).
- **Free tier:** ledger execution must respect tier gating (`AgentContext.allowed_subagents`).
- **P4 auth:** background runs execute without a live user JWT — needs a service-context
  decision (hard gate: auth touch → escalate at intake).
- **Anon identity:** client-supplied `user_id` bounds how much trust P6 memory can carry
  pre-login.

## 6. Suggested sequencing

P1 → P2 ship together as one arc ("the agent plans and acts, safely") — P2's undo model is
what makes P1's multi-step execution acceptable without approval fatigue. Then P7 (make it
visible), P3 (make it verified), P4 (make it proactive), P5/P6 opportunistic.

Sources: LangChain deepagents docs, planning-agents & ambient-agents blogs, LangGraph
memory/HITL docs, LangMem SDK, VerifiAgent (arXiv 2504.00406), Agent-as-a-Judge (arXiv
2410.10934), supervisor-vs-swarm analyses (Augment, Focused), Mindtrip Stays launch (Jul
2026), AG-UI protocol (CopilotKit).
