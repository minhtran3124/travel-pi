---
slug: agent-memory-layers
doc: design
lang: en
scope: P2 — episodic memory (past-trip examples) + structured namespaces
created: 2026-06-30
status: proposed
depends_on: P1 (design.md) — reuses `_namespace`, the `extract_memory` node, and `allow_memory_write`
note: English is the source of truth. P2 is sequenced AFTER P1.
---

# P2 Design — Episodic memory + structured namespaces

Adds the third long-term memory type from the LangChain framework (see
`research.md`): **episodic** — *what the agent has experienced* (past planning
interactions, examples, outcomes). The planner recalls similar past trips to
produce better, more personalised plans ("last time you preferred X").

Builds directly on P1's foundation:

- `_namespace(user_id, kind)` already exists (P1 D3) → add the `"episodes"` kind.
- The `extract_memory` node already runs at turn end with `runtime.store` + state
  (P1 D1/D6) → extend it to also write an episode after a planning turn.
- `allow_memory_write` already gates writes (P1 D5) → reuse for episode writes.

Non-goals (deferred): explicit user ratings/feedback capture, automatic outcome
backfill from bookings beyond approval, cross-user "popular trips" recall,
LangSmith trace loop.

## Architecture

```
WRITE (extend P1 node):
  ... → reflection → extract_memory ─┬─ prefs / instructions   (P1)
                                     └─ episode (if flow was   (P2 NEW)
                                        planner/booking)
                                          │ upsert to ("users", uid, "episodes")
                                          ▼  keyed by trip_id (overwrite on re-plan)
                                         END

READ (planner recall):
  supervisor → planner.assistant
                  │ calls recall_past_trips(query)        (P2 NEW tool)
                  ▼ store.search(("users", uid, "episodes"), query) → top-K
            few-shot examples fold into the answer
```

- **Write path:** the existing `extract_memory` node, when the turn's
  `current_flow` was a trip-shaped flow (`planner` / `booking`), additionally
  produces a compact **episode summary** and upserts it to the `episodes`
  namespace. Best-effort, gated by `allow_memory_write`.
- **Read path:** a new tool `recall_past_trips(query)` (mirrors
  `get_user_preferences`) bound to the planner. The LLM calls it before planning;
  it semantically searches the user's episodes and returns the closest matches as
  few-shot context.

## What is an "episode"? (E1)

An episode = a compact, durable record of one *completed planning interaction*:

```json
{
  "text": "Planned a 3-day Da Nang beach trip for a mid-range budget; traveller chose the beachfront hotel and a slow-paced itinerary.",
  "trip_id": "trip_abc",
  "city": "Da Nang",
  "outcome": "approved"
}
```

- `text` — the embedded field (semantic retrieval); a 1–2 sentence summary of the
  request + what was planned + how it landed.
- `trip_id`, `city` — metadata for keying + optional filtering.
- `outcome` — `"approved"` (plan accepted at the HITL gate), `"proposed"` (planned
  but not yet accepted), or `"booked"`. Conveys signal strength.

Episodes are **examples + outcomes**, not raw transcripts. Only durable,
trip-level signal is kept (the same "not every trace is memory" principle as P1).

## Key decisions

### E2 — When/where episodes are written

Reuse the P1 `extract_memory` node; **do not** add a separate node.

- After a turn whose `state["current_flow"]` ∈ {`planner`, `booking`}, the
  extraction step also asks the fast LLM for an `episode` summary (one extra field
  in the same JSON it already returns — no extra LLM call).
- Keyed by `trip_id` when present, else a stable derived key. Re-planning the same
  trip **overwrites** its episode (latest state wins) rather than appending — keeps
  the namespace bounded.
- `outcome` is set from context: the `plan` HITL approval path (P1 leaves it
  `goto=END` on cancel) marks `"approved"`; a plain planner turn marks
  `"proposed"`. **Open item:** wiring `"booked"` requires the booking sub-agent to
  signal success — proposed as a follow-up, not blocking P2 v1.

Rationale: one write site, consistent with P1, no new latency (same LLM call), and
the node already has `runtime.store` + `user_id` + `current_flow` + `trip_id`.

### E3 — Store schema: `episodes` namespace + helpers

