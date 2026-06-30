---
slug: agent-memory-layers
status: proposed
owner: Minh Tran
created: 2026-06-30
---

# Agent Memory Layers — P2: Episodic memory + planner few-shot retrieval

Implements the P2 row from `research.md` (Improvement roadmap) on top of the
shipped P1 background-extraction + procedural-injection work. Adds (a) a per-user
**episodic** memory namespace storing durable past-trip outcomes, written by the
existing P1 background `extract_memory` node, and (b) a `recall_past_trips`
few-shot retrieval tool bound to the **planner** sub-agent, so plans personalise
to "what worked for this traveller before". Reuses the existing `BaseStore` +
`_namespace(user_id, kind)` + `InjectedStore`/`InjectedState` patterns — no new
architecture.

## 1. Motivation

P1 closed the write gap for *traveller-level* durable signals (preferences +
standing instructions) and the *procedural* read path. What is still missing is
**episodic** memory: per-trip outcomes ("on the Tokyo trip you preferred a slow
pace and stayed in Shinjuku") retrieved as few-shot examples so the planner
doesn't plan every trip from scratch. The foundation is already in place — the
store already generalises to `("users", uid, kind)` and the background extractor
already runs once per non-FAST turn — so this is a low-cost, in-pattern
extension.

## 2. Non-goals

- Trip-lifecycle write triggers (e.g. capturing an episode only when a trip is
  marked "completed"). P2 writes opportunistically from the conversation via the
  background extractor, same as P1. A lifecycle hook is a future refinement.
- Cross-user episode sharing / collaborative filtering.
- Episodic retrieval for sub-agents other than the planner (concierge/budget
  later if useful).
- LangSmith trace/observability loop (still conflicts with provider-agnostic
  design — unchanged from P1).
- Episodic "decay" / TTL (keep it simple for P2; key-addressed upsert bounds
  growth to one episode per trip_id).
- `"booked"` outcome backfill from the booking sub-agent — needs a booking
  success signal not available in P2 v1. Episodes store `outcome="proposed"` for
  plain planner turns and `"approved"` after the HITL plan-approval gate; the
  `"booked"` upgrade is a documented follow-up.

**Scope note (closes research P2 row 2 — "structured namespaces"):** P1's
generalised `_namespace(user_id, kind)` already delivers the structured
`prefs`/`procedural`/`episodes` separation; P2 only adds the `"episodes"` kind.
No data migration; prefs/procedural keep their existing namespaces.

## 3. Success criteria

- A non-FAST turn that discusses/finalises a trip writes a durable **episode**
  to `("users", uid, "episodes")` via the background node — no extra LLM call
  beyond P1's single extraction call.
- The planner can call `recall_past_trips(query=...)` and receive its own past
  episodes ranked by semantic similarity, as few-shot context.
- Seeded episodes change the planner's system/tool context on a later turn
  (assertable on `FakeLLM`).
- FAST mode still performs zero extra LLM calls (the extractor is already gated
  by `allow_memory_write`; episodes ride the same gate).
- P1 behavior is unchanged for users with no episodes (empty namespace → tool
  returns `[]`; planner prompt v3 degrades gracefully).
- Best-effort: any episode extract/store/tool error never breaks the turn.
- All new tests pass on `FakeLLM` + `InMemoryStore` (no network).
- P1's shipped tests stay green (the extractor change is backward-compatible:
  a missing `episodes` key parses to an empty list).
## 4. Tasks

### Task 2.1 — Store: episodes namespace + helpers

```xml
<task id="2.1" wave="1">
  <files>apps/api/app/memory/store.py, apps/api/tests/memory/test_store_episodes.py</files>
  <action>Add `upsert_episode(store, user_id, key, value: dict)` and `search_episodes(store, user_id, *, query=None, limit=3) -> list[dict]` for the `"episodes"` kind, mirroring the existing prefs/instructions helpers (naming follows P1's `upsert_*`/`search_*` convention). Use `_namespace(user_id, "episodes")` (the generalised helper from P1). Values keep the RICH episode schema `{"text": ..., "trip_id": ..., "city": ..., "outcome": ...}`; the shared semantic index (`_index_config`) embeds the `text` field — the `text` is the one-sentence summary carrying city + durable outcome so retrieval is self-contained, while `trip_id`/`city`/`outcome` are stored metadata (and `outcome ∈ {"proposed","approved","booked"}` conveys signal strength). `upsert_episode` is key-addressed (overwrite, not append) — the natural key is `trip_id` (one episode per trip, idempotent re-extraction). Do NOT change `upsert_preference`/`search_preferences`/`upsert_instruction`/`get_instructions`. Test: upsert two episodes, semantic `search_episodes` returns both; overwrite same key replaces; episodes are isolated per user; episodes and prefs live in separate namespaces; empty user → `[]`; rich metadata (`trip_id`/`city`/`outcome`) round-trips through the store.</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/memory/test_store_episodes.py -x</verify>
  <done>Episode helpers persist + recall via an InMemoryStore; prefs/instructions helpers unchanged.</done>
</task>
```

