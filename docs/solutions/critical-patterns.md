# Critical Patterns

Promoted learnings that cost the most to discover and save the most by knowing.
Read this file at the start of every planning session.
Items here met all three criteria: affects multiple features, would waste ≥30 min if unknown, generalizable.

---

## [2026-06-26] monorepo-operate-from-subdir
**Type:** knowledge
**Module:** monorepo
**Tags:** monorepo, turborepo, pnpm, relocation, python, cwd-tooling
**Applicable when:** Moving a self-contained language sub-app into apps/<x> and you want to avoid rewriting its imports.

Move the sub-app as one block into `apps/<x>/` and run every tool with CWD=that dir; keep the top-level import package name unchanged. Relative tool config (alembic `prepend_sys_path=.`, compose `build:.`, ruff `src`) stays valid, so a wholesale move needs **zero import rewrites** (avoided 622 `from app.` edits). Let Turborepo orchestrate a non-JS app via a thin `package.json` shelling to `make`.

**Full doc:** docs/solutions/monorepo/operate-from-subdir.md
---

## [2026-06-26] pnpm-node-floor-mismatch
**Type:** bug
**Module:** ci
**Tags:** ci, pnpm, node-version, github-actions, packagemanager
**Applicable when:** CI setup-node fails with `ERR_UNKNOWN_BUILTIN_MODULE: node:sqlite`, or when bumping the pinned packageManager pnpm version.

A pinned `packageManager: pnpm@11` needs Node ≥22.13 (it imports `node:sqlite`), but CI `node-version: "20"` ran it → cryptic crash. Treat `packageManager` + CI `node-version` + `engines.node` as one coupled triple and raise all three together. A `node:<builtin>`-not-found during install means "package manager on too-old Node," not a real missing module.

**Full doc:** docs/solutions/ci/pnpm-node-floor-mismatch.md
---

## [2026-06-26] phase1-architecture-decisions
**Type:** decision
**Module:** monorepo
**Tags:** monorepo, turborepo, pnpm, nextjs, tanstack-query, sse, identity
**Applicable when:** Designing a Next.js + FastAPI monorepo frontend (layout, tooling, data layer, identity, SSE transport).

Five forks resolved: relocate via operate-from-subdir (not import rewrite); Turborepo + pnpm with a Python package.json wrapper; client + TanStack Query (interactive + streaming, not SEO); local pseudo-identity as the single swappable auth seam (no BE change); SSE direct-to-origin (Next proxy buffers SSE).

**Full doc:** docs/solutions/monorepo/phase1-architecture-decisions.md
---

## [2026-06-26] wave-shared-file-partition
**Type:** failure
**Module:** harness
**Tags:** subagent-parallelism, wave-parallelism, blast-radius, test-infra, shared-types
**Applicable when:** Dispatching ≥2 parallel wave subagents that consume shared test infra or a shared type contract.

The wave file-overlap guard only checks DECLARED `<files>`; it's blind to shared infrastructure (a test harness none of the tasks "owned") and shared type contracts (one type edited from multiple owned files). Parallel agents collided on undeclared shared surfaces. Fix: create/own shared infra + types in an earlier single-task wave; check parallel-safety at the import/dependency level, not just declared paths.

**Full doc:** docs/solutions/harness/wave-shared-file-partition.md
---

## [2026-07-03] reflection-humanmessage-language-flip
**Type:** bug
**Module:** agent/reflection
**Tags:** langgraph, message-roles, reflection-loop, tool-error-handling, prompt-versioning, uvicorn-reload
**Applicable when:** Working on LangGraph multi-agent nodes that inject synthetic messages into state["messages"] (e.g. reflection/revision loops, retry prompts) where a prompt rule keys behavior off "the traveller's latest message".

The reflection self-critique loop injected its "please improve" revision note as a `HumanMessage`, so the concierge's language-detection rule ("reply in the language of the traveller's latest message") misread it as real user input and silently flipped the reply to English mid-conversation. Fixed by making the injected note a `SystemMessage` — internal control messages must never be `HumanMessage` when a prompt keys off "latest message."

**Full doc:** docs/solutions/agent/reflection-humanmessage-language-flip.md
---

## [2026-07-03] langgraph-thread-reset-and-prompt-reload
**Type:** knowledge
**Module:** agent/reflection
**Tags:** langgraph, checkpointer, poisoned-thread, uvicorn-reload, prompt-versioning
**Applicable when:** Debugging an AI-agent behavior that appears to repeat across multiple turns of one conversation thread, or verifying a fix/prompt change against a live dev agent.

