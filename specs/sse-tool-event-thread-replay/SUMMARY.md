# sse-tool-event-thread-replay — Summary

Lane: normal
Confidence: high
Reason: bug fix in the SSE mapper (client-visible stream behavior) touching mapper.py + a regression test; no manifest hard gate fires (no route/shape/auth/schema change).
Flags: existing behavior
Affects: app/streaming/mapper.py (agent SSE stream — tool_call / panel / tool_result events)
Input-type: change request
Route: using-git-worktrees → subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> [Image #2] duplicate when call tool find places (x5). Investigate issue and suggestion solution to resolve it/

(Image #2 = docker log of one concierge turn: ONE `search_places` call at 13:39:57, then ~25
`POST /v1/chat/completions` between 13:39:58 and 13:40:31 with no `[agent]` log lines, then
`node=reflection revisions=1`.)

## What changed

Patched `apps/api/app/streaming/mapper.py` on branch `fix/sse-tool-event-thread-replay`
(direct patch, per user request): (1) the pre-turn `aget_state` snapshot now also collects
every prior message id + tool_call id, and any message in an `updates` delta whose id (or
tool_call_id) is in that snapshot is skipped; (2) a per-stream `emitted_tool_results` set
emits `panel` + `tool_result` once per tool_call_id, mirroring `emitted_tool_calls`.
Regression test: `apps/api/tests/streaming/test_mapper_tool_event_dedup.py` (3 cases).

### Root cause (verified offline, FakeLLM, no network)

`stream_agent_events` (`apps/api/app/streaming/mapper.py`) consumes
`graph.astream(..., stream_mode=["messages","updates"], subgraphs=True)` and, in `updates`
mode, walks **every** message in every node delta:

1. **Same-turn double sighting.** A sub-agent's `ToolMessage` shows up twice per turn: once
   from the subgraph namespace (`('concierge:<id>',) / tools`) and again from the parent
   namespace (`() / concierge`) because the parent's update for a subgraph node is the
   subgraph's whole output. `tool_call` events are deduped by `emitted_tool_calls`; `panel` and
   `tool_result` are **not**.
2. **Cross-turn history replay (the ×N).** The sub-agent shares `TravelAgentState`, so the
   parent-level `concierge` delta carries the **entire** `messages` list of the thread, including
   `AIMessage(tool_calls)` and `ToolMessage(artifact=...)` from previous turns. Each of those is
   re-emitted as if new: old `tool_call` ids are not in this stream's `emitted_tool_calls` set, so
   the FE activity trail gets a fresh "search_places · running" step for every past search; every
   old places artifact is re-emitted as `panel` + `tool_result`.
3. **LLM amplification.** Under `language=vi`, each `panel` emission runs
   `localize_panel` → `_localize_vi` → one `translate_llm.ainvoke` **per place description**
   (4 places per panel). So one search in a thread with K prior searches costs
   `(2 + K) × 4` translation calls. The screenshot's ~24 silent completions ≈ 6 emissions × 4
   places — consistent with 4–5 earlier `search_places` turns on that thread, i.e. the "×5".

Offline repro (3 turns, one thread, one `search_places` per turn, `language=vi`):

| Turn | tool_call | panel | tool_result | translator calls |
| --- | --- | --- | --- | --- |
| 1 | 1 | 2 | 2 | 8 |
| 2 | 2 | 3 | 3 | 12 |
| 3 | 3 | 4 | 4 | 16 |

Expected per turn: 1 / 1 / 1 / 4.

### Rationale

Fix belongs in the mapper (single emission point), not in the graph or the FE: the graph's
parent-level replay is normal LangGraph behavior for a shared-state subgraph, and the FE
already upserts panels by kind (which is why the drawer looks fine while the activity trail and
the LLM bill do not).

### Proposed solution (for the plan)

1. **Snapshot pre-turn message ids** — the mapper already calls `graph.aget_state(cfg)` before
   the loop (language seed). Also collect `{m.id}` for every message in `_pre.values["messages"]`
   and the `tool_call` ids on those `AIMessage`s. Skip any message whose id / tool_call_id is in
   that snapshot → kills the cross-turn replay (bug 2, the ×N).
2. **Dedupe ToolMessages within the turn** — add `emitted_tool_results: set[str]` keyed by
   `tool_call_id`, mirroring `emitted_tool_calls`; emit `panel` + `tool_result` only on first
   sighting → kills the same-turn double (bug 1).
3. **Regression test** in `tests/streaming/` using the existing `_FakeGraph` scripted-`astream`
   pattern: (a) same `ToolMessage` yielded from `('concierge:1',)/tools` and `()/concierge` →
   exactly one `panel` and one `tool_result`; (b) pre-state `values["messages"]` containing an
   old `AIMessage(tool_calls)` + `ToolMessage(artifact)` that reappear in the parent delta → zero
   events for them; (c) translator call count == number of places (4), not a multiple.
4. Reflection-revision passes re-run the tool under a **fresh** call id, so they still surface
   (FE comment in `attachPanelToMessage` relies on that) — no change needed there.

Alternative considered: skip root-namespace `updates` whose node name is in `SUBAGENTS`
entirely. Simpler, but the multi-intent path (`synthesis_worker` nesting) makes namespace
reasoning fragile; id-based dedupe is namespace-agnostic. Batching the 4 per-place translation
calls into one is a separate optimisation, out of scope.

### Adjacent finding (not in scope — mention only)

`state["revisions"]` is never reset between turns (only read in `nodes.py`, incremented on
revise). The screenshot shows `revisions=1 → END (no revision)` on a turn that made no revision,
so once a thread has revised once, reflection is effectively disabled for the rest of the thread.
Worth its own ticket.

### Alternatives considered

- see "Proposed solution" above

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| offline repro of duplicate emissions (temp test, since deleted) | `cd apps/api && DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= ../../.venv/bin/python -m pytest tests/streaming/test_zz_repro_dup_panel.py -q -s` | 1 | intentional `assert False` to print counts; table above is its output | |
| regression + streaming suite | `cd apps/api && DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= ../../.venv/bin/python -m pytest tests/streaming tests/api/agent/test_stream_events.py -q` | 0 | 63 passed | |
| lint | `cd apps/api && ruff check app/streaming/mapper.py tests/streaming/test_mapper_tool_event_dedup.py` | 0 | | |
| full BE suite | `make test` | 2 | 2096 passed, 5 failed — the same 5 fail on `main` (local `.env` keys: langfuse/openai/openrouteservice), unrelated to this change | |

### Not auto-verified

- the ~24 silent completions in the screenshot are translator calls — reached traceability (count matches `(2+K)×4` and the mapper is the only LLM caller without `[agent]` logging on that path); not re-run because the container log for that window is gone (`docker logs api-api-1` returns nothing for 13:39–13:41)

### Rollback

- `git revert <sha>` (mapper-only change, no schema/contract)

### Harness-Delta

- none
