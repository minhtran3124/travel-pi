# Test Matrix — dashboard-delight (slice 2)

Execution session: 2026-07-11. All checks run from `apps/api/` unless noted.
Suite: `../../.venv/bin/python -m pytest tests/api -k "dashboard or places or tips or visa or bookings or hotels or board or agent_config" -q` → **299 passed, 471 deselected**.

## Per-task verify gates

| Task | Verify command | Result |
|---|---|---|
| 1.1 tips/places reduced-motion | `grep -q prefers-reduced-motion tips.html && grep -q prefers-reduced-motion places.html && pytest -k "tips or places"` | ✅ 166 passed; guards present in both |
| 1.2 agent-config roster + ban | `! grep -E 'border-left:[^;]*(2\|3\|4)px' agent_config.html && pytest -k "agent_config"` | ✅ 0 banned stripes; `.ac-secbar` removed; 200 |
| 2.1 board settle (hero) | `grep -q prefers-reduced-motion board.html && pytest -k "board or dashboard"` | ✅ 40 passed; dateline + colon-blink + flap-settle present |
| 2.2 bookings stub ledger | `pytest -k "bookings"` | ✅ 42 passed; stub-code + bk-stamp shipped |
| 2.3 search route-arc + settle | `grep -q prefers-reduced-motion search.html && pytest -k "search or flight"` | ✅ 115 passed; empty-arc + s-flap-settle present |
| 3.1 visa passport stamp | `grep -q prefers-reduced-motion visa.html && pytest -k "visa"` | ✅ 12 passed; stamp-in aligned to spec |

## Design-system bans (changed templates)

| Ban | Check | Result |
|---|---|---|
| Colored side-stripe (`border-left/right` > 1px accent) | `grep -nE 'border-(left\|right):[^;]*(2\|3\|4\|5)px'` across all 7 templates | ✅ Only match is `bookings.html .ref { border-left: 2px dashed var(--line) }` — a **neutral** perforation motif (same pattern as `flight_detail.html` `.pass-perf`), not a colored accent stripe |
| Gradient text | `grep -nE 'background-clip:[[:space:]]*text\|text-fill-color'` | ✅ None found |
| Glassmorphism | `grep -nE 'backdrop-filter'` in new templates | ✅ None added by this slice; pre-existing modal/photo backdrops unchanged |

## Motion hygiene

| Check | Result |
|---|---|
| Every changed template has a `prefers-reduced-motion` block | ✅ board, bookings, search, agent_config, tips, places, visa — all present |
| Board settle total ≤ 600 ms | ✅ `animation-delay: min(calc(var(--i)*28ms), 400ms)` + `.18s` duration = **580 ms** max |
| Board settle once-per-navigation | ✅ JS adds `.is-settling` on `DOMContentLoaded`, removes after 650 ms, skips on bfcache (`pageshow` persisted) and under reduced-motion |
| New keyframes all guarded | ✅ `clk-blink`, `flap-settle` (board), `s-flap-settle` (search), `stamp-in` (visa) — each has a reduced-motion override |

## AA contrast — stamp / stub / roster text (WCAG, both themes)

Computed via relative-luminance formula; opacity-composited where the element uses opacity.

| Element | Sunset | Nightfall | Threshold | Pass |
|---|---|---|---|---|
| Bookings "Cancelled" stamp (red @0.9 on panel) | 5.15:1 | 4.88:1 | ≥4.5 (normal) | ✅ |
| Bookings stub-code (accent-dim on panel) | 9.06:1 | 10.72:1 | ≥4.5 | ✅ |
| Roster agent name (ink on panel) | 13.88:1 | 13.19:1 | ≥4.5 | ✅ |
| Roster section count-chip — accent | 9.06:1 | 10.72:1 | ≥3.0 (large) | ✅ |
| Roster section count-chip — cyan | 7.79:1 | 7.40:1 | ≥3.0 | ✅ |
| Roster section count-chip — violet | 6.31:1 | 6.00:1 | ≥3.0 | ✅ |
| Visa stamp — visa-free (green @0.9) | 7.26:1 | 6.97:1 | ≥4.5 | ✅ |
| Visa stamp — visa-required (red @0.9) | 5.15:1 | 4.88:1 | ≥4.5 | ✅ |

No color-alone meaning: the bookings stamp keeps the "Cancelled" text label; the visa stamp carries "Visa-Free Entry" / "Visa Required" text; roster sections carry glyph + title + count.

## Render smoke (server HTML)

Throwaway `client`-based GETs (run then removed — no Python committed per the templates-only scope). All asserted the new markup is present in the rendered output:

| Route | Asserted artifacts |
|---|---|
| `/dashboard/flights` | `dateline`, `clk-colon`, `fids-board`, `flap-settle`, `is-settling` |
| `/dashboard/flights/search` | `empty-arc`, inline `<svg>`, `s-flap-settle`, `prefers-reduced-motion` |
| `/dashboard/bookings` | `stub-code`, `bk-stamp`, `border-left: 2px dashed` |
| `/dashboard/agent-config` | no `ac-secbar`, `ac-secglyph`, `data-agent="supervisor"` |
| `/dashboard/tips`, `/dashboard/places` | `prefers-reduced-motion` |
| `/dashboard/visa` | `stamp-in`, `prefers-reduced-motion` |

Result: **6/6 passed**.

## Theme coverage note

Sunset and Nightfall share the same server-rendered DOM; Nightfall is a client-side `html[data-theme="nightfall"]` token swap (CSS variable values only). All structural artifacts are theme-agnostic, and AA was computed for **both** token sets above. A live cross-theme screenshot pass (Sunset + Nightfall + one reduced-motion pass per changed page) is the remaining manual visual step — recommended in a browser before merge.
