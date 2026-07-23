---
problem_type: decision
module: monorepo
tags: monorepo, turborepo, pnpm, nextjs, tanstack-query, sse, identity, architecture
severity: critical
applicable_when: Designing a Next.js + FastAPI monorepo frontend — choosing repo layout, tooling, data layer, identity, and SSE transport.
affects:
  - apps/api/Makefile
  - turbo.json
  - pnpm-workspace.yaml
  - apps/web/src/lib/query/
  - apps/web/src/lib/identity/provider.tsx
  - apps/web/src/components/chat/useAgentStream.ts
supersedes: null
confidence: high
confirmed_at: 2026-06-26
---

## Applicable When

You are converting a single-app repo into a Next.js + FastAPI monorepo and building the first frontend — facing layout, tooling, data-layer, identity, and streaming-transport forks.

## Decision 1 — Relocate via operate-from-subdir (not import rewrite)
### Context
Moving the FastAPI backend under `apps/api/`. The naive path renames the package (`from app.` → `from apps.api.app.`, ~622 imports) plus path surgery across alembic/docker-compose/ruff.
### Options Considered
- A: Move + rewrite all imports to the `apps.api.app` namespace.
- B: Move as a self-contained block, `cd apps/api`, keep `app` as the top-level package.
### Decision & Rationale
Chose **B**. Relative refs (alembic `prepend_sys_path=.`, compose `build:.`, ruff `src=["app"]`) resolve from `apps/api`, and the import package name is unchanged — so the change is a `git mv` + CWD switch instead of 622 edits. Far smaller diff = far lower regression surface on a wholesale move. (See docs/solutions/monorepo/operate-from-subdir.md.)
### Consequences
Affects `apps/api/Makefile` (VENV=../../.venv), CI `working-directory: apps/api`, docker build context. Open feature branches need rebase onto the moved paths. Commit `5f9dcad`.

## Decision 2 — Turborepo + pnpm workspaces; Python app via thin package.json
### Context
Needed a task orchestrator across the JS frontend and the Python backend.
### Options Considered
- Plain folders / pnpm workspaces only / Turborepo + pnpm.
### Decision & Rationale
Chose **Turborepo + pnpm workspaces** (current Next.js monorepo best practice). The Python app joins the same `turbo` task surface via a thin `package.json` wrapper whose scripts shell to `make` — uniform commands without porting Python into the JS toolchain.
### Consequences
Affects root `package.json`, `turbo.json`, `pnpm-workspace.yaml`, `apps/api/package.json`. Commit `41d7027`.

## Decision 3 — FE data layer = client + TanStack Query
### Context
A trip-planner FE with interactive itinerary/budget editing and a streaming chat widget.
### Options Considered
- A: client + TanStack Query · B: RSC-first + Server Actions · C: hybrid.
### Decision & Rationale
Chose **A**. The data is authed-feeling and user-owned (not SEO-sensitive), so RSC's server-render benefit is low here; meanwhile the planner needs optimistic mutations and the widget needs streaming — both handled directly by TanStack Query under one client-side mental model. Hybrid adds two coordination models for little gain.
### Consequences
More client JS, less RSC benefit — accepted. Query-key factories + typed openapi-fetch client (`41df5fb`).

## Decision 4 — SSE direct-to-origin, proxy for JSON only
### Context
The agent chat widget consumes an SSE stream; other calls route through the Next `/api/be` proxy.
### Options Considered
- Stream through the Next proxy (with fallback) / connect direct-to-origin from the start.
### Decision & Rationale
Chose **direct-to-origin** via `NEXT_PUBLIC_API_URL`. The Next proxy/compression buffers SSE (issues #48427/#9965), stalling token streaming — going direct avoids the buffering rather than fighting it; the proxy still serves JSON. (See docs/solutions/streaming/agent-sse-on-nextjs.md.)
### Consequences
FE needs `NEXT_PUBLIC_API_URL`; CORS must allow the browser origin. Commit `ae6a9a9`.

## Decision 5 — Local pseudo-identity as the single auth seam
### Context
BE has no auth and `GET /trips` returns ALL trips, but the FE needs "my trips."
### Options Considered
- localStorage UUID pseudo-identity / name-prompt / single fixed user / add real BE auth now.
### Decision & Rationale
Chose **localStorage UUID pseudo-identity**. Concentrates future real-auth into ONE replaceable provider seam without prematurely building backend auth (a hard-gate, high-risk change) before the product shape settles; keeps the BE untouched and the FE shippable now.
### Consequences
All trips appear as "mine" until real auth lands — a known, bounded limitation. Provider in `ccb0e37`.

## Related
- docs/solutions/monorepo/operate-from-subdir.md
- docs/solutions/streaming/agent-sse-on-nextjs.md
