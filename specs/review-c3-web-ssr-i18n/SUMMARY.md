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

## What changed

<not started — intake record only>

### Rationale

<pending design/research>

### Alternatives considered

- pending

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Corroborate "0 loading.tsx" | `find apps/web/src -name loading.tsx \| wc -l` | 0 | prints 0 | |
| Corroborate hardcoded aria-labels | `grep -rn 'aria-label="' apps/web/src --include='*.tsx' \| grep -v test` | 0 | 3 hits: login/page.tsx:70, AgentAvatar.tsx:21, UserMenu.tsx:78 | |

### Not auto-verified

- none yet (no claims made)

### Rollback

- Intake only so far: `git rm -r specs/review-c3-web-ssr-i18n`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- none
