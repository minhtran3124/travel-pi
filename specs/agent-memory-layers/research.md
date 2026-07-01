---
slug: agent-memory-layers
doc: research
source: https://www.langchain.com/blog/how-to-give-your-agent-memory
created: 2026-06-30
---

# Agent Memory — LangChain framework vs travel-pi codebase

Comparison of LangChain's "How to give your agent memory" framework against the
current travel agent implementation, with what we can apply, what we cannot, and
how to improve. Drives the P1 design (`design.md`) + plan (`PLAN.md`).

## 1. What the article proposes

The post is a **conceptual framework + product loop**, not a code guide.

**Memory taxonomy**

- **Short-term** — context for the task in front of the agent: current thread,
  recent messages, tool results, intermediate reasoning.
- **Long-term** — context that persists beyond the current run, split into three
  cognitive types:
  - **Semantic** — *what the agent knows*: facts, preferences, general knowledge.
  - **Episodic** — *what the agent has experienced*: past interactions, examples,
    actions, outcomes.
  - **Procedural** — *how the agent should behave*: instructions, workflows,
    policies, skills.

**Three-part loop** (the productised part, built on LangSmith)

1. **Capture traces** (LangSmith Observability) — input, model calls, tool I/O,
   retrieved docs, routing decisions, latency, errors, user feedback.
2. **Analyze traces** (LangSmith Engine) — find patterns, diagnose root cause,
   surface the concrete change needed.
3. **Update memory** (LangSmith Context Hub) — a *versioned* store of durable
   context (instructions, tools, skills), not ad-hoc prompt edits.

**Principles**

- Not every trace becomes memory — most stays history; some becomes dataset
  examples, evals, code changes, or tool-schema fixes.
- Memory needs a **refresh path** so future runs load the update (avoid stale
  cached prompts/tools).
- **Protect behavior with evals** — if a memory update matters, have a way to
  detect when that behavior regresses.

## 2. What the codebase has today

Foundation already matches the standard LangGraph pattern the article implies.

| Layer | Abstraction | Backend | Scope | Write timing | Article type |
|---|---|---|---|---|---|
| Checkpointer | `AsyncPostgresSaver` (`agents/checkpointer.py`) | Postgres / `MemorySaver` | thread (per conversation) | after every node | **Short-term** |
| Store | `PostgresStore`+pgvector (`memory/store.py`) | Postgres / `InMemoryStore` | cross-thread (per user) | hot-path via tool | **Semantic** (prefs only) |
| Summarizer | `RemoveMessage` reducer (`memory/summarizer.py`) | in state field | thread | `summarize` node | short-term compression |
| RAG | `VectorStore` (`rag/retriever.py`) | pgvector | **global** (not per-user) | seed time | knowledge base (not memory) |
| `AgentContext` | dataclass (`agents/context.py`) | per-request | ephemeral | — | config (not persisted) |

Key facts:

- Long-term writes are **100% hot-path**: only the **journal** sub-agent has
  `save_user_preference` (`tools/memory_tools.py`), and only if the LLM chooses to
  call it. Easy to miss.
- Store values are `{"text": ...}` under one namespace `("users", uid, "prefs")`,
  semantically indexed (`_index_config()`), shared embeddings with RAG.
- Procedural injection scaffolding already exists: `system_with_summary()`
  (`agents/state.py:29`) folds `trip_context` + `summary` into one leading system
  message. Adding a "learned instructions" fragment is a natural extension.

## 3. Apply / cannot apply / improve

### Can apply (foundation is ready, low cost)

- **Procedural memory** — currently absent (RAG is *global static* knowledge, not
  per-user learned behavior). Reuse the `system_with_summary` injection path +
  store. **(P1)**
- **Background writes** — replace "LLM remembers if it remembers to call the tool"
  with a dedicated post-turn extraction step decoupled from answer generation.
  **(P1)**
- **Episodic memory** — new namespace `("users", uid, "episodes")` storing past
  trip outcomes / examples, retrieved as few-shot. `BaseStore`+index already
  supports it. **(P2)**
- **"Not every trace is memory"** — an extraction policy that keeps only durable
  signals (stable prefs, standing instructions) and drops one-off detail. **(P1)**
- **Evals against regression** — `FakeLLM`-based tests asserting memory writes +
  injection behavior; no SaaS needed. **(P1/P3)**

### Cannot apply / should not

- **LangSmith Observability / Engine / Context Hub** — a commercial SaaS loop.
  This repo is deliberately **provider-agnostic** (`init_chat_model`, `FakeLLM`
  in tests, no network). Adopting the full LangSmith stack contradicts the
  architecture and is overkill for a mock backend. We build a lightweight
  equivalent instead (in-graph extraction + store + tests).
- **Automated trace→analyze→update loop** — needs observability + eval pipeline
  infra not present. Not worth it for a mock backend yet; revisit if real traffic
  + LangSmith are adopted later.

### Improvement roadmap

| Priority | Item | Files | Why |
|---|---|---|---|
| **P1** | Background memory extraction node (fast LLM, best-effort, gated) | `agents/nodes.py`, `agents/graph.py`, `memory/extractor.py` | Closes biggest gap: only journal writes today |
| **P1** | Per-user procedural instructions: store + fold into `system_with_summary` | `memory/store.py`, `agents/state.py`, `agents/nodes.py` | Reuses existing injection, ~0 cost |
| **P2** | Episodic namespace + few-shot retrieval tool for planner | `memory/store.py`, `tools/memory_tools.py` | "Last time you preferred X" → better plans |
| **P2** | Structured namespaces (`prefs` / `procedural` / `episodes`) | `memory/store.py` | Clear multi-tenant separation, typed search |
| **P3** | Eval tests protecting memory behavior on `FakeLLM` | `tests/` | Mirrors article's "protect with evals" without SaaS |

**Recommendation:** ship **P1 first** (background extraction + procedural
injection) — it touches files that already carry the relevant pattern, delivers
value immediately, and does not alter the core architecture. P2 (episodic) is the
natural follow-up.
