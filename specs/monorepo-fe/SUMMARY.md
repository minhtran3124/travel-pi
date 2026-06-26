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

**Phase 0 Wave 1 shipped** (commit `5f9dcad`); waves 2–4 paused on a Node-version blocker.
See `PLAN.md` §8 Status Log + Resume checklist.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| BE suite from new location | `cd apps/api && ../../.venv/bin/python -m pytest tests/ -q` | 0 | 848 passed |
| Renames-only move | `git diff --cached --name-status -M` (at commit) | 0 | 311×R100 + Makefile R067 + 2 new spec files |
| Hook still parses | `bash -n .claude/hooks/commit-quality-gate.sh` | 0 | path globs → apps/api/* |

### Deviations

- Rule 3 — Pulled Task 4.2 forward into wave 1: relocation broke the commit-quality gate's
  `tests/`/`app/`/`scripts/` globs and blocked the commit. Updated all path prefixes to
  `apps/api/*`. `.claude/` is gitignored → local-only, not committed. Authorized by user.
- Rule 1 — commit-quality gate secrets scan now scans **added lines only** (`grep '^+[^+]'`);
  it was flagging benign rename-deletion artifacts (`ors_api_key="test-key"` fixtures). Local-only.

### Rollback

- Revert wave 1: `git revert 5f9dcad` (or `git reset --hard 5f9dcad^` on this unpushed branch).
- Harness hook edits are uncommitted local changes under gitignored `.claude/` — restore from
  backup/upstream if needed (not under version control in this repo).

### Blocker (resume gate)

Local Node **v18.0.0** < pnpm 18.12 / Next 15 18.18 / Turborepo 18.12. Upgrade to Node ≥20 LTS
before waves 2–4.