### Task 2.2 — Extractor: add `episodes` category (single call, backward-compatible)

```xml
<task id="2.2" wave="1">
  <files>apps/api/app/memory/extractor.py, apps/api/app/prompts/memory_extraction/v2.md, apps/api/app/prompts/active.yaml, apps/api/tests/memory/test_extractor.py</files>
  <action>Add an `episodes: list[dict] = field(default_factory=list)` field to `ExtractedMemories`. In `_parse_content`, parse a third top-level `episodes` array with the same defensive per-item `{"key","text"}` validation as prefs/instructions (missing/malformed → silently skipped; a wholly absent `episodes` key → empty list, so P1 outputs still parse); additionally accept optional per-item `city`/`outcome` fields when present (default `city=None`, `outcome="proposed"`). Add `prompts/memory_extraction/v2.md`: keep the existing prefs + instructions sections verbatim, add an **episodes** section — "a one- to two-sentence durable *outcome* of a trip discussed this turn that will inform future planning: city + what the traveller liked/disliked (pace, area, airline, hotel style, budget fit). Ignore raw day-by-day itinerary, specific flight numbers, exact dates. Include a short `city` and an `outcome` (`"proposed"` by default; the system overrides to `"approved"` when the plan was accepted)." Refine the shared durability rule to: "Extract ONLY durable signals. For prefs/instructions ignore one-off trip detail; for episodes capture the trip's durable outcome, not its itinerary." Output shape becomes `{"preferences":[...],"instructions":[...],"episodes":[{"key","text","city?","outcome?"}]}`; empty arrays when nothing qualifies. Bump `active.yaml`: `memory_extraction: 2`. Tests (FakeLLM): valid JSON with episodes → populated `episodes` (incl. `city`/`outcome` when given); P1 JSON without an `episodes` key → `episodes == []` (backward compat); malformed episodes items skipped; empty arrays → empty.</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/memory/test_extractor.py -x</verify>
  <done>Extractor emits a third `episodes` category in the same single LLM call; defensive parse keeps P1 behavior; prompt v2 registered.</done>
</task>
```

### Task 2.3 — Node: upsert episodes in `extract_memory`

```xml
<task id="2.3" wave="2">
  <files>apps/api/app/agents/nodes.py, apps/api/tests/agents/test_memory_extraction.py</files>
  <action>In `make_extract_memory_node`, after the existing prefs + instructions upsert loops, add `for ep in extracted.episodes: upsert_episode(store, user_id, ep.get("key") or state.get("trip_id") or "<slug>", {"text": ep["text"], "trip_id": state.get("trip_id"), "city": ep.get("city"), "outcome": ep.get("outcome", "proposed")})` inside the same try/except (so a store error is still swallowed and logged). Determine the episode `outcome` from context: plain planner turn → `"proposed"` (the extractor default); a turn that passed the HITL `plan`-approval gate → `"approved"` — detect via `state.get("current_flow")`/an approval flag the plan node sets (see Task 2.3b), else fall back to the extractor's `outcome`. Prefer `state.get("trip_id")` as the episode key when present (idempotent per trip); fall back to the extractor's `ep["key"]` slug. Update the `logger.info` counts line to include `episodes=%d`. No change to the FAST gate or the best-effort `{}` return. Tests (FakeLLM + InMemoryStore): a non-FAST turn whose extractor returns an episode writes it to `search_episodes(store, user_id)` with rich metadata (`trip_id`/`city`/`outcome`); `allow_memory_write=False` (FAST ctx) still writes nothing (incl. no episode); empty `episodes` array writes nothing; P1-style JSON (no `episodes` key) still writes prefs/instructions and no episode; a turn flagged approved by the plan gate writes `outcome="approved"`.</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/agents/test_memory_extraction.py -x</verify>
  <done>Background node persists rich episodes (same gate, same single call, same best-effort contract); `outcome` reflects the HITL approval; P1 extraction tests stay green.</done>
</task>
```

