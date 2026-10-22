# gh-147-dated-hotel-availability-routing — Research Brief

**Depth: Standard** (intake lane `normal` → Standard per `rules/research-depth.md`).
Re-run of the classifier with evidence found no Deep signal: no migration/schema or data-loss
work, no high-blast file, no new dependency or external integration, no shared runtime config
contract, no auth/session/transaction-scope change. Depth stays **Standard** — not upgraded.

**External surface: none.** No dependency added or upgraded, no external system integrated, no
version-specific API relied on. Official-docs coverage is therefore not applicable (see Source
Pack); the unconditional upstream search still ran.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **reuse existing** — bind the already-shipped `search_hotels` tool to the `concierge` domain and disambiguate it against `browse_hotels` in the concierge prompt |
| **Why this is the lightest credible path** | Every piece already exists and is proven in production (the tool, its panel, its localization, its tests); the only genuinely new artifact is one prompt section plus its pin test. |
| **Confidence** | 85% — the code change is trivial and fully verifiable; the residual 15% is prompt-compliance, which is probabilistic and has failed once before on this exact surface (MIN-51). |
| **Next step** | `writing-plans` → a 3-wave PLAN: (1) registry binding + rewritten registry guard test, (2) concierge v12 + `active.yaml` + CHANGELOG + pin test + `browse_hotels` docstring, (3) eval re-run on `hotels` + `errors`. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm workspaces + Turborepo): FastAPI backend `apps/api/`, Next.js frontend `apps/web/` |
| Primary language + runtime | Python 3.14 locally / **3.12 in Docker** (`docker-py312-vs-local-py314`); single venv at repo root |
| Frameworks / platforms | FastAPI, SQLAlchemy 2.0 + Alembic, LangGraph / LangChain (multi-agent supervisor graph), DeepEval-based eval harness under `apps/api/eval/` + portable `evalkit/` |
| Relevant packages | `app.tools.registry`, `app.tools.hotel_tools`, `app.prompts.registry` + `app/prompts/<agent>/vN.md`, `app.agents.subagents._base`, `app.streaming.panels.hotels` |
| Detectable versions | `app/prompts/active.yaml` on `main`: supervisor 11, concierge 11, planner 13, booking 7, communication_style 8 |
| Important constraints | `rules/behavior.md` §3 Surgical Changes (match existing style, no adjacent refactors); prompt bumps follow copy-`vN`→`vN+1` + pointer (`supervisor-active-yaml-is-a-pointer`); BE commands run from `apps/api/`; tests default to SQLite |

---

## Feature Understanding and Assumptions

- **Requested feature:** give the concierge the ability to search hotels **with and without
  dates** — bind `search_hotels` alongside `browse_hotels` — while explicitly **not** giving it
  any booking power.
- **What success appears to mean:** a traveller who states check-in/check-out (and party size) in
  a pure hotel-search conversation gets a real, dated availability answer from the concierge
  instead of "I can't check real room availability"; a traveller who states **no** dates still
  gets the dateless catalog browse and is **not** interrogated for dates. Observable as
  golden `hotels-multi_turn-en-01` (+ `hotels-multi_turn-vi-01`, `hotels-happy-en-02`) passing
  while `hotels-happy-*`, `hotels-ambiguous-*` and `errors-*` keep passing.
- **Assumptions from the request:** `book_hotel` stays out of the concierge; booking remains the
  only HITL-gated, premium domain; the eval goldens are the oracle and are not to be edited.
