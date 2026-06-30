---
slug: agent-memory-layers
doc: design
lang: en
scope: P1 — background memory extraction + procedural memory injection
created: 2026-06-30
status: proposed
note: English is the source of truth; Vietnamese mirror lives in design.vi.md.
---

# P1 Design — Background extraction + Procedural memory

Closes two gaps vs the LangChain memory framework (see `research.md`):

1. **Background writes** — stop relying on the LLM choosing to call
   `save_user_preference`. A dedicated post-turn step mines the latest exchange.
2. **Procedural memory** — per-user standing instructions, persisted cross-thread
   and folded into the system prompt every turn via the existing
   `system_with_summary` path.

Non-goals (deferred): episodic memory, structured-namespace migration, RAG
per-user scoping, LangSmith trace loop.

## Architecture

```
START → load_context → summarize → supervisor → <sub-agent> → reflection
          │  (NEW: also loads procedural                          │
          │   instructions from store)                            │ accept / END
          ▼                                                       ▼
   state.instructions ──fold──► system_with_summary        extract_memory  (NEW)
                                                                   │ best-effort write
                                                                   ▼
                                                                  END
```

- **Read path (procedural):** `load_context` gains `runtime.store`, reads
  `get_instructions(store, user_id)`, writes `state["instructions"]`.
  `system_with_summary` folds it into the single leading system message.
- **Write path (background):** a new terminal `extract_memory` node runs after the
  answer (reflection's accept/END paths route here). It uses the **fast LLM** to
  extract durable prefs + standing instructions from the last exchange and upserts
  them to the store. Best-effort; gated off for FAST mode.

## Key decisions

### D1 — Where extraction runs: in-graph terminal node (not async fire-and-forget)

Chosen: an in-graph `extract_memory` node before `END`.

- **Testable + checkpointer-consistent**; mirrors the existing `summarize` node.
- **Perceived latency ≈ 0 for streaming**: the sub-agent already streamed its
  answer tokens before reflection/extract run, so the user sees the reply first;
  only the "turn complete" signal is delayed by one fast-LLM call.
- **Gated**: skips entirely when `allow_memory_write` is false (FAST mode → zero
  cost), and is **best-effort** (any error is swallowed, never breaks the turn).
- Rejected: async fire-and-forget in the router/stream endpoint — lower latency
  but lives outside the graph, needs a separate store handle, isn't checkpointed,
  and is harder to test. Documented as a future optimization if latency bites.

### D2 — Extraction is a pure function + thin node wrapper (mirrors summarizer)

- `memory/extractor.py`: pure `extract_memories(messages, llm) -> ExtractedMemories`.
  Sends `[SystemMessage(prompt), HumanMessage(last_exchange)]`, parses a small JSON
  object from the reply, returns a typed result. **Defensive parse**: any
  JSON/shape error → empty result (write nothing). Unit-testable without a graph.
- `make_extract_memory_node(llm)` in `agents/nodes.py`: reads
  `runtime.context.allow_memory_write` (skip if false), calls `extract_memories`,
  upserts results to `runtime.store`, returns `{}` (no state change).

Output shape:

```json
{
  "preferences": [{"key": "diet", "text": "vegetarian"}],
  "instructions": [{"key": "language", "text": "always reply in Vietnamese"}]
}
```

`preferences` → `prefs` namespace (existing); `instructions` → `procedural`
namespace (new). Only the **last user + assistant turn** is inspected, keeping the
prompt small and avoiding re-extracting old history.

### D3 — Store: generalize namespace, add procedural helpers (back-compat)

`memory/store.py`:

- `_namespace(user_id, kind)` → `("users", user_id, kind)`; keep `_prefs_namespace`
  delegating to it so existing prefs entries are unchanged.
- Add `upsert_instruction(store, user_id, key, value: dict)` and
  `get_instructions(store, user_id, *, query=None, limit=10) -> list[dict]` for the
  `"procedural"` kind. Values stay `{"text": ...}` so the semantic index keeps
  working. Existing `upsert_preference` / `search_preferences` untouched.

### D4 — Procedural injection via existing `system_with_summary`

- `agents/state.py`: add `instructions: str` to `TravelAgentState`;
  `system_with_summary` folds it **before** the summary:
  `"Standing traveller instructions:\n{instructions}"`. Returns `base` unchanged
  when all three fields are empty (no behavior change for new users).
- `agents/nodes.py`: `load_context_node(state, runtime)` (add `runtime` param so
  LangGraph injects it) reads `runtime.store`, calls `get_instructions`, joins the
  texts, returns `{"instructions": ...}`. Best-effort; missing store / no user →
  `{}`.

### D5 — Context gate: `allow_memory_write`

`agents/context.py`:

- Add `allow_memory_write: bool = True` to `AgentContext`.
- `_MODE_POLICY`: FAST → `False`; BALANCED / DEEP → `True`.
- `resolve_agent_context` passes it through. **Not tier-gated** — memory is a cheap
  UX differentiator; free users keep it. (Product call: confirm before D.1-style
  wiring; default keeps it on.)

### D6 — Graph wiring (contained)

`agents/graph.py`:

- Add `extract_memory` node: `make_extract_memory_node(pick("extract_memory"))`,
  fast tier, static edge `extract_memory → END`.
- `agents/nodes.py` reflection: the two `Command(goto=END)` (accept + no-revision)
  become `Command(goto="extract_memory")`. The REVISE loop-back is unchanged.
  `plan` cancellation keeps `goto=END` (nothing to extract on cancel).

### D7 — Prompt

- `prompts/memory_extraction/v1.md` — instruct the model to emit the JSON shape,
  extract only **durable** signals (stable preferences, standing instructions),
  ignore one-off trip detail, and return empty arrays when nothing qualifies.
- `prompts/active.yaml` — add `memory_extraction: 1`.

## Risks & mitigations

- **Latency** — one extra fast-LLM call per non-FAST turn. Mitigated by streaming
  (answer already shown) + FAST-mode skip. If still a problem → move to async (D1
  rejected option).
- **Bad extractions polluting memory** — defensive JSON parse + "durable only"
  prompt + `key`-addressed upsert (overwrite, not append) bound the blast radius.
- **Provider-agnostic / tests** — `extract_memories` is pure and FakeLLM-driven;
  a fake returning canned JSON proves writes, a fake returning empty proves the
  no-op path.

## Test matrix (proof)

| Behavior | Check |
|---|---|
| store: instruction upsert + recall | `tests/memory/test_store_instructions.py` |
| extractor: valid JSON → typed result | `tests/memory/test_extractor.py` (FakeLLM) |
| extractor: garbage/empty → empty result (no raise) | same |
| node: writes prefs + instructions to store | `tests/agents/test_memory_extraction.py` |
| node: `allow_memory_write=False` → no LLM call, no write | same |
| injection: instructions in store → appear in system prompt | `tests/agents/test_procedural_injection.py` |
| context: FAST → `allow_memory_write=False`; BALANCED/DEEP → True | `tests/agents/test_context_*.py` |
