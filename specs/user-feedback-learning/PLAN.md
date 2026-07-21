---
slug: user-feedback-learning
status: shipped
owner: Minh Tran
created: 2026-07-21
---

# Deep Research — Learning from User Feedback

## 1. Motivation

Clarify how user feedback should become memory in the travel agent, specifically whether
learning should be a supervisor-routed specialist and which component decides what is safe and
useful to retain.

## 2. Non-goals

- No runtime code, database schema, API contract, or prompt change.
- No automatic prompt rewrite, model fine-tuning, or production rollout.
- No adoption of LangMem as a new dependency; it is used only as an architectural reference.

## 3. Success Criteria

- Describe the current implementation from graph entry through background memory write and recall.
- Separate per-user memory, product-level improvement, and model-weight training.
- Compare supervisor-routed, in-graph, hot-path, and background approaches.
- Define a concrete write policy, target flow, risks, evaluation gates, and phased roadmap.
- Support conclusions with current code references and primary/official sources.

## 4. Tasks

### Task 1.1 — Map the current graph and memory lifecycle

- **Files:** `apps/api/app/agents/graph.py`, `apps/api/app/agents/nodes.py`, `apps/api/app/routers/agent.py`, `apps/api/app/memory/`, `apps/api/app/prompts/memory_extraction/`
- **Action:** Trace the runtime topology, background task scheduling, extraction policy, store namespaces, and recall path from implementation and tests.
- **Verify:** `rg -n "run_memory_extraction|extract_memory_llm|load_context_node|MemoryKind" apps/api/app apps/api/tests`
- **Done:** The research distinguishes current code from stale architecture documentation.

### Task 2.1 — Research current memory and feedback patterns

- **Files:** `specs/user-feedback-learning/RESEARCH.md`
- **Action:** Review official LangGraph, LangMem, LangSmith, and OpenAI memory guidance for long-term memory, hot-path/background writes, feedback-driven prompt optimization, evaluation, and user controls.
- **Verify:** `rg -n "docs.langchain.com|langchain-ai.github.io|help.openai.com" specs/user-feedback-learning/RESEARCH.md`
- **Done:** Every material external claim has a direct primary or official source.

### Task 3.1 — Select the travel-pi target architecture

- **Files:** `specs/user-feedback-learning/RESEARCH.md`
- **Action:** Compare architecture options and specify ownership, event/candidate records, promotion rules, conflicts, privacy controls, and the online/offline split.
- **Verify:** `rg -n "Decision|Write policy|Target architecture|FeedbackEvent|MemoryCandidate|Offline" specs/user-feedback-learning/RESEARCH.md`
- **Done:** The answer explicitly states whether the supervisor routes to a memory agent and who decides what is learned.

### Task 4.1 — Record evidence and handoff

- **Files:** `specs/user-feedback-learning/SUMMARY.md`
- **Action:** Record scope, rationale, alternatives, verification evidence, and implementation boundaries.
- **Verify:** `git diff --check -- specs/user-feedback-learning`
- **Done:** Research is reviewable and implementation can be planned separately without reopening the core architecture question.

## 5. Risks

- Existing documents describe both the old terminal-node design and the newer background design;
  the research must treat current code as authoritative.
- “Learn” is ambiguous between personalization, system improvement, and weight training; collapsing
  them would produce an unsafe architecture.
- Implicit feedback is weak evidence; treating clicks or silence as durable preference can create
  false memories.

## 6. Status Log

- 2026-07-21 — Research completed against current code and official sources; recommendation and
  rollout recorded in `RESEARCH.md`.
