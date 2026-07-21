# Research Brief — GH-106: AgentConfigCache cross-process freshness + reflection-checkbox CSS fix

Depth mode: **Deep** — trips two Deep signals: (1) changes a shared runtime configuration
contract (`AgentConfigCache` is a process-wide singleton read by every `/agent/chat` and
`/agent/stream` request); (2) touches a high-blast file (`app/core/agent_config_cache.py`,
a core, widely-imported module). Consistent with the high-risk lane already assigned at intake
(`specs/gh-106-reflection-toggle-not-honored/SUMMARY.md`).

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | Use built-in (no new dependency, no new infra) — extend the existing `AgentConfigCache` with a version-poll keyed off `AgentConfig.updated_at`, a column that already exists (inherited from `UUIDBase`/`TimestampMixin`) and is already correctly bumped by both current write paths. |
| **Why this is the lightest credible path** | The version marker this needs already exists in the schema and is already maintained correctly — the only work is changing `_maybe_refresh()`'s decision logic and adding one cheap repository query. No migration, no new external service, no engine-specific code. |
| **Confidence** | 90% |
| **Next step** | Proceed to `/writing-plans` using `specs/gh-106-reflection-toggle-not-honored/design.md` as the spec; the design is already reviewed and approved (2-round spec-review, `design.md` §9 Status log). |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo: FastAPI backend (`apps/api/`) + Next.js frontend (`apps/web/`); this feature is backend-only |
| Primary language + runtime | Python ≥3.10 (`pyproject.toml`); local dev observed on 3.14, Docker/CI on 3.12 (per project memory `docker-py312-vs-local-py314`) |
| Frameworks / platforms | FastAPI `>=0.110.0,<0.137.0`, SQLAlchemy `>=2.0.0,<2.1.0`, Alembic `>=1.13.0,<2.0.0`, Pydantic `>=2.6.0,<3.0.0`, Jinja2 `>=3.1.0` (`apps/api/requirements.txt`, `pyproject.toml`) |
| Relevant packages | None new — no dependency-manifest change in this feature (ruled out Redis/pub-sub explicitly, see Recommendation) |
| Detectable versions | As above; DB engine is SQLite locally / Postgres (`pgvector/pgvector:pg17`) in Docker (`apps/api/docker-compose.yml`), selected by `DATABASE_URL` |
| Important constraints | `CLAUDE.md`: "ORM confined to `repositories/`"; async only for real I/O (this is sync, correctly — DB reads, no external I/O); `.claude/rules/auto-correct-scope.md` Rule 4 hard gate "replacing a service/pattern" — already acknowledged, drove the high-risk lane |

---

## Feature Understanding and Assumptions

