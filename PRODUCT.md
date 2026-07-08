# Product

## Register

product

## Users

Frequent, confident travelers managing more than one trip at a time. They come to
the app to research destinations, build and adjust itineraries, and keep bookings,
budget, and logistics in one place — often returning across the lifecycle of a trip
(planning → in-transit → recap). They value speed, density of useful information at
a glance, and an AI agent that can do real work (plan, book, answer) rather than
just chat. The primary job on any screen: *make the next decision about a trip and
move on* — shortlist a place, lock a booking, check a budget, ask the agent.

## Product Purpose

A travel planner built around an AI agent. Users plan trips, explore places, manage
bookings, and track budget; a streaming, human-in-the-loop chat agent (planner /
concierge / journal / booking / budget sub-agents) does the heavy lifting alongside
the manual UI. Success is the user trusting the agent enough to hand off real tasks,
and the surrounding UI being fast and legible enough that they never feel managed —
they feel in control. Everything the agent can do, the user can also do directly, and
vice-versa.

## Brand Personality

**Energetic, playful, friendly.** Three words: *lively, warm, capable.* The voice is a
well-traveled friend who happens to be great at logistics — encouraging, never stiff,
never corporate. Delight comes from momentum and small moments (a confident accent, a
satisfying confirmation, motion that feels alive), not from mascots or confetti. The
agent should read as an enthusiastic guide that's genuinely good at the job.

**Reference qualities (the *specific* thing to borrow, not the whole app):**
- **Airbnb** — friendly, photo-forward warmth; rounded, approachable surfaces that
  stay grown-up.
- **Hopper** — playful color and lively motion; the agent-as-guide energy where the
  product feels like it's actively helping.
- **Duolingo** — high personality and the craft of *delight as a system* (earned
  micro-moments) — borrow the polish of its delight, **not** its mascot/gamification.

> **Direction note (live tension):** the shipped visual system today is *calm and
> restrained* (clean white panels, near-black ink, a single chartreuse accent). The
> desired personality is *more energetic and playful than that.* The path forward is
> to keep the clean, fast, legible base and inject energy through accent use, motion,
> photography/illustration, and copy — **not** by abandoning restraint for noise. Bias
> future work toward closing this gap deliberately.

## Anti-references

- **Generic SaaS dashboard** — card-grid sea, gray-on-white, the hero-metric template,
  identical icon+heading+text tiles. The AI-slop default; avoid entirely.
- **Corporate OTA (Expedia / Booking)** — dense, ad-heavy, banner clutter, fake-urgency
  badges ("2 left at this price!"). Cheap-feeling; the opposite of trustworthy.
- **Childish / over-gamified** — confetti everywhere, cartoon mascots, juvenile. Playful
  must stay grown-up.
- **Cold enterprise tool** — sterile dense data tables, zero warmth, no personality.

## Design Principles

1. **Capable, not corporate.** Personality and warmth are features, not decoration —
   but every playful choice must also make the user faster or more confident. Delight
   that costs clarity is cut.
2. **Energy through motion and accent, not noise.** Carry the lively feel with
   intentional motion, photography, and the chartreuse accent used decisively — never
   by adding more color, more borders, or more cards.
3. **Agent-native parity.** Anything the user can do in the UI, the agent can do, and
   anything the agent does is visible and reversible in the UI. Neither path is a
   second-class citizen.
4. **In control, never managed.** The interface keeps the user oriented and in charge
   even as the agent acts — clear state, human-in-the-loop checkpoints, nothing
   happening behind their back.
5. **Earned delight.** Small, systematic moments (confirmations, transitions, the agent
   landing a result) — Duolingo's craft of delight without its mascots. One memorable
   touch beats ten decorative ones.
6. **One system, no one-offs.** Every new component or element composes the shared design
   system — the `ui/` primitives and tokens documented in `DESIGN.md` — before inventing
   anything bespoke. Consistency is the product feeling trustworthy; a screen that reaches
   for a native browser dialog or a hand-rolled control breaks the "capable, not corporate"
   frame. Extend the system deliberately; never route around it.

## Accessibility & Inclusion

Target **WCAG 2.1 AA.** Body text ≥4.5:1, large text ≥3:1 against its surface; the
status palette is already AA-tuned on light surfaces. Full keyboard navigation,
visible focus rings (already present), and a `prefers-reduced-motion` alternative for
every animation (the energetic motion direction makes this non-negotiable, not
optional). Don't encode meaning in color alone — pair status/topic color with text or
icon.
