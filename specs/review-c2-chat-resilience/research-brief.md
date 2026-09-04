# review-c2-chat-resilience — Research Brief

Depth: **Deep** (intake lane `high-risk` → Deep per `rules/research-depth.md`; not upgraded or
downgraded during research). External surface: relies on a version-specific LangGraph API
(`Pregel.aget_state`) but adds no new dependency — the pinned `langgraph>=1.0,<2.0` (installed
1.2.6) is already vendored in this repo's `.venv`, so the authoritative source for D3's open
question is the installed source itself, read directly.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **reuse existing** — the `interrupt_pending`/`interrupt_payload` field pair, naming convention, and `graph.aget_state(cfg)` read mechanism all already exist in this codebase for a related purpose; D2/D3 adopt them rather than inventing new shapes. |
| **Why this is the lightest credible path** | Confirms the design's already-chosen field names for free and resolves D3's flagged uncertainty (does a bare thread-only `cfg` suffice for `aget_state`?) from the installed library's own source, not inference. |
| **Confidence** | 92% |
| **Next step** | `writing-plans` → `PLAN.md`. D3's cfg question is now closed (see Docs Findings), so nothing blocks planning. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm + Turborepo): FastAPI `apps/api`, Next.js `apps/web` |
| Primary language + runtime | TypeScript (Next 16.2.9, React 19.2.4) / Python (FastAPI, LangGraph) |
| Frameworks / platforms | LangGraph 1.2.6 (pinned `>=1.0,<2.0`), LangGraph-checkpoint 4.1.1, `@supabase/ssr` |
| Relevant packages | `langgraph`, `langgraph-checkpoint-sqlite`/`-postgres` (dev/test vs prod checkpointer) |
| Detectable versions | `apps/api/requirements-ai.txt`; `.venv/bin/python -c "import importlib.metadata as m; m.version('langgraph')"` → `1.2.6` |
| Important constraints | `rules/behavior.md` §3 (surgical changes); `auto-correct-scope.md` Rule 4 (a route signature change — sync→async — is not itself a hard gate here, it's mechanical, not architectural judgment) |

---

## Feature Understanding and Assumptions

- **Requested feature:** per `design.md` (approved, 2 review rounds): a Stop affordance during
  streaming (D1), rehydrating a pending HITL interrupt after reload via an extended
  `GET .../messages` response (D2/D3/D4), and not permanently forfeiting a claimable
  anonymous-history key on a transient claim failure (D5). Side-panel persistence is explicitly
  out of scope (D6); GitHub issue #109 is split to `review-c2b-fix-gh-109` (D0).
- **What success appears to mean:** the plan's eventual Success Criteria will assert `isStreaming`
  resets on stop, the new response shape round-trips with the right `interrupt_pending`/payload,
  and a non-403 claim failure keeps the localStorage key.
- **Assumptions from the request:** the design's D1–D6 decisions are final (both review rounds
  approved); no new scope beyond what design.md states.
- **Assumptions still needing confirmation:** none — D3's cfg question, the one open item design.md
  flagged for xia2, is resolved below.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `apps/api/app/schemas/agent.py:94-95` — `ChatResponse` already has `interrupt_pending: bool = False` and `interrupt_payload: dict \| None = None`. Same field names D2 independently chose. |
