---
problem_type: decision
module: api/core
tags: rate-limiting, build-vs-buy, slowapi, fastapi-limiter, limits, pyratelimiter, redis, no-redis, durable, dependencies
severity: standard
applicable_when: Tempted to replace apps/api/app/core/rate_limit.py (the hand-written DB-backed limiter) with a popular rate-limiting library, or facing a rate-limiter build-vs-buy call under a no-Redis / DB-only constraint.
affects:
  - apps/api/app/core/rate_limit.py
  - apps/api/app/repositories/rate_limit.py
  - apps/api/requirements.txt
supersedes: null
confidence: high
confirmed_at: 2026-07-21
---

## Applicable When

Someone proposes swapping travel-pi's hand-written rate limiter (`specs/rate-limit-primitive`, PR
#110) for a popular off-the-shelf library — a reasonable NIH instinct worth an evidence-backed answer
rather than re-litigating. More generally: any rate-limiter build-vs-buy call where the deployment has
**no Redis/Memcached and the SQL database is the only shared store**, yet the limiter must be durable
and correct across multiple workers/processes.

## Context

We ship a ~150-line DB-backed limiter: a `rate_limit_counters` table, an atomic fixed-window
`UPDATE count = count + 1`, a `RateLimitError(429)` with `Retry-After`, and a reusable FastAPI
dependency keyed per-effective-user. It is tested cross-engine (8 pass on Postgres, 19 on SQLite).

Hard constraints: (1) NO new infra dependency — no Redis/Memcached; DB (SQLite local / Postgres prod)
is the only shared store. (2) Durable + correct across workers (not per-process in-memory). (3)
Per-authenticated-user keying. (4) Integrate with the `AppError`→status envelope + request-scoped
SQLAlchemy session.

A deep-research pass (5 angles, 20 sources, 25 claims adversarially verified) measured the field.

## Findings (verified, primary sources)

| Library | Storage backends | No-Redis + durable cross-worker? |
|---|---|---|
| **slowapi** (wraps `limits`) | redis / memcached / in-memory | ❌ falls back to in-memory = per-process, not durable |
| **fastapi-limiter** | Redis (v0.2.0 claims "powered by pyrate-limiter", low-confidence 2-1) | ❌ Redis-oriented |
| **`limits`** (the engine under slowapi/flask-limiter) | Redis / Memcached / MongoDB / Valkey / in-memory — **NO SQL backend** | ❌ in-memory is per-process; every durable backend is a network service |
| **PyrateLimiter** | in-memory / **SQLite** / **Postgres** / Redis | ⚠️ SQLite is single-host-many-process (file lock); its Postgres concurrency-correctness claim was **REFUTED 0-3** |

- Every high-adoption FastAPI limiter (slowapi, fastapi-limiter, `limits`) is **fundamentally
  Redis/in-memory oriented**. Without Redis they degrade to per-process in-memory — exactly the
  cross-worker-undercount bug the hand-written limiter avoids. (`limits` backend list: 3-0; slowapi
  memory-fallback: 3-0.)
- `limits` is healthy (5.8.0, Feb 2026, ~577★) and exposes its algorithms (fixed / moving / sliding
  window) with `hit/test/get_window_stats`, plus a **custom-storage registry** — so a hybrid (borrow
  its algorithms, keep our DB backend) is technically viable (3-0).
- **PyrateLimiter** is the one popular lib with native DB backends (SQLite + Postgres), but: SQLite is
  single-host only, its Postgres cross-writer correctness is **unverified/refuted**, it is
  leaky-bucket (different model), and it would still need custom wiring to our envelope/session.

## Decision

**Keep the hand-written limiter (build).** Reconsider only via the two triggers below.

Rationale:
1. No popular library satisfies the crux constraint (no-Redis **and** durable cross-worker). They are
   Redis/in-memory-first; dropping Redis gives per-process counters — the precise failure we avoid.
2. The only DB-native popular option (PyrateLimiter) has unverified multi-writer Postgres correctness
   and a single-host SQLite backend — it does not clearly beat our tested atomic `UPDATE`.
3. Our code is small, tested on real Postgres + SQLite, integrates with `AppError` + the request
   session, and reuses the booking/trip `begin_nested()`/`IntegrityError` convention. Adopting a
   library would add a dependency and a model mismatch while we would **still own the DB-atomicity
   logic** anyway.

## Reconsider when

- **Burst-at-boundary** of the fixed window becomes a real problem → port `limits`' sliding-window-
  counter *algorithm* while keeping our table + atomic increment (clean hybrid — do not swap storage).
- **Infra gains Redis** → slowapi / fastapi-limiter become reasonable (less code, battle-tested).

## Caveat

The deep-research synthesis step itself failed on a usage limit, so this was synthesized manually from
21 verified claims. The load-bearing facts (no SQL-durable backend in the top libraries; `limits`
custom-storage registry; PyrateLimiter's SQLite/Postgres backends) are all 3-0. Precise PyPI download
counts were not fully verified, but the conclusion rests on architecture, not popularity numbers.
