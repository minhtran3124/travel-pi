---
slug: min-54-chat-ui-polish
status: active
owner: Minh Tran
created: 2026-07-06
---

# MIN-54 — Chat UI/UX polish (spacing · bold · emoji)

## 1. Motivation

Chat replies read loose and flat. Tighten typography so answers scan like a search
result, and make the assistant feel friendlier with tasteful, contextual travel emoji —
without over-formatting. Naming (#4 "Tin") is already shipped (MIN-60); **out of scope**.

Live scope = 3 of the 4 issue points:
- **#1 Spacing/typography** — reduce line-height and heading→text / paragraph / list gaps in the web renderer.
- **#2 Bold discipline** — lightly tighten the existing prompt rule so bold marks only the specific value.
- **#3 Emoji** — add contextual travel-emoji guidance to the system prompt (v4 has none).

## 2. Non-goals

- No renaming / re-branding the bot (already "Tin", MIN-60).
- No change to the markdown engine (Streamdown stays), the message data flow, or theme tokens.
- No new dependency, no schema/API change.

## 3. Success Criteria

- Assistant markdown line-height and heading/paragraph/list spacing are visibly tighter; light & dark both fine (spacing is theme-agnostic).
- `communication_style` active version = 5, containing contextual-emoji guidance + tightened bold rule, with the **"Tin"** identity preserved.
- `apps/api` prompt tests green (incl. `test_tin_identity`); `apps/web` typecheck/lint green.

## 4. Tasks

Wave 1 has two tasks touching disjoint apps (`apps/web` ⟂ `apps/api`) → run in parallel.

### Task 1.1 — Tighten web chat markdown spacing

```xml
<task id="1.1" wave="1">
  <files>apps/web/src/components/chat/AssistantMarkdown.tsx, apps/web/src/components/chat/MessageList.tsx</files>
  <action>In AssistantMarkdown.tsx className (l.27-35): change the markdown text line-height from `leading-relaxed` to `leading-normal`, and ADD arbitrary-value margin overrides to tighten Streamdown's default heading/paragraph/list gaps — use rem arbitraries (NOT named spacing tokens, which shadow the scale per tailwind-spacing memory): `[&_h2]:mt-[0.75rem] [&_h2]:mb-[0.25rem] [&_h3]:mt-[0.75rem] [&_h3]:mb-[0.25rem] [&_p]:my-[0.375rem] [&_ul]:my-[0.375rem] [&_ol]:my-[0.375rem] [&_li]:my-[0.125rem]`. Keep the existing `[&>*:first-child]:mt-0 [&>*:last-child]:mb-0` resets and heading font-size overrides. In MessageList.tsx l.57, change the assistant bubble `leading-relaxed` to `leading-normal` to match. Do NOT touch bg/text/border/shadow tokens (theme-flipping).</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec tsc --noEmit</verify>
  <done>Typecheck passes; markdown text uses leading-normal and has explicit tighter h2/h3/p/ul/li margins; no theme-token edits.</done>
</task>
```

### Task 1.2 — Add communication_style v5 (emoji + tighter bold)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/prompts/communication_style/v5.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md</files>
  <action>Copy v4.md to v5.md verbatim, then make TWO edits: (a) In §How to Format, sharpen the bold bullet to: only the specific value carries bold — a name, a number, a price, a date, a place — never a whole sentence or a generic word. (b) Add a new "### Emoji" subsection under §How to Format: use tasteful, contextual travel emoji to feel friendly, sparingly — map to context (🏨 stays, ✈️ flights, 🌴 destinations, 💰 price/budget, 📅 dates, 🌤️ weather, 🍜 food, 🗺️ itinerary/getting-around, 🎒 packing); at most ~1 in a short reply, a few across a long structured reply; place at the start of a line/section or right before a key term, never mid-sentence and never on every bullet; skip emoji entirely in disclaimers, warnings, or when a tool failed / news is bad. Preserve the §Identity "Tin" block unchanged. Then bump active.yaml line 3 `communication_style: 4` → `communication_style: 5`, and add a CHANGELOG.md entry for v5 (MIN-54: emoji guidance + tightened bold).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/prompts -x -q</verify>
  <done>Active communication_style resolves to v5 text containing "Tin"; prompt tests green.</done>
</task>
```

## 5. Risks

- **Line-height too tight** — `leading-normal` (1.5) is a conservative reduction from 1.625; revert to `leading-relaxed` if it reads cramped (phase-level visual check).
- **Emoji over-use** — mitigated by explicit "sparingly / not every bullet / skip on bad news" rules; DeepEval `format_quality_metric` (MIN-54) rewards *tasteful* emoji, penalizes spam.
- **Streamdown class specificity** — arbitrary-variant overrides must win over Streamdown's bundled `my-*`; verified by later source order. If a gap doesn't tighten, bump specificity, don't `!important`.

## 6. Status Log

- 2026-07-06 — intake (normal lane, medium confidence); research done; plan written; branch `feat/min-54-chat-ui-polish` off v3.
- 2026-07-06 — Wave 1 done (1.1 web spacing + 1.2 prompt v5). Verify: `pytest tests/prompts` 11 passed, web `tsc --noEmit` clean. Independent reviewer: no issues. Naming out of scope (Tin/MIN-60).