A bad tool-error message or synthetic instruction written into LangGraph's checkpointed state (Postgres `checkpoints`/`checkpoint_writes`/`checkpoint_blobs`/`store`) resurfaces on every future turn of that thread — clearing the display-only `messages`/`conversations` tables is not enough for a clean re-test. Separately, `uvicorn --reload`'s watcher only restarts on `.py` changes, so editing a prompt `.md` or `active.yaml` silently does nothing until `docker compose restart api` forces the module-level `PromptRegistry` singleton to reload.

**Full doc:** docs/solutions/agent/langgraph-thread-reset-and-prompt-reload.md
---

## [2026-07-03] reflection-humanmessage-language-flip-decisions
**Type:** decision
**Module:** agent/reflection
**Tags:** langgraph, message-roles, reflection-loop, category-matching, fuzzy-match, prompt-versioning
**Applicable when:** Adding or debugging a free-text agent-tool argument that must map to a fixed set of DB values, or injecting a programmatic/internal instruction into a LangGraph agent's state["messages"].

Two decisions from the same session: (1) fixed a category exact-match miss (`"cafes"` vs. seeded `"cafe"`) by adding `PlaceService.resolve_category()` — a backend fuzzy-matcher reusing the existing `best_match()`/`resolve_city()` pattern — rather than relying on a tool-schema hint the model might not follow; (2) fixed the reflection language-flip bug structurally (message role, not just wording) by using `SystemMessage` for internal notes, matching the graph's existing system/human/AI role discipline.

**Full doc:** docs/solutions/agent/reflection-humanmessage-language-flip-decisions.md
---

## [2026-07-08] supervisor-active-yaml-is-a-pointer
**Type:** failure
**Module:** agent/prompts
**Tags:** langgraph, prompts, supervisor, prompt-registry, active-yaml, versioned-prompts, silent-no-op
**Applicable when:** About to change the wording of any agent/supervisor system prompt loaded through the prompt registry (files under apps/api/app/prompts/<agent>/).

`app/prompts/<agent>/active.yaml` is only a name→version pointer map — the real prompt prose lives in the versioned `vN.md` it points to (e.g. `supervisor/v5.md`), which is what `registry.get(<agent>)` returns. Editing `active.yaml` to change wording is a silent no-op and can corrupt the map; edit the active `vN.md` instead. Distinct from the "prompt edits need a graph rebuild" learning — this is editing the wrong file entirely.

**Full doc:** docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md
---

## [2026-07-11] llm-parses-code-computes
**Type:** decision
**Module:** agent/tools
**Tags:** llm, structured-output, date-resolution, tool-design, determinism, i18n, few-shot
**Applicable when:** An agent tool must turn free-text human input (dates, durations, quantities, budgets) into a precise machine value, and you are choosing between a hardcoded parser, an LLM that returns the final value, or a split.

Both obvious options fail: a hardcoded lexicon never converges (it asked the traveller to clarify "tuần tới", which means exactly what "tuần sau" means), and letting the LLM return the final value reintroduces the arithmetic bug class it was built to prevent. Split by strength — **the model returns a structured INTENT (`{kind:"weekday", weekday:0, week:"next"}`), never a date; code does the arithmetic.** A misread phrase is then visible in the trace and fixable with a few-shot; a silent +7-day slip becomes impossible. A numeric fast path (ISO/DD-MM) skips the model entirely.

**Full doc:** docs/solutions/agent/llm-parses-code-computes.md
---

## [2026-07-11] new-agent-config-node-seeds-null-model
**Type:** bug
**Module:** agent/config
**Tags:** agent-config, seed, llm, get_agent_llm, 403, silent-degradation, deploy
**Applicable when:** Adding a NEW agent-config node (a new sub-agent, or any component that calls get_agent_llm with a new name) — including a tool that makes its own LLM call.

`app/db/seed.py::_seed_agent_config` inserts a new node's row with **NULL provider/model**, so the node looks configured (row exists, dashboard lists it) while `get_agent_llm` quietly falls back to the env default model against OpenAI directly — a **403** on a gateway account, on every call, in one feature only. A new agent node is a deploy step: seed its provider/model (`scripts/seed_agent_config.py --nodes <name>`, run with `-w /app -e PYTHONPATH=/app` in the container) and rebuild the graph. When something passes every test but fails everywhere in the real stack, suspect config/data state and read the provider's HTTP status in the container log.

**Full doc:** docs/solutions/agent/new-agent-config-node-seeds-null-model.md
---

## [2026-07-11] verify-against-invented-rule
**Type:** failure
**Module:** harness
**Tags:** verification, testing, invariants, parametrize, anchor-dependence, evidence, false-proof
**Applicable when:** Implementing behavior whose correct output depends on WHEN it runs (weekday, month boundary, timezone, fiscal period) — or any time you are about to write a test whose expected values you derived from a rule you yourself invented.

