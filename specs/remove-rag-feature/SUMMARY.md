# remove-rag-feature — Summary

Lane: normal
Confidence: high
Reason: Removes existing, request-time behavior (RAG is a live agent tool wired into the concierge sub-agent, gated by tier, with test + eval coverage) and cuts across multiple domains (tool registry, agent gating/context, memory subsystem's shared embeddings dependency, eval harness, specs docs) — 2 flags fired (existing-behavior, multi-domain). No hard gate: no auth/authz, no required DB migration or data loss (no ORM-owned RAG tables — pgvector-created collections are runtime/PGVector-managed, not Alembic-managed; the existing `enable_pgvector_extension` migration is left as a harmless no-op, not reverted), no audit/security surface, no external-provider *behavior* change (a call path is removed, not modified), no validation weakened, no high-blast-radius file touched.
Flags: existing-behavior, multi-domain
Affects: app/tools/registry.py (concierge tool list), app/agents/constants.py + context.py + subagents/_base.py (RAG_TOOL_NAME / allow_rag gating), app/memory/store.py (imports get_embeddings/EMBED_DIM from app.rag.embeddings — needs refactor, not deletion, of that dependency), app/rag/* (deleted), tests/rag/ + tests/tools/test_rag_tools.py (deleted), eval/ RAGAS harness + scripts/ingest_rag.py (deleted or descoped), specs/travel-agent/PLAN.md (RAG sections marked superseded)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<paste the original request, verbatim>

Turn 1 (via `/feature-intake` command args): "remove rag feature for project now. For now, we use tool almost, RAG will be defer."

Turn 2 (clarifying question — scope): Asked whether RAG should be fully deleted now or just disabled/unwired to be reversible later, given "RAG will be defer" could mean either. Options offered: "Disable only" (recommended), "Full deletion", "Archive + unwire".

Turn 2 (user answer): "Full deletion" — selected explicitly from the options above.

## What changed

RAG feature fully removed on branch `chore/remove-rag-feature` via `/subagent-driven-development`, all 3 waves complete: (1) relocated the shared embeddings helper to `app/core/embeddings.py`, removed `allow_rag`/`RAG_TOOL_NAME` gating, deleted the RAG tool wrapper + concierge registry wiring, stripped retrieval/RAGAS surface from the eval harness, annotated `specs/travel-agent/PLAN.md`'s RAG sections as superseded, and dropped RAG-only pip dependencies; (2) pointed `app/memory/store.py` at the relocated embeddings helper; (3) deleted `app/rag/`, `tests/rag/`, and `scripts/ingest_rag.py`. Full suite: 1235 passed, 0 failed. Grep for every RAG symbol across `app/`, `tests/`, `eval/`, `scripts/` returns nothing but one harmless docstring mention.

### Rationale

User explicitly chose full deletion over the reversible "disable only" default after being shown the tradeoff (harder-to-reverse diff, touches `app/memory/store.py`'s shared embeddings import). Full deletion is now the confirmed scope, not an assumption.

### Alternatives considered

- Disable only (remove `RAG_TOOLS` from the concierge's tool registry, leave `app/rag/`, tests, and eval untouched) — rejected by user in favor of full deletion.
- Archive + unwire (park `app/rag/` code in an unimported location) — rejected by user in favor of full deletion.

### Deviations

- Rule 1 — Fixed an orphaned docstring phrase in `eval/run_eval.py` ("Runs the routing and retrieval datasets" → "Runs the routing dataset") after deleting the retrieval-eval function. `apps/api/eval/run_eval.py`. Commit `e0bb019`.
- Rule 3 — `risk-corroboration.sh`'s `weakening-validation` hard gate fired on deleting `assert "search_destination_knowledge" in names` (test for the deleted RAG tool). Downgraded via `RISK_WARN_CATEGORIES="weakening-validation"` for that one commit — matches this repo's documented false-positive pattern (memory: `weakening-validation-gate-on-removed-assert` — deleting any assert/raise line trips this gate even for in-scope deletions). `apps/api/tests/agents/test_subagents.py`. Commit `8366805`.
- Rule 3 (implicit, ruff-on-edit) — the now-orphaned `lc_tool` import in `tests/agents/test_depth_toggles.py` was auto-stripped after deleting the two RAG-gating tests and their fixture tools. Commit `e0bb019`.
- Rule 3 — `risk-corroboration.sh`'s `weakening-validation` hard gate fired again on Task 3.1 (deleting whole test files under `tests/rag/` that contain `assert` statements). Same documented false-positive pattern; downgraded via `RISK_WARN_CATEGORIES="weakening-validation"` for that one commit. `apps/api/tests/rag/*`. Commit `3d0dc6a`.
- Rule 1 — Final `/correctness-review` (adversarial, whole-diff, model: opus, independent of implementers) found the active concierge prompt (`app/prompts/concierge/v5.md`) still instructed the LLM to "retrieve destination notes from the knowledge base" and quote them as source-of-truth, with no tool left to back it (`search_destination_knowledge` was deleted from the concierge's tool list in Task 1.3). Scored 75/100 by an independent cheap-model scorer (just under the pipeline's default 80 threshold — the score was pulled down because the stale prompt file itself carries no diff lines, a scoring-rubric artifact, not doubt about reality). I independently re-verified by reading the live prompt file directly and treated it as real despite the sub-80 score. Fixed out-of-plan-scope (not in PLAN.md's original `<files>` — see PLAN.md Status Log entry): created `app/prompts/concierge/v6.md` (collapses the "retrieved facts / live tools" two-tier grounding into one tool-results-are-truth tier) and bumped `active.yaml`'s `concierge: 5 → 6`. `apps/api/app/prompts/concierge/v6.md`, `apps/api/app/prompts/active.yaml`. Commit `e6cacbe`.

### Advisory Findings

- [Score 25/100 — below the 80 threshold, not fixed] Correctness review also flagged (P3, low confidence): a Postgres-checkpointed LangGraph thread interrupted mid-tool-call to `search_destination_knowledge` at the exact moment this diff deployed could fail to resume cleanly (ToolNode no longer recognizes the tool name). Independent scorer confirmed low confidence: this repo is a mock/demo backend (per root CLAUDE.md) without real persistent production checkpoint state, and the trigger condition (a thread paused between tool-call emission and tool-result production, at the precise moment of this deploy) is highly contrived. No action taken — advisory only.

### Post-merge CI failure (found after PR #60 opened)

CI (`.github/workflows/`) failed on the `api` job — a clean `pip install` from `requirements.txt` +
`requirements-ai.txt` (unlike my long-lived local dev venv, which had leftover cached packages)
surfaced `NameError: name 'np' is not defined` inside `langchain_core.embeddings.fake.
DeterministicFakeEmbedding._get_embedding`, cascading into ~22 test failures across
`tests/memory/`, `tests/core/test_embeddings.py`, and `tests/agents/test_memory.py` — every path
that embeds without an LLM key (the CI/test default). Root cause: `pgvector` and
`langchain-postgres` (both removed in Task 1.6) each declare `numpy` as a direct dependency;
`langchain-core` itself does not, even though `DeterministicFakeEmbedding` needs `numpy` at
runtime. Removing those two packages silently dropped `numpy` from a fresh install. My local venv
never showed this because `pip install -r` doesn't uninstall now-unlisted transitive packages —
numpy stayed cached from before this branch existed, masking the regression through every local
test run in this session (Waves 1–3, both correctness/intent reviews, and the pre-push
test-runner). Only CI's clean-room install caught it.

Fixed: added an explicit `numpy>=1.21,<3` line to `requirements-ai.txt` with a comment explaining
why. Verified in a **genuinely fresh venv** (`python3 -m venv` + `pip install -r requirements.txt
-r requirements-ai.txt`, not the cached local one) — reproduced the failure without the pin,
confirmed 1235 passed / 0 failed with it. Commit `74abb23`, pushed to PR #60.

- Rule 3 — missing dependency (`numpy`), added to `requirements-ai.txt` with rationale above. `apps/api/requirements-ai.txt`. Commit `74abb23`.
- Rule 3 — `risk-corroboration.sh`'s `external-provider` hard gate fired on the same commit (generic pattern-match on any `requirements*.txt` diff). This is a transitive-dependency restoration, not a new external service/AI-provider integration — downgraded via `RISK_WARN_CATEGORIES="external-provider"` for that one commit.

**Harness-Delta (added):** local dev venvs that predate a branch can mask a dependency-removal
regression that only a clean install (CI, or a fresh venv) will catch — `pip install -r` never
uninstalls packages dropped from a requirements file. Worth a standing practice: when a plan task
removes a top-level pip dependency, verify in a throwaway fresh venv, not just the shared dev one,
before considering the task's tests authoritative.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| baseline (pre-wave) | `pytest -q` (with `.env` aside) | 0 | 1252 passed — clean baseline before any change |
| Wave 1 spec compliance | manual `git diff`/`git show` inspection per task vs. `b7a7544` (reviewer subagents couldn't report back — no `SendMessage` tool on the `reviewer` agent type in async/named mode; verified directly instead) | 0 | All 6 tasks byte/logic-match their spec; no extra/missing changes |
| Wave 1 lint | `ruff check` on all 13 touched Python files | 0 | All checks passed |
| Wave 1 full suite | `pytest -q --ignore=tests/rag` (with `.env` aside) | 0 | 1235 passed, 0 failed (tests/rag/ temporarily excluded — collides on module basename with new tests/core/test_embeddings.py until Wave 3 deletes it) |
| Wave 2 memory tests | `pytest tests/memory/ -q` (with `.env` aside) | 0 | 37 passed — semantic index works via relocated app.core.embeddings |
| Wave 3 pre-delete sweep | `grep -rn "app\.rag\b" app tests eval scripts` | 0 (matches only inside files being deleted) | Confirmed safe to delete app/rag/, tests/rag/, scripts/ingest_rag.py |
| Wave 3 final sweep | `grep -rn "app\.rag\b\|rag_tools\|RAG_TOOLS\|RAG_TOOL_NAME\|allow_rag\|search_destination_knowledge" app tests eval scripts` | 0 | Only 1 harmless docstring mention (app/core/embeddings.py's relocation note) remains |
| Wave 3 full suite | `pytest -q` (with `.env` aside) | 0 | 1235 passed, 0 failed — no collection errors, tests/rag/ collision resolved |
| Post-correctness-review prompt fix | `pytest tests/prompts/ tests/agents/test_state_system_prompt.py -q` + full suite (with `.env` aside) | 0 | 13 passed + 1235 passed — concierge v6 loads as active, no "knowledge base" reference, exclude_names test intact |
| Post-intent-review docs fix | `pytest -q` (with `.env` aside) | 0 | 1235 passed, 0 failed — docs-only change, no code touched |
| CI failure repro + fix | `python3 -m venv <fresh>; pip install -r requirements.txt -r requirements-ai.txt; pytest -q` in a genuinely fresh venv (not the cached local one) | 1 (repro, pre-fix) → 0 (post-fix) | Reproduced the `NameError: name 'np' is not defined` CI failure locally; 1235 passed / 0 failed after adding `numpy>=1.21,<3` to requirements-ai.txt |

### Intent Findings

Final `/intent-review` (fresh subagent, blind to PLAN.md, model: opus, BASE=b7a7544 HEAD=e6cacbe, oracle = this file's `### Intent` block) found 2 findings:

- **#1 gap (fixed)** — "remove rag feature for project now" + the user's explicit **"Full deletion"** choice. The diff deleted RAG from code but left it described as a live capability in this project's canonical architecture docs: `WORKFLOW.md` (whole outdated `allow_rag` table row, tool-filter description, concierge tool list, "RAG · MCP · observability" section, `embedding_model` "Drives" column), `WORKFLOW_DIAGRAM.md` (mermaid node + tool-inventory row), `TECHSTACKS.md` (2 dependency rows for packages this diff removed from `requirements-ai.txt`), `CLAUDE.md` and `AGENTS.md` (layout line naming `rag/` as a directory). Fixed: removed all of it. Commit `ab686d9`. Historical `specs/<slug>/` records for other already-shipped features were correctly left untouched (frozen audit trail, not living docs — `specs/travel-agent/PLAN.md` already got its own SUPERSEDED annotation in commit `d4bb3a0`).
- **#2 drift, behaviorally-equivalent (advisory, not fixed)** — the `enable_pgvector_extension_postgres_only` Alembic migration's docstring rationale ("so RAG tables can use the vector type") is now stale-worded, but the migration itself must stay (still needed by `memory/store.py`'s own pgvector-backed `PostgresStore` semantic index — confirmed in Non-goals). Not fixed: editing an existing Alembic migration file, even just a comment, is unnecessary risk for a purely cosmetic staleness with no behavioral impact; `## 2. Non-goals` already documents that this migration is intentionally retained.

**Separately flagged (not a gap/drift/excess against THIS diff's intent, but surfaced to the user directly):** `specs/web-content-enrichment/` (status: `proposed`/`design`, not yet executed) is a *forward-looking* spec that explicitly plans to add a `search_web_guides` tool "alongside the existing pgvector `search_destination_knowledge`" — its premise now assumes a deleted foundation. Redesigning or archiving that spec is a judgment call outside this task's scope; left untouched and called out to the user for a decision.

### Rollback

Commits on `chore/remove-rag-feature` (oldest first): `dbd8212` (Task 1.1), `d4bb3a0` (Task 1.5), `e0bb019` (Tasks 1.2+1.4+1.6, shared-index collision — see Harness-Delta), `8366805` (Task 1.3), `72a6534` (Task 2.1), `3d0dc6a` (Task 3.1), `e6cacbe` (correctness-review fix: stale concierge prompt), `ab686d9` (intent-review fix: stale architecture docs), `74abb23` (post-PR CI fix: missing numpy dependency).

- Full revert: `git revert --no-commit ab686d9 e6cacbe 3d0dc6a 72a6534 8366805 e0bb019 d4bb3a0 dbd8212 && git commit`
- Or reset the branch to its base: `git reset --hard b7a7544` (only before merging/pushing).

### Harness-Delta

- backlog — `.claude/hooks/render-plan-on-write.sh` looks for the renderer at
  `$REPO_DIR/skills/visual-planner/render_plan.py`, but it actually lives at
  `.claude/skills/visual-planner/render_plan.py`. The `[ -f "$RENDER" ] || exit 0`
  guard makes this fail silently — no PLAN.html, no error surfaced. Rendered
  `PLAN.html` manually for this task instead. Not fixed here (touching
  `hooks/*` is a Rule-4 high-blast-radius file per `auto-correct-scope.md`) —
  flag via `/compound` for a human to confirm the intended path before patching.
- backlog — Wave 1's 6 subagents shared one working tree/git index (no per-task
  worktree isolation). A plain `git commit` commits the *entire* staged index,
  not just the files a given subagent just `git add`ed — so whichever subagent's
  `git commit` ran first (here, Task 1.6's) swept in Task 1.2's and Task 1.4's
  already-staged-but-uncommitted files into one mislabeled commit (`e0bb019`,
  titled "drop RAG-only pip dependencies" but containing 3 tasks' work). File
  *contents* were unaffected (tasks had zero file overlap, verified via diff) —
  only commit attribution/traceability suffered, breaking the "commit sha per
  task" contract in `rules/wave-parallelism.md`. Flag via `/compound`: either
  serialize same-wave commits, or give each wave-parallel task its own worktree.
- backlog — Two implementer subagents (task-1-1, task-1-2) self-marked their
  TaskUpdate status `completed` despite reporting `DONE_WITH_CONCERNS`; per
  `subagent-driven-development`, only the controller should set `completed`
  (after spec + quality review). Reverted both to `in_progress` manually each
  time. Flag via `/compound`: the implementer-prompt template should explicitly
  say "do not call TaskUpdate to mark yourself completed."
- backlog — All 6 `reviewer`-type spec-compliance review subagents (dispatched
  named/async per this session's pattern) went idle without ever delivering
  their verdict text — the `reviewer` agent type has no `SendMessage` tool, so
  once spawned as a named/addressable teammate it has no channel to report
  back proactively (unlike `general-purpose` implementers, which do have
  `SendMessage`). Worked around by performing the spec-compliance diff review
  directly instead of through the subagents. Flag via `/compound`: either add
  `SendMessage` to the `reviewer` type, or dispatch review agents anonymously
  (no `name`) so results arrive via the standard task-notification channel.
