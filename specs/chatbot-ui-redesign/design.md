# Chatbot UI Redesign — Design

Status: approved (autonomous, per the intake waiver in `SUMMARY.md` → Intent)
Date: 2026-08-28

---

## 1. Sources — how the references were actually read

Dribbble returns an HTTP 202 anti-bot challenge to `WebFetch` and to `curl`, so both shots
were opened in a real browser via the chrome-devtools MCP and read from viewport screenshots
plus `document.body.innerText`.

| Ref | Shot | Designer |
|---|---|---|
| **A** | [Next-Gen AI Assistant Mobile App UI](https://dribbble.com/shots/27153471-Next-Gen-AI-Assistant-Mobile-App-UI) | Nodus Labs |
| **B** | [AI Chatbot Mobile App UI Design](https://dribbble.com/shots/27628978-AI-Chatbot-Mobile-App-UI-Design) | Yeasin Arafat |

### Ref A — observed

Light, airy, pastel lilac→mint gradient ground; frosted/glassy cards; heavy rounding.

- **Home:** avatar + "Welcome Back, Alex John", a display headline, a search field, a **2×2
  capability grid** (New Chat / Image Generate / Voice Generate / Video Generate — each an
  icon tile + title + one-line subtitle + a corner "open" arrow), then a **History** section
  of collapsible recent-session rows.
- **Voice:** full-bleed iridescent orb, transcript as large centered type with *keyword
  highlighting*, a waveform, a mic FAB, refresh + dismiss controls.
- **Chat:** user bubbles right (lilac fill), assistant bubbles left (white, small bot avatar),
  a timestamp under every message, a **per-message action row** (👍 / 👎 / regenerate) under
  the assistant's last turn, a **horizontal action-chip rail** directly above the composer
  (Voice Mode / Create Image / Rewrite), composer placeholder "Ask anything…".
- Self-described highlights: *"smart conversation flow with intuitive chat interface"*,
  *"clean, modern UI with soft gradients and minimal design"*.

### Ref B — observed

Dark violet (#08040E → #591097) with a magenta gradient accent (#C21A38); 3D mascot.

- **Onboarding:** 3D robot mascot, "Smarter Days Start Here – Meet Your Assistant", paged dots.
- **Home:** "Hello, Alexa Garcia" + a "Try Premium ✨" pill, a 2×2 capability grid (voice /
  new chat / search by image), a **Recent Search** list of arrow rows, and a floating
  segmented **mode dock** hovering above the bottom edge.
- **Chat:** a **model/version selector pill in the header** ("AI 1.3.2 ⌄"); the user's prompt
  rendered as flat text with a marker icon rather than a bubble; the assistant reply as a
  **result card** — generated image on top, then labeled sections ("Description 1/2/3" with
  bold labels); a feedback row (👍/👎) plus a **download** action; composer with a `+` attach
  button and a gradient circular send button.
- Self-described highlights: *"modern dark mode interface"*, *"scalable design system for
  future AI features"*.

### Where the two agree (the strongest signal)

Both are mobile-first, and both converge on five patterns:

1. Rich answers are **cards inside the conversation**, not plain prose.
2. Every assistant turn carries a **per-message action row**.
3. The empty state is a **capability grid**, not a wall of text.
4. **Recent conversations** are a first-class entry point.
5. The composer owns a **chip rail** of contextual next actions.

Two things they agree on that we deliberately will *not* take: heavy gradient/glass surfaces,
and capability tiles for features that do not exist behind them (image gen, voice, premium).

---

## 2. Where our chat stands today

Read at `apps/web/src/components/chat/` (~3.8k LOC, 10 components + 7 side-panel renderers).

**Already good — do not rebuild:** streaming markdown with incomplete-token repair
(`AssistantMarkdown` + Streamdown), a typed SSE protocol, a HITL interrupt checkpoint
(`InterruptPrompt`), a curated empty state, follow-up suggestion chips driven by the agent's
`current_flow`, dark mode, i18n (en/vi), and 7 tested panel renderers.

**Real gaps, ranked by evidence:**

| # | Gap | Evidence |
|---|---|---|
| G1 | The agent's work is invisible. `subagent` / `tool_call` / `tool_result` events **are parsed and then thrown away** — the UI shows only "Working on it…". | `useAgentStream.ts:377` — *"subagent / tool_call / tool_result: not surfaced"*; `parseSSE.ts:10-11` defines all three. |
| G2 | Results are divorced from the question that produced them. Panels live in a drawer beside the panel, keyed globally, not attached to a turn. | `ChatWidget.tsx` renders `SidePanel` as a flex sibling; `stream.panels` is one flat array. |
| G3 | Broken on phones. The widget is a `w-[min(92vw,400px)]` floating card, and when a panel exists it sits **side by side** with the drawer in a `flex-row`. At 390px that is two panels in 92vw. | `ChatWidget.tsx` `flex flex-row items-end`; `ChatPanel.tsx:79-80` — the only responsive values in the whole chat module. |
| G4 | No per-message affordances — no copy, no regenerate-this-turn. Retry exists only as a panel-wide band after a failure. | `MessageList.tsx` renders a bubble and nothing else. |
| G5 | Empty state is a vertical list of 4 rows; no personalization, no recents. | `ChatEmptyState.tsx`. |
| G6 | Chrome is fragmented: a status line, a separate "Show/Hide panel" band, a separate retry band, and a separate suggestions band can all stack between the transcript and the composer. | `ChatPanel.tsx` — four conditional bands. |

---

## 3. Design forks — the decisions and why

### Fork 1 — Visual language: adopt the references' look, or keep ours?

**Chosen: keep the Travel Planner design system; borrow interaction patterns only.**

Ref B is violet/magenta on near-black; Ref A is pastel gradients and glass. Our shipped
system is white/ink with a single chartreuse accent (`--lime #cbf24a`), hairline borders,
soft shadows, and a hand-tuned dark palette — used by the trips, places, bookings and
dashboard surfaces. Repainting only the chat widget in someone else's palette would make the
co-pilot look like a third-party embed inside our own app, and would break the invariant the
design system encodes (lime = the one "active/signal" color, ink = the one primary action).

The value in these shots is **not** the palette — it is the interaction grammar (result
cards, per-message actions, capability grid, chip rail). That transfers cleanly; the color
does not. *Rejected:* a "dark violet AI mode" theme — it would fork the token set, double the
dark-mode test surface, and orphan the existing `on-ink` / `on-accent` contract.

### Fork 2 — Where do rich results live: drawer, inline, or both?

**Chosen: hybrid — an inline result card in the transcript, expandable to the drawer.**

Both references put results inline, and they are right for the common case: adjacency between
a question and its answer is what makes a chat legible. But we are not a phone-sized single
column — our `RoutePanel` is a MapLibre map and `HotelsPanel` a multi-item list, and the chat
column is 400px. Going fully inline would either squash the map to uselessness or force the
transcript wide on every turn.

So: every panel becomes an inline `ResultCard` **attached to the turn that produced it**
(compact header, key facts, a thumbnail/preview), with an "Open" affordance that promotes it
into the existing drawer on desktop or a bottom sheet on mobile. This fixes G2 without
discarding 7 tested renderers — the registry is reused verbatim, wrapped rather than replaced.

*Rejected — keep the drawer only:* leaves G2 unfixed; the drawer already loses the mapping
between turn and result and needs a `mapHidden` latch hack to stay usable.
*Rejected — inline only:* deletes working, tested code and degrades the map/list panels.

### Fork 3 — Surface shape: floating widget everywhere, or responsive?

**Chosen: responsive — full-screen sheet under `sm`, docked floating panel at `sm`+.**

Both references are phone designs, and our current chat is the one part of the app that has
essentially no responsive rules (G3). Under 640px the panel + drawer flex-row is unusable.
A full-height sheet on mobile also unlocks the reference patterns (capability grid, result
cards) that need width to breathe.

*Rejected — a separate `/chat` route for mobile:* new route, new layout, new auth/shell
wiring, and it splits the co-pilot away from the trip context it derives from `usePathname()`.
A breakpoint is a fraction of the cost for the same outcome.

### Fork 4 — Agent transparency: hide the work, or show it?

**Chosen: show it — a live activity trail per turn. This is the highest-value change in the plan.**

Ref A sells "smart conversation flow"; Ref B sells a model-version pill. Both are proxies for
one thing: *the user should feel the system is doing something specific*. We already emit the
raw material and discard it (G1). A multi-agent travel planner that silently spins for 10
seconds behind "Working on it…" reads as broken; the same 10 seconds reading
"✈️ Searching flights · 🏨 Checking hotels · ⛅ Weather in Da Nang" reads as competent.

The trail streams while the turn runs, then **collapses to a single summary line**
("Used 3 tools · 8s", expandable) once the answer lands — so a scrolled-back transcript stays
clean. Cost: zero backend work, one reducer, one presentational component.

*Rejected — a model/version pill (Ref B):* we have per-agent DB-backed model config that the
end user neither chooses nor should think about; exposing it is leaking implementation.
*Rejected — raw tool names:* `search_hotels(args_preview=…)` is internal vocabulary. The trail
maps tool → a human, localized label, falling back to a generic "Working…" step for unmapped
tools, never to the raw name.

### Fork 5 — Per-message actions: which ones?

**Chosen: copy + regenerate now; thumbs up/down deferred.**

Both refs show 👍/👎. There is **no feedback endpoint**: `apps/api/app/routers/` has no
`feedback` route, and `specs/user-feedback-v1/` is still a spec. Shipping thumbs that POST
nowhere is theatre. Copy and regenerate are honest — both are pure client actions over state
we already hold (`retry` exists in `useAgentStream`). The action row is built so a rating pair
drops in as two more buttons once `user-feedback-v1` lands.

### Fork 6 — Recents / conversation history

**Chosen: out of scope; the empty state is redesigned without it.**

Both refs make recents a headline feature and it is genuinely the next-best thing after this
work. But conversation listing is a backend capability (persistence exists via the LangGraph
checkpointer; a *list-my-conversations* contract does not) — it is a new public endpoint, i.e.
a `public-contract` hard gate, i.e. a different lane and a different spec. Folding it in here
would silently convert a normal-lane frontend change into a high-risk one. Recorded in §5.

### Fork 7 — Mascot / illustrated identity

**Chosen: keep the "Tin" monogram; no mascot.**

Ref B's 3D robot is charming and is also an asset pipeline: an illustrator, light/dark
variants, multiple poses for states, and a brand decision about whether a travel assistant
should look like a robot at all. "Tin" already has a shipped identity (`AgentAvatar`, the lime
launcher, the naming work from MIN-54/MIN-60). We spend the delight budget on **motion** —
the activity trail, the result-card reveal, the launcher pulse — which is cheaper, on-brand,
and degrades correctly under `prefers-reduced-motion`.

---

## 4. Target shape

```
┌──────────────────────────────────────┐
│ ⬤ Tin · Travel Assistant   ⚙ ⤢ ✕     │  header: identity + one status pill
├──────────────────────────────────────┤
│  ⬤ Hi! I'm Tin 👋                     │  empty state: greeting +
│  ┌──────────┐ ┌──────────┐            │  2×2 capability grid (Ref A/B)
│  │ 🗾 Plan  │ │ ☕ Nearby │            │
│  └──────────┘ └──────────┘            │
├──────────────────────────────────────┤
│                    ┌────────────────┐ │
│                    │ user bubble    │ │  transcript
│                    └────────────────┘ │
│  ⬤ ▸ Used 3 tools · 8s                │  activity trail (Fork 4), collapsed
│  ⬤ assistant markdown …               │
│    ┌────────────────────────────────┐ │
│    │ 🏨 4 stays in Da Nang    Open ↗│ │  inline ResultCard (Fork 2)
│    └────────────────────────────────┘ │
│    ⧉ Copy   ↻ Regenerate               │  message actions (Fork 5)
├──────────────────────────────────────┤
│ [ Add a day ➕ ][ Find a stay 🏨 ]     │  chip rail, attached to composer
│ ┌──────────────────────────────┐  ➤   │
│ │ Ask Tin anything…            │      │
│ └──────────────────────────────┘      │
└──────────────────────────────────────┘
```

Under `sm`: the same tree as a full-height sheet; `ResultCard` "Open" pushes a bottom sheet
instead of the side drawer.

## 5. Non-goals / explicitly deferred

- Conversation history & recents (Fork 6) — needs a new API contract; own spec, own lane.
- 👍/👎 rating (Fork 5) — unblocked by `specs/user-feedback-v1/`.
- Voice mode, image generation, attachments, premium upsell — no backend capability; would be
  fake UI.
- Any `apps/api` change. This plan consumes the SSE contract exactly as it is today.
- Palette / token changes in `globals.css` beyond additive motion keyframes.

## 6. Risks

| Risk | Mitigation |
|---|---|
| The activity trail becomes noise on fast turns | Only render it after ≥1 `tool_call`; collapse on `done`; never show raw tool names. |
| Inline result cards make long threads heavy | Cards are compact summaries; the heavy renderer stays in the drawer/sheet behind "Open". |
| Mobile sheet traps focus / breaks scroll | Explicit a11y task (focus trap, `Escape`, `aria-modal`, body-scroll lock) with tests. |
| Regression in the 7 existing panel renderers | `panel/registry.ts` and the renderers are **not** edited — `ResultCard` wraps them; their tests must stay green untouched. |
| Visual regressions are hard to prove | Per-task vitest render assertions for behavior; a Playwright screenshot pass at phase level for looks (per `rules/plan-format.md`, browser checks are phase-level, not task `Verify`). |
