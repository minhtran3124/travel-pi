---
slug: remove-rag-feature
status: active
owner: Minh Tran
created: 2026-07-04
---

# Remove RAG Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Fully delete the RAG (retrieval-augmented generation) feature — the concierge sub-agent's `search_destination_knowledge` tool, its pgvector/hybrid-search backend, and its eval/test coverage — since the agent now relies on tool calls instead, per the user's explicit choice of "Full deletion" at intake.

**Architecture:** RAG is a live, request-time LangGraph tool (not dormant scaffolding): `app/tools/rag_tools.py` wraps `hybrid_search()` from `app/rag/retriever.py`, is registered in the concierge's tool list (`app/tools/registry.py`), and is gated by `AgentContext.allow_rag` (tier-based) via a filter in `app/agents/subagents/_base.py`. The one non-obvious coupling: `app/memory/store.py` reuses `get_embeddings()`/`EMBED_DIM` from `app.rag.embeddings` for the *unrelated* long-term-memory semantic index — that dependency must be relocated to a new home (`app/core/embeddings.py`) before `app/rag/` can be deleted. No DB migration is needed: there are no Alembic-managed ORM tables for RAG (pgvector collections are runtime-created by `langchain-postgres`), and the existing `enable_pgvector_extension_postgres_only` migration stays in place untouched (it's also what backs the Postgres-only path of `memory/store.py`'s semantic index).

**Tech Stack:** FastAPI / LangGraph 1.x / LangChain 1.x, `langchain-postgres` (PGVector), `langgraph-checkpoint-postgres` (`PostgresStore`, unaffected), pytest.

**Reference:** `specs/remove-rag-feature/SUMMARY.md` (intake record, Lane: normal), `specs/remove-rag-feature/research-brief.md` (full footprint map).

---

## 1. Motivation

The product direction is tool-calling first; RAG retrieval is deferred indefinitely per user decision at intake. Rather than leave a disabled-but-present feature (which the user explicitly declined — see SUMMARY.md `### Alternatives considered`), this plan removes it cleanly: the code, its tests, its eval harness entry, and its RAG-only dependencies.

## 2. Non-goals

- Does not touch `app/memory/store.py`'s Postgres/in-memory store *selection* logic, checkpointer, or any non-RAG memory behavior — only the *source* of `get_embeddings`/`EMBED_DIM` changes.
- Does not revert or drop the `enable_pgvector_extension_postgres_only` Alembic migration — it remains a harmless no-op cleanup step and is still relevant to `memory/store.py`'s Postgres semantic index.
- Does not remove `episodic recall` (`recall_past_trips`, `allow_episodic`) — a separate, unrelated gated capability that happens to share the filter pattern in `subagents/_base.py`.
- Does not touch `langgraph-checkpoint-postgres` or its dependencies (confirmed it does not depend on the `pgvector` or `langchain-postgres` pip packages — verified via `importlib.metadata.requires`).
- Does not re-add RAG later — if it returns, that's new feature work with its own intake.

## 3. Success Criteria

- `grep -rn "app\.rag\|rag_tools\|RAG_TOOLS\|RAG_TOOL_NAME\|allow_rag\|search_destination_knowledge" apps/api/app apps/api/tests apps/api/eval apps/api/scripts` returns nothing (except historical prose mentions in `specs/travel-agent/PLAN.md`, which are annotated superseded, not deleted).
- Full backend test suite passes on SQLite (`make test`).
- The concierge sub-agent's tool list no longer includes any RAG tool; `AgentContext` no longer has an `allow_rag` field.
- `app/memory/store.py`'s semantic index still works (existing memory tests green) — `get_embeddings`/`EMBED_DIM` now sourced from `app/core/embeddings.py`.

## 4. Tasks

### Wave 1 — independent removals (zero file overlap, run in parallel)

#### Task 1.1 — Relocate the shared embeddings helper

```xml
<task id="1.1" wave="1">
  <files>app/core/embeddings.py, tests/core/test_embeddings.py</files>
  <action>
Create `app/core/embeddings.py`. This is the RAG-independent half of
`app/rag/embeddings.py` — `get_embeddings()` and `EMBED_DIM` only (NOT
`get_vector_store`, which is RAG-specific and will be deleted in Task 3.1).

```python
"""Embedding model selection, shared by the agent-memory semantic index.

``get_embeddings()`` uses OpenAI when a key is configured and a deterministic
fake otherwise, so local dev and the test suite embed without a key or
network. Relocated from ``app.rag.embeddings`` when the RAG feature was
removed (specs/remove-rag-feature) — ``app.memory.store`` is the only
remaining consumer.
"""

