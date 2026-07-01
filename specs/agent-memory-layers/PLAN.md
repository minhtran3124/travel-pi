---
slug: agent-memory-layers
status: proposed
owner: Minh Tran
created: 2026-06-30
---

# Agent Memory Layers — P1: Background extraction + Procedural memory

Implements P1 from `research.md` per the design in `design.md`. Adds (a) a
post-turn background memory-extraction node and (b) per-user procedural-memory
injection, reusing the existing `BaseStore` + `system_with_summary` paths.

## 1. Motivation

Today long-term writes are 100% hot-path — only the journal sub-agent's
`save_user_preference` tool, and only when the LLM chooses to call it. There is no
procedural memory (per-user standing instructions). This closes both gaps without
touching the core architecture.

## 2. Non-goals

- Episodic memory (P2), structured-namespace migration (P2), RAG per-user scoping.
- LangSmith trace/observability loop (commercial SaaS; conflicts with the
  provider-agnostic design).
- Async fire-and-forget extraction (documented fallback if latency bites).

## 3. Success criteria

- A non-FAST turn writes durable preferences + standing instructions to the store
  without the LLM having to call a tool.
- Stored instructions are folded into the leading system message on every later
  turn for that user.
- FAST mode performs zero extra LLM calls (gated off).
- New users see no behavior change (all-empty fields → base prompt unchanged).
- Best-effort: any extraction/store error never breaks the turn.
- All new tests pass on `FakeLLM` (no network).

## 4. Tasks

### Task 1.1 — Store: procedural namespace + helpers

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/memory/store.py, apps/api/tests/memory/test_store_instructions.py</files>
  <action>Add `_namespace(user_id, kind) -> ("users", user_id, kind)` and make `_prefs_namespace` delegate to it. Add `upsert_instruction(store, user_id, key, value: dict)` and `get_instructions(store, user_id, *, query=None, limit=10) -> list[dict]` for the "procedural" kind, mirroring the existing prefs helpers (value keeps the `{"text": ...}` shape so the semantic index works). Do NOT change `upsert_preference` / `search_preferences` behavior. Test: upsert two instructions, recall returns both; overwrite same key replaces.</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/memory/test_store_instructions.py -x</verify>
  <done>Instruction helpers persist + recall via an InMemoryStore; prefs helpers unchanged.</done>
</task>
```

### Task 1.2 — Context: `allow_memory_write` flag

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/agents/context.py, apps/api/tests/agents/test_context_memory_write.py</files>
  <action>Add `allow_memory_write: bool = True` to `AgentContext`. In `_MODE_POLICY` set FAST→False, BALANCED→True, DEEP→True. Thread it through `resolve_agent_context` (not tier-gated — free keeps it). Test: FAST resolves to False; BALANCED and DEEP resolve to True; default `AgentContext()` is True.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_context_memory_write.py -x</verify>
  <done>Flag present, mode policy correct, default preserves today's behavior.</done>
</task>
```

### Task 1.3 — State: `instructions` field + system-prompt fold

```xml
<task id="1.3" wave="1">
  <files>apps/api/app/agents/state.py, apps/api/tests/agents/test_state_system_prompt.py</files>
  <action>Add `instructions: str` to `TravelAgentState`. In `system_with_summary`, fold instructions in BEFORE summary as `"Standing traveller instructions:\n{instructions}"`; return `base` unchanged when trip_context, summary, AND instructions are all empty. Test: with only instructions set → system content includes them; with all empty → returns `base` unchanged; ordering is base, trip_context, instructions, summary.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_system_prompt.py -x</verify>
  <done>Instructions appear in the single leading SystemMessage; empty case is a no-op.</done>
</task>
```

### Task 1.4 — Extractor pure function + prompt

