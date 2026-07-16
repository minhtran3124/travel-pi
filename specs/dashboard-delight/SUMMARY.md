# SUMMARY — dashboard-delight

- **Lane:** normal
- **Confidence:** high
- **Reason:** Templates-only visual amplification of 4 flat dashboard pages + 2
  hygiene fixes; no Python, no API surface, no hard-gate signals. Multi-file /
  multi-wave → normal lane with per-task verify gates; direction confirmed by the
  user (flat spots + one hero, travel-metaphor theatrics, plan-then-execute).

## Rationale

The dashboard's identity ("Sunset Departures Board") is carried by a few strong
pages while board/bookings/search/agent-config stayed generic; research also found
two design-system violations (banned side-stripes in agent_config.html, missing
reduced-motion guards in tips/places). Amplifying the flat pages with the system's
own airport metaphor closes the gap without touching what already works.

## Alternatives considered

- **Whole-dashboard systemic pass** — rejected for this slice: higher regression
  surface across slice-1's fresh a11y work, and the strong pages don't need it.
- **Single hero page only** — rejected: leaves the ban violations and the flattest
  pages (bookings, agent-config) unfixed.
- **Shared settle/stamp primitives in base.html** — rejected at plan level: creates
  wave file-overlap and regression surface; page-scoped CSS keeps tasks disjoint.

### Deviations

- **Task 3.1 (visa stamp)** was largely already implemented in the template
  (rounded border, rotation, uppercase, status-coloured, `stamp-in` entrance +
  reduced-motion guard). The execution pass aligned the entrance to the plan's
  specified parameters (scale 1.15→1, ~200 ms) — a 2-line change; structure
  untouched.
- **Cross-theme screenshots** are a client-side concern: Sunset/Nightfall share
  one server-rendered DOM (Nightfall is a `data-theme` token swap), so AA was
  verified for both token sets programmatically; a live browser screenshot pass
  remains the recommended manual step before merge.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Full slice-1 selection | `cd apps/api && ../../.venv/bin/python -m pytest tests/api -k "dashboard or places or tips or visa or bookings or hotels or board or agent_config" -q` | 0 | **299 passed**, 471 deselected |
| Per-task gates (1.1→3.1) | (see TEST_MATRIX.md) | 0 | 166 / 200 / 40 / 42 / 115 / 12 passed |
| Ban: colored side-stripes | `grep -nE 'border-(left\|right):[^;]*(2\|3\|4\|5)px'` over 7 templates | 0 | only the neutral `var(--line)` perforation in bookings (sanctioned motif); no gradient text; no new glassmorphism |
| AA stamp/stub/roster | luminance script, both themes | 0 | all ≥4.5:1 (normal) / ≥3:1 (large); no color-alone meaning |
| Reduced-motion guards | `grep -q prefers-reduced-motion` per template | 0 | all 7 changed templates; settle ≤580 ms, once-per-nav |
| Render smoke | throwaway `client` GETs (removed) | 0 | 6/6 new artifacts present in rendered HTML |

### Rollback

- Templates only: `git revert <task shas>` — no migrations, no data.