from __future__ import annotations

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from app.core.config import get_settings

EMBED_DIM = 1536  # text-embedding-3-small dim
_FAKE_EMBED_DIM = EMBED_DIM  # the fake matches so dims are stable across modes


def get_embeddings() -> Embeddings:
    """Return the embedding model: OpenAI when keyed, deterministic fake otherwise.

    :return: The embedding model.
    """
    s = get_settings()
    if s.openai_api_key:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key)
    return DeterministicFakeEmbedding(size=_FAKE_EMBED_DIM)
```

Create `tests/core/test_embeddings.py`, porting only the one test from
`tests/rag/test_embeddings.py` that exercises `get_embeddings` (the other two
port `get_vector_store`, which is not being relocated — they'll be deleted
with the rest of `tests/rag/` in Task 3.1):

```python
"""Shared embeddings helper (relocated from tests/rag/test_embeddings.py;
specs/remove-rag-feature)."""

from langchain_core.embeddings import DeterministicFakeEmbedding


def test_get_embeddings_fake_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.embeddings import get_embeddings

    emb = get_embeddings()
    assert isinstance(emb, DeterministicFakeEmbedding)
    # deterministic: same text -> same vector
    assert emb.embed_query("Tokyo") == emb.embed_query("Tokyo")
    get_settings.cache_clear()
```

Do NOT touch `app/rag/embeddings.py` or `app/memory/store.py` in this task —
those are handled in Wave 2/3 once this new module exists.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_embeddings.py -x</verify>
  <done>New module importable and its test passes; app/rag/ untouched so far.</done>
</task>
```

#### Task 1.2 — Remove `allow_rag` gating from the agent context/tool-filter layer