| `Local` | `apps/api/app/routers/agent.py:411-413` — the buffered `/agent/chat` handler computes `interrupts = result.get("__interrupt__", [])`; `interrupt_pending = bool(interrupts)`; `interrupt_payload = interrupts[0].value if interrupts else None`. This reads interrupts off a **just-completed invoke's return dict**, a different mechanism than a pure state read — not directly reusable for D3 (a GET with no invocation), but confirms the payload shape (`.value` off a LangGraph `Interrupt` object) matches what `mapper.py` and D3 both use. |
| `Local` | `apps/api/app/streaming/mapper.py:283-293` — the streaming path's post-drain interrupt read: `state = await graph.aget_state(cfg)`; `interrupts = state.interrupts`; same `.value` access. This is the read-only mechanism D3 extends, always called with the full per-run `cfg` (thread_id + callbacks + metadata) already in scope from the active stream — not evidence either way on whether a *bare* cfg works. |
| `Local` | `apps/api/tests/api/agent/test_agent_chat.py:117-123,368-380` — `booking_client` fixture (`app = _make_app(tmp_path, "booking", "Hotel booked!", premium_users=["u1"])`) reliably drives a real interrupt via `POST /agent/chat {"message": "book me a hotel in Paris", "user_id": "u1"}`, asserting `interrupt_pending is True`. Directly reusable for the new list-messages interrupt test D2's Tests section calls for — no new fixture needed. |
| `Local` | `docs/solutions/agent/local-postgres-checkpointer.md` — "Any in-progress multi-turn flow (planner interrupt, booking confirmation) is lost" when the dev checkpointer degrades to an in-process `MemorySaver` (Postgres down). Within one running server process this is consistent for both write and read (no false negative mid-process); it only bites across a server **restart**, which is already a pre-existing limitation of the whole interrupt mechanism, not something D3 introduces. |
| `Local` | `docs/solutions/agent/side-panel-language-decisions.md:106,118` — corroborates the same `graph.aget_state(cfg)` idiom used pre-stream to seed language, calling out "a second `aget_state` read per stream" as an accepted cost pattern in this codebase — D3's one extra `aget_state` call per `GET .../messages` request matches that precedent. |
| `Docs` (installed source, version-pinned) | `.venv/.../langgraph/pregel/main.py` — `Pregel.aget_state(self, config, *, subgraphs=False)` reads, in order: `ensure_config(config)` (fills standard `RunnableConfig` defaults for any missing key), `config[CONF].get(CONFIG_KEY_CHECKPOINT_NS, "")` (defaults to `""`, falsy, skips the subgraph-delegation branch entirely for a top-level graph), `merge_configs(self.config, config)` (graph-level defaults, not caller-required), and finally `thread_id = config[CONF][CONFIG_KEY_THREAD_ID]` — the **only** required key. No `callbacks`, `metadata`, or `run_id` is read anywhere in this method. |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** `apps/api/app/routers/agent.py` (`_thread_id`,
  `_config`, `list_conversation_messages`, the buffered-chat interrupt block for naming precedent),
  `apps/api/app/schemas/agent.py` (`ChatResponse`, `Message`, `Conversation`), `apps/api/app/streaming/mapper.py`
  (the streaming interrupt read), `apps/api/tests/api/agent/test_agent_chat.py` (`booking_client`
  fixture + interrupt tests), `apps/api/tests/api/agent/test_agent_history.py` (the three tests D2
  must update), `apps/web/src/components/chat/useAgentStream.ts` (`send`/`retry`/`resume`,
  `abortRef`, hydrate effect), `apps/web/src/lib/query/agent.ts` (`fetchConversationMessages`,
  `fetchClaim`), `apps/web/src/components/chat/{ChatComposer,ChatPanel,InterruptPrompt}.tsx`.
