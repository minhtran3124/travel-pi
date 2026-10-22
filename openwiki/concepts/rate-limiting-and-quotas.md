---
type: concept
title: Rate limiting and quotas
description: The two throttling mechanisms in the API — a reusable database-backed per-subject fixed-window rate limiter with atomic increments, independent transactions and opportunistic pruning, applied today to feedback submissions; and the free-tier daily agent-turn quota checked before any graph work — plus how each surfaces as 429 responses and headers.
tags:
  - rate-limiting
  - quota
  - fixed-window
  - abuse
  - feedback
  - free-tier
  - headers
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-5300fab0b97a7cfb93201ea7
    resource: repo://apps/api/app/core/config.py
  - id: openwiki-source-7aeb9f0efe0972a74fa7f984
    resource: repo://apps/api/app/core/errors.py
  - id: openwiki-source-e9a79baff778e214a53a3965
    resource: repo://apps/api/app/core/rate_limit.py
  - id: openwiki-source-e8e83e7fa00852cc21a4ef40
    resource: repo://apps/api/app/db/models/rate_limit_counter.py
  - id: openwiki-source-317f9c0d55a27936830e7380
    resource: repo://apps/api/app/exceptions.py
  - id: openwiki-source-48cde84fc647394c277c19ac
    resource: repo://apps/api/app/repositories/conversation.py
  - id: openwiki-source-fd4730dbc7970ad15a86934c
    resource: repo://apps/api/app/repositories/rate_limit.py
  - id: openwiki-source-b842553da9494f6fbfc62431
    resource: repo://apps/api/app/research/service.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-1dfc4194f3074148c4c9d16d
    resource: repo://apps/api/app/routers/feedback.py
  - id: openwiki-source-c0a7e6f1ad1c76847a455b8a
    resource: repo://apps/api/app/services/quota_service.py
  - id: openwiki-source-e367aa7aabde754472afac4e
    resource: repo://apps/api/app/tools/web_search_tools.py
  - id: openwiki-source-1ca9f0ece8c96c923bf27fdc
    resource: repo://apps/api/tests/api/agent/test_feedback_rate_limit.py
  - id: openwiki-source-dc59508a81e3e800fdc5629f
    resource: repo://apps/api/tests/api/agent/test_quota.py
  - id: openwiki-source-10c285325f2bef613eeee4ef
    resource: repo://apps/api/tests/api/test_rate_limit_dependency.py
  - id: openwiki-source-ecc662dd273923f2f408732a
    resource: repo://apps/api/tests/db/test_rate_limit_repository.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
---

# Rate limiting and quotas

The API throttles in two different ways, for two different reasons, and it is important not to confuse them:

| Mechanism | Purpose | Subject | Storage | Error |
|---|---|---|---|---|
| Rate limiter (`app/core/rate_limit.py`) | Short-window abuse protection on a specific action | Authenticated user id, or an explicitly namespaced anonymous id | `rate_limit_counters` table, one row per policy/subject/window | `RateLimitError`, 429 with `Retry-After` and `X-RateLimit-*` |
| Daily quota (`app/services/quota_service.py`) | Product limit on free-tier agent usage | Authenticated user id | Counted from persisted user messages | `QuotaExceededError`, 429 with an upgrade message |

Neither is per-IP or per-device; that is intentionally out of scope. Redis is deliberately not a dependency, so both are built on the application database and work identically on SQLite and Postgres.

## The rate limiter

### Policy and subject

`rate_limit(name=..., limit=..., window_seconds=..., subject=...)` builds a FastAPI dependency; `enforce_rate_limit(session, name=..., subject=..., ...)` is the underlying callable for routes whose subject must come from the request body. A policy with a non-positive limit or window is rejected **at startup** when the dependency is built, and again at enforcement, because a zero window would divide by zero.

The default subject resolver returns the verified bearer subject and `None` for anonymous callers, and **`None` means the limit is skipped**. A client-supplied id is never used as the subject by default because it is spoofable and shares the id space of real users; anonymous endpoints must pass their own resolver that namespaces the id. `test_default_resolver_ignores_spoofable_query_user_id` pins this.

### Enforcement semantics

- **The limiter must run before the request's unit of work starts a transaction.** `enforce_rate_limit` raises if the request session is already in a transaction, and rate-limit dependencies are listed before any session-using dependency. On SQLite a caller-owned transaction could hold the writer lock and deadlock the limiter.
- **The hit is committed on an independent session** (a `sessionmaker` cached per engine, bound to the same engine as the request), so the increment counts even when the request later fails with a 4xx or 5xx or rolls back. `test_rejected_404_requests_still_count` and `test_increment_persists_when_request_errors` cover this.
- When a subject was resolved, the decision is stored on `request.state` so the header middleware emits the real `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`; on routes without a limiter the middleware reports the informational `RATE_LIMIT_NOMINAL` instead (see [Backend request lifecycle](../architecture/backend-request-lifecycle.md)).
- Over the limit, `RateLimitError` carries `retry_after` (seconds to the window boundary, at least 1), which the error handler turns into a `Retry-After` header, plus the policy metadata for the `X-RateLimit-*` headers.

