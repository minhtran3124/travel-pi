# min-57-side-panel-language — Summary

Lane: high-risk
Confidence: high
Reason: Full-stack fix chosen (static-label i18n + backend locale plumbing + LLM translation of dynamic panel content following the detected typed language) trips 5 flags incl. public contract (new ChatRequest locale/language) and multi-domain.
Flags: external-systems, public-contracts, existing-behavior, weak-proof, multi-domain
Affects: ChatRequest schema (apps/web + apps/api), agent stream/panels contract (app/streaming/panels.py, lib/stream/panel.ts), side-panel renderers (apps/web/src/components/chat/panel/*)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim intake oracle for /intent-review. Combines the Linear issue MIN-57 body
     with the two scope decisions the user made at intake. -->

From Linear MIN-57 (Bug: Side panel still returns English when the user asks in Vietnamese):

> ## Problem
> When the user chats in Vietnamese, the main chat response is already in the correct language, but the **side panel** (supplementary information, hotel/flight details, suggestions, etc.) is still displayed in English → an inconsistent language experience.
>
> ## Suspected causes (need further investigation)
> * The side panel may be pulling data directly from mock data / the backend API (which is in English) without going through the translate/re-generate step via the LLM the way the main chat does.
> * There may be missing logic to detect the user's language and pass it down to the side panel component.
> * The side panel may be rendering hardcoded labels in English instead of following the locale.
>
> ## Proposed solutions (to be evaluated — pick the appropriate approach)
> 1. **Pass the current conversation language** (detected from the user's input) down to the side panel component, so the side panel uses the correct locale for static labels (e.g. "Price" → "Giá").
> 2. For dynamic content pulled from the backend (hotel names, descriptions, etc.), consider:
>    * Translating via the LLM before displaying it in the side panel (keep proper nouns intact, translate only the descriptive parts).
>    * Or normalizing the backend to return data by locale if the data supports multiple languages.
> 3. Add i18n for the static labels in the side panel (use key-value pairs per language instead of hardcoding).
>
> ## To do
> * Investigate the side panel's current data flow (data source, whether it passes through the LLM or not).
> * Identify the list of static labels that need i18n.
> * Implement language detection + pass the language down to the side panel.
> * Test cases: user asks entirely in Vietnamese throughout the conversation; user switches language mid-conversation.

Scope decisions confirmed by the user at intake:

- **Scope = Full language consistency.** Fix BOTH (a) the hardcoded static labels in the panel renderers (via existing next-intl) AND (b) the dynamic backend content (hotel/weather descriptions, AQI advice, amenity/category names) — plumb a locale into `ChatRequest` → agent → `panels.py` and LLM-translate the descriptive text while keeping proper nouns intact.
- **Language signal = Detected typed language.** The side panel follows the language the user actually typed (as the chat reply does), NOT the UI locale cookie — even if the UI toggle is set to English.

## What changed

<!-- Filled by the executing agent(s). Intake only records lane/confidence/intent. -->

Not yet implemented — intake only.

### Rationale

Bug is caused by two independent string sources: (a) hardcoded English labels in `apps/web/src/components/chat/panel/registry.ts` + each panel renderer, which bypass the existing next-intl infra; and (b) dynamic content served English from the agent SSE `panel` stream (`app/streaming/panels.py`), because `ChatRequest` carries no locale and the backend is never told the language. The user chose full consistency over a frontend-only quick fix, accepting the higher-risk backend plumbing.

### Alternatives considered

- **Static-labels-only (frontend, normal lane)** — wire panel renderers to next-intl, leave dynamic content English. Rejected by user: leaves descriptions in English, partial fix.
- **Static now / dynamic later (phased)** — ship FE fix, open a follow-up issue for backend translation. Rejected by user in favor of doing both now.
- **Follow the UI locale cookie** instead of detected typed language. Rejected: chat reply already follows typed language; cookie would desync panel from the actual conversation language.

### Deviations

- none

### Verify

<!-- Filled during execution. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| _pending implementation_ | _—_ | _—_ | intake only |

### Rollback

<!-- Required (high-risk lane). Populate with exact undo commands once branch/commits exist. -->

- Revert code: `git revert <sha>` for each implementation commit
- Revert `ChatRequest` schema change: covered by the code revert (no DB migration if locale stays request-only; if a migration is added, `alembic downgrade -1`)

### Harness-Delta

- none
