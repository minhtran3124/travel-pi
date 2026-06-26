# SUMMARY — monorepo-fe

Lane: high-risk
Confidence: medium
Reason: Multi-domain restructure (flags #6 public-contract, #7 cross-platform, #8 existing-behavior, #10 multi-domain). Relocating the BE breaks every Makefile/Docker/Alembic/CI path and introduces a new Next.js FE domain. No auth/data hard gate, but high blast radius on run/test/seed tooling.
Flags: public-contract, cross-platform, existing-behavior, multi-domain
Affects: repo layout, Makefile, Dockerfile/compose, alembic paths, CI workflow, `app/` location (BE → apps/api)
Input-type: New initiative
Route: Full high-risk chain (brainstorming → xia2 → writing-plans → using-git-worktrees → subagent-driven-development), phased — Phase 0 restructure ships before FE feature work.
Escalate: resolved — intake questions answered (layout, FE stack, tooling, scope). Remaining low-confidence item: the FE app's feature surface, to be pinned in /brainstorming before any FE PLAN.

## Intent

User's request (verbatim): "current codebase is for the BE only. I want to make update for mono repo with support both FE and BE in the same repo."

Intake clarifications (user-selected):
- **Layout**: Move BE into `apps/api` — relocate `app/`, `tests/`, `scripts/` under `apps/api/`, add `apps/web/` for the FE.
- **FE stack**: Next.js (React).
- **Tooling**: "best practice codebase structure for nextjs" — owner defers to current Next.js monorepo best practice (recommendation: pnpm workspaces + Turborepo, the Vercel-standard layout; BE stays on `uv`).
- **Scope**: Full FE app — a complete travel-planner frontend. This is a multi-PLAN initiative, not one PR.

Note: the `apps/`/`packages/` skeleton CLAUDE.md calls "stale" no longer exists on disk — `apps/` will be created fresh, no revival needed. CLAUDE.md's "ignore apps/" line will need updating as part of Phase 0.

## Rationale

Convert the BE-only FastAPI repo into a Next.js + FastAPI monorepo. Two concerns are separable and MUST be phased:

1. **Phase 0 — Restructure (high-risk, mechanical):** move BE under `apps/api`, scaffold `apps/web` (Next.js) + workspace tooling (pnpm + Turborepo), rewire Makefile/Docker/Alembic/CI to the new paths. Done = `make test` (685 tests) green from new location; `make dev`/`make seed`/Docker parity intact. No behavior change to the API.
2. **Phase 1+ — FE app (separate initiative):** build the travel-planner frontend against the FastAPI API. Feature surface is undefined → needs `/brainstorming` first. Will spawn its own PLAN(s).

## Alternatives

- Keep BE at root + add `frontend/` (rejected — owner chose the cleaner `apps/api` + `apps/web` monorepo).
- Plain folders / no tooling (deferred to best-practice: Turborepo + pnpm workspaces).
- Build full FE in one pass (rejected by phasing — "full FE app" is many stories; restructure ships first as its own PLAN).

## Status

Intake complete. Next: `/brainstorming` to scope the FE app, then `/xia2` + `/writing-plans` for Phase 0 (restructure). No code touched yet.
