# chatbot-ui-redesign — Summary

Lane: high-risk
Confidence: medium
Reason: Redesigns already-shipped chat behavior across ~30 apps/web files and adds a responsive/mobile surface; 3 flags fire (existing-behavior, cross-platform, weak-proof). Intake classified `normal` (no real hard gate: the SSE wire contract is consumed as-is, no auth/authz code is touched). Raised to `high-risk` at commit time because risk-corroboration's `authorization` signal fires on the literal token `role` in chat-message/ARIA markup (`role: "assistant"`, `role="dialog"`) — a documented false positive (see memory: the `session` token case) — and the honest response to an untunable signal is to carry high-risk evidence rather than weaken the gate: independent review (spec PASS), live browser UAT, full SC verify table, and rollback are all recorded below.
Flags: existing-behavior, cross-platform, weak-proof
Affects: apps/web chat surface (`src/components/chat/**`) — consumer-only of the `/agent/stream` SSE contract; no apps/api change
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

review UI/UX in https://dribbble.com/shots/27153471-Next-Gen-AI-Assistant-Mobile-App-UI and https://dribbble.com/shots/27628978-AI-Chatbot-Mobile-App-UI-Design and make plan for redesign chatbot UI

make thinking and research by yourself, no need any approval from me. think and make plan for re-design with details/clear plan, can explain why we stick with this way, not that way, ...

## What changed

Waves 1–4 executed (2026-09-01). The `apps/web` chat surface now: surfaces the agent's
tool/subagent work as a live activity trail per turn (`useAgentStream` no longer discards
`subagent`/`tool_call`/`tool_result`; new `ActivityStep`, `ChatMessage.activity`+`.panels`),
renders panel results as inline `ResultCard`s that promote to the drawer (desktop) or an
in-sheet bottom sheet (compact), adds Copy/Regenerate per completed turn, becomes a
full-viewport sheet below 640px (`useIsCompact`, focus trap, Escape, scroll lock), restyles
the empty state into a 2×2 capability grid, moves follow-up chips into the composer as one
rail, consolidates the header to a single status pill, and adds en/vi keys with a recursive
parity test. New components: `AgentActivityTrail`, `MessageActions`, `ResultCard`.
`src/components/chat/panel/**` and `parseSSE.ts` untouched, per Global Constraints.

### Rationale

Normal lane, not high-risk: the work is confined to one frontend module, is fully
reversible by `git revert`, and consumes the existing typed SSE contract rather than
altering it. Confidence is `medium` rather than `high` because the request named two
visual references without saying how literally to follow them — resolved with a
documented default (adopt their *interaction* patterns, reject their *palette*; see
`design.md` §Forks) rather than a blocking question, which the request explicitly
waived ("no need any approval from me").

### Alternatives considered

- **Escalate the aesthetic fork to the user.** Rejected: the request explicitly delegated
  the decision and asked for the reasoning to be written down instead.
- **Treat this as `tiny` (CSS-only restyle).** Rejected: it touches >2 files, changes shipped
  interaction behavior, and introduces a new responsive surface.
- **Classify `high-risk` because it is user-facing.** Rejected: no manifest hard gate fires —
  user-facing ≠ hard-gated, and inflating the lane manufactures ceremony without adding proof.

### Deviations