### Task 2.3b — Plan node: surface HITL approval to the episode write

```xml
<task id="2.3b" wave="2">
  <files>apps/api/app/agents/nodes.py, apps/api/app/agents/state.py, apps/api/tests/agents/test_memory_extraction.py</files>
  <action>The `plan_node` HITL gate (already in `nodes.py`) returns `Command(goto=END)` on cancel and `Command(goto="booking")` on approve. P2 leaves that routing intact but additionally signals approval so the *later* `extract_memory` episode write can set `outcome="approved"`. Add a `plan_approved: bool` field to `TravelAgentState` (default `False`, plain sentinel — not persisted as user intent). On approval set `plan_approved=True` in the `Command.update`; on cancel leave it `False`. Then in `extract_memory` (Task 2.3) read `state.get("plan_approved")`: when true, force the episode `outcome="approved"` regardless of the extractor's value; when false, keep the extractor default `"proposed"`. No routing change (the approved plan still proceeds to `booking`, then `reflection`, then `extract_memory`). Test (FakeLLM): a turn that resumes the plan gate with `Command(resume={"approved": True})` runs to `extract_memory` and writes an episode with `outcome="approved"`; a cancelled gate writes `outcome="proposed"` (or no episode).</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/agents/test_memory_extraction.py -x</verify>
  <done>HITL approval flows into the episode `outcome`; plan routing unchanged.</done>
</task>
```

### Task 2.4 — Retrieval tool + planner wiring + prompt

```xml
<task id="2.4" wave="3">
  <files>apps/api/app/tools/memory_tools.py, apps/api/app/tools/registry.py, apps/api/app/prompts/planner/v3.md, apps/api/app/prompts/active.yaml, apps/api/tests/tools/test_tool_registry.py, apps/api/tests/agents/test_planner_episodic.py</files>
  <action>memory_tools.py: add `@tool recall_past_trips(query: str, user_id: Annotated[str, InjectedState("user_id")], store: Annotated[BaseStore, InjectedStore]) -> list` — "Recall this traveller's past trip outcomes to personalise the plan (e.g. pace, area, airline preferences they liked before)." Returns `search_episodes(store, user_id, query=query, limit=3)`; hides `store`/`user_id` from the LLM schema (C3). Export `EPISODE_TOOLS = [recall_past_trips]` and a constant `EPISODIC_TOOL_NAME = "recall_past_trips"` (in `app/agents/constants.py`, mirroring `RAG_TOOL_NAME`). registry.py: import `EPISODE_TOOLS`, add it to `TOOLS_BY_DOMAIN["planner"]`; confirm `TOOL_METADATA["recall_past_trips"]` auto-generates as `readOnly=True, destructive=False` (do NOT add to `_WRITE`/`_DESTRUCTIVE`). subagents/_base.py: extend the existing RAG filter line so the planner's `active_tools` ALSO drops `recall_past_trips` when `allow_episodic` is false — i.e. `active_tools = [t for t in tools if (allow_rag or t.name != RAG_TOOL_NAME) and (allow_episodic or t.name != EPISODIC_TOOL_NAME)]` (read `allow_episodic = ctx.allow_episodic if ctx is not None else True`). prompts/planner/v3.md: copy v2, add under "How to Work": "Before planning, call `recall_past_trips` with the destination/intent as the query and let past outcomes guide your suggestions (pace, area, airline/hotel style). Treat the results as prior examples to adapt, not facts to repeat — do not assume the same dates or city. Skip if it returns nothing." Bump `active.yaml`: `planner: 3`. Tests: registry test — `recall_past_trips` is in planner tools, schema hides store/user_id, metadata is readOnly; integration (FakeLLM + InMemoryStore) — seed an episode for a user, run a planner turn, assert the planner LLM received a tool-call for `recall_past_trips` (FakeLLM scripted) and that the tool returned the seeded episode; empty user → tool returns `[]` and the planner proceeds normally; gating — an `AgentContext(allow_episodic=False)` strips `recall_past_trips` from the planner's bound tools (mirrors the `allow_rag` filter test).</action>
  <verify>cd apps/api && OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py tests/agents/test_planner_episodic.py -x</verify>
  <done>Planner recalls past trips via a read-only per-user tool, gated by `allow_episodic` (default on); seeded episodes reach the planner on later turns; E5 anti-parroting framing in the prompt; empty users degrade gracefully.</done>
</task>
```

