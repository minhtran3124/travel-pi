# Workflow State

Source of truth for the currently-active spec. Updated by skills and by the `state-breadcrumb.sh` hook.

## Active Spec

- **Slug:** gh-199-rest-duplicate-booking-warning
- **Phase:** design  <!-- design | research | plan | implement | review | shipped -->
- **Last skill:** feature-intake (+ ESCALATIONS E001/E002 decided) → next: brainstorming → xia2 (Deep) → writing-plans
- **Last action:** gh-200 shipped — PR #206 merged → main (e5f72d0): items 1–4 of #200 (hotel warning quotes the
  existing booking, availability before the duplicate block, id-bearing `[possible-duplicate:<id>]` marker,
  per-booking override guard against every matching booking, FakeLLM graph test); item 5 (`_as_date` softening)
  deferred, #200 left open ("Refs #200"). gh-199 unblocked: E001 A (extend `ErrorResponse` with optional
  `code` + `details`; 409 `possible_duplicate`), E002 A (FE: `errors.ts` 409 mapping + regenerated
  `schema.d.ts`, no page UI). Lane high-risk / confidence high. Start from `github/main` (local `main` was stale).
- **Updated:** 2026-09-15

## Recent Specs

<!-- Populated as specs are created. Keep last 10. -->

| Slug | Created | Last phase | Status |
|---|---|---|---|
| ci-secret-scanning | 2026-09-15 | shipped | merged via PR #210 → main (af28801) |
| state-md-auto-update-on-merge | 2026-09-15 | shipped | merged via PR #209 → main (fbee3f2); high-risk/high; A (post-merge workflow) + B (session log out of STATE.md) |
| gh-199-rest-duplicate-booking-warning | 2026-09-15 | design | high-risk/high; E001 A (ErrorResponse code+details), E002 A (FE plumbing only); next: brainstorming |
| gh-200-duplicate-warning-polish | 2026-09-15 | shipped | merged via PR #206 → main (e5f72d0); items 1–4; item 5 deferred (#200 open); C1 fixed in review |
| gh-198-booking-duplicate-check-atomic | 2026-09-15 | shipped | merged via PR #203 → main (22dadff); per-owner xact advisory lock |
| gh-194-duplicate-booking-warning | 2026-09-14 | shipped | merged via PR #197 → main (ef9aec1); agent-only duplicate warning |
| specialist-task-description | 2026-09-10 | shipped | merged via PR #192 → main (f67e7c6); fan-out task note; value not demonstrated by eval |
| prompt-caching-system-prefix | 2026-09-08 | shipped | merged via PR #190 → main (b96569a); caching already on (71.9%), 24h retention + report script |
| close-product-loop-s2-guide-and-map | 2026-09-09 | shipped | merged via PR #172 → main (8cdfed4); UAT found and fixed a tab-overflow regression |
| gh-147-dated-hotel-availability-routing | 2026-09-09 | shipped | merged via PR #171 → main (a6e7998); hotels eval 50% → 83.3% |
| flight-booking-passenger-count | 2026-09-09 | shipped | merged in PR #167 |
| close-product-loop-s1-booking-ui | 2026-09-08 | shipped | merged via PR #167 → main (4cb8f10) |
| close-product-loop | 2026-09-08 | design | umbrella design APPROVED by user; 6 slices, S1 shipped (PR #167) |
| gh-156-flight-search-before-create-trip | 2026-09-08 | shipped | merged via PR #165 → main (0a7b6d7) |
| side-panel-multi-category-tabs | 2026-09-08 | shipped | merged via PR #164 → main (9114bac); browser UAT in specs/…/uat |
| plan-approved-line-reset | 2026-09-07 | shipped | merged via PR #158 → main |
| agent-system-copy-i18n | 2026-09-07 | shipped | merged via PR #145 → main |
| agent-tool-round-budget | 2026-09-05 | shipped | merged via PR #143 → main |
| agent-budget-trip-context | 2026-09-05 | shipped | merged via PR #142 → main |
| catalog-content-i18n | 2026-09-05 | shipped | merged via PR #141 → main |

## Notes

- Skills update the "Active Spec" block when they start/finish
- `state-breadcrumb.sh` (SessionEnd hook) writes session breadcrumbs to the gitignored
  `.harness-state/session-log.md`, not here, so this file stays clean between sessions
- `.github/workflows/state-on-merge.yml` marks a spec shipped here (and in its RUN.json)
  after its PR merges into main
- `/session-tracker` reads this file to resume work across sessions
- If the Active Spec block is stale (>7 days without update), treat as idle
