# SUMMARY — web-trip-planner (monorepo-fe Phase 1)

Lane: high-risk
Confidence: high
Reason: New multi-module public-facing frontend (5 feature surfaces + streaming agent widget) consuming the full BE contract; multi-domain. No BE changes, no auth added. Built per design.md, executed wave-by-wave with per-wave review + final correctness + intent gates.
Flags: public-contract (consumes ~70 endpoints), cross-platform (new browser FE), multi-domain
Affects: apps/web (new frontend), .github/workflows/ci.yml (web job), apps/api unchanged
Input-type: New initiative (Phase 1 of monorepo-fe)
Route: brainstorming → spec-review → xia2 → writing-plans → subagent-driven-development (this record)
Escalate: no — direction confirmed via brainstorming Q&A; no hard gate (no auth/data-loss/BE change)

## Intent

The user opted to build **Phase 1 — the full FE app** (after Phase 0 delivered the monorepo + Next.js scaffold). Scope was pinned through brainstorming Q&A (the user's selections, verbatim where decisive):

- **Center of gravity:** "1 + 2" — **Trip planning hub + Agent co-pilot** together.
- **Bar:** "Product MVP foundation" — solid architecture, extensible patterns, balanced polish + correctness, built to scale.
- **Identity:** "Local pseudo-identity (Recommended)" — stable browser `userId`, a thin seam to swap for real auth; no BE change.
- **Agent UX:** "the chat icon display bottom-right. click it and show chat popup" — a floating Kith-style chat widget (launcher FAB → popup panel), per the Kith Hotel screenshots the user supplied.
- **Design:** "reuse the BE dashboard design. Note that the FE will have 2 parts, first part is the normal dashboard help user can view trip, plan, etc … just thing belong to the user. The second part for chat widget like the Kith" — main app reuses the "Sunset Departures Board" design system (apps/api/DESIGN.md); chat widget styled like Kith (lime accent).
- **Phase 1 modules (multi-select):** Trips (list + create + itinerary) · Budget + expenses · Saved places + shortlist · Bookings view.
- **Data layer:** "Client + TanStack Query (Recommended)" + OpenAPI-typed client.
- **Execution:** "Subagent-driven (this session)" then "continue to end".

Non-goals (design §2): no booking creation flow, no full discovery/search parity, no drag-and-drop, no real auth, no BE changes, no packages/sdk yet.

## Rationale

Reuse > adapt > build (xia2): adapt openapi-typescript + openapi-fetch + TanStack Query into the existing scaffold; build the design system + chat widget bespoke. The BE contract is consumed as-is. See design.md + research-brief.md.

## Progress — all 15 plan tasks shipped (Waves 1–7)

| Wave | Commits |
|---|---|
| 1 Foundation (deps, gen:api → schema.d.ts, vitest/MSW) | `94fa016` |
| 2 typed client+keys · @theme + 8 ui primitives · identity | `41df5fb` · `a370d69` · `ccb0e37` |
| 3 app shell + providers | `98d4c74` |
| 4 trips · bookings · places | `9b11aa6` · `3900b0e` · `f6fc708` |
| 5 itinerary · budget+expenses · shortlist | `6b989d4` · `ea8cfc5` · `7b8f508` |
| 6 chat widget (+ conversation_id fix + correctness flush/fallback fix) | `a7c3f71` · `aab9938` · `ae6a9a9` |
| 7 e2e smoke · CI test step | `f22f02a` · `ed0da53` |

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Unit/component/hook suite | `cd apps/web && pnpm test` | 0 | 32 passed (vitest; playwright excluded) |
| Typecheck | `pnpm exec tsc --noEmit` | 0 | clean |
| Production build | `pnpm --filter @travel/web build` | 0 | 4 routes (/trips,/trips/[id],/places,/bookings) |
| e2e smoke | `pnpm e2e` (BE on :8000) | 0 | create trip → add item → persists (proven on :3100; foreign server occupies :3000) |

### Deviations

- Rule 3 — Task 1.1: approved `esbuild`/`msw` native build scripts in `pnpm-workspace.yaml` `allowBuilds` (vitest needs esbuild postinstall). Commit `94fa016`.
- Rule 3 — Wave 4: shared `src/test/setup.ts` patched (absolutize relative `/api/be` Request so openapi-fetch + MSW resolve in jsdom; hoist `server.listen`). Needed for ALL query-hook tests. Committed within `f6fc708`. Plan delta: shared test infra wasn't in any task's file partition.
- Rule 3 — Wave 4: `qk` factory params typed as `type` (not `interface`) so they satisfy `Record<string,unknown>` (TS2345). Cross-file; reconciled green.
- Rule 1 — Wave 6: pinned client-side `conversation_id` (was null on every streamed turn → no multi-turn memory). Commit `aab9938`.
- Rule 1 — Final correctness pass: parseSSE final `TextDecoder` flush (multibyte-split test) + guard stream→fallback on zero-tokens-received (avoid duplicate agent writes; keep partial + amber notice otherwise). Commit `ae6a9a9`.

### Known limitation (recorded, not fixed — Phase 2)

- **SSE payload framing (correctness #1):** the agent stream frames each token as `data: {chunk}\n\n`; a token whose content contains a blank line (`\n\n`) is indistinguishable from the event delimiter, so paragraph breaks in streamed assistant text can be mangled. The robust fix is **backend-side** (base64/JSON-encode each `data:` payload), which is a Phase-1 non-goal (no BE changes). Recorded for Phase 2. Impact: content-fidelity only (P2), no crash; rare for LangGraph message tokens.

### Rollback

- Revert the whole FE: `git revert 5e8f4c8..HEAD` (or reset the branch to `5e8f4c8` — pre-Phase-1-execution). All work is on `feat/monorepo-fe`, unpushed.

## Status

All waves complete; final correctness fixes (#2/#3) landing; intent review pending. Then `finishing-a-development-branch`.