### Task 2.5 — Context: `allow_episodic` flag (default `True`)

```xml
<task id="2.5" wave="1">
  <files>apps/api/app/agents/context.py, apps/api/tests/agents/test_context_episodic.py</files>
  <action>Add `allow_episodic: bool = True` to `AgentContext`. In `_MODE_POLICY` set FAST→`True`, BALANCED→`True`, DEEP→`True` (DEFAULT ON for everyone in P2 v1 — mirrors P1 memory policy, NOT RAG). Thread it through `resolve_agent_context`. Product decision (resolved): episodic recall stays on for all tiers in v1; the flag exists so flipping free→`False` later is a one-line `_MODE_POLICY` change with no rewiring (e.g. tie to tier like `allow_rag`). Test: default `AgentContext()` is `True`; FAST/BALANCED/DEEP all resolve to `True`; free tier does NOT gate it (free BALANCED → `True`, unlike `allow_rag`).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_context_episodic.py -x</verify>
  <done>`allow_episodic` flag present, default `True` for all modes/tiers; gate exists and is testable; P1 behavior unchanged.</done>
</task>
```

## 5. Key decisions

### D1 — Episode write path: extend the P1 background extractor (one call)

Chosen: add `episodes` as a third category to the **existing** `extract_memories`
call, not a second extractor and not an LLM-discretionary tool.

- **Zero extra latency** over P1 — episodes ride the single fast-LLM call that
  already runs on non-FAST turns. A second extractor (cleaner prompt separation)
  would double extraction latency; rejected for P2.
- **Consistent with P1's philosophy** — P1 rejected "LLM calls a tool if it
  remembers to" as the gap it was closing; a `save_episode` tool the planner must
  choose to call would repeat that gap. Background extraction is the established
  pattern.
