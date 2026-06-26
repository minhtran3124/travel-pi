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