```xml
<task id="1.4" wave="1">
  <files>apps/api/app/memory/extractor.py, apps/api/app/prompts/memory_extraction/v1.md, apps/api/app/prompts/active.yaml, apps/api/tests/memory/test_extractor.py</files>
  <action>Create `extractor.py` with a typed result (e.g. a dataclass `ExtractedMemories(preferences: list[dict], instructions: list[dict])`) and pure `extract_memories(messages, llm) -> ExtractedMemories`: build `[SystemMessage(registry.get("memory_extraction")), HumanMessage(<last user+assistant exchange transcript>)]`, invoke llm, parse the JSON object from `.content` defensively (any JSON/shape/type error → empty result, never raises). Add `prompts/memory_extraction/v1.md` instructing the model to emit `{"preferences":[{"key","text"}],"instructions":[{"key","text"}]}`, extract ONLY durable signals (stable prefs, standing instructions), ignore one-off trip detail, and return empty arrays when nothing qualifies. Register `memory_extraction: 1` in `active.yaml`. Tests (FakeLLM): valid JSON → populated result; malformed/empty/non-JSON content → empty result with no exception.</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/memory/test_extractor.py -x</verify>
  <done>Pure extractor parses valid output and degrades to empty on bad output; prompt + active.yaml wired.</done>
</task>
```

### Task 2.1 — Graph wiring: load procedural + extract_memory node

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/nodes.py, apps/api/app/agents/graph.py, apps/api/tests/agents/test_memory_extraction.py, apps/api/tests/agents/test_procedural_injection.py</files>
  <action>nodes.py: (1) Give `load_context_node` a `runtime: Runtime[AgentContext]` param; best-effort read `runtime.store` + `state.get("user_id")`, call `get_instructions`, join texts, return `{"instructions": ...}` (merge with existing trip_context return; missing store/user → omit). (2) Add `make_extract_memory_node(llm)` returning a node `extract_memory(state, runtime)` that: returns `{}` if `runtime.context` exists and `allow_memory_write` is False; else best-effort calls `extract_memories(state["messages"], llm)`, upserts each preference via `upsert_preference` and each instruction via `upsert_instruction` to `runtime.store` for `state["user_id"]`; always returns `{}`; swallow + log any error. (3) In the reflection node, change the two `Command(goto=END)` (accept + no-revision) to `Command(goto="extract_memory")`; leave the REVISE loop-back and plan-cancel paths unchanged. graph.py: add node `extract_memory` = `make_extract_memory_node(pick("extract_memory"))`, add static edge `extract_memory -> END`; ensure reflection `destinations` includes "extract_memory". Tests (FakeLLM + InMemoryStore): turn with a fake extractor LLM writes prefs+instructions to store; `allow_memory_write=False` (FAST ctx) writes nothing; procedural test: seed an instruction in store, run a turn, assert the model received it in the system prompt.</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/agents/test_memory_extraction.py tests/agents/test_procedural_injection.py -x</verify>
  <done>Background node persists extracted memory (gated off for FAST); procedural instructions reach the system prompt on later turns; full agent suite green.</done>
</task>
```

## 5. Risks

- **Latency** — one extra fast-LLM call per non-FAST turn; mitigated by streaming
  (answer already shown) + FAST skip. Fallback: async extraction (design D1).
- **Memory pollution** — defensive parse + "durable only" prompt + key-addressed
  upsert (overwrite, not append).
- **Local `.env` OPENAI_API_KEY=test** breaks embedding-backed store tests; verify
  commands unset it so `get_embeddings()` uses the deterministic fake
  (see `env-openai-key-test-breaks-llm-tests`).

## 6. Waves

| Wave | Tasks | Parallelism | Files disjoint? |
|---|---|---|---|
| 1 | 1.1 store, 1.2 context, 1.3 state, 1.4 extractor+prompt | 4 parallel | store.py / context.py / state.py / extractor.py+prompts — yes |
| 2 | 2.1 nodes+graph wiring | single | nodes.py + graph.py coupled, run after wave 1 |

## 7. Status Log

- 2026-06-30 — Plan drafted (proposed). Awaiting review before execution.