- Rule 2 (orphan cleanup): controller initialized the two new `ChatMessage` fields in
  `MessageList.render.test.tsx` (Task 3.1's file) between waves 1–2 to keep `tsc` green, and
  removed two unused-var orphans (`panels` destructure in `ChatPanel.tsx`, `beforeEach` import
  in `MessageActions.test.tsx`) after wave 4 lint.
- Tasks 2.2/2.3/2.4: plan suggested lucide-react icons; repo has no such dependency — kept the
  existing inline-SVG convention instead (no new dependency).
- Task 2.1: `AgentActivityTrail` gained plan-sanctioned optional `elapsedMs?` prop.
- Task 2.3: no generic count key in `Chat`; reused `Panel.places.results` plural for the
  card's "# results" line (present in both locales).

- User-directed (2026-09-01, overrides part of Task 3.3 / Fork 7): the header keeps a
  gradient wash — restored as `bg-gradient-to-l from-lime-soft/55 via-panel to-panel`
  (lime at the right fading leftward, per the user's direction) — and card surfaces
  (`ResultCard`, empty-state tiles) moved from `shadow-card` to the stronger existing
  `shadow-lift` token. No new tokens introduced. Also user-directed: the `AgentAvatar`
  disc was removed from the empty-state greeting (kept in the header and message rows),
  and the empty-state tiles were restyled to the reference card language (rounded-[20px],
  soft lime-soft gradient, raised round icon chip, ↗ corner chip, hover lift).
- UAT bug (user-reported, 2026-09-01): clicking a `ResultCard` on desktop while the drawer
  was already open did nothing — `onOpenPanel` only un-hid the drawer, never selected the
  clicked panel's tab. Fixed by giving `SidePanel` an optional additive `focus?: {kind,
  nonce}` prop (render-phase adjust-on-change, uncontrolled otherwise) wired from
  `ChatWidget`. This is a narrow, additive deviation from the "do not edit panel/**"
  constraint; all pre-existing panel tests pass unmodified and a focus test was added
  (panel suite 25/25).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Plan contract (task schema + SC table) | `python3 .claude/scripts/check_plan_contract.py specs/chatbot-ui-redesign/PLAN.md` | 0 | `plan-contract: ... passed` | |
| Stream hook: per-turn activity + panels | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx` | 0 | 12/12 — incl. regenerate/resume-loop tool events + elapsedMs | SC-1 |
| Activity trail component | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/AgentActivityTrail.test.tsx` | 0 | 5/5 | SC-2 |
| Message actions (copy/regenerate) | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/MessageActions.test.tsx` | 0 | 6/6 | SC-3 |
| Inline result card | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ResultCard.test.tsx` | 0 | 4/4 | SC-4 |
| Responsive shell (no drawer <640px) | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatWidget.test.tsx` | 0 | 2/2 | SC-5 |
| Empty-state capability grid | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatEmptyState.test.tsx` | 0 | 3/3 | SC-6 |
| Composer chip rail | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatComposer.test.tsx` | 0 | 7/7 | SC-7 |
| Header status pill | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatHeader.test.tsx` | 0 | 10/10 | SC-8 |
| en/vi key parity | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/messages.parity.test.ts` | 0 | 2/2, recursive both directions | SC-9 |
| Panel renderers untouched | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/panel` | 0 | 7 files / 24 tests, zero diff under panel/ | SC-10 |
| Typecheck | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec tsc --noEmit` | 0 | | SC-11 |
| Panel a11y/motion integration | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatPanel.test.tsx` | 0 | 11/11 | SC-12 |
| Lint | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web run lint` | 0 | 0 errors 0 warnings after orphan cleanup | |
| Full apps/web suite | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src` | 0 | 32 files / 172 tests (post-review-fix) | |

### Review

Independent read-only review (2026-09-01): **Spec PASS** (all Global Constraints held —
parseSSE/panel untouched, additive-only CSS, en/vi parity, three loops share
`handleActivityEvent`); **Quality CONCERNS** → all 5 findings fixed same-day:

1. (major) Regenerate on a completed turn re-sent via `send()` → duplicate user bubble +
   re-saved question. Fixed: hook gained `regenerate()` — drops the old answer and re-runs
   through the shared rerun flow with `retry:true` (BE skips re-saving the question).
2. `elapsedMs` never populated (summary always "0s"). Fixed: stamped on the assistant
   message in all three flows' completion path; `MessageList` passes it to the trail.
3. `tp-trail-dot` / `tp-card-in` keyframes were dead CSS. Fixed: wired to the running dot
   and the ResultCard reveal.
4. Empty errored assistant bubble still offered Copy/Regenerate. Fixed: actions render only
   when the turn produced content.
5. Tool events untested through the non-send loops. Fixed: stream tests now cover the rerun
   (retry/regenerate) and resume loops plus `elapsedMs`.

Live UAT (2026-09-01, real browser via chrome-devtools MCP) additionally caught:

6. Duplicate `ResultCard`s per turn — the graph re-emits a panel per reflection/revision
   pass (fresh tool_call_id, same kind); the flat drawer array hid it via
   `upsertPanelByKind` but the per-turn attach was a plain append (3 identical Weather
   cards observed). Fixed: `attachPanelToMessage` upserts by `kind`, mirroring the drawer;
   regression test added. Post-fix suite: 173/173, tsc 0, lint 0.

### Not auto-verified

- The reference review in `design.md` — reached **provenance** (both Dribbble shots were
  loaded in a real browser and read from screenshots + page text, recorded in `design.md`
  §Sources); not re-runnable because Dribbble blocks unauthenticated fetch (HTTP 202 challenge).
- Task 4.3 visual acceptance — **done** (2026-09-01, tier: provenance — real Chrome via
  chrome-devtools MCP on the user's signed-in session; not headless-re-runnable because all
  routes sit behind Supabase auth). Evidence in `screenshots/uat-chatbot-ui-redesign/`:
  desktop 1440×900 light (empty 2×2 grid; streaming with live "Finding places" trail;
  completed with collapsed "Used 2 tools · 8s", one Places card, Copy/Regenerate, chip
  rail, drawer), desktop dark completed, mobile 390×844 dark (full sheet, no drawer, no
  expand toggle; card promoted to in-sheet bottom sheet), mobile light empty (single-column
  grid). Regenerate exercised live: re-ran without a duplicate user bubble.
  Known behavior (out of scope): a regenerated turn appends a second assistant row in the
  DB, so a page reload hydrates both answers (fixing it needs an API change).

### Rollback

- `git revert` the branch's commits (frontend-only, no migration, no contract change);
  or drop branch `feat/chatbot-ui-redesign` before merge.

### Harness-Delta

- backlog — lightningcss (Tailwind v4/Turbopack) SILENTLY drops an `animation` shorthand it
  cannot parse (delay before easing: `220ms 40ms cubic-bezier(...)`), then tree-shakes the
  now-unused `@keyframes` too — the class exists in source, computes `animation: none`, no
  build warning. Canonical order (`name duration easing delay fill`) fixes it. Worth a
  `docs/solutions/` note.
- backlog — `WebFetch` cannot read Dribbble (202 anti-bot challenge) and neither can `curl`;
  the working path is the chrome-devtools MCP (`new_page` + `take_screenshot` + `evaluate_script`).
  Worth a `docs/solutions/` note so the next design-reference task does not spend three
  failed fetches rediscovering it.
