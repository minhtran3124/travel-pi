# gh-166 — `list_trips` agent tool — Research Brief

**Depth: Deep** (intake lane `high-risk` → Deep per `rules/research-depth.md`; not re-scored here —
xia2 may only raise depth). No evidence emerged that would raise it further.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing** — clone the `get_trip_summary` tool shape over the already-present `TripService.list_trips()`; no new abstraction, no new dependency |
| **Why this is the lightest credible path** | Every layer below the tool already exists and is owner-scoped; the only missing piece is the ~25-line `@tool` wrapper and the prompt rule that makes the model reach for it |
| **Confidence** | 92% |
| **Next step** | `writing-plans` — the design's five components map to tasks; the two conditionals (supervisor routing, eval baseline) each need an explicit task |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm/Turborepo monorepo — FastAPI backend (`apps/api`), Next.js frontend (`apps/web`); this change is backend-only |
| Primary language + runtime | Python — venv 3.14 local, **3.12 in Docker** (`docs/solutions/` py312-vs-py314) |
| Frameworks / platforms | FastAPI 0.136.3, SQLAlchemy 2.0.51, Pydantic 2.13.4, LangGraph 1.2.6, langchain-core 1.4.8, mcp 1.28.0 |
| Relevant packages | `langgraph.prebuilt.InjectedState`, `langchain_core.tools.tool`, `mcp.server.fastmcp.FastMCP` |
| Detectable versions | `apps/api/requirements.txt` (ranges) + installed versions above (exact) |
| Important constraints | `rules/behavior.md` §3 surgical changes; `CLAUDE.md` stage/commit as separate commands; `hooks/risk-corroboration.sh` (public-contract, block-mode); ruff-on-edit hook strips imports added before their use |

## Feature Understanding and Assumptions

- **Requested feature:** GitHub issue #166 — the agent has no way to list a user's trips, so it
  answers "how many trips i have?" from the single active `trip_id` and states it as the whole set.
- **What success appears to mean:** the real count with trip names (SC-1); no trip id in the reply
  (SC-2); not served over MCP (SC-3); never another user's trips (SC-4); a named existing trip is
  recognised rather than offered as a fresh idea (SC-5).
- **Assumptions from the request:** E001-A (read-only; no `select_trip`, no mid-turn `trip_id`
  rebinding) and E003-B (excluded from the MCP surface) are settled — this brief researches how to
  build that, not whether to.
- **Assumptions still needing confirmation:** which sub-agent the supervisor actually routes
  "how many trips do I have" to. Everything else is confirmed from artifacts.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `TripService.list_trips()` exists (`app/services/trip_service.py:116`) and is already owner-scoped — it passes `self._user_id` to `TripRepo.list_trips(user_id)`, which filters `user_id` **and** `deleted_at IS NULL`, ordering `created_at DESC` |
| `Local` | `grep -rn "list_trips" apps/api/app` hits only routers/repositories/services — **nothing** under `app/tools/`. The issue's root cause is confirmed, not assumed |
| `Local` | `dump()` (`app/tools/_base.py:119`) is `model_dump(mode="json")` — it is what turns `date` fields into strings. A hand-built projection **bypasses** it (see Risks) |
| `Local` | `TripRepo.list_trips` runs an unfiltered `select(models.TripItem)` — every item of every trip in the database, grouped in Python. Pre-existing; out of scope |
| `Local` | `Trip` (`app/schemas/trip.py:130`) has **no `status` field** — the issue's suggested "(id, title, city, dates, status)" projection cannot include one |
| `Local` | MCP: `build_mcp_server` registers `tool.func`; dumping `get_trip_summary`'s served `inputSchema` shows `user_id` as a plain optional string — `InjectedState` is invisible to FastMCP. Verified by running it, not inferred |
| `Local` | `docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md` — no hand-authored `args_schema`; descriptions inline via `Annotated[..., Field(...)]` |
| `Local` | `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md` — `active.yaml` is a name→version pointer; editing a `vN.md` without bumping it is a silent no-op |
| `Local` | `docs/solutions/agent/concierge-hotel-tool-choice.md` — never promise a specialist a capability its bound toolset cannot execute (why the guard is split negative/positive) |
| `Upstream` | langgraph discussion #5410 (InjectedState + MCP over streamable-http) reaches the same conclusion independently: identity-ish params must be set programmatically, not left model/caller-suppliable, "so there is no risk of data leaking between users". Corroborates E003-B |
| `Upstream` | langgraph issues #6241 / #6350 and langchain #31688 — the recurring failure mode is injected params being treated as ordinary required schema fields. Same root cause as the local `args_schema` learning; reinforces "don't hand-author a schema" |
| `Inference` | The supervisor will route the counting question to `planner` or `journal` — both hold `TRIP_TOOLS`. Not verified; §5 of the design makes it an observation step rather than a guess |