- **Requested feature:** Two bundled fixes (per `design.md`, itself the product of a full brainstorm with the user): (A) make `AgentConfigCache` detect a config write from another OS process within a few seconds instead of up to 1h (future-proofing — no multi-process deployment exists today); (B) fix a CSS bug where the "Reflection enabled" checkbox visually renders on every agent's dashboard-edit modal instead of only `reflection`.
- **What success appears to mean:** A dashboard config write is visible to every process within one poll interval; a DB hiccup during a poll fails open (serves stale cache, doesn't break `/agent/chat`); the checkbox is invisible for non-`reflection` agents.
- **Assumptions from the request:** Table size stays small (~9 rows, one per `AGENT_CONFIG_NODES` entry) — a few-second full-table poll/reload is cheap regardless.
- **Assumptions still needing confirmation:** None outstanding — the brainstorm + 2-round spec review already resolved the open questions (TTL-shrink vs. version-poll vs. LISTEN/NOTIFY vs. Redis; global vs. per-field scope; schema-column vs. memory-only). If the exact poll-interval default (`design.md` suggests "e.g. 3") needs a firmer number, that's a PLAN-time detail, not a research gap.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/core/agent_config_cache.py` (current TTL cache, `_maybe_refresh`, `invalidate`); `app/repositories/agent_config.py` (`upsert`, single write chokepoint besides the seeder); `app/db/base.py` (`TimestampMixin.updated_at`, `onupdate=_utc_now_iso`); `app/db/models/agent_config.py` (`AgentConfig(UUIDBase)` — inherits the timestamp); `app/db/seed.py::_seed_agent_config` (second write path, also ORM); `app/core/config.py:176` + `app/core/lifespan.py:51-52` (the 2 references to the setting being renamed); `app/templates/agent_config.html` (CSS root cause, `.am-field { display: flex }` at line 315 vs. `hidden` at line ~55/403); `apps/api/tests/core/test_agent_config_cache.py` (existing tests coupled to the old TTL mechanism, 2 of which need rewriting) |
| `Upstream` | Unleash (feature-flag SDK) polling-mode revision-ID mechanism — GitHub issue [unleash/unleash#11281](https://github.com/unleash/unleash/issues/11281), a real production bug report about a write path failing to bump the revision ID, directly analogous to this design's "every write path must bump `updated_at`" invariant (mitigated here because both write paths already go through the SQLAlchemy ORM, which handles it declaratively) |
| `Docs` | GitLab engineering docs on polling with ETag caching (https://docs.gitlab.com/development/polling/); LaunchDarkly SDK docs on polling-mode monitoring via conditional requests (https://launchdarkly.com/docs/sdk/features/monitoring) — both confirm "cheap version/ETag check, expensive reload only on mismatch" is an established, named pattern (not a bespoke invention for this repo) |
| `Inference` | Poll-frequency DB load is "negligible" for a ~9-row table — reasoned from table size and existing `list_all()` cost, not measured under load; flagged as a risk to revisit if the table grows materially (`design.md` §8) |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** `app/core/agent_config_cache.py`, `app/repositories/agent_config.py`, `app/db/models/agent_config.py`, `app/db/base.py`, `app/core/config.py`, `app/core/lifespan.py`, `app/templates/agent_config.html` + `agent_config_edit.html`, `app/services/agent_config_service.py`, `scripts/seed_agent_config.py`, `app/db/seed.py`, `apps/api/tests/core/test_agent_config_cache.py`, `tests/agents/test_agent_context.py`, `tests/agents/test_depth_toggles.py`, `tests/api/agent_config/test_agent_config_dashboard.py`.
- **Existing abstractions or extension points:** `AgentConfigRepository` is the single ORM-confined access point (per `CLAUDE.md` layering) — the new `max_updated_at()` method belongs there, not in the cache or service layer. `AgentConfigCache._generation` already demonstrates the "bump a counter only when data actually changed" idiom this design extends with a DB-backed equivalent (`_known_updated_at`).
- **Conventions worth preserving:** Single write chokepoint per table (`AgentConfigRepository.upsert`, plus one ORM `session.add` in the seeder) — both already go through SQLAlchemy, so `TimestampMixin`'s `onupdate` fires without any new discipline being asked of future write paths.
- **What can likely be reused:** `updated_at` (already present, already correctly bumped — no migration); the existing `_maybe_refresh()` control flow (TTL-elapsed check stays, only the body changes from "always reload" to "poll, then conditionally reload"); the existing `invalidate()` same-process-instant-refresh semantics (unchanged).
- **What appears missing locally:** No prior spec for the original TTL cache (referred to as "MIN-47" in code comments/docstrings) was found under `specs/` — likely implemented without its own spec directory, or the directory was since removed/renamed. This does not block the current work; the current code is the source of truth and was read directly.

---

## Upstream Findings

- **Repositories inspected:** Unleash (`unleash/unleash`, GitHub issue #11281) — a feature-flag platform whose polling-client SDKs use a revision-ID check before a full feature-set refetch; the issue documents a real regression where a write path didn't bump the revision, silently reintroducing staleness — the exact failure mode this design's "verify every write path" analysis (`design.md` §5) is guarding against.
- **Pattern or capability already present upstream:** "Cheap version/ETag poll, expensive reload only on mismatch" is the standard fallback mode for feature-flag SDKs that don't have a live push channel (SSE/websocket) available or enabled.
- **Files, modules, or areas worth modeling:** None directly portable (Unleash's mechanism is client-server over HTTP, not same-process-vs-DB) — the pattern's *shape* transfers, not any code.
- **How closely the upstream pattern matches this repo:** Structurally identical goal (detect "did the shared source change" cheaply before paying for a full reload); this repo's version marker is a DB column instead of an HTTP header, which is the natural adaptation for a DB-backed, multi-process (not client-server) topology.
- **Any upstream gaps or uncertainties:** None material — the pattern is simple enough that the "gap" upstream repos hit (forgetting to bump the marker on some write path) is exactly what this repo's evidence (both write paths already ORM-managed) rules out structurally rather than by convention/discipline.

---

## Docs Findings

- **Official sources checked:** GitLab engineering docs (polling + ETag), LaunchDarkly SDK docs (polling-mode monitoring). No SQLAlchemy-specific docs needed — `onupdate` is a well-established, already-in-use Column option in this codebase (`TimestampMixin`, applied to every model via `UUIDBase`).
- **Version-matched vs latest-stable status:** N/A — no version-sensitive API is being adopted; `onupdate` behavior is stable across SQLAlchemy 1.x/2.x and already exercised elsewhere in this codebase.
- **Built-in capabilities that already support the feature:** SQLAlchemy's `Column(..., onupdate=...)` (already declared on `TimestampMixin.updated_at`) is sufficient — no SQLAlchemy event hooks, no triggers, no additional library needed.
- **Current recommended APIs or workflows:** None beyond what's already in place; this is a query pattern (`SELECT MAX(updated_at)`), not an API adoption.
- **Important caveats, deprecations, or migration notes:** None. `updated_at` is stored as an ISO-8601 string (`_utc_now_iso()`, not a native `DateTime` column) — confirmed this sorts correctly under `MAX()`/string comparison on both SQLite and Postgres since the format is fixed-width, zero-padded, and always UTC.

---

## Recommendation

- **Primary recommendation:** Use built-in — extend `AgentConfigCache`/`AgentConfigRepository` with a version-poll against the already-existing `updated_at` column, exactly as specified in `specs/gh-106-reflection-toggle-not-honored/design.md`.
- **Why this is the lightest credible path:** Zero new schema, zero new dependency, zero new infrastructure; the one thing a version-poll design normally requires (a reliably-bumped version marker) is already present and already correctly maintained by both write paths going through the ORM.
- **Why the next-best alternative lost:** TTL-shrink-only was ruled out during brainstorm as strictly worse on the axis that mattered (propagation latency bound) for equivalent DB-load cost at this table size; Postgres `LISTEN/NOTIFY` was ruled out for needing an engine-conditional code path (SQLite has no equivalent) plus a new persistent-connection background task; Redis/pub-sub was ruled out as a new external-service dependency (its own Rule-4 hard gate) with no existing infrastructure to build on, for a future-proofing task with no concrete deployment driving it.
- **What would change this recommendation:** If a concrete multi-process deployment plan emerges with a hard sub-second propagation SLA, `LISTEN/NOTIFY` (Postgres-only, with a documented SQLite-dev fallback) would become worth the added complexity. Not the case today.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** All captured in `design.md` §8 (Rule-4 hard gate mitigation, settings rename blast radius, poll-frequency-vs-DB-load, CSS fix scope, scope-bundling ceremony, startup redundant-reload edge case) — no new risks surfaced by this research pass.
- **Evidence gaps:** None material. The one soft gap (no prior spec found for the original "MIN-47" TTL-cache feature) doesn't affect this design since current code was read directly rather than relying on historical docs.
- **Version uncertainties:** None — no version-sensitive API is being adopted.
- **Follow-up questions for the user:** None — the brainstorm + 2-round spec review already resolved every open design fork. Proceed to `/writing-plans`.

---

## Source Pack

- **Local files read:** `apps/api/app/core/agent_config_cache.py`, `apps/api/app/repositories/agent_config.py`, `apps/api/app/db/base.py`, `apps/api/app/db/models/agent_config.py`, `apps/api/app/db/seed.py`, `apps/api/app/core/config.py`, `apps/api/app/core/lifespan.py`, `apps/api/app/templates/agent_config.html`, `apps/api/app/templates/agent_config_edit.html`, `apps/api/scripts/seed_agent_config.py`, `apps/api/tests/core/test_agent_config_cache.py`, `apps/api/requirements.txt`, `pyproject.toml`, `specs/gh-106-reflection-toggle-not-honored/{SUMMARY.md,ESCALATIONS.md,design.md}`, `specs/agent-reflection-toggle/SUMMARY.md`, `specs/min-48-dashboard-agent-config/design.md`.
- **Upstream repositories or pages checked:** https://github.com/unleash/unleash/issues/11281
- **Official docs domains or pages checked:** https://docs.gitlab.com/development/polling/, https://launchdarkly.com/docs/sdk/features/monitoring

---

## Evidence Boundary

> Confirmed from artifacts: `AgentConfig` inherits `updated_at`/`onupdate` via `UUIDBase`/`TimestampMixin`; both write paths (`AgentConfigRepository.upsert`, `app/db/seed.py::_seed_agent_config`) go through the SQLAlchemy ORM with no raw-SQL bypass; the settings rename touches exactly 2 call sites; the CSS root cause (`.am-field { display: flex }` overriding `hidden`) matches the live template line-for-line; `tests/core/test_agent_config_cache.py` has 2 tests that will break under the new design (verified by tracing `Repo._session()` against a string factory) — all independently re-verified by the spec-review subagent against the live source, not just asserted in `design.md`.
>
> Inferred from patterns: poll-frequency DB load stays negligible at current table size (reasoned, not load-tested); the version-poll pattern's applicability here follows Unleash/GitLab/LaunchDarkly precedent by analogy, not a direct code transplant.
>
> Not checked: actual production deployment topology for this API outside this repo (confirmed via user answer during brainstorm: none exists yet — future-proofing only, no external infra to inspect); no load-testing was performed on the poll query.
