# review-c-web-experience — Summary

Lane: high-risk
Confidence: high
Reason: 5 flags fired (existing behavior, weak proof, multi-domain, cross-platform, public contracts) plus two hard gates — auth (E2E login fixture through the Supabase middleware) and public-contract (BE conversation read contract extended for interrupt rehydration, E002). Direction ambiguity was resolved by the human at intake (ESCALATIONS.md E001–E003), so confidence is high.
Flags: existing behavior, weak proof, multi-domain, cross-platform, public contracts, auth (adjacent), external systems (Supabase auth in e2e)
Affects: apps/web/playwright/*, .github/workflows/ci.yml (web job), apps/web/src/components/chat/useAgentStream.ts + ChatPanel/ChatWidget, apps/api/app/routers/agent.py (conversation read contract, if interrupt-on-reload is in scope), apps/web/src/app/**/loading.tsx, apps/web/src/i18n/*
Input-type: new initiative
Route: high-risk parent record — executed as four child specs (E001-A, `review-c2` split into two during its own brainstorming on 2026-09-04): `review-c1-e2e-auth-ci` → `review-c2-chat-resilience` (Stop button, interrupt rehydration, side panel, claim-403) → `review-c2b-fix-gh-109` (BE streaming-duplication bug, different subsystem) → `review-c3-web-ssr-i18n`, each with its own SUMMARY/PLAN and the brainstorming → xia2 → writing-plans → using-git-worktrees → subagent-driven-development chain.
Escalate: no (E001–E003 decided at intake by the human on 2026-09-04; see ESCALATIONS.md)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> chay /feature-intake cho section "C. Web app & trải nghiệm" theo artifact link https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview

Section C of the Travel-Pi Deep Review (artifact above; same text in `docs/reviews/2026-09-02-deep-review.md` §3.C), quoted verbatim:

> **10 — E2E gần như chết; identity hai đầu.** 2 spec Playwright / 6 test, không chạy CI; `trip-smoke.spec.ts` vào thẳng `/trips` không login trong khi middleware giờ redirect về `/auth/login`, nên gần như chắc chắn đã hỏng. FE vẫn mint UUID localStorage gửi qua `X-User-Id` trong khi trips cần bearer; không có hook `useSession` dùng chung. (`playwright/trip-smoke.spec.ts` · `lib/identity/provider.tsx` · `lib/api/client.ts`)
>
> **11 — Chat UX tốt nhưng còn lỗ.** `useAgentStream.ts` (849 dòng) xử lý 429, drop, reset, interrupt/resume, retry, claim khi đăng nhập. Thiếu: nút Stop khi đang stream; interrupt state chỉ ở memory nên reload là graph "kẹt" ở plan node; panel mất khi đóng/reload; claim thất bại (403) im lặng nên user có thể mất lịch sử mà không biết; issue #109 (clarification re-stream 3 lần) còn mở.
>
> **12 — Không có loading/SSR, i18n rò rỉ nhỏ, khoảng cách "calm vs energetic" chưa đóng.** 53/72 file .tsx là client component, 0 `loading.tsx`; vài aria-label hardcode tiếng Anh; locale là cookie nên không có URL localized để share. Visual vẫn calm: không photography, coral token gần như không dùng.

## What changed

Intake only. No implementation edits. The section was classified, its claims were corroborated against `main` (commit 2a1c039), and three scope decisions were escalated. Corroboration result:

| Item | Claim | Status on main | Evidence |
| --- | --- | --- | --- |
| 10 | E2E not in CI; `trip-smoke` hits `/trips` unauthenticated | **Confirmed** | `.github/workflows/ci.yml` web job runs lint/test/build only; `playwright/trip-smoke.spec.ts:26` does `page.goto("/trips")`; `src/lib/supabase/middleware.ts:14,60` gates `/trips` → `/auth/login` |
| 10 | FE still mints localStorage UUID sent as `X-User-Id`; no shared session hook | **Stale — already fixed by review-A (PR #129)** | `src/lib/identity/provider.tsx` derives identity from the Supabase session only; `src/lib/api/client.ts` attaches the bearer via `authHeader()`; `client.test.ts:8` asserts no `X-User-Id`; `src/lib/identity/useUserId.ts` exports the shared `useIdentity()` / `useUserId()` hooks. Only a one-shot legacy-claim read of the old localStorage key remains (`useAgentStream.ts:217`). |
| 11 | No Stop button while streaming | **Confirmed** | `abortRef` exists in `useAgentStream.ts:192` but no chat component wires a user-facing stop |
| 11 | Interrupt state memory-only | **Confirmed** | `useAgentStream.ts:182` `useState<InterruptState>`; nothing rehydrates it |
| 11 | Claim 403 fails silently | **Confirmed** | `useAgentStream.ts:222` swallows the error and clears the key regardless |
| 11 | Issue #109 open | **Confirmed** | `gh issue view 109` → OPEN |
| 12 | 0 `loading.tsx` | **Confirmed** | `find apps/web -name loading.tsx` → 0 |
| 12 | Hardcoded English aria-labels | **Confirmed (3)** | `auth/login/page.tsx:70`, `chat/AgentAvatar.tsx:21`, `auth/UserMenu.tsx:78` |
| 12 | Locale is a cookie, no localized URL | **Confirmed** | `src/i18n/locale.ts` uses `next/headers` cookies |
| 12 | "calm vs energetic" visual gap | **Not verifiable** — design taste, no success criterion |

### Rationale

The lane is high-risk on flag count alone; the hard gates make it unarguable. Confidence is low, not because any single item is unclear, but because "run intake on the section" admits at least three scopings that produce materially different plans (one spec vs three slices vs bugs-only), one premise is stale, and item 12's visual half has no verifiable criterion. Per `rules/orchestration.md`, ambiguous direction escalates regardless of lane.

### Alternatives considered

- Treat the whole section as one high-risk spec — rejected as the default: it mixes an e2e/CI fix, chat-resilience work needing a BE contract, and an SSR/i18n/visual refactor; a single PLAN.md would be >15 tasks with unrelated verify surfaces.
- Silently drop the stale identity claim and proceed — rejected: dropping scope is the user's call (`rules/behavior.md` §1), so it is recorded above and in E001.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Corroborate "no X-User-Id" | `grep -rln 'X-User-Id' apps/web/src` | 0 | only `src/lib/api/client.test.ts` (negative assertion) | |
| Corroborate "0 loading.tsx" | `find apps/web/src -name loading.tsx \| wc -l` | 0 | prints 0 | |
| Corroborate "e2e not in CI" | `grep -n playwright .github/workflows/ci.yml` | 1 | no match | |
| Corroborate #109 open | `gh issue view 109 --repo minhtran3124/travel-pi --json state` | 0 | `"state":"OPEN"` | |
| Summary shape | `python .claude/scripts/verify_summary.py --lane review-c-web-experience` | see below | | |

### Not auto-verified

- "trip-smoke.spec.ts is broken" — reached provenance (middleware source + spec source agree it would redirect); not re-run because Playwright/chromium is not installed in this session and the BE is not up. A real run is the first task of slice C1.
- "interrupt survives reload = graph stuck at plan node" — reached traceability (no rehydration code exists); the BE-side behaviour (whether the checkpoint's pending interrupt can be read back) was not exercised.

### Rollback

- Intake only: `git rm -r specs/review-c-web-experience`.

### Design backlog (E003-A, out of scope)

- Item 12 visual half — "calm vs energetic": no photography, coral token nearly unused. Revisit as a `brainstorming` design fork with a screenshot-reviewed deliverable when a product owner names the target feel.

### Harness-Delta

- backlog — a deep-review section is an *initiative*, not a change request; intake currently has to hand-slice it into child specs by escalation. A `feature-intake` "initiative → slices" step (one SUMMARY per slice, parent links) would remove the E001-style ask.