- **Existing abstractions or extension points:** `_thread_id`/`_config` in `agent.py` are already
  the single seam for building a LangGraph thread key from `(user_id, trip_id, conversation_id)`;
  D3 reuses `_thread_id` directly and builds a deliberately smaller `_config`-shaped dict (not the
  full `_config` helper, which requires `run_id`/`metrics` this read doesn't have).
  `GraphDep = Annotated[Any, Depends(get_travel_graph)]` is the existing DI pattern for injecting
  the compiled graph into a route.
- **Conventions worth preserving:** `interrupt_pending`/`interrupt_payload` field names (already
  established on `ChatResponse`); routes that need the graph inject `GraphDep`, not a module-level
  singleton; ownership checks return an empty/absent result rather than 403/404 (`list_conversation_messages`'s
  existing "neither leaks message contents nor confirms a conversation's existence" comment).
- **What can likely be reused:** the `booking_client` fixture and its interrupt-triggering request
  body for the new BE test; the `interrupt_pending`/`interrupt_payload` names; the `.value`
  extraction pattern from `mapper.py`.
- **What appears missing locally:** a precedent for calling `aget_state` with a bare thread-only
  cfg (resolved via source read, not a repo precedent — see Docs Findings); a Stop/cancel affordance
  anywhere in the FE chat UI (confirmed absent by the design's own grep).

---

## Upstream Findings

- **Repositories inspected:** none beyond the installed package itself — the question was
  "does this exact pinned version's method require more than thread_id," which the installed
  source answers definitively; no broader upstream pattern search was needed.
- **Pattern or capability already present upstream:** `aget_state`/`get_state` reading a
  checkpoint by thread id with no other required config is LangGraph's documented low-level
  state-access API (`StateSnapshot`), consistent with what the source shows.
- **Files, modules, or areas worth modeling:** none — the repo's own `mapper.py` usage is already
  the right model, differing from D3 only in cfg richness (D3 correctly identified the difference
  and now confirms it doesn't matter).
- **How closely the upstream pattern matches this repo:** exact match — same installed version,
  same method, read directly.
- **Any upstream gaps or uncertainties:** none remaining for this question.

---

## Docs Findings

- **Official sources checked:** none fetched over the network — the version-pinned, authoritative
  answer was available locally in the installed package (`.venv/.../langgraph/pregel/main.py`),
  which is strictly more precise than a general docs page for "does *this* pinned version require
  more config keys." Recorded here rather than under Upstream because it settles an
  external-surface/version-specific-API question, matching this section's purpose.
- **Version-matched vs latest-stable status:** exact version match (1.2.6, the installed and
  requirements-pinned version) — no drift risk.
- **Built-in capabilities that already support the feature:** `Pregel.aget_state(config)` requires
  only `config["configurable"]["thread_id"]`; `ensure_config` fills every other standard key with
  safe defaults. D3's `cfg = {"configurable": {"thread_id": thread_id}}` is sufficient — **confirmed,
  not assumed**.
- **Current recommended APIs or workflows:** unchanged from what `mapper.py` already does;
  D3 is a narrower, still-correct application of the same API.
- **Important caveats, deprecations, or migration notes:** none for this version pin. The one
  operational caveat (`local-postgres-checkpointer.md`) — a degraded in-process `MemorySaver`
  loses interrupt state across a server restart — is a pre-existing property of the whole HITL
  mechanism, not something D3's read path adds or worsens.

---

## Recommendation

- **Primary recommendation:** **reuse existing** field names and read mechanism; implement D1–D6
  as designed. No adaptation needed for D3 beyond what design.md already specifies.
- **Why this is the lightest credible path:** everything D2–D4 need is already established
  vocabulary (`interrupt_pending`/`interrupt_payload`) and an already-used API
  (`graph.aget_state`), and D3's one open question is now closed by reading the installed source
  rather than guessing.
- **Why the next-best alternative lost:** inventing new field names (e.g. `pendingInterrupt`) was
  never seriously considered — it would fragment the API's vocabulary against the existing
  `ChatResponse` fields for no benefit.
- **What would change this recommendation:** if a future LangGraph major version changed
  `aget_state`'s required config shape, this confirmation would need re-checking — out of scope
  here since the repo pins `<2.0`.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  1. `list_conversation_messages` becomes `async def` — confirm no caller depends on it being
     sync (route handlers are called by FastAPI either way; this is purely internal). Low risk.
  2. The response-shape change breaks four existing test assertions (already named in design.md
     D2 and the Tests section) — the plan must include those four edits as tasks, not just the new
     interrupt test, or `finishing-a-development-branch`'s suite run will fail.
  3. A degraded checkpointer (dev Postgres down) returns a state with no interrupts even when one
     was genuinely pending before a server restart — pre-existing limitation, not a regression;
     worth one line in the plan's Risks section so it isn't rediscovered as a "new" bug.
- **Evidence gaps:** no BE test for the new `GET .../messages` interrupt fields exists yet — the
  plan writes it, modeled on `booking_client`.
- **Version uncertainties:** none — installed version read directly.
- **Follow-up questions for the user:** none — design.md's one open question is resolved.

---

## Source Pack

- **Local files read:** `apps/api/app/routers/agent.py`, `apps/api/app/schemas/agent.py`,
  `apps/api/app/streaming/mapper.py`, `apps/api/app/streaming/persistence.py`,
  `apps/api/tests/api/agent/test_agent_chat.py`, `apps/api/tests/api/agent/test_agent_history.py`,
  `apps/api/requirements-ai.txt`, `apps/web/src/components/chat/useAgentStream.ts`,
  `apps/web/src/components/chat/{ChatComposer,ChatPanel,InterruptPrompt}.tsx`,
  `apps/web/src/lib/query/agent.ts`, `apps/web/messages/en.json`,
  `docs/solutions/INDEX.md`, `docs/solutions/critical-patterns.md`,
  `docs/solutions/agent/local-postgres-checkpointer.md`,
  `docs/solutions/agent/side-panel-language-decisions.md`,
  `specs/review-c2-chat-resilience/design.md`, `specs/review-c-web-experience/SUMMARY.md`.
- **Upstream repositories or pages checked:** `- none found` (question settled from installed source).
- **Official docs domains or pages checked:** `- none (local-only; no external surface beyond the
  already-installed, version-pinned langgraph package, read directly at Docs Findings above)`.

---

## Evidence Boundary

> **Confirmed from artifacts:** `Pregel.aget_state`'s only required config key is
> `configurable.thread_id` (read from the installed 1.2.6 source); `interrupt_pending`/
> `interrupt_payload` already exist as a naming convention on `ChatResponse`; the `booking_client`
> fixture reliably produces a real interrupt; the four BE test assertions D2 names do index the
> response as a bare list; `list_conversation_messages` is currently `sync def` with no `graph`
> parameter.
>
> **Inferred from patterns:** that reusing the existing field names is the right call (a design
> judgment, not a fact) — recorded as the Recommendation, not asserted as verified.
>
> **Not checked:** no test was actually run in this session (xia2 does not execute code); the
> `list_conversation_messages` async-conversion has not been compiled/type-checked yet — that
> happens in the implementation task.
