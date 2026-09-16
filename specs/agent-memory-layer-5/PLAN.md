---
slug: agent-memory-layer-5
status: proposed
owner: Minh Tran
created: 2026-09-16
---

# Agent Memory — Layer 5 (P0 slice)

## 1. Motivation

Per `design.md` §1, the playbook's Layer 5 is absent here and two of its consequences block
launch: the model cannot tell a fresh stored fact from a stale one (`state.py` asks it to,
`nodes.py` never gives it the date), and a traveller has no route to inspect or delete what
the agent stored about them — including the standing instructions that are re-injected into
every system prompt. A third, smaller gap: history compression triggers on a message count,
not on context pressure.

This plan carries **P0#2, P0#3 and P0#4**. P0#1 (the memory guard) stays in PR #214 and is a
merge dependency, not a task here — see `SUMMARY.md` → Hard-gate narrowing.

## 2. Non-goals

- Automatic expiry / supersession / contradiction detection (P1, `design.md` §6).
- Any change to `app/memory/extractor.py` or `extraction_runner.py` — that is #214's surface.
- The deferred poisoning eval golden (#214 Task 4.1).
- Knowledge graph, skill promotion, Mem0/Zep migration, hierarchical summarization,
  storage tiering (`design.md` §6, refused).

## Global Constraints

- **Identity is never client-supplied.** Every `/memory` route resolves `user_id` from
  `CurrentUserDep` only. A `user_id` reaching a store namespace from a path segment, query
  parameter, or request body is a blocking defect, not a review nit.
- **No new table, no Alembic migration, no new runtime dependency, no scheduler.** If a task
  appears to need one, stop and escalate — the premise is wrong.
- **Additive prompt changes only.** §4.1 may append a parenthetical and one clause to the
  preferences block. Rewording the base system prompt is out of scope.
- **Never remove existing behavior.** The token budget ORs with the message-count threshold;
  it does not replace it. Removing a branch here trips `remove-functionality`.
- **One store instance.** Routers reach the store via `GraphDep` → `graph.store`. Never call
  `open_store` / `get_store` in request scope (`lifespan.py:116-135`).
- **Absent data renders as absent.** A memory row without a parseable `updated_at` renders
  with no age suffix. Never substitute "unknown", a default date, or `now`.
- **Nothing that changes daily goes into the system-prompt prefix.** Fact age is a
  month-granularity bucket, never a day count. Prompt caching is implicit, on, and measured at
  71.9%, and the preferences/instructions blocks sit *before* `summary`
  (`research-brief.md`; `docs/solutions/agent/prompt-caching-implicit-idle-eviction.md`).
- **Do not use `llm.get_num_tokens_from_messages()`.** `transformers` is absent from this venv,
  so the base implementation raises — including under the test `FakeLLM`. The char/4 estimator is
  the portable option; say so in a comment at the call site.
- **Mount `/memory` under the existing `Tags.agent`.** `Tags` has no `memory` member and adding a
  20th one touches a shared enum read by every router and changes the generated OpenAPI tag list.
  Memory is agent state; the smaller diff is correct here.
- Run `cd apps/api && ../../.venv/bin/ruff check app scripts` and `ruff format` before each
  commit. Node work uses v24 (`export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`).
- Stage and commit as **separate** commands (a PreToolUse hook blocks `git add … && git commit …`).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | This delivery exposes no HTTP route for memory: the OpenAPI document contains no `/memory` path (E001 decision A — P0#3 is deferred until #214 merges) | `.venv/bin/python -m pytest apps/api/tests/api/routes/test_no_memory_route_yet.py -q` | exit 0 |
| SC-2 | A stored preference carries its `updated_at` through typed search, and a missing/unparseable timestamp yields no age rather than a guess | `.venv/bin/python -m pytest apps/api/tests/memory/test_fact_age.py -q` | exit 0 |
| SC-3 | Preferences and standing instructions reach the system prompt with a month-granularity recorded-age suffix, and without one when the timestamp is absent; no rendered age string contains a day count | `.venv/bin/python -m pytest apps/api/tests/agents/test_memory_age_prompt.py -q` | exit 0 |
| SC-4 | Compression triggers on estimated token pressure even when the message count is below threshold, and the message-count trigger still fires | `.venv/bin/python -m pytest apps/api/tests/memory/test_summarize_token_budget.py -q` | exit 0 |
| SC-5 | `delete_memory` removes the row and its pgvector embedding on an indexed Postgres store — a subsequent search returns nothing (regression pin on `store_vectors` `ON DELETE CASCADE`) | `.venv/bin/python -m pytest apps/api/tests/memory/test_memory_delete.py -q` | exit 0 |
| SC-6 | Agent behavior does not regress against the pinned eval baseline | `make eval-check` | exit 0 |

> Scope note: this SC table is the acceptance contract for **this delivery only** (P0#2 + P0#4).
> The P0#3 criteria — `/memory` list + hard-delete routes, generated client types, settings UI —
> are held in §7 and will be renumbered into their own plan when #214 merges. SC-1 exists to pin
> that deferral: it fails the moment a `/memory` route is added to this delivery.

## 4. Tasks

### Task 0.1 — Gate: pin the E001 deferral (wave 0)

- **Files:** apps/api/tests/api/routes/test_no_memory_route_yet.py
- **Action:** `PLAN.md`'s original gate ("confirm #214 is merged") did not pass: PR #214 is OPEN
  with all four CI jobs failing in 3s (evidence in `ESCALATIONS.md` E001). The owner chose
  **decision A** — ship the #214-independent subset and defer P0#3. This task turns that decision
  into a check instead of a comment: add a test asserting the generated OpenAPI document contains
  **no** `/memory` path. It is an anti-regression pin, not a permanent rule — the follow-up plan
  that ships P0#3 deletes this test in its first task, which is exactly the signal that the
  deferral ended deliberately rather than by drift. `list_memory` / `delete_memory` are still
  implemented in Task 1.1; the constraint is that nothing reachable by a user calls them yet.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/routes/test_no_memory_route_yet.py -q`
- **Done:** The test passes against the current app and fails if a `/memory` route is registered.
- **Criteria:** SC-1
- **Interfaces:** Consumes the FastAPI app's OpenAPI document (pre-existing). Produces `apps/api/tests/api/routes/test_no_memory_route_yet.py`.

### Task 1.1 — Store: carry `updated_at`, add `format_age`, `list_memory`, `delete_memory` (wave 1)

- **Files:** apps/api/app/memory/store.py, apps/api/tests/memory/test_fact_age.py, apps/api/tests/memory/test_memory_delete.py
- **Action:** In `store.py`: (a) add `updated_at: str | None = None` to `Preference`,
  `Instruction` and `Episode`, populated in each `from_item` from `item.value.get("updated_at")`;
  (b) add `format_age(updated_at, *, now=None) -> str | None` returning a **month-granularity
  bucket** (`"this month"`, `"a few months ago"`, `"over a year ago"`) and `None` for
  missing/unparseable input — code computes the delta, the model only reads it
  (`docs/solutions/agent/llm-parses-code-computes.md`); the `now` parameter exists so tests
  are deterministic. **Do not return a day count** (`"today"`, `"3 days ago"`): that string
  changes daily inside a cached prompt prefix — see Global Constraints and `research-brief.md`; (c) add `list_memory(store, user_id, kind, *, limit=50) -> list[dict]`
  returning rows that **preserve `key`** (the UI's delete handle — `search_memory` drops it);
  (d) add `delete_memory(store, user_id, kind, key) -> bool` wrapping `store.delete(ns, key)`,
  idempotent, coercing `kind` through `MemoryKind` so an unknown kind raises before it can be
  interpolated into a namespace. Do not change the existing per-kind helpers' signatures.
  Cover deletion against **Postgres**, not only `InMemoryStore`. `research-brief.md` resolved
  the cascade question: `store_vectors` carries
  `FOREIGN KEY (prefix, key) REFERENCES store(prefix, key) ON DELETE CASCADE`
  (`langgraph/store/postgres/base.py:104-112`, langgraph 1.2.6), so one `DELETE FROM store`
  removes the embedding row too. The Postgres test is therefore a **regression pin on that
  cascade**, not an investigation — and it must exercise an *indexed* store, since the cascade
  ships in `VECTOR_MIGRATIONS` and a store created without an index has no `store_vectors` table.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_fact_age.py tests/memory/test_memory_delete.py -q`
- **Done:** Typed search returns `updated_at`; `format_age` returns `None` on absent input; a deleted key is absent from a subsequent search on both backends.
- **Criteria:** SC-2, SC-5
- **Interfaces:** Consumes the LangGraph BaseStore API (pre-existing, external). Produces `format_age`, `list_memory`, `delete_memory` in `apps/api/app/memory/store.py`.

### Task 1.2 — Token-aware compression threshold (wave 1)

- **Files:** apps/api/app/memory/summarizer.py, apps/api/app/core/config.py, apps/api/tests/memory/test_summarize_token_budget.py
- **Action:** Add `summarize_token_budget: int` to `Settings` beside `summarize_threshold`, with
  a conservative default and a short comment naming the 0.85 headroom factor. In
  `should_summarize`, add an **OR** branch: compress when the estimated token count exceeds
  `summarize_token_budget * 0.85`. Estimate deterministically from character length
  (`chars / 4`), counting tool-call arguments as well as `content` — a fan-out turn's tokens
  live in tool payloads, which is the case the message count misses. Do not call a provider
  tokenizer: the decision runs before the model call and the value is a ceiling, not accounting.
  The existing message-count branch must stay reachable and its current tests must pass unmodified.
  Add a one-line comment naming why the framework tokenizer is not used: `transformers` is absent,
  so `BaseLanguageModel.get_num_tokens_from_messages` raises under `FakeLLM`
  (`research-brief.md` → Evidence Ledger).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_summarize_token_budget.py tests/agents/test_memory.py -q`
- **Done:** A short but token-heavy history triggers compression; a long-but-light history still triggers via the count; no existing summarizer test was edited.
- **Criteria:** SC-4
- **Interfaces:** Consumes the application settings object (pre-existing). Produces the token branch in `apps/api/app/memory/summarizer.py` and `summarize_token_budget` in `apps/api/app/core/config.py`.

### Task 2.1 — Render fact age into the system prompt (wave 2)

- **Files:** apps/api/app/agents/nodes.py, apps/api/app/agents/state.py, apps/api/tests/agents/test_memory_age_prompt.py
- **Action:** In `nodes.py:load_context`, render preferences as `- {key}: {text} (recorded {age})`
  and standing instructions as `- {text} (recorded {age})`, using `format_age`; when it returns
  `None`, omit the parenthetical entirely so an untimestamped row renders exactly as it does
  today. The instructions path currently reads through `get_instructions` (dicts) — switch it to
  `search_memory_typed(..., MemoryKind.PROCEDURAL)` so it carries `updated_at`, matching how the
  preferences path already uses the typed API. In `state.py:with_extra_context`, reword the
  preferences block so it names the marker instead of gesturing at staleness the model cannot
  observe: state that each line ends with when it was recorded and that anything older than a few
  months should be confirmed with the traveller before acting. Append only — do not restructure
  the block order or touch the other six context sections.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_memory_age_prompt.py tests/agents/test_memory.py -q`
- **Done:** A timestamped preference and instruction each reach the system prompt with an age suffix; an untimestamped one renders unchanged; the assembled prompt is still a single leading `SystemMessage`.
- **Criteria:** SC-3
- **Interfaces:** Consumes `format_age` from Task 1.1, plus the pre-existing typed search helper. Produces the age-rendered blocks in `apps/api/app/agents/nodes.py` and the reworded preferences clause in `apps/api/app/agents/state.py`.

### Task 3.1 — Eval + prompt-cache regression gate (wave 3)

- **Files:** specs/agent-memory-layer-5/SUMMARY.md
- **Action:** Task 2.1 alters the system prompt of every agent turn, so both behavior **and
  prompt-cache economics** must be re-measured, not assumed. First record the cache baseline and
  then the post-change reading — a cache regression is a silent cost regression that no test
  catches: `cd apps/api && ../../.venv/bin/python -m scripts.cache_hit_report --since 24h`
  (needs `DATABASE_URL`). Then run `make eval-smoke` (18 cases, real agent, no judge — needs
  the Docker db and `apps/api/.env`) to catch a gross regression cheaply, then `make eval-check`
  for the judged run and the regression gate against `eval/baselines/main.json`. Record both in
  SUMMARY `### Verify` with their exit codes. On a drop, re-check the rendered prompt before
  touching the baseline — a baseline edited to accommodate a regression is not a gate.
  Prompt edits are not hot-reloaded: `docker exec api-api-1 touch app/main.py` before evaluating
  against the dev agent.
- **Verify:** `make eval-check`
- **Done:** `make eval-smoke` and `make eval-check` each recorded in SUMMARY `### Verify` with their exit code; `make eval-check` exits 0 against the unmodified `eval/baselines/main.json`.
- **Criteria:** SC-6
- **Interfaces:** Consumes `apps/api/app/agents/state.py` (Task 2.1). Produces eval evidence rows in `specs/agent-memory-layer-5/SUMMARY.md`.

## 5. Risks

Carried from `design.md` §5; the execution-time ones:

| Risk | Handling |
| --- | --- |
| ~~`PostgresStore.delete` may orphan the pgvector embedding row~~ — **resolved by research** | `ON DELETE CASCADE` on `store_vectors(prefix, key)` (langgraph 1.2.6 source). Task 1.1's Postgres test is now a regression pin on the cascade, and must use an *indexed* store |
| Prompt-cache regression from Task 2.1 — silent, no test catches it | Month-granularity bucket (Global Constraints) is the mitigation; Task 4.1 records `cache_hit_report --since 24h` before and after |
| Live DB never checked for `store_vectors` | The cascade was read in source, not executed. Task 1.1's Postgres test is the first execution of it; if the table is absent, stop — the store was created unindexed and delete semantics differ |
| Prompt change (Task 2.1) shifts agent behavior | Task 4.1 is a required gate, not a courtesy |
| Hard delete is irreversible | Confirmation token on delete-all (Task 2.2); recorded in `SUMMARY.md` → Rollback |
| A third `status: active` plan mis-binds the blast-radius and lane hooks | This plan ships `status: proposed`. `agent-memory-layer-5` sorts alphabetically **before** `gh-193-…` and `place-category-meta`, both currently active, so flipping it to `active` prematurely captures their gates |
| `.env` in `apps/api` reddens the local test suite | Override `DATABASE_URL` to sqlite for unit runs; never pass an empty `OPENAI_API_KEY` in a worktree without `.env` |

## 6. Deferred — P0#3, blocked on PR #214 (E001 decision A)

The three tasks below are **written and reviewed but not executed in this delivery**. They are
fenced deliberately: per `rules/plan-format.md`, a task section inside a code fence is treated as
an illustration, so the renderer, the `subagent-driven-development` Step-0 gate and
`hooks/blast-radius-check.sh` all ignore them. That is the mechanism that keeps them out of this
run's scope without losing the specification.

**Unblock procedure** when #214 merges: run its guard tests at the new base, open a follow-up spec
(or a second PLAN in this one), unfence these three tasks (D.1–D.3), renumber them and their `SC` rows into that
plan's own table, and delete `apps/api/tests/api/routes/test_no_memory_route_yet.py` (the SC-1 pin
from Task 0.1) in the same change.

Their original success criteria, to be renumbered on unfencing:

- `GET /memory` returns the caller's own three kinds; cross-user access and anonymous access are rejected.
- `DELETE /memory` without `confirm=delete-all` deletes nothing.
- The settings page lists all three kinds with no hardcoded user-facing string.
- The generated OpenAPI client types include the new routes.

```markdown
### Task D.1 — `/memory` routes: list and hard-delete

- **Files:** apps/api/app/routers/memory.py, apps/api/app/schemas/memory.py, apps/api/app/routers/main.py, apps/api/tests/api/memory/test_memory_routes.py, apps/api/tests/api/memory/test_memory_delete_all_guard.py
- **Action:** New router with three routes: `GET /memory` (all three kinds for the caller, rows
  `{kind, key, text, updated_at, age}`), `DELETE /memory/{kind}/{key}` (hard delete, 204 whether
  or not the key existed), and `DELETE /memory` (delete-all, **requires** `confirm=delete-all`;
  without it, delete nothing and return 400). Resolve identity from `CurrentUserDep` and from
  nowhere else — never from the path, query, or body; this is the property `memory_tools.py`
  protects via `InjectedState`, and the REST surface must not reopen it. Reach the store through
  `GraphDep` → `graph.store`; never construct one per request. `kind` is validated against
  `MemoryKind`; an unknown kind is 422, not a namespace lookup. Use `tags=[Tags.agent]` — do not
  add a `Tags` member — and follow the `app/routers/feedback.py` shape
  (`APIRouter(prefix=..., tags=..., responses=error_responses(422))`). Register the router in
  `app/routers/main.py`. Tests must cover: unauthenticated → 401; user A cannot see or delete
  user B's rows; delete-all without the token is a no-op.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/memory -q`
- **Done:** `GET /memory` returns rows for all three kinds; `DELETE /memory/{kind}/{key}` returns 204 on both an existing and a missing key; `DELETE /memory` without the token returns 400 and leaves the row count unchanged; an anonymous request to any of the three returns 401; user A's token returns 0 of user B's rows.
- **Criteria:** (renumber on unfencing)
- **Interfaces:** Consumes `list_memory`, `delete_memory` and `format_age` (Task 1.1), plus the pre-existing auth and graph request dependencies. Produces `apps/api/app/routers/memory.py` and `apps/api/app/schemas/memory.py`.

### Task D.2 — Regenerate the OpenAPI client types

- **Files:** apps/web/src/lib/api/schema.d.ts, apps/api/tests/api/routes/test_openapi_memory.py
- **Action:** Regenerate `schema.d.ts` from the updated OpenAPI document using the repo's
  existing codegen command — do not hand-edit it. Add a backend test asserting the three
  `/memory` operations appear in the generated OpenAPI schema, so a future route rename cannot
  silently desync the client.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/routes -q -k memory`
- **Done:** `schema.d.ts` contains all three `/memory` operation ids, and re-running the codegen command leaves the file byte-identical (`git diff --exit-code apps/web/src/lib/api/schema.d.ts` exits 0).
- **Criteria:** (renumber on unfencing)
- **Interfaces:** Consumes `apps/api/app/routers/memory.py` (Task 2.2). Produces a regenerated `apps/web/src/lib/api/schema.d.ts`.

### Task D.3 — Settings → Memory page

- **Files:** apps/web/src/app/settings/memory/page.tsx, apps/web/src/app/settings/memory/page.test.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** New route (there is no `settings` route today, so this is a new page). Three
  sections — Preferences, Standing instructions, Past trips — each row showing the text, when it
  was recorded, and a delete control; plus a delete-all action behind an explicit confirmation
  that sends `confirm=delete-all`. Every user-visible string goes through `messages/en.json` and
  `messages/vi.json`; hardcoded copy is a blocking defect. Use the generated types from Task 3.1
  rather than hand-written response shapes. Node v24 for all pnpm work.
- **Verify:** `pnpm --dir apps/web test -- src/app/settings/memory`
- **Done:** The page renders one section per kind; the per-row delete control issues `DELETE /memory/{kind}/{key}` and the delete-all control issues `DELETE /memory?confirm=delete-all`; every user-visible string resolves through a key present in both `en.json` and `vi.json`.
- **Criteria:** (renumber on unfencing)
- **Interfaces:** Consumes `apps/web/src/lib/api/schema.d.ts` (Task 3.1) and `apps/api/app/routers/memory.py` (Task 2.2). Produces `apps/web/src/app/settings/memory/page.tsx` and the new i18n keys.
```

## 7. Status Log

- 2026-09-16 — Intake (`SUMMARY.md`): high-risk / high confidence. Owner narrowed the hard gate
  with three scope decisions: all three memory kinds, hard delete, PR #214 as a dependency
  rather than a merge.
- 2026-09-16 — `design.md` written and approved.
- 2026-09-16 — This plan drafted, `status: proposed`.
- 2026-09-16 — `research-brief.md` written (xia2, Deep). Both open external-surface questions
  answered, and the brief forced three plan edits: (1) `format_age` returns a month bucket, not a
  day count, to protect the 71.9% prompt-cache hit rate; (2) the char/4 estimator is mandatory,
  not merely preferred, because `transformers` is absent and the framework tokenizer raises under
  `FakeLLM`; (3) the pgvector-orphan risk is resolved (`ON DELETE CASCADE`) and its test
  re-purposed as a regression pin. Owner confirmed month granularity the same day.
- 2026-09-16 — **E001 raised and decided (A).** Task 0.1's original gate did not pass: PR #214 is
  OPEN with `api` / `eval-smoke` / `secrets` / `web` all failing in 3s and no review yet. Owner
  chose to ship the #214-independent subset. Plan re-sequenced: SC table cut to SC-1..SC-6 for this
  delivery; Tasks 2.2 / 3.1 / 3.2 (P0#3) moved to §7, fenced; old Task 4.1 renumbered 3.1; new
  Task 0.1 now pins the deferral with a no-`/memory`-route test.
- **Remaining preconditions:** none for this delivery. P0#3 stays blocked on #214 merging.