A P0 (a date off by exactly 7 days, into a paid-booking flow) survived 51 green tests, a REPL spot-check, and a live probe that **recorded the wrong answer as proof**. Every check asked "does the code match the rule?"; none asked "is the rule right?" — a test whose expected values come from the same head that wrote the implementation is a tautology with a green tick. The tests also pinned a single anchor weekday, and it was the one where the bug is invisible. Fix: **assert INVARIANTS derivable from meaning, not tables of expected values, and parametrize over every anchor.** An invariant catches a wrong rule; a value table only restates it.

**Full doc:** docs/solutions/harness/verify-against-invented-rule.md
---

## [2026-07-11] negative-grep-is-not-absence
**Type:** failure
**Module:** harness
**Tags:** grep, evidence, not-observed-vs-absent, prompts, active-yaml, search-methodology
**Applicable when:** About to conclude "only file X does Y" from a search — especially when removing a rule/behavior that may be stated in several places, and above all across the versioned agent prompts.

A filtered grep returned nothing, so the scope was set to one prompt file. The rule was also in `planner/v6.md` — the **dominant** path — wrapped across lines the filter's second `AND` term never matched. The feature shipped with the behavior it removed still active on the main path; the live probe passed only because the prepended grounding note happened to out-argue the contradictory prompt. When REMOVING a rule, **enumerate the active prompts (via `active.yaml`) and read them** — never grep for phrasing you are, by definition, unsure of — then pin the removal with a test asserting the retired phrases are ABSENT.

**Full doc:** docs/solutions/harness/negative-grep-is-not-absence.md
---

## [2026-09-08] planner-search-first-save-later
**Type:** decision
**Module:** agent/planner
**Tags:** prompts, planner, create_trip, search_flights, tool-ordering, intent-scoping, eval
**Applicable when:** Writing or reviewing any prompt, tool docstring, or routing rule that makes a setup/write step ("no active trip → create one") a precondition of a turn, or adding a search tool to the planner.

Planner v12 made `create_trip` step one of every trip-less turn, so a bare flight search became `create_trip → resolve_date` and never reached `search_flights` (GH-156, golden `flight_search-multi_turn-vi-01`); the baseline "pass" still carried the unrequested trip in its trace. Decision: **search first, save later** — search tools never need a trip; `create_trip` only when the traveller wants to build or save an itinerary. General rule: **gate a setup/write step on the intent that needs it, never on the absence of state**, and state the rule in BOTH the prompt and the tool description, because the model reads each independently.

**Full doc:** docs/solutions/agent/planner-search-first-save-later.md
---

## [2026-09-08] a-check-that-cannot-fail
**Type:** failure
**Module:** harness
**Tags:** verification, gates, false-green, vitest, negative-control, mutation-testing, review-methodology, evidence
**Applicable when:** Adding or reviewing any check that is supposed to protect something — a task Verify, a Success Criterion, a CI gate, a lint rule, or a test written to close a review finding. Above all when the check is new and has only ever been seen green.

One slice shipped seven checks that were green while proving nothing: a `-t` filter matching no test name exits 0; a multi-file `vitest` filter exits 0 on a partial match; a catalog parity test passes on a tree with none of the new keys; a cookie assertion covering only `value`; a `next-intl` identity mock swallowing a hardcoded string; branch cases that could not tell their own branch apart; and a gate regex matching one of four ways to write the thing it guards. None was visible by reading — eight rounds of document and per-task review passed them all. A new gate is not finished until it has been observed red: break the thing it protects, watch it fail, restore, and record what you broke.

**Full doc:** docs/solutions/harness/a-check-that-cannot-fail.md
---

## [2026-09-08] nextjs-16-proxy-and-loading-boundaries
**Type:** knowledge
**Module:** web
**Tags:** nextjs-16, proxy, middleware, loading-tsx, suspense, rsc, sec-fetch-dest, supabase-ssr, session-cookies, client-fetch
**Applicable when:** Working on apps/web routing, the proxy/middleware convention file, a loading affordance, or anything that reads request headers before a page renders.

`loading.tsx` never paints for a client-fetch page — it is the Suspense fallback for server rendering, and a `"use client"` page never suspends on the server (measured three ways). Next also strips its own Flight headers (`rsc`, `next-router-prefetch`) from `request.headers` inside the proxy, so a condition reading them silently never fires while a hand-built unit test still passes; key on `sec-fetch-dest` instead. `middleware` is deprecated in 16.0.0 and renamed to `proxy`, Node runtime by default, and only `pnpm build` proves Next resolves the convention file.

**Full doc:** docs/solutions/web/nextjs-16-proxy-and-loading-boundaries.md
---
