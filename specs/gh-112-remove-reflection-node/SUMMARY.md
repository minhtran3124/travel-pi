# gh-112-remove-reflection-node — Summary

Lane: normal
Confidence: high
Reason: bounded deletion of one graph node and everything that existed only to serve it. No hard
gate: no auth/authorization change, no migration, no new or removed public contract (the SSE `reset`
event and its FE handling are deliberately kept), and the quality question was settled with a
measured A/B before any code changed.
Flags: existing-behavior, high-blast-file (`agents/graph.py`, `agents/nodes.py`)
Affects: parent graph topology; `AgentContext`; `TravelAgentState`; the agent-config dashboard's
`enabled` UI; the prompt registry.
Input-type: change request (GitHub #112)
Route: normal → direct implementation on a branch off `main`
Escalate: no

### Intent

> new gh issue cho viec remove node reflection khoi workflow, ko phai la check enable tu db config nua
>
> (then, after the issue was written and the eval gate run) 2. new branch from main and implement

#112 supersedes #106: instead of making the DB `enabled` toggle gate the reflection node, the node
is removed.

### What changed

- **Graph** — `reflection` node deleted; `dispatch_next` now routes to `END` instead
  (`agents/graph.py`, `agents/nodes.py`). Topology diagram and comments updated.
- **Constants** — `DEFAULT_MAX_REVISIONS`, `REFLECTION_REVISE_NOTE` removed; `reflection` dropped
  from `FAST_AGENTS`; the `MAX_LEDGER_STEPS` recursion note no longer reserves headroom for a revise
  loop.
- **State** — `TravelAgentState.revisions` removed outright (no deprecation window).
- **Context** — `AgentContext.allow_reflection` and `.max_revisions` removed, along with
  `resolve_agent_context(allow_reflection=...)`.
- **Router** — the `AgentConfigCache.get("reflection")` lookup added by #106 is gone. REST reply
  assembly no longer strips a "superseded draft": nothing supersedes an answer within a turn any
  more, so every answer belongs to a distinct sub-agent of a multi-intent turn.
- **Prompts** — `app/prompts/reflection/v1.md` deleted, `active.yaml` pin removed, CHANGELOG entry
  added.
- **Config surface** — `reflection` dropped from `AGENT_CONFIG_GROUPS`/`AGENT_DESCRIPTIONS`, so it
  disappears from the dashboard and from a fresh seed. The reflection-only `enabled` checkbox (both
  the edit page and the shared modal, plus its JS and CSS) is removed.
- **Docs** — `WORKFLOW.md` topology, request-flow, `AgentContext` table, `FAST_AGENTS` list, and the
  known-limitations list.
- **Tests** — reflection-node tests deleted; `dispatch_next` tests retargeted to `END`; two
  memory-extraction fixtures no longer script the judge's "OK" slot; `agent_config` layer tests that
  used `"reflection"` as a sample agent name now use `"summarize"`. Two new guards added in
  `tests/agents/test_graph.py`.

### Rationale

The node cost one extra LLM round-trip per turn (and a full sub-agent re-run on `REVISE`) for a
single unrubriced `REVISE`/accept verdict, and it needed special-casing to avoid harm — the
`awaiting_user` short-circuit (MIN-68/#99) and the SystemMessage-not-HumanMessage revise note
(`docs/solutions/agent/reflection-humanmessage-language-flip.md`). It was already `enabled=False` on
the dev DB.

### Decisions

- **The SSE `reset` event stays.** Deleting it was considered and rejected: its other producer is the
  ledger-drain supersede (gh-109), so removing it would regress that. On `main` the producer is still
  the message-id-inequality heuristic, which serves both cases — it is left untouched here so this
  change alters no streaming behavior. Its comment no longer attributes it to reflection.
- **`revisions` dropped with no deprecation window.** Nothing outside reflection wrote it and no
  router or service seeded it; old checkpoints keep the channel in their persisted `channel_values`
  and the compiled graph simply stops declaring it.
- **The `reflection` row in `agent_config` is left orphaned — no migration.** Seeding is derived from
  `AGENT_CONFIG_NODES`, so dropping the name removes it from the dashboard and fresh seeds; the row
  on existing databases just stops being read. The `enabled` column is kept and now has no reader.
- **Nothing replaces the judge.** Guarded by a measured A/B instead (below).

### Eval gate (run BEFORE the change)

Both arms on commit `42ab13c`, all nodes `gpt-5.4-mini`, judge `gpt-4o-mini` @ 0.70, 34/37 cases
scored. Reports: `apps/api/eval/reports/gh-112-baseline-reflection-on.md` and
`gh-112-ab-reflection-on-vs-off.md`.

| Metric | N | reflection ON | reflection OFF |
|---|---|---|---|
| Response Language | 10 | 1.00 / 100% | 1.00 / 100% |
| Search vs Booking Intent | 5 | 0.89 / 80% | 0.97 / 100% |
| Format Quality | 4 | 0.89 / 100% | 0.88 / 100% |
| Memory Recall | 8 | 0.84 / 87.5% | 0.84 / 87.5% |
| Tool Correctness | 4 | 1.00 / 100% | 1.00 / 100% |
| Suggestion Relevance (GEval) | 8 | 0.64 / 50% | 0.75 / 62.5% |

No rubric regresses without reflection. Both nominal gains are worth exactly one case on N=5/N=8, so
they read as "no cost", not "reflection was harmful". Suggestion Relevance is the noise floor (its
deterministic twin passes 8/8 in both arms) and `no_hallucination` scores nothing.

### Alternatives considered

- **Keep the node, honor the DB toggle** — what #106 shipped. Rejected: a toggle hides the cost but
  keeps the node, the revise loop, and its special cases in the codebase and the topology.
- **Delete the `reset` SSE event too** — rejected, see Decisions.
- **Replace the judge with a rubric-based reviewer** — out of scope; the A/B gives no evidence a
  replacement is needed.

### Deviations

- **The mapper cleanup described in the issue does not apply on `main`.** The issue's scope was
  written against the gh-109 branch, where `reset` is keyed to the reflection node via
  `pending_reset`. On `main` that code does not exist yet — the heuristic is message-id inequality.
  Only comments were adjusted; the `pending_reset` removal lands after #114 merges. **Expect a
  conflict in `app/streaming/mapper.py` between this branch and PR #114** (gh-109).

### PR review follow-up (Codex, PR #115)

- **F3 (P1) — no `PLAN.md` for a 38-file change. Confirmed.** `rules/plan-format.md` triggers a plan
  at >2 files; only `SUMMARY.md` was written. `PLAN.md` added alongside this file, recorded from the
  implementation as executed (tasks 1.1–4.1) rather than back-dated as a guess.
- **F4 (P2) — companion docs still described the node. Confirmed.** `WORKFLOW.md` was updated but
  `CLAUDE.md:72` and `WORKFLOW_DIAGRAM.md` (both mermaid graphs + the prose) still routed every
  specialist through `reflection`, leaving contradictory architecture guidance for anyone onboarding.
  Fixed in Task 4.1. While editing the diagram, pre-existing drift was found and flagged in a header
  note rather than silently rewritten: it still draws `extract_memory` as an in-graph node with a
  "skipped in FAST" label, though extraction is a post-response background task and modes were
  removed in MIN-43.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full backend suite | `cd apps/api && DATABASE_URL=sqlite:///<tmp> ../../.venv/bin/python -m pytest tests/ -q` | 1 | 1780 passed, 5 failed — the **same 5** fail on unmodified `main`: `.env` supplies real `OPENAI_API_KEY`/`ORS_API_KEY`/Langfuse values, so the "no key configured" / "offline estimate" / "disabled by default" tests fail. All 21 tests in those three files pass when run from a directory without `.env`. |
| No reflection node in the compiled graph | `pytest tests/agents/test_graph.py::test_graph_has_no_reflection_node -q` | 0 | asserts on `graph.get_graph().nodes` |
| No extra LLM call on a normal turn | `pytest tests/agents/test_graph.py::test_normal_turn_makes_no_fast_llm_call -q` | 0 | counts fast-model `_generate` calls; would have been ≥1 before |
| Lint | `cd apps/api && ../../.venv/bin/ruff check app scripts` | 0 | clean |
| Format | `ruff format` on all changed `.py` | 0 | 4 files reformatted, then clean |
| Docs reconciled (F4) | `grep -rn reflection WORKFLOW.md WORKFLOW_DIAGRAM.md CLAUDE.md` | — | only the intentional "removed in #112" notes remain |
| Reflection references gone | `grep -rn reflection apps/api/app apps/web/src` | — | only `app/data/places.py` ("sunrise reflections", unrelated) and the `agent_config` model comment recording that `enabled` lost its reader |

### Rollback

- `git revert <sha>` — reversible. The reflection prompt, node, and tests are recoverable from git
  history; no migration was applied and no DB row was deleted.

### Harness-Delta

- backlog: the issue's file-level scope was authored against a feature branch, not the base branch it
  would be implemented on. A scope written from `git grep` on branch A can be partly inapplicable on
  branch B — worth stating the base commit in the issue when the scope names line numbers.
