# gh-112 — Remove the reflection node from the agent workflow

Retro-recorded after implementation (PR #115 review, F3): the change touched 38 files across the
graph, routing, config surface, prompts, templates, docs and tests, which is well past the >2-file
threshold in `rules/plan-format.md`, and only `SUMMARY.md` had been written. The tasks below are the
implementation as executed and verified, not a forward-looking guess — recorded so the scope and
verification strategy are auditable without re-reading the diff.

**Base:** `github/main` (`6165903`). **Branch:** `fix/gh-112-remove-reflection`.

**Gate before any code (already satisfied):** the ON/OFF eval A/B on commit `42ab13c` showed no
rubric regresses with reflection off. Committed separately as `9d4b758`
(`apps/api/eval/reports/gh-112-*.md`). Without that result this plan does not start.

---

### Task 1.1 — Delete the node and re-route the graph (wave 1)

- **Files:** apps/api/app/agents/nodes.py, apps/api/app/agents/graph.py
- **Action:** Delete `make_reflection_node`. Point `dispatch_next` at `END` in all three exits
  (awaiting-user, illegal queued flow, empty queue) and update its docstring. Drop the node
  registration and the `make_reflection_node` import from `graph.py`; change `dispatch_next`'s
  `destinations` to `(*SUBAGENTS, END)`; update the module topology diagram and edge comments.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_graph.py -q`
- **Done:** `reflection` is absent from `graph.get_graph().nodes`; a sub-agent turn ends at
  `dispatch_next → END`.

### Task 1.2 — Remove the state and context fields it owned (wave 1)

- **Files:** apps/api/app/agents/state.py, apps/api/app/agents/context.py,
  apps/api/app/agents/constants.py
- **Action:** Drop `TravelAgentState.revisions` outright (no deprecation window — nothing else
  writes it and no router seeds it; old checkpoints keep the channel in their persisted
  `channel_values` and the graph simply stops declaring it). Remove `AgentContext.allow_reflection`
  and `.max_revisions` plus the `resolve_agent_context(allow_reflection=...)` kwarg. Remove
  `DEFAULT_MAX_REVISIONS`, `REFLECTION_REVISE_NOTE`, and the `reflection` entry in `FAST_AGENTS`;
  correct the `MAX_LEDGER_STEPS` comment that reserved recursion headroom for the revise loop.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -q`
- **Done:** `grep -rn "allow_reflection\|max_revisions\|revisions" apps/api/app` is empty.

### Task 1.3 — Drop the router's reflection plumbing (wave 1)

- **Files:** apps/api/app/routers/agent.py
- **Action:** Remove the `AgentConfigCache.get("reflection")` lookup added by #106 and pass only
  `tier`/`timezone` to `resolve_agent_context`. Simplify REST reply assembly: nothing supersedes an
  answer within a turn any more, so stop popping the previous answer on a revise-note SystemMessage
  and keep every distinct sub-agent's answer.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent -q`
- **Done:** `/agent/chat` returns every sub-agent answer of a multi-intent turn; no reflection symbol
  remains in the router.

### Task 2.1 — Retire the prompt (wave 2)

- **Files:** apps/api/app/prompts/reflection/v1.md, apps/api/app/prompts/active.yaml,
  apps/api/app/prompts/CHANGELOG.md
- **Action:** `git rm` the prompt directory, drop the `reflection: 1` pin, add a CHANGELOG entry
  recording that nothing loads a reflection prompt any more and pointing at the eval A/B.
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; registry.get('supervisor')"`
- **Done:** the registry loads with no reflection entry; `active.yaml` has no orphan pin.

### Task 2.2 — Remove it from the config surface (wave 2)

- **Files:** apps/api/app/data/agent_config.py, apps/api/app/db/models/agent_config.py,
  apps/api/app/templates/agent_config.html, apps/api/app/templates/agent_config_edit.html
- **Action:** Drop `reflection` from the support-node group and `AGENT_DESCRIPTIONS` (so it leaves
  `AGENT_CONFIG_NODES`, the dashboard and fresh seeds). Remove the reflection-only `enabled`
  checkbox from both templates plus its JS branch and the `#am-enabled-field[hidden]` CSS rule.
  Keep the `enabled` column — **no migration**, and the orphaned row on existing databases is left
  in place; record in the model comment that the column now has no reader.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config -q`
- **Done:** the dashboard renders no reflection card and no enabled checkbox; no Alembic revision
  was added.

### Task 3.1 — Update the test suite (wave 3)

- **Files:** apps/api/tests/agents/*.py, apps/api/tests/api/agent/*.py,
  apps/api/tests/api/agent_config/*.py, apps/api/tests/core/test_agent_config_cache.py,
  apps/api/tests/db/test_agent_config_model.py, apps/api/tests/eval/test_harness_multiturn.py
- **Action:** Delete the reflection-node tests; retarget `dispatch_next` assertions from
  `"reflection"` to `END`; drop the judge's `"OK"` slot from the two memory-extraction fixtures that
  relied on reflection consuming it first; rename the `agent_config` layer tests that used
  `"reflection"` as a sample agent name to `"summarize"`; correct stale comments attributing a
  fast-LLM response to the judge.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///$(mktemp -d)/t.db ../../.venv/bin/python -m pytest tests/ -q`
- **Done:** only the 5 pre-existing `.env`-leak failures remain (they fail identically on unmodified
  `main`).

### Task 3.2 — Add the guards that keep it gone (wave 3)

- **Files:** apps/api/tests/agents/test_graph.py
- **Action:** Add `test_graph_has_no_reflection_node` (asserts on `graph.get_graph().nodes`, so a
  stray `add_node` or import fails the suite) and `test_normal_turn_makes_no_fast_llm_call` (counts
  fast-model `_generate` calls on a short-history turn — reflection was its only per-turn consumer,
  so the count must be zero). Assert on the call count rather than node names so the guarantee
  survives a topology rename.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_graph.py -q`
- **Done:** both guards pass and would have failed before Task 1.1.

### Task 4.1 — Reconcile the documentation (wave 4)

- **Files:** WORKFLOW.md, WORKFLOW_DIAGRAM.md, CLAUDE.md
- **Action:** Update the `WORKFLOW.md` topology diagram, request flow, `AgentContext` table,
  `FAST_AGENTS` list and known-limitations list. Replace `Refl` with `dispatch_next` in both
  `WORKFLOW_DIAGRAM.md` mermaid graphs and the prose beneath them. Fix the graph description in
  `CLAUDE.md`. (Waves 1–3 shipped before this task was identified; added after the PR #115 review
  found the two companion docs still contradicting `WORKFLOW.md`.)
- **Verify:** `grep -rn "reflection" WORKFLOW.md WORKFLOW_DIAGRAM.md CLAUDE.md`
- **Done:** the only remaining matches are the intentional "removed in #112" notes.

---

## Out of scope

- **The SSE `reset` event.** Its other producer is the gh-109 ledger-drain supersede, so deleting it
  would regress that. On `main` the producer is still the message-id-inequality heuristic, which
  serves both cases — left untouched, so this change alters no streaming behavior. The
  `pending_reset` removal described in the issue belongs to a follow-up after #114 lands.
- **A migration for the orphaned `reflection` row.** Deliberate; see Task 2.2.
- **Any replacement for the judge.** The eval A/B gives no evidence one is needed.