- **Conceptually unified** — episodes are *durable* too ("on past trips you've
  preferred X"), just at trip granularity rather than traveller granularity. The
  unifying policy stays "extract only durable signals that inform future
  conversations" (research.md §1: "not every trace is memory").
- **Pollution safety** — the prompt keeps a hard line: prefs/instructions ignore
  one-off trip detail; episodes capture only the *durable outcome* (city + liked
  pace/style), never the raw itinerary. Key-addressed upsert (one episode per
  `trip_id`) bounds growth.
- **Backward-compatible** — `_parse_content` already treats a missing top-level
  key as empty, so P1-era extractor output (no `episodes`) parses unchanged; P1
  tests stay green.
- Rejected: a trip-lifecycle write trigger (capture on "trip completed") — most
  semantically correct but needs a new trigger point outside the graph, out of
  the `memory/store.py` + `tools/memory_tools.py` scope, and harder to test on
  FakeLLM. Documented as a future refinement.

### D2 — Store shape: `("users", uid, "episodes")`, rich episode value

- Reuses P1's generalised `_namespace(user_id, kind)`; `kind = "episodes"`.
- Value keeps the **rich episode schema** `{"text": ..., "trip_id": ..., "city": ..., "outcome": ...}` (per design E1). The shared semantic index (`_index_config`) embeds only the `text` field — the one-sentence summary carrying city + durable outcome so a `search_episodes` hit is self-contained few-shot context; `trip_id`/`city`/`outcome` are stored metadata (`outcome ∈ {"proposed","approved","booked"}` conveys signal strength). Naming follows P1's `upsert_*`/`search_*` convention.
- Key = `trip_id` when the state carries one (idempotent: re-extracting the same trip overwrites, not appends), else the extractor's slug. Mirrors prefs (`"diet"`) / instructions (`"currency"`) key-addressed upsert.

### D3 — Retrieval tool: read-only, planner-bound, gated by `allow_episodic`

- `recall_past_trips(query)` uses `InjectedStore` + `InjectedState("user_id")`,
  identical injection pattern to `get_user_preferences` — the model supplies only
  the semantic `query`; it can never address another traveller's memory (C3).
- Bound to the **planner** only (research roadmap: "few-shot retrieval tool for
  planner"). `TOOLS_BY_DOMAIN["planner"] += EPISODE_TOOLS`.
- **Gated by `allow_episodic` (default `True`)** — a new `AgentContext` flag (Task 2.5). NOT tied to `allow_rag`: episodic memory is per-user personalisation, not the global knowledge base. Product decision (resolved): **on for everyone in P2 v1** (mirrors P1 D5 "memory is a cheap UX differentiator", not RAG's free=off). The flag exists so flipping free→`False` later is a one-line `_MODE_POLICY` change. Mechanically: `subagents/_base.py` extends its tool filter to also drop `t.name == EPISODIC_TOOL_NAME` when `allow_episodic` is false (same pattern as the existing RAG filter).
- Read-only: auto-annotated `readOnly=True, destructive=False`; not added to
  `_WRITE`/`_DESTRUCTIVE`.

### D4 — Planner prompt v3 (with E5 anti-parroting framing)

- Copy v2, add a "recall past trips before planning" step + the E5 "adapt, don't
  repeat" framing: treat recalled episodes as prior examples to adapt (pace,
  budget, area), not facts to repeat; do not assume the same dates or city. Bump
  `active.yaml` `planner: 3`. The step is skippable ("skip if it returns nothing")
  so users with no episodes see no behavior change.

### D5 — Prompt bumps

- `memory_extraction` v1 → v2 (add `episodes` section + refined durability rule).
- `planner` v2 → v3 (add the recall step + E5 framing). Both registered in `active.yaml`.

### D6 — Episode `outcome` wired from the HITL plan-approval gate

- A plain planner turn stores `outcome="proposed"` (the extractor default). A turn
  that passed the `plan` HITL gate stores `outcome="approved"` — the plan node sets
  a `plan_approved` state flag on approval (Task 2.3b), which `extract_memory` reads
  to override the outcome. `"booked"` (booking sub-agent success) is a documented
  follow-up, not in P2 v1.

## 6. Risks

- **Latency** — no increase over P1 (episodes ride the existing single extraction
  call). FAST mode still skips entirely via `allow_memory_write`. Streaming
  mitigation unchanged (answer already shown before extraction runs).
- **Memory pollution** — the single-call design asks the model to both *ignore*
  trip detail (prefs/instructions) and *capture* trip outcome (episodes). Mitigated
  by a hard prompt line separating the two and key-addressed upsert (one episode
  per `trip_id`). If cross-contamination shows up in real traffic, fall back to a
  dedicated episode extractor (D1 rejected option) at the cost of one extra call.
- **Episode growth** — bounded to one episode per `trip_id` (overwrite on
  re-extract). A future TTL/decay is a non-goal for P2.
- **Provider-agnostic / tests** — `extract_memories` stays pure + FakeLLM-driven;
  the retrieval tool is FakeLLM + InMemoryStore-testable. `OPENAI_API_KEY=""` so
  `get_embeddings()` uses the deterministic fake (same caveat as P1, see
  `env-openai-key-test-breaks-llm-tests`).
- **P1 regression** — the extractor change is additive + backward-compatible
  (missing `episodes` key → empty list). P1's `test_extractor.py` and
  `test_memory_extraction.py` must stay green unchanged.

## 7. Waves

| Wave | Tasks | Parallelism | Files disjoint? |
|---|---|---|---|
| 1 | 2.1 store, 2.2 extractor+prompt, 2.5 context flag | 3 parallel | store.py / extractor.py+prompts / context.py — yes |
| 2 | 2.3 node upsert, 2.3b plan-approval flag | single (coupled) | both touch nodes.py + state.py — run together after wave 1 |
| 3 | 2.4 tool + planner wiring + integration | single | tools/memory_tools.py + registry.py + _base.py + prompts/planner — depends on 2.1 helpers + 2.5 flag; integration test exercises the full path (benefits from 2.3/2.3b) |

## 8. Status Log

- 2026-06-30 — P2 plan drafted (proposed). Builds on shipped P1 (`feat/agent-memory-layers`). Awaiting review before execution.