```xml
<task id="1.2" wave="1">
  <files>app/agents/context.py, app/agents/constants.py, app/agents/subagents/_base.py, tests/agents/test_agent_context.py, tests/agents/test_context_episodic.py, tests/agents/test_depth_toggles.py</files>
  <action>
These three source files + three test files are tightly coupled (a shared
field/constant/filter) — edit together so no intermediate state has a broken
import.

**`app/agents/constants.py`**: delete the `RAG_TOOL_NAME` constant and its
comment block (lines 39-42, the "--- tooling ---" section's RAG_TOOL_NAME
part). Keep `EPISODIC_TOOL_NAME` and its comment — unrelated capability.

**`app/agents/context.py`**:
- Remove the `allow_rag: bool = True` field from the `AgentContext` dataclass.
- In `resolve_agent_context`, delete the `allow_rag = True` init and the
  `allow_rag = False` line inside the `if tier == Tier.FREE:` branch, and
  remove `allow_rag=allow_rag,` from the returned `AgentContext(...)` call.
- Update the docstring: remove the two RAG bullets ("**free**: ``allow_rag=False``
  always; ..." mentions RAG) — keep the booking-exclusion bullet, rewording
  the free-tier bullet to only describe the booking ceiling.

**`app/agents/subagents/_base.py`**:
- Remove `RAG_TOOL_NAME` from the `from app.agents.constants import (...)`
  import (keep `EPISODIC_TOOL_NAME`).
- In `assistant()`, remove `allow_rag = ctx.allow_rag if ctx is not None else True`
  and simplify the `active_tools` filter to only the episodic condition:
  ```python
  active_tools = [
      t for t in tools if (allow_episodic or t.name != EPISODIC_TOOL_NAME)
  ]
  ```
- Update the comment above it ("Filter the RAG + episodic-recall tools...")
  to say "Filter the episodic-recall tool...".

**`tests/agents/test_agent_context.py`**: remove every `assert ctx.allow_rag is
...` line and the RAG-referencing comments (`# free tier: RAG always off`,
`# D.1: free tier always has RAG off`). Rename
`test_free_gates_rag_and_booking` -> `test_free_gates_booking` (drop the RAG
half of the name and its assertion) and
`test_premium_unlocks_rag_and_all_subagents` -> `test_premium_unlocks_all_subagents`.
Update the module docstring (drops "free loses RAG and booking; premium keeps
all sub-agents and RAG" -> "free loses booking; premium keeps all sub-agents").

**`tests/agents/test_context_episodic.py`**: delete the trailing
`assert ctx.allow_rag is False` line and its "Contrast: RAG IS gated..."
comment in `test_free_tier_does_not_gate_episodic` (the test still makes
sense asserting only `allow_episodic is True`).

**`tests/agents/test_depth_toggles.py`**:
- Remove `RAG_TOOL_NAME` from the `from app.agents.subagents._base import
  (...)` import (keep `build_subagent`).
- Delete the `search_destination_knowledge` fake `@lc_tool` fixture function
  (lines ~127-130).
- Delete both `test_assistant_drops_rag_tool_when_allow_rag_false` and
  `test_assistant_keeps_rag_tool_when_allow_rag_true` in full, along with the
  `# RAG tool gating in assistant node` section comment above them.
- Update the module docstring bullets: remove "Assistant node drops the RAG
  tool when allow_rag=False." / "...keeps the RAG tool when allow_rag=True."
  Keep the `get_weather` fake tool only if still referenced elsewhere in the
  file (it is not, after the two RAG tests are removed — delete it too as an
  orphan of this change).
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py tests/agents/test_context_episodic.py tests/agents/test_depth_toggles.py -x</verify>
  <done>No `allow_rag` / `RAG_TOOL_NAME` symbol remains in app/agents/; all three test files pass.</done>
</task>
```

#### Task 1.3 — Delete the RAG tool and its registry wiring

```xml
<task id="1.3" wave="1">
  <files>app/tools/rag_tools.py, app/tools/registry.py, tests/tools/test_rag_tools.py, tests/agents/test_subagents.py</files>
  <action>
- Delete `app/tools/rag_tools.py` entirely.
- In `app/tools/registry.py`: remove the line
  `from app.tools.rag_tools import RAG_TOOLS` (line 18), and in
  `TOOLS_BY_DOMAIN["concierge"]` change
  `PLACE_TOOLS + WEATHER_TOOLS + RAG_TOOLS + ROUTING_TOOLS + TIP_TOOLS`
  to `PLACE_TOOLS + WEATHER_TOOLS + ROUTING_TOOLS + TIP_TOOLS`.
- Delete `tests/tools/test_rag_tools.py` entirely (it only tests the
  deleted tool's args_schema).
- In `tests/agents/test_subagents.py`: delete the
  `test_concierge_has_rag_tool` function at the end of the file (it asserts
  `"search_destination_knowledge" in names`).
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagents.py tests/tools/ -x</verify>
  <done>Concierge tool list no longer includes any RAG tool; deleted test file is gone; remaining tool tests pass.</done>
</task>
```

#### Task 1.4 — Strip RAG out of the eval harness

```xml
<task id="1.4" wave="1">
  <files>eval/metrics.py, eval/run_eval.py, tests/eval/test_eval_smoke.py, eval/datasets/rag.json</files>
  <action>
- In `eval/metrics.py`: delete the `retrieval_hit_rate` function and the
  `ragas_faithfulness` function in full (both are RAG-only metrics). Keep
  `routing_accuracy`. Update the module docstring: drop "plus an optional
  RAGAS faithfulness wrapper used only by real-model runs."
- In `eval/run_eval.py`: delete the `run_retrieval_eval` function in full and
  the `RETRIEVAL_THRESHOLD = 0.8` constant. Keep `ROUTING_THRESHOLD`,
  `load_dataset`, `run_routing_eval`, and `main()` (which only exercises
  routing already).
- In `tests/eval/test_eval_smoke.py`: delete the `test_retrieval_eval_pipeline`
  function in full (it imports `app.rag.embeddings.get_vector_store` and the
  now-deleted `run_retrieval_eval`/`RETRIEVAL_THRESHOLD`). Keep the two
  routing tests and the `from langchain_core.documents import Document`
  import removal check — if `Document` becomes unused after deleting the
  retrieval test, remove that import too.
- Delete `eval/datasets/rag.json` (only consumer was the deleted retrieval
  eval test).
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/ -x</verify>
  <done>Eval harness has no retrieval/RAGAS surface left; routing eval smoke test still passes.</done>
</task>
```

#### Task 1.5 — Annotate the historical spec as superseded

```xml
<task id="1.5" wave="1">
  <files>specs/travel-agent/PLAN.md</files>
  <action>
This is a historical planning doc (Vietnamese) — do not rewrite or delete its
RAG content wholesale (auto-correct-scope.md guardrails favor annotation over
destructive edits to already-shipped plan records). Add a single short note
directly under the `### Phase 4 — RAG (pgvector)` heading (around line 270)
and directly under `#### Task 8.1 — Eval harness (RAGAS + LLM-as-judge + CI
gate)` (around line 368):

```
> **SUPERSEDED (2026-07-04):** RAG was fully removed — see
> `specs/remove-rag-feature/`. The agent now relies on tool calls only.
```

Leave every other line in the file untouched (task history, file tree, risk
notes) — this is an audit trail, not live documentation.
  </action>
  <verify>grep -c "SUPERSEDED (2026-07-04)" specs/travel-agent/PLAN.md</verify>
  <done>Both RAG sections carry a superseded annotation; nothing else in the file changed (git diff shows only 2 additions).</done>
</task>
```

#### Task 1.6 — Drop RAG-only pip dependencies

```xml
<task id="1.6" wave="1">
  <files>requirements-ai.txt</files>
  <action>
Remove the RAG-only dependency lines and their comment header from
`requirements-ai.txt`:

```
# RAG — pgvector via langchain-postgres.
langchain-postgres>=0.0.12
pgvector>=0.3,<1.0
```

Also remove the inline comment `# RAG chunking (not pulled transitively by
langchain 1.x)` after `langchain-text-splitters>=0.3,<1.0` and delete that
line entirely — `langchain_text_splitters.RecursiveCharacterTextSplitter` is
only used by `app/rag/ingest.py`, which is deleted in Task 3.1.

Do NOT remove `langgraph-checkpoint-postgres` — verified (via
`importlib.metadata.requires("langgraph-checkpoint-postgres")`) that it only
needs `psycopg`/`psycopg-pool`/`orjson`, not the `pgvector` or
`langchain-postgres` pip packages; it backs `app/memory/store.py`'s
`PostgresStore`, which is unaffected by this removal.
  </action>
  <verify>cd apps/api && ! grep -q "langchain-postgres\|^pgvector\|langchain-text-splitters" requirements-ai.txt</verify>
  <done>requirements-ai.txt has no RAG-only packages; langgraph-checkpoint-postgres line untouched.</done>
</task>
```

### Wave 2 — relocate memory's embeddings import (depends on Task 1.1)

#### Task 2.1 — Point `memory/store.py` at the relocated embeddings helper

```xml
<task id="2.1" wave="2">
  <files>app/memory/store.py</files>
  <action>
Change the import on line 33 from:
```python
from app.rag.embeddings import EMBED_DIM, get_embeddings
```
to:
```python
from app.core.embeddings import EMBED_DIM, get_embeddings
```
Update the module docstring (lines 12-17): replace "the shared
``app.rag.embeddings`` model" with "the shared ``app.core.embeddings``
model". No other logic in this file changes — `_index_config()`,
`open_store()`, `get_store()`, and all the `upsert_*`/`search_*` functions
are untouched.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/memory/ -x</verify>
  <done>memory/store.py imports from app.core.embeddings; all memory tests still pass (semantic index behavior unchanged, same EMBED_DIM/get_embeddings).</done>
</task>
```

### Wave 3 — delete the RAG package itself (depends on all of Wave 1 + Wave 2)

#### Task 3.1 — Delete `app/rag/`, `tests/rag/`, and the ingestion script; final sweep

```xml
<task id="3.1" wave="3">
  <files>app/rag/embeddings.py, app/rag/ingest.py, app/rag/retriever.py, app/rag/__init__.py, tests/rag/conftest.py, tests/rag/test_embeddings.py, tests/rag/test_retriever.py, scripts/ingest_rag.py</files>
  <action>
Delete the entire `app/rag/` package (all four files) and the entire
`tests/rag/` directory (all three files), and delete `scripts/ingest_rag.py`.

By this point (Wave 1 + Wave 2 complete): `app/memory/store.py` imports from
`app.core.embeddings` (Task 2.1), `app/tools/rag_tools.py` is already deleted
(Task 1.3), `eval/run_eval.py`'s retrieval function is already deleted (Task
1.4) — so nothing in `app/`, `tests/`, `eval/`, or `scripts/` still imports
`app.rag.*`. Confirm this before deleting:

```bash
grep -rn "app\.rag\b" apps/api/app apps/api/tests apps/api/eval apps/api/scripts
```
Expected: no output. If anything shows up, stop and fix that reference first
— do not delete `app/rag/` out from under a live import.
  </action>
  <verify>cd apps/api && grep -rn "app\.rag\b\|rag_tools\|RAG_TOOLS\|RAG_TOOL_NAME\|allow_rag\|search_destination_knowledge" app tests eval scripts; test $? -ne 0 && make test</verify>
  <done>app/rag/, tests/rag/, and scripts/ingest_rag.py no longer exist; grep for every RAG symbol across app/tests/eval/scripts returns nothing; full `make test` suite is green.</done>
</task>
```

## 5. Wave summary

| Wave | Tasks | Parallelism |
|------|-------|-------------|
| 1 | 1.1 embeddings relocation (new file), 1.2 context/constants/_base gating removal, 1.3 rag_tools + registry, 1.4 eval harness, 1.5 spec annotation, 1.6 requirements | 6 parallel |
| 2 | 2.1 memory/store.py import switch | single (depends on 1.1) |
| 3 | 3.1 delete app/rag/, tests/rag/, scripts/ingest_rag.py + final sweep | single (depends on all of Wave 1 + 2.1) |

Wave 1 file sets are disjoint (verified above — no task shares a path with another in the same wave). Wave 2 must wait for Task 1.1 (new module must exist before `memory/store.py` imports it) and, to be safe, all of Wave 1 (so nothing else is mid-edit). Wave 3 must wait for Wave 2 (nothing may still import `app.rag.*`).

## 6. Risks

- **Import-order hazard**: deleting `app/rag/` before `memory/store.py` (Task 2.1) or `rag_tools.py` (Task 1.3) stop importing from it would 500 the whole agent graph at build time (`core/lifespan.py` builds the graph once at startup). Mitigated by the Wave 3 dependency ordering and the explicit pre-delete grep in Task 3.1.
- **Orphaned pgvector-created tables in Postgres deployments**: `langchain-postgres`'s PGVector auto-creates collection tables (`travel_pois`) at runtime; these aren't dropped by this plan (no Alembic model owns them). Non-blocking — an operator can manually drop the `travel_pois` collection in Postgres if desired; out of scope per `## 2. Non-goals`.
- **`langchain-postgres`/`pgvector` pip package removal (Task 1.6)**: double-checked `langgraph-checkpoint-postgres` doesn't transitively need them (verified via `importlib.metadata.requires`) — if that check was wrong, `make test-docker` (Postgres suite) would fail on import; the plan's `Success Criteria` only requires SQLite `make test`, so also run `make test-docker` once after Wave 3 as an extra safety net before considering this fully done.

## 7. Status Log

- 2026-07-04 — Plan drafted from `specs/remove-rag-feature/SUMMARY.md` + `research-brief.md`. Status: proposed.
- 2026-07-04 — Status: active. Isolated on branch `chore/remove-rag-feature` (in-place `git switch -c` off `v3`). Baseline: 1252 tests passing (`.env` aside).
- 2026-07-04 — Wave 1 complete (6 parallel tasks). Commits: `dbd8212` (1.1), `d4bb3a0` (1.5), `e0bb019` (1.2+1.4+1.6 — shared-index commit collision, see SUMMARY.md Harness-Delta; contents verified correct via direct diff review), `8366805` (1.3). Spec-compliance verified by direct `git diff`/`git show` inspection (reviewer subagents couldn't report back — see Harness-Delta). Lint clean; suite green (1235 passed, `tests/rag/` temporarily excluded pending Wave 3).
- 2026-07-04 — Wave 2 complete. Commit: `72a6534` (2.1). Memory tests: 37 passed.
- 2026-07-04 — Wave 3 complete. Commit: `3d0dc6a` (3.1). Final sweep clean; full suite 1235 passed, 0 failed. RAG feature removal done.
- 2026-07-04 — Final adversarial `/correctness-review` (BASE=b7a7544, HEAD=3d0dc6a) found a real gap the plan's `<files>` scope never anticipated: `app/prompts/concierge/v5.md` (the production-active concierge system prompt) still instructed the LLM to "retrieve destination notes from the knowledge base" and quote them as source-of-truth, with no tool left to back that instruction. Fixed out-of-plan-scope (files added retroactively below) by creating `app/prompts/concierge/v6.md` (v5 with the two RAG-referencing clauses reworded to a single tool-results-are-truth grounding tier) and bumping `active.yaml`'s `concierge: 5 → 6`. See SUMMARY.md `### Deviations` for full rationale. **Files retroactively in scope:** `app/prompts/concierge/v6.md` (new), `app/prompts/active.yaml`.
- 2026-07-04 — Final `/intent-review` (fresh subagent blind to this PLAN.md, model: opus, BASE=b7a7544, HEAD=e6cacbe, oracle = SUMMARY.md `### Intent`) found 2 findings: a `gap` (fixed, commit `ab686d9`) — canonical architecture docs (`WORKFLOW.md`, `WORKFLOW_DIAGRAM.md`, `TECHSTACKS.md`, `CLAUDE.md`, `AGENTS.md`) still described RAG as a live capability, contradicting the user's explicit "Full deletion" intent; and a `drift` (advisory, not fixed) — the pgvector-extension migration's docstring rationale is now stale-worded but the migration itself correctly stays per `## 2. Non-goals`. Separately flagged to the user (not a finding against this diff's intent): `specs/web-content-enrichment/` is an unexecuted forward-looking spec whose premise assumes RAG still exists — left untouched, needs a human decision. Status: all review gates (spec, correctness, intent) passed; ready for `finishing-a-development-branch`.