`memory/store.py` (extends P1's `_namespace`):

- `upsert_episode(store, user_id, key, value: dict)` → `_namespace(uid, "episodes")`.
  `value` carries `text` (+ `trip_id`/`city`/`outcome`); `text` is what the index
  embeds, so semantic search works out of the box. Naming follows P1's
  `upsert_preference`/`upsert_instruction` convention.
- `search_episodes(store, user_id, *, query=None, limit=3) -> list[dict]` — semantic
  when a query is given, else recency. Default `limit=3` to keep few-shot small.
  Naming follows P1's `search_preferences` convention.
- Key choice: `trip_id` if available, else a content-derived slug. Overwrite, not
  append.

"Structured namespaces" (research P2 row 2) is **mostly already delivered by P1's
`_namespace`** — P2 just adds the `episodes` kind. No data migration needed; prefs
keep their existing namespace.

### E4 — How episodes are retrieved: a recall tool on the planner

Chosen: a tool `recall_past_trips(query)` (in `tools/memory_tools.py`), bound to
the planner via `TOOLS_BY_DOMAIN["planner"]`.

```python
@tool
def recall_past_trips(
    query: str,
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
) -> list:
    """Recall the traveller's similar past trips to inform a new plan."""
    return search_episodes(store, user_id, query=query)
```

- Mirrors `get_user_preferences` exactly — same injection pattern, same per-user
  isolation guarantee (`InjectedState("user_id")` → the LLM can never address
  another traveller's episodes).
- The planner prompt gains a "recall first" line + the E5 "adapt, don't repeat"
  framing: *"Before drafting a plan, call `recall_past_trips` to check the
  traveller's history and reuse what worked — treat the results as prior examples
  to adapt (pace, budget, area), not facts to repeat; do not assume the same dates
  or city. Skip if it returns nothing."*

Rejected for v1: **auto-injecting** episodes into the planner system prompt every
turn (like P1's procedural injection). It is deterministic but spends tokens on
every planner turn even when irrelevant, and needs a planner-specific load step.
Documented as an upgrade if the LLM under-uses the tool. (The recall tool is the
lighter, more surgical first step.)

### E5 — Few-shot formatting

The tool returns a list of episode dicts; the planner prompt instructs the model to
treat them as **prior examples to adapt, not facts to repeat** — e.g. "reuse the
pacing/budget the traveller liked; do not assume the same dates or city." This
keeps recall as guidance, avoiding stale plans being parroted back.

### E6 — Prompt updates

- `prompts/planner/v3.md` (new version, keep v1 + v2) — add the "recall first"
  guidance + how to use the examples (E5). Flip `active.yaml` `planner: 3`.
- `prompts/memory_extraction/v2.md` (extends P1's v1) — when the flow is
  trip-shaped, also emit an `episode` object. Flip `active.yaml`
  `memory_extraction: 2`.

### E7 — Gating & cost

- **Writes** reuse `allow_memory_write` (FAST off, BALANCED/DEEP on) — no extra LLM
  call (episode rides the existing extraction JSON).
- **Reads** are cheap: `store.search` only (one embedding of the query, no LLM).
- **Tier-gating recall via `allow_episodic` flag (default `True`).** Product
  decision (resolved): episodic recall stays **on for everyone in P2 v1**, mirroring
  P1's memory policy (P1 D5: "memory is a cheap UX differentiator") rather than RAG.
  An `allow_episodic: bool = True` flag is added to `AgentContext` now (with a
  `True` default in all three mode policies) so the gate exists and is testable;
  flipping free→`False` later is a one-line policy change with no rewiring.
  Mechanically: filter `recall_past_trips` out of the planner's `active_tools` when
  `allow_episodic` is false, reusing the `_base.py` RAG-filter pattern
  (`t.name == EPISODIC_TOOL_NAME`).

## Risks & mitigations

- **Episode bloat** — key by `trip_id` + overwrite, low `limit=3` recall → bounded
  namespace and prompt size.
- **Cold start** (new user, no episodes) — recall returns `[]`; planner proceeds
  exactly as today. No special-casing needed.
- **Unknown outcome** — store as `"proposed"`; the value is still useful as an
  example. `"booked"` backfill is a documented follow-up.
- **Stale plans parroted** — E5 prompt framing ("adapt, don't repeat") + semantic
  (not exact) recall.
- **Cross-user leakage** — same `InjectedState("user_id")` isolation as P1; the LLM
  never supplies the namespace.

## Test matrix (proof)

| Behavior | Check |
|---|---|
| store: episode record + recall (semantic) | `tests/memory/test_store_episodes.py` |
| store: re-record same `trip_id` overwrites | same |
| extractor: trip-shaped flow → emits `episode`; non-trip flow → none | `tests/memory/test_extractor_episode.py` (FakeLLM) |
| node: writes episode to `episodes` namespace, keyed by trip_id | `tests/agents/test_episode_write.py` |
| tool: `recall_past_trips` returns the user's episodes only (isolation) | `tests/tools/test_recall_past_trips.py` |
| planner: calls recall and incorporates it | `tests/agents/test_planner_recall.py` (FakeLLM) |
| cold start: no episodes → empty, no error | covered in tool + planner tests |
| gating: `allow_episodic=False` → recall tool filtered out | `tests/agents/test_episodic_gating.py` |

## Dependency note

P2 **must follow P1** — it reuses `_namespace`, the `extract_memory` node, and
`allow_memory_write`. A `PLAN-P2.md` (XML tasks) is drafted only after P1 ships, so
the wiring targets the real post-P1 code rather than a moving target.