## Local Findings

- **Relevant files:** `app/tools/trip_tools.py`, `app/tools/registry.py`, `app/mcp/server.py`,
  `app/agents/state.py` (`system_with_summary`), `app/agents/nodes.py` (`load_context`),
  `app/services/trip_service.py`, `app/repositories/trip.py`, `app/prompts/{planner,journal}/`,
  `app/prompts/active.yaml`, `tests/tools/`, `tests/mcp/test_mcp_server.py`, `eval/datasets/journal.json`.
- **Existing abstractions / extension points:** `TRIP_TOOLS` (append → planner + journal inherit
  automatically; `budget` filters by a name allowlist, `concierge` binds no trip tools);
  `TOOL_METADATA` derives `readOnly` from absence in `_WRITE`; `session_scope` / `dump` /
  `tool_error` / `log_tool_call` in `_base.py`.
- **Conventions worth preserving:** injected params carry `= None` defaults; `user_id is None` →
  `ToolException`; `AppError` → `tool_error`; module docstring already documents the
  no-`args_schema` rule; a tool's own docstring is its model-facing description.
- **What can likely be reused:** the whole stack below the tool. Cleanest projection is
  `dump(trip)` first, then pick keys off the JSON-able dict — dates arrive pre-stringified and
  `items` collapses to `len(...)`.
- **What appears missing locally:** the `@tool` wrapper; a by-name exclusion mechanism in
  `server.py` (today: destructive-by-metadata, `create_trip` implicitly by `tool_call_id`); a
  seeded-trip eval fixture (`eval/adapters/db_oracle.py` records this gap explicitly — out of scope).

## Upstream Findings

