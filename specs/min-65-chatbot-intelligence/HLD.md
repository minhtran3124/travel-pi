---
slug: min-65-chatbot-intelligence
doc: high-level-design
ticket: MIN-65 — Improve chatbot intelligence: memory, reasoning & suggestion quality
created: 2026-07-12
status: proposed
related: specs/agent-memory-layers/ (P1 shipped, P2 episodic shipped), specs/min-55-shortcut-suggestions/, specs/min-58-chatbot-eval-deepeval/
---

# HLD — Chatbot Intelligence: Memory, Reasoning & Suggestion Quality

## 1. Context & the real gaps

MIN-65 asks for 3 groups of improvement. After a deep codebase review, **most of the
long-term memory infrastructure is already shipped** — this design only patches the
actual gaps, it does not rebuild anything.

| Ticket requirement | Current state in code | Gap |
|---|---|---|
| Long-term preference memory | ✅ `PostgresStore` + pgvector semantic index (`app/memory/store.py`), background extraction after every turn (`extraction_runner.py`), profile injection (MIN-53) | General prefs (beyond the 3 profile keys) are **not auto-injected** — only journal/planner see them via a tool |
| Entity tracking within a session | ❌ No slot/entity state. Flight dates, party size, destination only live in raw history + summary (lossy). PR #84 patched this with a "never guess dates" prompt | **The largest pillar-1 gap** — needs structured slot state |
| Summarizing long conversations | ✅ `summarizer.py`: threshold 20, keep_last 5, tool-pair-safe split | No meaningful gap here (moving slots into state removes the risk of summary dropping facts) |
| Checkpointer + memory store | ✅ `AsyncPostgresSaver` + store in lifespan | — |
| Intent inference | Only scattered prompt-level rules | Needs a systematic guardrail + slots as the foundation |
| Multi-intent routing | ❌ Supervisor is **single-hop**, structured output has 1 `target_agent`; multi-intent is blocked by a prompt rule "pick one" | Needs a secondary intent + dispatch |
| Asking only for the missing field | Prompt-driven, no way to know exactly which field is already known | Slots enable "ask only missing" |
| Answers with a reason attached | No rule for this | Prompt (communication_style) |
| Proactive suggestions | ✅ MIN-55 but a **static map** keyed on `current_flow` | Needs a state-aware, personalized rule engine |
| Ranking by preference | ❌ Tools return results in the service's default sort | Needs a deterministic re-rank inside the tool |
| Measurable eval | ✅ DeepEval harness (MIN-58) but **single-turn only** | Needs multi-turn `run_case` + 2 new metrics |

## 2. Research — running the decision tree per information type

