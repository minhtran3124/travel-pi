---
problem_type: bug
module: web/components
tags: tailwind, responsive, overflow, tabs, mobile, uat, playwright, layout
severity: standard
applicable_when: Adding a tab, chip, or any item to a horizontal flex strip whose item count can grow — especially one rendered inside a trip/detail page that must work at 390px.
affects:
  - apps/web/src/components/ui/Tabs.tsx
supersedes: null
confidence: high
confirmed_at: 2026-09-09
---
## Problem

Adding the sixth tab to the trip page broke the whole document at mobile width. At a
390px viewport the page itself scrolled sideways to 458px, dragging the header and every
section with it. No test caught it; it was found by browser UAT taking a screenshot at
mobile size.

## Root Cause

The tab strip is a `flex` row with no overflow handling, so its default
`overflow-x: visible` lets children push past the container instead of scrolling inside
it. Six tabs measured 434px of content in a 342px box. Flex children also default to
`min-width: auto`, so they refuse to shrink below their text width — the row cannot
absorb the excess, and the overflow propagates up to the document.

Five tabs happened to fit. The bug was latent from the day the component was written and
was triggered by content, not by the change that exposed it.

## Fix

Make the strip scroll inside itself, and stop the children from shrinking:

## Code Example

```tsx
<div
  role="tablist"
  className="flex gap-md overflow-x-auto border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
>
  {tabs.map((t) => (
    <button key={t.id} className="shrink-0 …">{t.label}</button>
  ))}
</div>
```

`overflow-x-auto` contains the overflow. `shrink-0` keeps each tab at its natural width so
the row scrolls rather than squeezing labels. The two `scrollbar` utilities hide the bar
without disabling the scroll.

## Regression Test

None at the unit level — jsdom has no layout engine and will report the same DOM as
passing at any width. The check that works is a browser assertion at a fixed viewport:
open the page at 390px and assert
`document.documentElement.scrollWidth <= window.innerWidth`. Add that to the UAT script
for any page with a growable horizontal strip.

## Prevention

- Any horizontal flex row whose item count can grow gets `overflow-x-auto` plus
  `shrink-0` children when it is written, not when it breaks.
- Run at least one UAT case at 390px. Overflow is a class of defect that is invisible to
  every test that does not perform layout.
