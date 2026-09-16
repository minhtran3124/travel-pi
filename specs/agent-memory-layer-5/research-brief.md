# Research Brief — agent-memory-layer-5

Depth: **Deep** (intake lane `high-risk` → Deep per `rules/research-depth.md`; re-run with evidence
in §Depth re-run below — unchanged, and no signal was found that would have lowered it).
External surface: **yes** — version-specific `langgraph` / `langchain-core` APIs.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing + use built-in** — no new abstraction. `store.delete` already cascades; the char/4 estimator stays; two design corrections apply (below) |
| **Why this is the lightest credible path** | Every capability the plan needs is already installed and load-bearing here; the two risks the plan flagged as unknown are now answered, and one answer invalidates part of the plan's own prompt design |
| **Confidence** | 88% |
| **Next step** | Apply the two corrections to `design.md` §4.1 and §4.2, then execute `PLAN.md` from Task 0.1. Do **not** start Task 2.1 against the current §4.1 wording |

### Two corrections this research forces

1. **`design.md` §4.1 as written would degrade prompt caching.** `format_age` returning
   `"today"` / `"3 days ago"` puts a **daily-changing string into the middle of the system-prompt
   prefix** (the preferences and instructions blocks sit before `summary`). Caching here is
   implicit, already on, and measured at 71.9%; `ground_current_date` was deliberately appended
   **last** precisely so the one volatile block could not invalidate the stable prefix
   (`docs/solutions/agent/prompt-caching-implicit-idle-eviction.md`). Restoring that property
   means **coarse buckets**, not a relative-days phrase — see §Recommendation.
2. **`design.md` §6's deferred "lazy TTL read filter" should be rewritten before it is built.**
   LangGraph ships native per-item TTL with an `expires_at` column and a background sweeper. The
   P1 item is `use built-in`, not `build` — but it carries a backend asymmetry that makes it a
   real design task, not a config flip (§Docs Findings).

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm workspaces + Turborepo): FastAPI API in `apps/api/`, Next.js web in `apps/web/` |
| Primary language + runtime | Python 3.14 in the repo venv (Docker runs 3.12 — `docs/solutions` records the split); Node v24 required for pnpm work |
| Frameworks / platforms | FastAPI 0.136.3, SQLAlchemy 2.0.51, LangGraph 1.2.6, langchain-core 1.4.8, Next.js + next-intl |
| Relevant packages | `langgraph` 1.2.6, `langgraph-checkpoint-postgres` 3.1.0, `langgraph-checkpoint` 4.1.1, `langchain-openai` 0.3.34, `psycopg` 3.3.4, `pgvector` 0.3.6, `tiktoken` 0.13.0 |
| Detectable versions | Read from the live venv via `importlib.metadata`, not from a manifest — this is the resolved set actually running |
| Important constraints | `CLAUDE.md`: stage/commit separately; Node v24; BE from `apps/api/`. `SUMMARY.md` Global Constraints: no new table/migration/dependency/scheduler; identity from `CurrentUserDep` only; never remove existing behavior |

---

## Feature Understanding and Assumptions

