# Product

## Register

product

## Users

Developers building and testing against the Travel Planner **mock API** — the
engineers wiring up the travel-agent frontend and the agent itself. Their
context is a dev workflow: they hit the mock endpoints (flights, hotels,
places, tips, weather, bookings) and need to *see* what came back without
reaching for `curl` or reading raw JSON in Swagger. The dashboard is the
human-readable window onto the same data the TypeScript client consumes. It's
glanced at on a second monitor mid-task, not lived in.

The job to be done: "Did the endpoint return what I expected, and does it look
right?" — answered in seconds, repeatedly, across a working session.

## Product Purpose

A server-rendered dashboard (`/dashboard/*`, Jinja2) that visualizes
everything the mock Travel Planner API returns: an airport-style FIDS board
for flights, a card grid for hotels and places, local tips by region, live
weather, and a ledger of bookings. It exists so developers can verify mock
behavior visually and so the mock reads as a *credible* stand-in for a real
travel product — useful both as a debugging surface and as a reference of
what the real thing should feel like.

Success looks like three things at once:
1. **Scannable** — dense travel data (routes, times, prices, status) is
   readable at a glance; the FIDS-board metaphor taken seriously.
2. **Credible** — it feels like a real travel product, so the mock is
   convincing as a reference implementation.
3. **Fast** — moving between flights / hotels / places / bookings is
   frictionless for repetitive checking.

## Brand Personality

Polished SaaS product — a notch warmer and more approachable than a raw ops
terminal, but still unmistakably data-first. Confident, clear, modern. The
voice is precise and plain: real labels, no marketing copy, no exclamation
points. Three words: **clear, credible, efficient.** The emotional goal is
quiet trust — the user should believe the data and never fight the interface
to read it.

## Anti-references

- **Generic AI-SaaS slop.** No cream/sand/parchment backgrounds, no tiny
  uppercase tracked eyebrows above every section, no endless identical
  icon+heading+text card grids, no gradient text, no big-number "hero metric"
  template.
- **Heavy enterprise/admin.** Not Bootstrap/AdminLTE clutter — no boxy gray
  panels stacked wall-to-wall, no colored side-stripe alert borders, no
  config-panel overload.
- **Over-designed marketing.** No landing-page flourishes bolted onto a data
  tool — glassmorphism everywhere, decorative gradients, or motion that
  fights legibility are all wrong here. Effects must earn their place by
  helping read the data.

## Design Principles

- **Data first, chrome second.** Every pixel should help read the data. If a
  decoration doesn't aid scanning, it's cut.
- **Scannable by structure.** Lean on the FIDS metaphor: tabular numerics,
  consistent column rhythm, and status carried by color coding the eye can
  learn (on-time / delayed / landed / boarding).
- **Credible realism.** Mimic the conventions of real travel products
  (boards, cards, ledgers) so the mock is convincing — never cartoonish, never
  obviously fake.
- **Polished, not precious.** SaaS-clean and a touch warm, but plain-spoken;
  resist marketing flourish and visual noise alike.
- **Frictionless traversal.** Section-to-section navigation is fast and
  predictable; the dashboard rewards repeated, habitual use.

## Accessibility & Inclusion

Target **WCAG AA**. On the dark theme this means body text ≥4.5:1 against its
panel background and large/bold text ≥3:1 — watch muted gray (`--muted`) on
panels, which is the likeliest failure. Keep visible focus rings (the existing
`--ring` token) on every interactive control. Honor
`prefers-reduced-motion`: the nav progress bar, hover lifts, and any future
transitions need a reduced/instant alternative. Don't encode meaning in color
alone — status remarks should carry a label, not just a hue.