- **Assumptions still needing confirmation:** none that change the recommendation. (The one open
  variable — whether the model reliably picks the right one of two hotel tools — is not
  resolvable by research; it is resolvable only by the keyed eval run in wave 3.)

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/tools/registry.py:36-68` — `TOOLS_BY_DOMAIN`; `concierge` gets `HOTEL_SEARCH_TOOLS` (= `[browse_hotels]`), `planner` gets `HOTEL_AVAILABILITY_TOOLS` (= `[search_hotels]`), `booking` gets `HOTEL_TOOLS` (= availability + `book_hotel`). Concierge cannot call `search_hotels` — the reported "defect" is the only reachable behavior. |
| `Local` | `app/tools/hotel_tools.py:510-515` — the three group constants; `HOTEL_SEARCH_TOOLS` is referenced **only** by the concierge entry, so `browse_hotels` and its docstring are concierge-private and safe to edit. |
| `Local` | `app/tools/hotel_tools.py:190-235` — `search_hotels` is read-only: no `user_id`, no `trip_id`, no writes; it resolves dates via `resolve_travel_date`, rejects past `check_in`, and returns the same `kind="hotels"` artifact. Six **required** args (`city`, `check_in`, `check_out`, `rooms`, `adults`, `children`) and a docstring ordering the model to "collect every one from the traveller and never guess". |
| `Local` | `app/prompts/supervisor/v11.md:17,33-34,43` — already routes pure hotel lookups, **naming `availability` explicitly**, to the concierge. The routing contract already assumes direction A; only the toolset disagrees. |
| `Local` | `app/prompts/concierge/v11.md:77-90` — contradicts A in three places: browse "only needs the **city**", "**do not ask for check-in/check-out, rooms, or guest counts**", "**You do not book, and you do not quote date-specific availability.**" |
| `Local` | `tests/tools/test_tool_registry.py:304-325` (`test_hotel_tool_split`) — asserts `"search_hotels" not in concierge`. This is the MIN-51 guard and it fails by design under A. |
| `Local` | `eval/datasets/hotels.json` — 3 goldens pin `expected_flow: concierge` + `expected_tools: [search_hotels]`; 2 pin `browse_hotels`; 3 pin no tool. `eval/baselines/main.json`: `hotels-happy-en-02`, `hotels-multi_turn-vi-01`, `hotels-multi_turn-en-01` all `passed: false`; the dateless ones pass. |
| `Local` | `specs/min-51-hotel-search-intent/PLAN.md` Status Log 2026-07-04 — the concierge **was** bound to `search_hotels` and failed live review: it "still asked for check-in/out/rooms/guests before showing hotels — because its only hotel tool was the availability `search_hotels`". `browse_hotels` was created to fix exactly that. |
| `Local` | `specs/review-b7-eval-baseline-ci/TRIAGE.md` run-2 note — "v10 both says planner owns `search_hotels` and that concierge does hotel availability lookups — **the prompt contradicts itself**". |
| `Local` | `app/agents/subagents/_base.py:115-170` (`_make_trip_guard`) — only tools that inject `trip_id` are guarded. `search_hotels` injects none, so it runs trip-less in any domain: no guard, no `awaiting_user`. |
| `Local` | `app/streaming/panels/hotels.py` — `from_hotels` (dated, `nights>0`) vs `from_catalog` (dateless, `nights=0`, empty dates). Both are `kind="hotels"`; the panel is built inside the tool by `panel_result`, so it is flow-agnostic. |
| `Local` | `apps/web/src/components/chat/AgentActivityTrail.tsx:16-17` — `search_hotels` and `browse_hotels` both already map to `"hotels"`. No FE change. |
| `Local` | `docs/solutions/agent/planner-search-first-save-later.md` (#156, 2026-09-08) — the same failure class solved four weeks ago: state the rule in **both** the prompt and the model-visible tool description, pin both with content tests, because "prompt text and tool docstrings are read by the model independently and a fix in only one leaves the other arguing for the old behaviour". |
| `Local` | `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md` — never edit prose in `active.yaml`; copy the active `vN.md` → `vN+1.md`, edit that, then move the pointer. |
| `Upstream` | LangGraph/LangChain tool-calling guidance: the docstring is the text the LLM reads to choose a tool, and vague docstrings are the primary cause of a model picking the wrong one among overlapping tools; the mitigations are disambiguating descriptions and limiting the option set. Matches the local `#156` lesson exactly. |
| `Inference` | Under A, the LLM's tool choice is the only remaining failure mode. It cannot be proven by unit tests (FakeLLM bypasses prompt content — stated in `tests/agents/test_hotel_search_intent.py`'s own docstring); truth-tier proof is the keyed eval run only. |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:**
  - `apps/api/app/tools/registry.py` — the one-line binding change.
  - `apps/api/app/tools/hotel_tools.py` — `browse_hotels` docstring (concierge-private); `search_hotels` docstring (shared with planner + booking — **do not touch**, see Recommendation).
  - `apps/api/app/prompts/concierge/v11.md` → new `v12.md`; `apps/api/app/prompts/active.yaml`; `apps/api/app/prompts/CHANGELOG.md`.
  - `apps/api/tests/tools/test_tool_registry.py::test_hotel_tool_split` — must be rewritten.
  - `apps/api/tests/prompts/test_concierge_prompt.py` — add the pin test (file already exists, MIN-50 pattern).
  - `apps/api/tests/agents/test_hotel_search_intent.py` — extend with a dated concierge turn.
  - `apps/api/eval/datasets/hotels.json`, `eval/baselines/main.json` — oracle unchanged; baseline re-run.
- **Existing abstractions or extension points:** `TOOLS_BY_DOMAIN` is a plain per-domain list —
  the documented extension point; `get_tools_for(domain)` is the only reader, consumed by the five
  `app/agents/subagents/*.py` factories. The prompt registry's `vN.md` + `active.yaml` pointer is
  the documented way to change agent prose.
- **Conventions worth preserving:** copy-then-bump prompt versioning with a CHANGELOG entry per
  spec slug; content pin tests under `tests/prompts/`; a registry test that states the *invariant*
  (what a domain must and must not hold) rather than a snapshot of the list.