- **Requested feature:** the P0 slice of Layer 5 — render stored-fact age into the prompt (P0#2),
  an authenticated view/hard-delete surface for all three memory kinds (P0#3), and a token-aware
  compression trigger (P0#4). PR #214's guard is a merge dependency, not part of this work.
- **What success appears to mean:** a traveller can permanently remove anything the agent stored
  about them; the model can tell a fresh fact from a stale one; compression fires on context
  pressure rather than on a message count. All without a new table, migration, dependency or scheduler.
- **Assumptions from the request:** the three narrowing decisions in `SUMMARY.md` are binding
  (all three kinds, hard delete, #214 as a dependency).
- **Assumptions still needing confirmation:**
  - That `PostgresStore.setup()` has actually run the vector migrations on the dev/prod database —
    the `ON DELETE CASCADE` that makes delete correct lives in `VECTOR_MIGRATIONS`, so a store
    that was ever created *without* an index has no `store_vectors` table and a different shape.
    Checked in code, **not** against a live database.
  - That the coarse-bucket wording (correction 1) is acceptable product behavior — it trades
    "recorded 3 days ago" for "recorded this month".

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `store_vectors` is created with `FOREIGN KEY (prefix, key) REFERENCES store(prefix, key) ON DELETE CASCADE` — `langgraph/store/postgres/base.py:104-112`. **Q1 answered: yes, `delete` removes the embedding row.** |
| `Local` | `store.delete()` is `PutOp(value=None)` → `DELETE FROM store WHERE prefix = %s AND key IN (...)` — `postgres/base.py:317-328`, `base/__init__.py:929`. One statement; the cascade does the rest. |
| `Local` | LangGraph ships native TTL: `TTLConfig(refresh_on_read, default_ttl, sweep_interval_minutes)` (`store/base/__init__.py:545-562`), `expires_at` + `ttl_minutes` columns (`postgres/base.py:82-85`), `sweep_ttl()` / `start_ttl_sweeper()` (`postgres/base.py:807-825`), `supports_ttl: bool = True` on `PostgresStore` (`postgres/base.py:728`). |
| `Local` | **`InMemoryStore` does not support TTL** — `supports_ttl` defaults to `False` (`store/base/__init__.py:719`) and nothing in `store/memory/__init__.py` sets it; `BaseStore.put` **raises `NotImplementedError`** when `ttl` is passed to a non-supporting store (`base/__init__.py:912-916`). |
| `Local` | `langchain_core` base `get_num_tokens_from_messages` falls back to `GPT2TokenizerFast.from_pretrained("gpt2")` via `transformers` (`language_models/base.py:42, 77-97, 103-115, 449-486`) and emits a "may be inaccurate" warning. |
| `Local` | **`transformers` is NOT installed** in this venv (checked via `importlib.metadata`). **Q2 answered:** the framework method raises on any model that does not override it — including the test `FakeLLM`. |
| `Local` | `ChatOpenAI` *does* override it, using `tiktoken.encoding_for_model` with an `o200k_base` fallback for `gpt-4o`/`gpt-4.1`/`gpt-5` prefixes (`langchain_openai/chat_models/base.py:1481-1497`). `tiktoken` 0.13.0 is installed. |
| `Local` | Prompt caching is implicit, **already on, measured 71.9%**; misses are idle eviction, not prefix instability; the volatile date note is appended **last** on purpose (`docs/solutions/agent/prompt-caching-implicit-idle-eviction.md`). |
| `Local` | Prefix block order today: style → agent prompt → profile → account email → instructions → trip context → summary → trip facts → preferences (`app/agents/state.py:160-195`). |
| `Local` | Reuse for P0#3 FE: `src/lib/query/bookings.ts` react-query hooks, `EmptyState`, `Spinner`, `Field`, `Select`, `useTranslations("<Ns>")` — `src/app/bookings/page.tsx:1-40`. Codegen is `pnpm gen:api` → `openapi-typescript http://localhost:8000/openapi.json -o ./src/lib/api/schema.d.ts` (`apps/web/package.json:10`). |
| `Local` | Router conventions: `APIRouter(prefix=..., tags=[Tags.x], responses=error_responses(422))`, `OptionalUserDep` / `CurrentUserDep` from `app/core/auth.py:149-150`, registration in `app/routers/main.py:37-58`. **`Tags` has no `memory` member** (`app/routers/tags.py`) — 19 members, `agent` is the closest. |
| `Docs` | TTL is officially documented (`docs.langchain.com` TTL how-to; JS reference for `TTLConfig`): `defaultTtl` in minutes, `refreshOnRead` resets expiry on `get`/`search`, `sweepIntervalMinutes` default 5. |
| `Upstream` | `langchain-ai/langgraph` PR #8905 and issue #5178: `TTLConfig.omit_expired` was **not honored in sqlite store read paths** — an expired-but-unswept item could still be returned. Treat "expired" as "will be swept", not "is invisible". |
| `Inference` | Because `store.py` degrades to `InMemoryStore` in tests and whenever pgvector is missing, adding `ttl=` to the `upsert_*` helpers would raise there. Any P1 TTL work must gate on `store.supports_ttl`, not on the settings URL. |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** `app/memory/{store,summarizer,extractor,extraction_runner}.py`;
  `app/agents/{nodes,state,context,checkpointer}.py`; `app/core/{config,lifespan,auth}.py`;
  `app/routers/{main,feedback,agent}.py`, `app/routers/tags.py`; `app/tools/memory_tools.py`;
  tests under `tests/memory/`, `tests/agents/test_memory.py`, `tests/tools/test_memory_tools.py`;
  `apps/web/src/app/bookings/page.tsx`, `src/lib/query/`, `messages/{en,vi}.json`.
- **Existing abstractions or extension points:** `MemoryKind` enum + `_namespace()` are already the
  single source of truth for the three namespaces; `search_memory` / `search_memory_typed` are
  already the unified dispatchers; `Preference` / `Instruction` / `Episode` already exist as the
  typed projection layer. P0#3's `list_memory` / `delete_memory` slot in beside them with no new concept.
- **Conventions worth preserving:** injected identity (`user_id` never model- or client-supplied —
  `memory_tools.py` header comment states this as the security property); one process-lifetime store
  from `lifespan`; best-effort memory reads that log and continue rather than fail a turn
  (`nodes.py:96-140` wraps each load in its own `try`); `_stamped()` as the only writer of `updated_at`.
- **What can likely be reused:** the whole store layer (add 2 functions + 1 field); the react-query
  + `useTranslations` page pattern verbatim; `error_responses(422)` / `CurrentUserDep` router shape;
  `pnpm gen:api` for `schema.d.ts`.
- **What appears missing locally:** no `Tags.memory`; no `settings` route in `apps/web/src/app`;
  no `tests/api/memory/` directory; nothing reads `updated_at` back out of the store.

---

## Upstream Findings

- **Repositories inspected:** `langchain-ai/langgraph` (the installed 1.2.6 source in-venv, plus
  PR #8905 / issue #5178 on GitHub); `redis-developer/langgraph-redis` (surveyed only, to check
  whether the TTL contract is store-specific — it is declared on `BaseStore`, so it is not).
- **Pattern or capability already present upstream:** per-item TTL, a sweeper thread, and
  `refresh_on_read` — the entire P1 "lazy TTL" item, already built.
- **Files, modules, or areas worth modeling:** `langgraph/store/postgres/base.py` `_prepare_batch_PutOp`
  (delete/insert split) and `sweep_ttl` — the shape any expiry work should call, not re-implement.
- **How closely the upstream pattern matches this repo:** closely for Postgres, **not at all for
  the degrade path** — `InMemoryStore` raising on `ttl` is the gap that makes this a design task.
- **Any upstream gaps or uncertainties:** the `omit_expired` read-path bug was filed against the
  sqlite store; whether the Postgres read paths in 1.2.6 filter expired rows before a sweep was
  **not** verified — it needs a live-DB check, not a source read.

---

## Docs Findings

- **Official sources checked:** `docs.langchain.com` LangGraph stores + TTL how-to (via Context7
  `/websites/langchain_oss_python_langgraph`, and via search for the TTL pages);
  `reference.langchain.com` `TTLConfig` / `PostgresStore`.
- **Version-matched vs latest-stable status:** the docs site is unversioned (latest-stable). The
  authority used for every load-bearing claim here is the **installed 1.2.6 source**, which is
  version-matched by construction. Where the two could differ, the source wins and is cited.
- **Built-in capabilities that already support the feature:** `store.delete` (with the cascade);
  `TTLConfig` + `start_ttl_sweeper` + per-item `ttl` on `put`; `ChatOpenAI.get_num_tokens_from_messages`.
- **Current recommended APIs or workflows:** pass `ttl=TTLConfig(...)` at store construction and
  call `start_ttl_sweeper()` explicitly — the sweeper does **not** auto-start (`postgres/base.py:712-713`).
- **Important caveats, deprecations, or migration notes:** Context7's LangGraph store pages returned
  **no TTL content at all** — the feature is materially under-documented relative to the source, so
  a future minor could change it with little doc signal. Pin behaviour with a test, not with a doc link.

---

## Recommendation

- **Primary recommendation:** **reuse existing + use built-in.** No new abstraction, and `PLAN.md`'s
  task structure survives intact. Three concrete adjustments:

  **(a) P0#2 — bucket the age; do not phrase it in days.** `format_age` should return a
  **coarse, slow-changing** bucket (`"this month"`, `"a few months ago"`, `"over a year ago"`) or a
  month stamp (`"recorded 2026-04"`) — never `"today"` / `"3 days ago"`. Rationale is cache
  economics, not style: the preferences and instructions blocks sit **before** `summary` in the
  prefix (`state.py:160-195`), so a string that changes daily invalidates the cached prefix for
  every user at every day rollover, in a system measured at 71.9% hit rate where the one volatile
  block was deliberately pushed to the end. A month-granularity bucket changes at most once a
  month, and only for rows sitting on a boundary. It also still satisfies the actual product
  requirement — the model needs to know *roughly how old*, not the exact day.
  *If per-day precision is ever genuinely wanted, the alternative is to move the age-annotated
  blocks after `summary`, adjacent to the date note — a prefix-order change, which is a bigger
  blast radius than bucketing and should not be bundled into this spec.*

  **(b) P0#4 — keep the char/4 estimator; the framework method is not usable here.** Not a
  preference: `transformers` is not installed, so the base `get_num_tokens_from_messages` raises
  for any model that does not override it — which includes the test `FakeLLM`, i.e. the entire
  unit-test path. `ChatOpenAI` does override it via tiktoken, so a real-provider run would work,
  but that makes the compression trigger **provider-dependent and untestable offline** for a value
  that is a ceiling with 15% headroom. `design.md` §4.2 stands as written; this brief upgrades it
  from "a reasonable choice" to "the only portable one", and that reason belongs in a code comment
  so nobody swaps it for the framework call later.

  **(c) P0#3 — `store.delete` is sufficient and complete; drop the pgvector worry from the risk
  register.** `store_vectors` carries `ON DELETE CASCADE` on `(prefix, key)`. Task 1.1 should still
  keep its Postgres-backed delete test, but as a **regression pin on the cascade**, not as an
  investigation of an unknown. One genuine prerequisite remains: the cascade only exists if
  `setup()` ran `VECTOR_MIGRATIONS`, so the test must exercise an **indexed** `PostgresStore`,
  which is what `open_store` always builds.

- **Why the next-best alternative lost:**
  - *Build a lazy read-time TTL filter now* (the `design.md` §6 P1 sketch) — loses to the built-in,
    which has an indexed `expires_at` and a sweeper. Re-implementing it as a read filter would also
    have inherited the exact bug upstream already filed (#5178): a read filter and a sweeper
    disagreeing about what "expired" means.
  - *Use `llm.get_num_tokens_from_messages()`* — loses on `transformers` being absent (raises in
    tests) and on making the trigger provider-coupled.
  - *Soft delete* — already rejected at intake; the cascade finding removes its last technical
    argument (there is no orphaned-embedding problem for hard delete to leave behind).

- **What would change this recommendation:** (i) if `store_vectors` turns out **not** to exist on the
  live database — i.e. the store was created unindexed — then delete semantics differ and Task 1.1
  needs a schema check first; (ii) if product decides per-day age precision is required, (a) flips
  from bucketing to a prefix-order change and needs its own cache measurement via
  `scripts/cache_hit_report.py`.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - **Prompt-cache regression from P0#2** — the top risk, and it is a *silent cost* regression, not
    a test failure. No unit test will catch it. Mitigate with bucketing (above) and measure with
    `../../.venv/bin/python -m scripts.cache_hit_report --since 24h` before/after, which
    `PLAN.md` Task 4.1 does not currently include.
  - **`Tags` enum has no `memory` member** — either add one (touches a shared 19-member enum read by
    every router, and changes the generated OpenAPI tag list) or mount the routes under `Tags.agent`.
    Prefer `Tags.agent`: smaller blast radius, and memory *is* agent state.
  - **Prompt edits are not hot-reloaded** — `docker exec api-api-1 touch app/main.py` is required
    before any manual verification of Task 2.1 (recorded in `PLAN.md`, repeated here because it is
    the most common false-negative in this repo).
- **Evidence gaps:**
  - Live-database confirmation that `store_vectors` exists and the cascade fires (source-read only).
  - Whether 1.2.6's **Postgres** read paths filter expired rows pre-sweep (the upstream bug was
    filed against sqlite). Only matters for the P1 TTL item, not for this P0 slice.
- **Version uncertainties:** LangGraph TTL is under-documented on the docs site relative to the
  1.2.6 source, so it is comparatively likely to shift in a minor. Any P1 TTL adoption should pin
  the behaviour with a test rather than rely on the doc.
- **Follow-up questions for the user:**
  1. Is a **month-granularity** age acceptable (`"recorded this month"` / `"a few months ago"` /
     `"over a year ago"`) instead of `"3 days ago"`? This is correction (a) and it is the only
     product-visible change this research proposes.
  2. Mount `/memory` under the existing `Tags.agent` tag rather than adding a 20th `Tags` member?

---

## Source Pack

- **Local files read:**
  `apps/api/app/memory/{store,summarizer,extractor,extraction_runner}.py`,
  `apps/api/app/agents/{nodes,state,context,checkpointer}.py`,
  `apps/api/app/core/{lifespan,auth,config,agent_config_cache}.py`,
  `apps/api/app/routers/{main,feedback,agent,tags}.py`,
  `apps/api/app/tools/memory_tools.py`,
  `apps/api/app/db/models/{agent_run,agent_run_step}.py`,
  `apps/api/eval/datasets/memory.json`,
  `apps/web/src/app/bookings/page.tsx`, `apps/web/package.json`,
  `docs/solutions/agent/prompt-caching-implicit-idle-eviction.md`,
  `docs/solutions/agent/{llm-parses-code-computes,eval-golden-notes-are-not-metrics}.md` (index entries),
  `specs/memory-poisoning-hardening/SUMMARY.md`,
  `.venv/.../langgraph/store/{base/__init__.py,postgres/base.py,memory/__init__.py}`,
  `.venv/.../langchain_core/language_models/base.py`,
  `.venv/.../langchain_openai/chat_models/base.py`,
  `CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/{orchestration,research-depth,behavior,plan-format,auto-correct-scope}.md`
- **Upstream repositories or pages checked:**
  - https://github.com/langchain-ai/langgraph/pull/8905
  - https://github.com/langchain-ai/langgraph/issues/5178
  - https://pkg.go.dev/github.com/wahanbo/langgraph-go/store/ttl (survey only — confirms the TTL
    contract is a store-level concept, not Postgres-specific; not used for any claim)
- **Official docs domains or pages checked:**
  - https://docs.langchain.com/oss/python/langgraph/stores
  - https://langchain-ai.github.io/langgraph/how-tos/ttl/configure_ttl/
  - https://docs.langchain.com/langsmith/configure-ttl
  - https://reference.langchain.com/javascript/interfaces/_langchain_langgraph-checkpoint-postgres.store.TTLConfig.html
  - https://reference.langchain.com/javascript/classes/_langchain_langgraph-checkpoint-postgres.store.PostgresStore.html

---

## Depth re-run

Re-classified with evidence per `rules/research-depth.md`: Deep signals confirmed — a shared runtime
configuration contract (the process-lifetime store read by every agent turn) and reliance on
version-specific APIs (`langgraph` 1.2.6 store internals, `langchain-core` 1.4.8 token counting).
No new signal, and none that would lower the depth. **Deep stands.** No migration/schema signal was
found, which is consistent with the plan's "no migration" constraint rather than a gap in it.

---

## Evidence Boundary

> **Confirmed from artifacts:**
> `store_vectors` FK is `ON DELETE CASCADE` (installed 1.2.6 source, `postgres/base.py:104-112`);
> `store.delete` issues a single `DELETE FROM store` (`postgres/base.py:317-328`);
> LangGraph has native TTL + sweeper and it does not auto-start (`postgres/base.py:82-85, 712-713, 807-825`);
> `InMemoryStore` does not support TTL and `put(ttl=...)` raises there (`base/__init__.py:719, 912-916`);
> `transformers` is absent from this venv (metadata query) so the base token counter raises;
> `ChatOpenAI` overrides it with tiktoken (`langchain_openai/chat_models/base.py:1481-1497`);
> prompt caching is on at 71.9% with the volatile block placed last (`docs/solutions/…`);
> current prefix block order (`state.py:160-195`);
> `Tags` has no `memory` member (`app/routers/tags.py`);
> `apps/web/src/app` has no `settings` route (directory listing);
> codegen command is `pnpm gen:api` (`apps/web/package.json:10`).
>
> **Inferred from patterns:**
> that adding a daily-changing age string mid-prefix will cost cache hits — the mechanism is
> documented and measured, but the specific regression was **not** measured for this change;
> that any P1 TTL adoption must branch on `store.supports_ttl` (follows from the raise, not observed
> in a failing run);
> that `Tags.agent` is preferable to a 20th enum member (judgment about blast radius, not a measurement).
>
> **Not checked:**
> the live dev/prod database — `store_vectors` existence and an actual cascading delete were never
> executed, only read in source;
> whether 1.2.6's Postgres read paths filter expired rows before a sweep (upstream bug was sqlite-only);
> `tiktoken`'s first-call BPE download behaviour inside the Docker image (irrelevant under
> recommendation (b), which does not call it — it would matter if (b) were reversed);
> any behaviour of PR #214's guard — this brief reached traceability on it via
> `specs/memory-poisoning-hardening/SUMMARY.md` and ran nothing;
> the eval suite was not run.
