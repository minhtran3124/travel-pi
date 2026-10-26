# review-c3-web-ssr-i18n — Summary

Lane: normal
Confidence: medium
Reason: no hard gate; flags existing behavior, multi-domain (routing, loading states, i18n). Confidence medium: the documented default is keep cookie-based locale and add loading.tsx + i18n'd aria-labels + cheap server-component conversions; the localized-URL question is a design fork to settle in brainstorming, not an escalation.
Flags: existing behavior, multi-domain
Affects: apps/web/src/app/**/loading.tsx (new), apps/web/src/i18n/*, apps/web/messages/*, auth/login/page.tsx, chat/AgentAvatar.tsx, auth/UserMenu.tsx, selected page.tsx client→server conversions
Input-type: spec slice
Route: normal — brainstorming (design fork: cookie locale vs [locale] path segment for shareable URLs) → xia2 (Standard) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (parent ESCALATIONS E001–E003 decided 2026-09-04; see ../review-c-web-experience/ESCALATIONS.md)
Parent: review-c-web-experience

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> chay /feature-intake cho section "C. Web app & trải nghiệm" theo artifact link https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview
>
> (follow-up, 2026-09-04) 1. ok  2. lam hop dong BE  3. backlog A

Slice of the parent intent (verbatim review text in `../review-c-web-experience/SUMMARY.md` § Intent):

> Item 12 (measurable half): 53/72 .tsx are client components, 0 `loading.tsx`; some aria-labels are hardcoded English; locale is a cookie so there is no shareable localized URL. (The "calm vs energetic" visual half is out of scope per E003-A — design backlog.)

Re-raised verbatim at re-intake (2026-09-08, `/feature-intake tiep tuc cho`):

> Không có loading state, i18n rò rỉ, visual còn nhạt
> 53 trên 72 file tsx là client component và không có file loading.tsx nào; vài aria-label hardcode tiếng Anh; locale nằm ở cookie nên không có URL để chia sẻ theo ngôn ngữ.
>
> Một phần — PR #141 và #145 đóng phần nội dung đa ngữ (catalog EN/VI, agent trả lời theo ngôn ngữ hội thoại). Phần loading và SSR chưa động: vẫn 0 loading.tsx.

**Re-intake verdict: no new spec.** This is the same slice; `review-c3-web-ssr-i18n` stays the
record (slug unchanged per the feature-intake never-rename rule). Sequencing per parent E001-A
(`c1 → c2 → c3`) is now unblocked: `review-c1-e2e-auth-ci` and `review-c2-chat-resilience` are both
`ready_to_merge`. Lane and Confidence re-affirmed unchanged.

**What PRs #141/#145 did and did not close.** They closed the *content* half of i18n — catalog
EN/VI via `content_translations` (#141) and agent replies following the conversation language
(#145). Neither touched this slice: the leak here is *chrome* (hardcoded `aria-label`s) and
*addressability* (cookie locale, no shareable URL), plus loading/SSR. Every original count still
holds on `main` at 0a7b6d7 — see the refreshed `### Verify` table.

## What changed

Two of the four list pages spun a bare spinner while loading and two place-held with a shaped
skeleton; the app header leaked English regardless of locale; and a chosen language lived only in a
cookie, so no link could carry it. All four pages now place-hold with a skeleton shaped like the
content that is coming, announce loading to a screen reader, and keep their header and filter row
live while data arrives. `?lang=vi` on any page link opens the app in that language for whoever
receives it. Six chrome strings moved into both catalogs.

Two supporting changes came with it: the Next 16 deprecation of the `middleware` convention was
taken (`src/middleware.ts` -> `src/proxy.ts`, via the official codemod, as its own commit), and
`Spinner` now requires an explicit `label` so the English default cannot reach a screen reader.

**The loading half was cut on evidence, and the deep-review item it came from is not fully closed.**
No `loading.tsx` ships. See `### Intent Findings`.

### Rationale

The slice kept the app's client-fetch architecture rather than converting pages to server
components, because a server fetch would need a server-side auth path that `authHeader()` is
deliberately built not to provide.

That constraint is what removed the `loading.tsx` half. A probe on the running dev server measured
`loading.tsx` never painting for a client-fetch page — with prefetch on and off — while an
`await`ing server component painted it every time. `loading.tsx` is the Suspense fallback for
*server* rendering of a segment; a `"use client"` page never suspends on the server, so the file
would have been inert. The measurement is recorded in `design.md` §3.1 rather than the reasoning,
so the decision can be re-tested instead of re-argued.

The shareable-URL half is a query param that seeds the cookie and redirects, not a `[locale]` path
segment. It reaches the outcome asked for at a fraction of the blast radius: no route restructure,
no `<Link>` rewrite, no middleware chain change.

### Alternatives considered

- **Convert the pages to server components and ship real `loading.tsx` boundaries.** Rejected by
  the user at design time as an architecture change, and it needs a server-side auth path this
  slice does not build. It remains the only way to close the intent's loading half — see
  `### Intent Findings`.
- **Ship `loading.tsx` anyway, as scaffolding for a future migration.** Rejected: four components
  that never render plus tests asserting a transition that does not occur, and a strong signal to
  the next reader that this app has SSR when it does not.
- **`[locale]` path segments for the shareable URL.** Rejected: touches every route, every internal
  `<Link>`, the auth middleware chain and both Playwright specs, to gain `hreflang` and
  per-language indexing that nobody asked for. Recorded as the upgrade path if SEO becomes a
  requirement.
- **Widen the hardcoded-string gate to all of `components/auth/`.** Rejected on evidence:
  `AuthHero.tsx` and `OAuthButtons.tsx` have zero `useTranslations` and belong to the auth surface
  owned by `auth-pages-redesign` behind an Auth hard gate. Widening would make the gate fire on
  files this slice must not touch — a gate someone would then have to switch off.

### Verify

Re-run on the branch head. Every row is a single pipe-free command; each names the Success Criterion
it satisfies. The 12 SC rows live in `PLAN.md` §3.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Proxy convention file | `test ! -f apps/web/src/middleware.ts && grep -q "export async function proxy" apps/web/src/proxy.ts` | 0 | `middleware.ts` gone, `proxy` exported | SC-1 |
| `?lang=` seeds the cookie and redirects | `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.seed.test.ts` | 0 | cookie asserted by full shape, not just value | SC-2 |
| Session cookies survive the redirect | `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.cookies.test.ts` | 0 | | SC-3 |
| Non-navigations are left untouched | `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.suppression.test.ts` | 0 | 7 cases incl. the `/auth/` route-handler case added by correctness review | SC-4 |
| `/trips` skeleton + live region | `cd apps/web && pnpm exec vitest run src/app/trips/page.test.tsx` | 0 | | SC-5 |
| `/trips/[tripId]` tab bar + live region | `cd apps/web && pnpm exec vitest run "src/app/trips/[tripId]/page.test.tsx"` | 0 | | SC-6 |
| `/bookings` skeleton, no spinner, filters live | `cd apps/web && pnpm exec vitest run src/app/bookings/page.test.tsx` | 0 | | SC-7 |
| `/places` skeleton, no spinner, filters live | `cd apps/web && pnpm exec vitest run src/app/places/page.test.tsx` | 0 | | SC-8 |
| Six new keys in both catalogs | `cd apps/web && node -e "const f=require('fs');const n=['Nav.menuOpen','Nav.menuClose','Account.signIn','Account.menuLabel','Account.signOut','TripDetail.loadingLabel'];for(const p of ['messages/en.json','messages/vi.json']){const j=JSON.parse(f.readFileSync(p));for(const k of n){const s=k.split('.');const v=j[s[0]];if(!v)throw new Error(p+' missing '+k);if(!v[s[1]])throw new Error(p+' missing '+k)}}" && pnpm exec vitest run src/messages.parity.test.ts` | 0 | parity alone passes on a tree with none of the keys, hence the presence half | SC-9 |
| Hardcoded-string gate | `cd apps/web && pnpm exec vitest run src/i18n/no-hardcoded-strings.test.ts` | 0 | each detector proves its own scanned count, clean tree, and fixture | SC-10 |
| Workspace type-check | `cd apps/web && pnpm exec tsc --noEmit` | 0 | proves no `Spinner` caller omits `label` | SC-11 |
| Proxy composition preserves the session | `cd apps/web && pnpm exec vitest run src/proxy.test.ts` | 0 | 5 cases, one per `applyLangParam` branch | SC-12 |
| Full suite | `cd apps/web && pnpm exec vitest run` | 0 | 47 files / 254 tests, from a 38/217 baseline | |
| Lint | `cd apps/web && pnpm lint` | 0 | 1 pre-existing warning in `chat/useAgentStream.ts` | |
| Build | `cd apps/web && pnpm build` | 0 | route table lists `f Proxy (Middleware)`; the Next deprecation warning is gone | |

### Intent Findings

`intent-review` ran blind to `PLAN.md` prose, `design.md` and `research-brief.md`, against the
verbatim `### Intent` above. Verdict: **gaps-found**. Its sharpest observation is recorded first
because it is correct and load-bearing:

> The branch is 12/12 against its own Success Criteria while leaving the intent's headline defect
> intact — the SC table itself encodes the drift.

- **gap, blocking — no `loading.tsx`, no `Suspense`, 53 client components unchanged.** The intent
  names the absence of `loading.tsx` as the defect, twice. It is still absent. This is not an
  execution failure: it is the user-approved scope reduction recorded in `### Rationale`, taken on
  a measurement. But on the intent's own terms the item is open, and the reviewer is right that the
  two gaps close together or not at all — with no async server work, a `loading.tsx` has nothing to
  wait on. **Closing it requires the RSC fork: a separate spec, `high-risk` lane, needing a
  server-side auth path.** Not fixed here, by decision.

  **Decision of record (standing, 2026-09-08).** The user was shown the measurement at design time
  — `loading.tsx` never painting for a client-fetch page — and chose "bỏ loading.tsx, giữ phần còn
  lại". The oracle re-surfaced it independently, blind to that reasoning, which is the point of the
  oracle; it does not overturn the decision. Deep-review item 12 therefore stays **open**, and
  closing it means the RSC fork as its own `high-risk` spec. Recorded here so the next reader finds
  the reason attached to the gap rather than having to reconstruct it.
- **gap, advisory — one hardcoded `aria-label` survives.** `app/auth/login/page.tsx:70`
  ("Sign-in method"), and the new gate excludes `app/auth/` by design. Legitimate as a boundary,
  but it is a named instance of the requested defect deferred to `auth-pages-redesign`, not a
  closed item.
- **drift, advisory, equivalent — shareable locale is `?lang=`, not a `[locale]` segment.** A
  shared `/trips?lang=vi` does render Vietnamese for the recipient. Residual the reviewer found and
  this slice did not consider: because the redirect strips `lang`, a user who then copies their
  address bar shares a locale-less URL again. "Hand someone a built link" works; "share the page I
  am looking at" does not.
- **excess, advisory — two unrequested surface changes**, both reported only, neither reverted: the
  `middleware.ts` -> `proxy.ts` codemod rename (not required by `applyLangParam`; taken because the
  convention is deprecated in Next 16 and this slice edits that exact file), and `Spinner.label`
  becoming required (a breaking change to a shared component's public API, with all 11 call sites
  already compliant).

### Correctness Findings

`correctness-review` ran six blind angles over `main..HEAD`. Nine distinct locations; five fixed in
`39b7788`, one escalated, three recorded here.

Fixed: live regions were mounted already populated and so may never have been announced — the
feature was silent (all four pages hoisted); `/auth/callback` and `/auth/confirm` were treated as
document navigations and would have 307'd a single-use magic-link code; the `aria-label` detector
matched one of four spellings; its JSX-text detector scanned test fixtures; a comment overstated
what the row-5 redirect preserves.

Escalated: **E001** — `proxy.ts:6` awaits `updateSession` with no boundary, so an auth-backend
outage returns 500 for every matched path including `/auth/login`. Predates this branch; the fix is
an auth-scope decision. **`ESCALATIONS.md` decision is `pending`, which blocks this slug.**

Recorded, not fixed:

- `langParam.ts:41-44` — `?lang=` is carried into the auth gate's `next=` param, costing one extra
  redirect after sign-in. End state is correct; the fix means rewriting a nested param inside a
  redirect's `Location` on the auth path, which is not worth the risk for a round trip.
- `langParam.ts:12` — a missing `sec-fetch-dest` is treated as a document navigation, so a
  Sec-Fetch-less client (Safari < 16.4) could receive a 307 for an RSC fetch. This is the
  documented decision in `design.md` §4.3 condition 3, locked by suppression case (f) for curl and
  link unfurlers, and no internal `?lang=` link exists today to reach it.
- `trips/page.tsx:22` — `momentum()` compares `toISOString()` (UTC) against local calendar dates,
  so at UTC+7 the strip misreports which trip is current between 00:00 and 07:00. Real, flagged
  `unmodified-line`, unrelated to this slice, and pre-existing. Fixing it here would bury a real
  bug in a PR nobody will review for it.

### Not auto-verified

- **The Playwright regression did not run.** `PLAN.md` §6 names `pnpm e2e` as a finish step. It
  could not be executed here: `playwright.config.ts` hardcodes `baseURL: http://localhost:3000`
  with `reuseExistingServer: !CI`, and port 3000 on this machine is held by an unrelated
  application. Playwright attached to that app and failed in `auth.setup.ts` on a strict-mode
  violation whose captured DOM carries Clerk class names (`cl-formFieldInput`,
  `cl-formFieldInputShowPasswordButton`) — this repository uses Supabase, so the run never reached
  our app. Nothing about this branch is implicated: it changes no file under `app/auth/`. Reported
  as **not run**, not as a pass and not as a failure. A reviewer on a clean machine, or CI (where
  `reuseExistingServer` is false), should run it.

- "The loading announcement is actually spoken by a screen reader" — reached **traceability**: the
  live region is now hoisted so its content changes after it exists, which is the shape assistive
  technology requires, and a test asserts the region exists in both states. No screen reader was
  run. This is the one claim in this slice whose proof needs a human with NVDA, JAWS or VoiceOver.
- "A shared `?lang=vi` link opens in Vietnamese for a real recipient" — reached **provenance**:
  proven by unit tests over `applyLangParam` and by the composition test loading `proxy.ts`; no
  browser UAT was run against a deployed instance.
- "The `pnpm build` route table proves Next resolves `src/proxy.ts`" — reached **truth** (the
  command was re-run and its output read), but it does not prove request-time behaviour of the
  composed proxy in production.
- Intent gaps above are decisions, not verifications: the loading half is absent by choice and no
  check can make that a pass.

### Rollback

- Whole branch: `git revert --no-commit 0a7b6d7..HEAD && git commit` from the worktree, or simply
  do not merge — nothing here is deployed.
- The one change with reach beyond this slice is the convention rename; revert it alone with
  `git revert 72f50ad`, which restores `src/middleware.ts` and its export name. Do that before
  reverting `74ffd25`, or the proxy will import a wiring that no longer has a file.
- No migration, no backend change, no public API change.

### Harness-Delta

- **backlog** — the `state-breadcrumb.sh` SessionEnd hook fires for every *subagent* that exits,
  appending a `### <timestamp>` block to the tracked `specs/STATE.md` with `user_turns: 0` and no
  exit reason. One wave of this run added 56 such lines. They carry no information a reader can
  act on and they put a tracked file into every feature diff, so they were reverted by hand here.
  The hook should either skip subagent sessions or write to an untracked location.