- **Repositories inspected:** `langchain-ai/langgraph` (discussion #5410, issues #6241, #6350),
  `langchain-ai/langchain` (issue #31688).
- **Pattern already present upstream:** the injected-vs-served-schema hazard is a known,
  repeatedly-filed class — not a local quirk.
- **Areas worth modeling:** nothing to copy. Upstream has no ready-made "exclude a tool from the
  MCP surface" helper; the local destructive-exclusion precedent in `server.py` is the closer fit.
- **How closely it matches:** conceptually identical, mechanically different — those reports are
  about `create_agent`/CLI validation, while this repo hand-rolls its sub-agents and its own
  `build_mcp_server`.
- **Gaps/uncertainties:** no upstream source states FastMCP's schema-derivation behavior as a
  contract, which is why it was verified locally by dumping the served schema.

## Docs Findings

- none (local-only; no external surface) — no dependency added or upgraded, no external system
  integrated, and no version-specific API newly relied upon: the change reuses `@tool` /
  `InjectedState` / `FastMCP` exactly as the repo already uses them. The one version-sensitive
  behavior the design leans on (FastMCP deriving the schema from the raw signature) was confirmed
  empirically at the pinned versions above rather than from documentation.

## Recommendation

- **Primary recommendation:** **Reuse existing.** Wrap `TripService.list_trips()` in a `@tool`
  cloned from `get_trip_summary`, project via `dump()`, append to `TRIP_TOOLS`, exclude by name in
  `build_mcp_server`.
- **Why this is the lightest credible path:** the service, the owner scoping, the session
  handling, the error mapping, the metadata derivation, and the domain binding all exist. The new
  code is one function plus one `if` in the MCP builder.
- **Why the next-best alternative lost:** widening `load_context` to inject all trips (design §
  Approaches, option 1) needs no tool but pays context on every turn, cannot reach a non-active
  trip, and leaves the agent-native-parity gap the issue names. Prompt-only (option 2) makes the
  question unanswerable.
- **What would change this recommendation:** if `select_trip` came back into scope (E001 reopened),
  the projection would need to carry ids and the tool would stop being a pure read — a different
  design, not a bigger one.

## Risks, Unknowns, and Follow-Up Questions

**Technical risks (Deep):**

1. **Date serialization.** A hand-built dict of `Trip` fields carries `datetime.date` objects;
   unlike every neighbouring tool it would not pass through `dump()`. Mitigation: project *from*
   `dump(trip)`. Left unmitigated this fails at JSON encoding, not at import — tests must assert
   the payload is JSON-serializable.
2. **Prompt edits that never reach the model.** Two independent traps: `active.yaml` must be
   bumped (`supervisor-active-yaml-is-a-pointer`), and the graph is baked at lifespan startup —
   `uvicorn --reload` watches only `.py`, so a prompt-only edit needs
   `docker exec api-api-1 touch app/main.py` before any manual verification.
3. **Routing.** Supervisor v11 has no example for the counting question; if it lands on
   `concierge` the tool is not bound and the bug survives the fix. Handled as an observation step,
   not a speculative v12 bump.
4. **Eval gate sensitivity.** The gate reads the **`journal` capability pass_rate**, not case
   count (`evalkit/baseline.py` skips ids present in only one report), and `journal` is already in
   `capabilities_below_threshold`. Hence +1 golden and reusing the existing naming case.
5. **Hard gate at commit time.** `risk-corroboration.sh` will see a new tool + MCP edit. The
   `Lane: high-risk` line in `SUMMARY.md` is what keeps it from blocking.
6. **`_no_active_trip()` mis-application.** Every other trip tool returns it when `trip_id` is
   `None`; this tool must not — no open trip is a normal state for this question. An implementer
   cloning mechanically will get this wrong.

**Evidence gaps:** the actual route for the counting question; whether the judged reply for the
updated `journal-ambiguous-vi-01` improves (it is #150's known failure — this change does not
claim to fix it).

**Version uncertainties:** none material. Docker 3.12 vs local 3.14 is a known divergence; nothing
here uses version-sensitive syntax.

**Follow-up questions for the user:** none — E001/E002/E003 settled the two that existed.

## Source Pack

- **Local files read:** `apps/api/app/tools/trip_tools.py`, `app/tools/registry.py`,
  `app/tools/_base.py`, `app/mcp/server.py`, `app/agents/state.py`, `app/agents/nodes.py`,
  `app/services/trip_service.py`, `app/repositories/trip.py`, `app/schemas/trip.py`,
  `app/routers/agent.py`, `app/prompts/active.yaml`, `app/prompts/planner/v13.md`,
  `app/prompts/supervisor/v11.md`, `tests/mcp/test_mcp_server.py`, `eval/adapters/config.py`,
  `eval/datasets/*.json`, `eval/baselines/main.json`, `requirements.txt`,
  `docs/solutions/agent/{explicit-args-schema-breaks-tool-injection,supervisor-active-yaml-is-a-pointer,concierge-hotel-tool-choice}.md`,
  `CLAUDE.md`, `.claude/rules/*.md`, `.claude/harness-manifest.json`
- **Upstream repositories or pages checked:** https://github.com/langchain-ai/langgraph/discussions/5410 ·
  https://github.com/langchain-ai/langgraph/issues/6241 · https://github.com/langchain-ai/langgraph/issues/6350 ·
  https://github.com/langchain-ai/langchain/issues/31688
- **Official docs domains or pages checked:** `- none (local-only; no external surface)`

## Evidence Boundary

> **Confirmed from artifacts (read or executed):** absence of any `list_trips` tool; owner scoping
> in service + repository; `Trip` has no `status`; `dump()` is `model_dump(mode="json")`;
> `TripRepo.list_trips`'s unfiltered item query; the MCP served schema exposing `user_id` (dumped
> live); `TOOL_METADATA` readOnly derivation; domain bindings for planner/journal/budget/concierge;
> `active.yaml` at planner 13 / journal 2; the 84-case `full` baseline and `journal` sitting below
> threshold; the eval runner's hardcoded `user_id = "eval"`.
>
> **Inferred from patterns:** which sub-agent receives the counting question; that the two prompt
> bumps will change behavior (prompt edits are not deterministically verifiable — only the eval
> run is evidence); that projecting from `dump()` is the least-surprising shape for reviewers.
>
> **Not checked:** whether the fix moves `journal-ambiguous-vi-01` from red to green (needs a
> judged run); FE behavior (untouched); any Postgres-vs-SQLite ordering difference for
> `created_at DESC` ties — the design's explicit-timestamps fixture rule sidesteps it rather than
> proving it absent.
