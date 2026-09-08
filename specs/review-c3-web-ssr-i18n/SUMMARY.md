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

<not started — intake record only>

### Rationale

<pending design/research>

### Alternatives considered

- pending

### Deviations

- **Rule 3 (task 1.1)** — `@next/codemod middleware-to-proxy` refused to run against a dirty
  worktree and was re-run with `--force`. The tree was dirty only with this spec's own files and
  untracked harness state. Verified harmless: `git diff a4c3b37..72f50ad` is a single rename,
  1 insertion / 1 deletion, and a byte-level diff of the base blob against `proxy.ts` shows
  exactly one changed line (the export name).
- **Controller (wave 1 setup)** — creating the isolated worktree required `rsync`-ing `.claude/`
  because the harness is untracked, and that carried in a *tracked* file another session was
  editing (`.claude/settings.json`, a 4-hooks-into-one-dispatcher refactor). Reverted with
  `git checkout -- .claude/settings.json` before the first commit, so none of it reached this
  branch. Recorded because the failure mode is silent: rsync of a mostly-untracked directory also
  copies tracked in-flight edits.

### Verify

Re-run 2026-09-08 on `main` @ 0a7b6d7 — every intake count is unchanged since 2026-09-04.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Corroborate "0 loading.tsx" | `find apps/web/src -name loading.tsx \| wc -l` | 0 | prints `0` (2026-09-08: still 0) | |
| Corroborate "no streaming boundary at all" | `grep -rn Suspense apps/web/src --include='*.tsx' \| grep -v test \| wc -l` | 0 | prints `0` — no `loading.tsx` *and* no manual `<Suspense>`; `error.tsx` + `not-found.tsx` do exist at `src/app/` | |
| Corroborate "53/72 client" | `grep -rl 'use client' apps/web/src --include='*.tsx' \| grep -v .test.tsx \| wc -l` vs `find apps/web/src -name '*.tsx' ! -name '*.test.tsx' \| wc -l` | 0 | prints `53` and `72` — the review's ratio is over non-test files (105 .tsx incl. tests) | |
| Corroborate hardcoded aria-labels | `grep -rn 'aria-label="' apps/web/src --include='*.tsx' \| grep -v test` | 0 | 3 hits, unchanged: `auth/login/page.tsx:70` "Sign-in method", `chat/AgentAvatar.tsx:21` "Tin", `auth/UserMenu.tsx:78` "Account menu". Note `AgentAvatar` "Tin" is the brand name — likely correct as-is, not a leak | |
| Corroborate "locale is a cookie, no localized URL" | `sed -n '1,15p' apps/web/src/i18n/request.ts`; `cat apps/web/src/middleware.ts` | 0 | `getRequestConfig` reads `LOCALE_COOKIE` only ("no i18n routing" in-file comment); `middleware.ts` runs Supabase `updateSession` only — no `next-intl` locale middleware, no `[locale]` segment | |
| Corroborate the visual half is untouched | `grep -rn coral apps/web/src \| grep -v test \| wc -l` | 0 | prints `0` — the coral token is unused, consistent with the review. Out of scope here per parent E003-A | |

### Not auto-verified

- "PRs #141/#145 did not touch loading/SSR or the aria-label/URL leak" — reached **provenance** (the six Verify rows above re-derive every original count on today's `main`, which post-dates both merges); not re-run as a per-PR diff review.
- "Sequencing is unblocked" — reached **traceability** (`run_state.py status` reports `ready_to_merge` for `review-c1-e2e-auth-ci` and `review-c2-chat-resilience`); their PRs were not re-checked against the remote.

### Rollback

- Intake only so far: `git rm -r specs/review-c3-web-ssr-i18n`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- none
