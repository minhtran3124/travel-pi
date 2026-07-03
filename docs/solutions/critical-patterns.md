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