Per [Choosing the Right AI Agent Memory Strategy — A Decision Tree Approach](https://machinelearningmastery.com/choosing-the-right-ai-agent-memory-strategy-a-decision-tree-approach/)
(4 memory types: working / semantic / episodic / procedural; 5 questions: persist past the
turn? → past the session? → fact or event? → what retrieval shape? → is there a learned
procedure?), run the tree **separately for each kind of information** the travel assistant
handles:

| Information type | Persists? | Across sessions? | Fact/Event | Memory type | In the repo |
|---|---|---|---|---|---|
| Slots for the trip being discussed (dates, destination, party size, budget) | past the turn | **no** (scoped to the conversation) | transient fact | **Working memory** → a `TravelAgentState` field, checkpointer-persisted per thread | **NEW** (`trip_facts`) |
| Durable preferences (cabin class, hotel type, airline, budget band) | yes | **yes** | stable fact | **Semantic** → store `prefs` namespace | Already exists; **injection widened** |
| Profile (name/gender/travel_group) | yes | yes | stable fact | Semantic (keyed read, not vector) | Already exists (MIN-53) |
| Standing instructions ("always reply in Vietnamese") | yes | yes | stable fact | **Procedural** → `procedural` namespace, injected every turn | Already exists (P1) |
| Past trips + outcome | yes | yes | **event** | **Episodic** → `episodes` namespace + `recall_past_trips` | Already exists (P2) |
| Agent's learned workflow | — | — | — | Procedural (prompt-rewriting) | **Out of scope** — not needed yet |

Retrieval policy (tree question 4 + LangMem/Mem0 research): profile + prefs is a **small,
bounded** store → **full-read & inject** every turn beats vector search (no embedding cost,
no recall-miss, deterministic). `store.search()` semantic lookup stays reserved for episodes
(already the case). This follows the principle "memory is one source of context competing
for the context window — only retrieve when it improves the answer."

### Primary references

- LangGraph long-term memory / LangMem (hot-path vs background writes): [docs.langchain.com/oss/python/langchain/long-term-memory](https://docs.langchain.com/oss/python/langchain/long-term-memory), [langchain-ai.github.io/langmem](https://langchain-ai.github.io/langmem/)
- Mem0 (single-pass extraction, ADD/UPDATE/DELETE conflict ops, hybrid retrieval): [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- MemGPT/Letta (core-memory always-in-context + archival cold storage): [leoniemonigatti.com/blog/memgpt](https://www.leoniemonigatti.com/blog/memgpt.html)
- Generative Agents (importance tagging at write time), MemoryBank (Ebbinghaus decay), A-MEM ([arxiv 2502.12110](https://arxiv.org/abs/2502.12110)), HippoRAG ([arxiv 2405.14831](https://arxiv.org/abs/2405.14831)), survey "Memory in the Age of AI Agents" ([arxiv 2512.13564](https://arxiv.org/pdf/2512.13564))
- Entity/slot tracking: state-schema fields for the current thread, store for cross-thread facts — never put per-turn slots in BaseStore

## 3. Option selection (options → decision)

### 3.1 Memory framework: build on existing vs adopt a library

| Option | Pros | Cons | Decision |
|---|---|---|---|
| **A. Keep building on the existing BaseStore + state** | Reuses everything already shipped in P1/P2; zero new dependency; FakeLLM-testable | Have to own dedup/conflict handling ourselves (kept minimal) | ✅ **CHOSEN** |
| B. Adopt Mem0 | Battle-tested conflict-resolution + dedup (LoCoMo 92.5) | A second memory system running alongside the checkpointer/store; external service; overkill for a mock backend | ❌ |
| C. Adopt the LangMem SDK | Official LangChain project | Pre-1.0 (0.0.30), slow release cadence; what we actually need (profile, background extraction) already has an equivalent in the repo | ❌ |
| D. Letta/MemGPT | Interesting paged-memory model | Commercial runtime, replaces the whole agent architecture | ❌ |

### 3.2 Entity/slot extraction: where should it live?

| Option | Pros | Cons | Decision |
|---|---|---|---|
| A. A dedicated extraction node every turn | Clean separation | +1 LLM call per turn (latency + cost) | ❌ |
| **B. Fold into the supervisor's structured output** | **Zero extra LLM calls** — the supervisor already calls `with_structured_output`; it already sees the full context | Supervisor schema grows → routing-quality risk (mitigated: fields are optional + routing eval already exists) | ✅ **CHOSEN** |
| C. A `record_trip_facts` tool for the sub-agent | Agent acts on its own initiative | LLM-discretionary — exactly the gap P1 already had to fix | ❌ |

Following the repo's `llm-parses-code-computes` critical pattern: the supervisor only
returns **raw text** for a slot (e.g. "next week", "8/15"); **code** normalizes it (dates via
`core/dates`, numbers via an int cast). The LLM is never allowed to compute the ISO date
itself.

### 3.3 Multi-intent routing

| Option | Pros | Cons | Decision |
|---|---|---|---|
| A. Sub-agent → supervisor re-entry (a full loop) | Generalizes to N intents | Loop isn't clearly bounded; +1 supervisor LLM call per hop | ❌ |
| **B. Supervisor returns a `secondary_agent` (max 2 intents/turn) + a `dispatch_next` node** | Bounded, deterministic, zero extra LLM calls; reflection still reviews the final answer | Only 2 intents per turn (enough for "hotel + flight") | ✅ **CHOSEN** |
| C. Handoff tools between sub-agents | Standard swarm pattern | Large topology change, hard to test, out of scope | ❌ |

### 3.4 Suggestions: rule engine vs LLM-generated

| Option | Pros | Cons | Decision |
|---|---|---|---|
| **A. State-aware rule engine over an expanded catalog of keys** | Deterministic, testable, keeps the FE contract (i18n key) unchanged, zero latency | Less "creative" than an LLM | ✅ **CHOSEN** (v1) |
| B. LLM generates free-text suggestions | Flexible | Breaks the FE contract (loses the i18n key), +1 LLM call, hard to eval reliably | ❌ (noted as a possible next step if the rule engine hits its ceiling) |

### 3.5 Ranking results by preference

Chose a **deterministic re-rank inside the tool** (stable-sort boost by preference match)
before building the summary + `panel_result` — preserves the mock backend's determinism,
stays testable, and adds no LLM call. LLM-based re-ranking was rejected (cost/latency, and
it would break determinism).

## 4. Overall architecture (after the change)

```
POST /agent/chat|stream
 → AgentContext (tier, tz, allow_*)
 → graph:
    load_context ── trip_context + instructions + profile
    │                + preferences (NEW: full-read prefs → inject)
    summarize ────── unchanged (slots now live safely in state)
    supervisor ───── SupervisorIntent{target, SECONDARY?, SLOTS raw}   (NEW)
    │                code normalizes slots → state.trip_facts (merge reducer)
    ▼
    sub-agent ────── system msg = base + profile + preferences + instructions
    │                + trip_facts ("Known trip facts — do NOT re-ask") + summary
    │                tools: re-rank hotels/flights by preferences (NEW)
    ▼
    dispatch_next ── pending intent left? → next sub-agent : reflection   (NEW)
    ▼
    reflection ───── unchanged → END
 → suggestions_for_flow(flow, trip_facts, profile, preferences)  (NEW: rule engine)
 → BACKGROUND: run_memory_extraction (adds updated_at + canonical keys)  (hardened)
```

**Key point:** every change lands on an existing seam — `system_with_summary` (injection),
`SupervisorIntent` (structured output), the static sub-agent→reflection edge (dispatch),
`suggestions_for_flow` (2 call sites), `content_and_artifact` tools (re-rank).

## 5. Phased delivery & mapping to Acceptance Criteria

| Phase | Content | Ticket AC |
|---|---|---|
| **P0 — Eval first** | Multi-turn `run_case`, `memory.json` + `suggestions.json` datasets, `memory_recall` + `suggestion_relevance` metrics, run the **baseline** | "add metrics before implementing" |
| **P1 — Memory** | `trip_facts` state + supervisor slot extraction + preference auto-injection + store hygiene (updated_at, canonical keys) | "don't repeat information within a session"; "prefs remembered across sessions" |
| **P2 — Reasoning** | `secondary_agent` + `dispatch_next` (multi-intent); prompt guardrails: intent inference, ask-only-missing, default-with-confirm | multi-intent routing; asking only for the missing field |
| **P3 — Suggestions** | Rule engine + expanded catalog + FE i18n keys; preference re-rank in hotel/flight tools; communication_style "reason with every recommendation" | "≥80% of replies carry a suggestion"; ranking by preference; reasons attached |
| **P4 — Measurement** | Re-run eval vs baseline, record RESULTS | "measured with the existing eval" |

P1/P2/P3 can be split into 3 Linear sub-issues as the ticket itself suggests — PLAN.md's
waves are laid out to allow cutting at those exact phase boundaries.

## 6. Non-goals

- Not adopting Mem0 / LangMem / Letta; no graph-memory, no Ebbinghaus decay, no A-MEM.
- No LLM-generated free-text suggestions (keeps the i18n-key contract with the FE).
- Not upgrading the reflection rubric (that belongs to MIN-59).
- `booking` never becomes a secondary intent (the HITL interrupt is complex — booking is
  always a single, standalone intent).
- No memory for anonymous users (keeps the existing `user_id` gate).
- No change to the public `/agent/chat`, `/agent/stream` contract (the `ChatResponse.suggestions`
  shape is unchanged — still a list of keys).