- **What can likely be reused:** everything except one prompt section — `search_hotels` itself,
  `HotelsPanel.from_hotels`, its `ContentTranslationService` localization, its error handling and
  panel tests (`tests/tools/test_booking_tools.py`, `tests/tools/test_hotel_tools_language.py`),
  the MCP annotations, and the FE trail mapping all work unchanged the moment the tool is bound.
- **What appears missing locally:** a *rule* telling the concierge which of two hotel tools to
  reach for. That rule has never existed, because the concierge has never held both.

---

## Upstream Findings

- **Repositories inspected:** none cloned — this is a repo-local wiring + prompt change with no
  external surface. General LangGraph/LangChain tool-calling guidance was searched instead.
- **Pattern or capability already present upstream:** overlapping-tool disambiguation is a known
  LangGraph concern; the standard remedy is the tool **description/docstring** (the text the model
  actually reads at selection time), plus keeping the option set small.
- **Files, modules, or areas worth modeling:** none externally. The closest and better-matched
  model is **in-repo**: `docs/solutions/agent/planner-search-first-save-later.md` (#156) applied
  the same remedy — rule stated in the prompt *and* in the model-visible tool description, both
  pinned by content tests.
- **How closely the upstream pattern matches this repo:** closely in principle, but generic; the
  repo's own #156 record is strictly more specific and is what the plan should follow.
- **Any upstream gaps or uncertainties:** upstream offers no way to make tool choice
  deterministic short of removing a tool or gating it in code — which is the fallback if the
  prompt does not hold (see Risks).

---

## Docs Findings

Not applicable — the change has **no external surface**: no dependency is added or upgraded, no
external system is integrated, and no version-specific API is relied on. Recorded here rather
than deleted, per `rules/research-depth.md` §Coverage.

---

## Recommendation

- **Primary recommendation:** **reuse existing.** Add `HOTEL_AVAILABILITY_TOOLS` to the
  `concierge` entry of `TOOLS_BY_DOMAIN` (concierge 15 → 16 tools, `book_hotel` still excluded),
  then make the choice between the two hotel tools mechanical in concierge **v12**:
  *no dates in the conversation → `browse_hotels`, and never ask for dates, rooms or guests in
  order to browse; the traveller has already given dates → `search_hotels` with exactly those
  values; never ask for booking details that were not volunteered; you still do not book.*
  Pin it with a content test, and amend `browse_hotels`'s docstring (concierge-private) so it
  stops sending dated searches to "the booking flow".
- **Why this is the lightest credible path:** the tool, its panel, its localization, its MCP
  annotation, its FE label and its tests already exist and already run under the planner and
  booking domains; `search_hotels` is `readOnly=True / destructive=False`, takes no `user_id` or
  `trip_id`, and is not `trip_guard`-gated, so binding it adds no new safety, tier, HITL or
  public surface (`ALL_TOOLS`/`TOOL_METADATA`/`/agent/manifest` are byte-identical). The change
  also *removes* an existing contradiction rather than adding a rule: supervisor v11 already
  promises concierge availability lookups, and three eval goldens already assume them.
- **Why the next-best alternative lost:**
  - *Re-route dated hotel turns to the planner (the superseded E001/B)* — needs no registry
    change but moves the ambiguity into the hottest prompt in the graph (supervisor, every
    turn), contradicts supervisor v11's own concierge bullet, and requires editing three eval
    oracles. Rejected by the user on 2026-09-09 (E002).
  - *Swap the concierge from `browse_hotels` to `search_hotels`* — this is literally MIN-51's
    original wiring and it is documented as having failed live review (date interrogation).
  - *Code-gate the tool choice (bind `search_hotels` only when dates are present in state)* —
    deterministic, but there is no such signal in `TravelAgentState`, and building one is a new
    abstraction for a single call site (`rules/behavior.md` §2). Kept as the **documented
    fallback** if v12 does not hold at k=3, mirroring #156's option 2.
  - *Edit the goldens instead* — makes a real capability gap disappear by moving the oracle.
- **What would change this recommendation:** a `tools_expected` regression on the dateless
  goldens (`hotels-happy-vi-01`, `hotels-happy-en-01`, `errors-happy-vi-01`,
  `errors-multi_turn-vi-01`) surviving a prompt iteration at k=3 → escalate to the code-gate
  fallback rather than iterating prose a third time.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  1. **Date interrogation returns (highest, and previously observed).** `search_hotels` has six
     required args and a docstring commanding the model to collect every one. MIN-51 records this
     exact regression when the concierge held that tool. Four currently-passing dateless goldens
     are exposed. Mitigation: the v12 rule + pin test must ship in the **same** wave as the
     binding, never after.
  2. **Shared docstring blast radius.** `search_hotels`'s docstring is read by planner and booking
     too, so editing it to add concierge-specific browse guidance would change two other agents'
     behavior for free. Mitigation: leave `search_hotels`'s docstring alone; put the rule in the
     concierge prompt and in `browse_hotels`'s docstring, which is concierge-private
     (`HOTEL_SEARCH_TOOLS` has exactly one consumer).
  3. **Panel tab collision (cosmetic).** A dateless browse and a dated search in one conversation
     both emit `kind="hotels"`, so the second replaces the first in the side panel. Pre-existing
     behavior for planner turns; not in scope.
  4. **Proof is probabilistic.** FakeLLM graph tests cannot validate tool choice — their own
     docstring says they "bypass prompt CONTENT for routing". Only the keyed eval gives
     truth-tier proof, and it is paid and nondeterministic (`make eval-check`, k=3).
- **Evidence gaps:** no live-LLM trace was captured in this research (read-only session, no eval
  run). The claim that v12 will hold is an expectation, not evidence, until wave 3 runs.
- **Version uncertainties:** none. Prompt versions were read from `active.yaml` on `main`
  (0a7b6d7); note the working tree previously showed `booking: 10` from another branch — on this
  branch it is `booking: 7`, which does not affect this change.
- **Follow-up questions for the user:**
  1. Should wave 3 run the paid judged gate (`make eval-check`, full + regression gate against
     `eval/baselines/main.json`), or the cheaper targeted run
     (`python -m eval --suite full --capability hotels --repeat 3` + the same for `errors`)?
  2. If v12 does not hold at k=3, do you want the code-gate fallback attempted in this branch, or
     tracked as a follow-up issue?

---

## Source Pack

- **Local files read:**
  - `apps/api/app/tools/registry.py`, `apps/api/app/tools/hotel_tools.py`
  - `apps/api/app/prompts/active.yaml`, `app/prompts/supervisor/v11.md`, `app/prompts/concierge/v11.md`, `app/prompts/CHANGELOG.md`
  - `apps/api/app/agents/subagents/_base.py`, `app/streaming/panels/hotels.py`, `app/agents/suggestions.py`
  - `apps/api/tests/tools/test_tool_registry.py`, `tests/agents/test_hotel_search_intent.py`, `tests/prompts/test_planner_prompt.py`, `tests/prompts/test_concierge_prompt.py`
  - `apps/api/eval/datasets/hotels.json`, `eval/datasets/errors.json`, `eval/baselines/main.json`
  - `apps/web/src/components/chat/AgentActivityTrail.tsx`
  - `specs/min-51-hotel-search-intent/PLAN.md`, `specs/review-b7-eval-baseline-ci/TRIAGE.md`, `specs/gh-156-flight-search-before-create-trip/SUMMARY.md`
  - `docs/solutions/agent/planner-search-first-save-later.md`, `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`, `docs/solutions/INDEX.md`, `docs/solutions/critical-patterns.md`
  - `CLAUDE.md`, `.claude/rules/behavior.md`, `.claude/rules/research-depth.md`, `.claude/harness-manifest.json`
- **Upstream repositories or pages checked:** LangGraph/LangChain tool-calling and tool-binding
  guidance (overlapping-tool disambiguation via docstrings) — general guidance only, no
  repository adopted:
  - https://www.braindrip.blog/courses/langgraph-agents/02-tools-and-models/binding-tools-to-models
  - https://medium.com/@gopiariv/handling-tool-calling-errors-in-langgraph-a-guide-with-examples-f391b7acb15e
- **Official docs domains or pages checked:** `- none (local-only; no external surface)`

---

## Evidence Boundary

> **Confirmed from artifacts (read on this branch, base `main` 0a7b6d7):** the concierge tool
> binding excludes `search_hotels`; `search_hotels` is read-only, trip-less and not
> `trip_guard`-gated; `ALL_TOOLS`/`TOOL_METADATA` do not change under A; supervisor v11 already
> routes availability lookups to the concierge; concierge v11 forbids exactly that; three hotel
> goldens pin `concierge` + `search_hotels` and all three fail in the committed baseline; four
> dateless goldens currently pass; `test_hotel_tool_split` asserts the opposite of A; the FE
> already maps both tool names to the hotels panel; MIN-51 recorded a live-review failure when the
> concierge held `search_hotels`.
>
> **Inferred from patterns:** that a concierge v12 rule + pin test will hold at k=3 (based on the
> #156 precedent, not on a run); that the panel-tab collision is cosmetic (reasoned from
> `kind`-based panel identity, not observed in a browser); that upstream guidance on docstring
> disambiguation transfers to this codebase.
>
> **Not checked:** no eval or live-LLM run was performed (read-only research session); the web
> hotels drawer was not opened in a browser to see a dateless and a dated panel in one thread; the
> Docker Postgres suite was not run; no measurement of concierge token/latency cost from the
> 16th tool.