### The counter repository

`RateLimitRepository.hit` (`app/repositories/rate_limit.py`) implements a **fixed window**: `window_start = now − (now mod window)`, `reset_at = window_start + window`. The increment is atomic at the database level (`UPDATE … SET count = count + 1` scoped by bucket, subject, window size and window start), so concurrent workers cannot under-count; when no row exists yet, the first hit is inserted inside a nested transaction and an `IntegrityError` from a racing worker falls back to the update. On SQLite a `busy_timeout` makes a concurrent writer wait rather than fail with "database is locked". `test_concurrent_existing_row_allows_exactly_limit` proves the exact-limit guarantee.

The `rate_limit_counters` table has a unique constraint over `(bucket, subject, window_seconds, window_start)`, which is also the increment's lookup index. **The window size is part of the policy identity**, so changing a policy's window starts fresh counters instead of reusing old ones. Each row stores `prune_after = window_start + 2 × window`, one window of clock-skew grace, and an index on `(bucket, prune_after)` lets the repository delete expired rows opportunistically, only when a new window row is created, keeping the `DELETE` off the hot path. The hardening migration that introduced these columns isolated legacy rows under a sentinel identity so they could never be reused (see [Data layer and migrations](../architecture/data-layer-and-migrations.md)).

### Where it is applied

Three policies are enforced today.

**Feedback.** `POST /agent/feedback` declares `feedback_rate_limit` as its first dependency, reads `FEEDBACK_RATE_LIMIT_MAX` and `FEEDBACK_RATE_LIMIT_WINDOW_SECONDS` per request so environment overrides apply, and resolves the subject as the JWT id, else `anon:<anonymous_user_id>` from the body, else `None` (in which case the limit is skipped and the service answers 401). Authenticated and anonymous subjects count separately. The feedback service itself is idempotent per client event and refuses to rate anything but a completed run (see [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md)).

**Live web search.** `search_web` and `find_places_live` call `enforce_rate_limit` with bucket `web_search`, the traveller's injected `user_id` as the subject, `WEB_SEARCH_USER_HOURLY_LIMIT` hits (default 30) and a 3600-second window, on a fresh `session_scope()` session before any provider call. A tool with no signed-in traveller refuses instead of skipping the limit. Over the limit, the `RateLimitError` is folded into a tool error the model reads, not an HTTP 429 (see [Live web search](../integrations/live-web-search.md)).

**Trip-research starts.** `ResearchService` calls `RateLimitRepository.hit` directly with bucket `research_start`, the user id as the subject, `RESEARCH_DAILY_LIMIT` (default 3) and a 24-hour fixed window. It commits on its own session factory, so the hit counts even if the booking then fails. The cap is spent only for a start that wins the per-trip lock and is not a resume, so a 409 or a resumed orphan run is free. All three launch paths go through it: the REST start and revise routes return 429, and the chat launcher replies `research_limit_reached` (see [Trip-research deep agent](../agent/trip-research-deep-agent.md)).

## The free-tier daily quota

`check_quota(user_id, tier, repo)` runs in both agent endpoints **before any conversation row, run row or graph work**, so a blocked turn costs nothing and no bytes are streamed. Premium users return immediately. For free users it counts the caller's `user`-role messages since 00:00 UTC today, joining messages to conversations by owner (ISO-8601 timestamps sort chronologically, so a string `>=` compare is a correct cutoff), and raises `QuotaExceededError` (429) once the count reaches `AGENT_FREE_DAILY_TURN_LIMIT` (default 20). The quota is a router-level precondition rather than part of the agent context, and the tier comes from the backend-resolved users table (see [Authentication and user tiers](auth-and-tiers.md)). `tests/api/agent/test_quota.py` covers under-limit, at-limit on both endpoints, premium bypass and the midnight boundary.

Because the count is derived from persisted user messages, a turn that was rejected by the quota does not itself consume quota, and resume turns (which send no new user message) are not counted either.

## Adding a new limit

Reuse `rate_limit(...)` or `enforce_rate_limit` rather than adding a library: pick a stable bucket `name`, decide on the subject resolver (and namespace any anonymous id), and attach the dependency ahead of any dependency that opens the request session. Per-user only is a deliberate constraint; a per-IP policy would need a different subject resolver and a decision about proxies.
