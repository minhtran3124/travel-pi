---
type: concept
title: Authentication and user tiers
description: How identity works end to end — Supabase sessions in the browser, bearer tokens verified by the API against the project JWKS, the AuthUser principal and owner-scoped data access, the backend-resolved free/premium tier that gates booking on both the REST and agent paths, dashboard basic auth, the operational scripts for users and tiers, and how tests replace the auth dependency.
tags: [auth, supabase, jwt, jwks, tiers, premium, authorization, ownership, dashboard]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-971a6d4aea52344000671dbc
    resource: repo://apps/api/app/core/auth.py
  - id: openwiki-source-eda0b38a403232caa7fc52bf
    resource: repo://apps/api/app/core/dashboard_auth.py
  - id: openwiki-source-7aeb9f0efe0972a74fa7f984
    resource: repo://apps/api/app/core/errors.py
  - id: openwiki-source-4d5e2594f7ee222ce365ae0c
    resource: repo://apps/api/app/db/models/user.py
  - id: openwiki-source-e8e214c40da48897dfccc504
    resource: repo://apps/api/app/enums.py
  - id: openwiki-source-3b21f05fbdbf5c2ab68ad7ad
    resource: repo://apps/api/app/repositories/trip.py
  - id: openwiki-source-371e007b9b16423f8f6e6ec3
    resource: repo://apps/api/app/repositories/user.py
  - id: openwiki-source-fc1d96b9ff665fbf4704c239
    resource: repo://apps/api/app/routers/flights.py
  - id: openwiki-source-578304a8aa1e84630ba3f292
    resource: repo://apps/api/app/routers/hotels.py
  - id: openwiki-source-2bebe8877415ffcf8e1536cc
    resource: repo://apps/api/app/services/booking_service.py
  - id: openwiki-source-e52f22dd7dfd7d00a70046ae
    resource: repo://apps/api/app/services/trip_service.py
  - id: openwiki-source-24072f12f4c9948f0045a98d
    resource: repo://apps/api/scripts/seed_supabase_user.py
  - id: openwiki-source-78f9336183df2b3a1038574f
    resource: repo://apps/api/scripts/set_tier.py
  - id: openwiki-source-87b0fc79431dbce39475f50c
    resource: repo://apps/api/tests/api/auth/test_jwt_auth.py
  - id: openwiki-source-3a2dde6adaa0b4f58984ea0b
    resource: repo://apps/api/tests/conftest.py
  - id: openwiki-source-a12105538dcb0232dfb18910
    resource: repo://apps/web/src/lib/api/client.ts
  - id: openwiki-source-354a4ce1fd16925f50a82a65
    resource: repo://apps/web/src/lib/supabase/authHeader.ts
  - id: openwiki-source-c4bea233c871a8644932e8f8
    resource: repo://apps/web/src/lib/supabase/middleware.ts
  - id: openwiki-source-aaa506ea8cabfd250f14882d
    resource: repo://apps/web/src/middleware.ts
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Authentication and user tiers

Identity is delegated to **Supabase Auth**. The web app holds the session and sends the access token as a bearer header; the API verifies that token cryptographically and never trusts anything else about who the caller is. Authorization then rests on two things the API resolves itself: the token's subject (ownership) and a tier stored in the API's own `users` table (capability ceiling).

## Verifying a bearer token

`get_current_user` in `apps/api/app/core/auth.py` extracts `Authorization: Bearer <token>`, fetches the signing key from the project's JWKS endpoint through a `PyJWKClient` cached per JWKS URL (the client caches keys internally), and decodes the JWT with `RS256` or `ES256`, the configured audience (`authenticated` by default) and the derived issuer. Any `PyJWTError` becomes an `AuthError` (HTTP 401) whose log line contains only the exception type, never the token. A token without a `sub` claim is rejected. If Supabase is not configured at all (`resolved_jwks_url` is `None`), every authenticated route fails with a 401 that says so; see [Configuration and environments](../architecture/configuration-and-environments.md) for the `SUPABASE_*` variables.

The result is a frozen `AuthUser` with `id` (the `sub`), `email`, `role` and the raw claims. `role` is read from `app_metadata.role`, which only an admin can set, **not** from the top-level `role` claim, which is always the Postgres role and can never identify an application admin.

`get_current_user_optional` returns `None` for a missing header **and** for an invalid, expired or misconfigured token, so hybrid routes can treat those callers as anonymous without raising. Two `Annotated` aliases, `CurrentUserDep` and `OptionalUserDep`, are what routers declare.

`tests/api/auth/test_jwt_auth.py` runs fully offline: it generates an RSA key pair in-process, monkeypatches the JWKS client, and asserts that a valid token authenticates, `app_metadata.role` surfaces, and missing, non-bearer, garbage, expired, wrong-audience, wrong-issuer and wrong-key tokens all yield 401.

## Ownership is the token subject

Every user-scoped route authenticates and then passes `auth_user.id` down as the owner: trip, booking, expense and saved-place services and repositories take a `user_id` on every read and write, so a foreign id behaves like a missing one (a `404`, never a `403`, so a probe cannot confirm a guessed id). The same subject becomes `state["user_id"]` in the agent graph, is injected into tools rather than supplied by the model, and scopes conversation history and claiming (see [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md) and [Trips, itinerary and budget](../domain/trips-itinerary-and-budget.md)). Earlier `user_id` query parameters on list endpoints are accepted but ignored, so identity can never be enumerated from the request.

## Tiers

`Tier` is a two-value enum, `free` and `premium`, stored as a plain string on the `users` table whose primary key is the Supabase user id. Three rules keep it trustworthy:

- **The tier is resolved by the backend only.** It is never read from a request body; `UserRepository.get_tier` returns the stored value or `free` when no row exists, and `ensure_user` creates a free row the first time a subject is seen.
- **REST booking is premium-only.** The `POST` book routes in `routers/flights.py` and `routers/hotels.py` declare `Depends(require_premium)`, which reads the tier from the database and raises `PremiumRequiredError` (HTTP 403 with an upgrade hint) for anyone else; an unknown stored value coerces to free.
- **Agent booking is premium-only too, by routing rather than by endpoint.** The agent router resolves the tier from the users table, `resolve_agent_context` removes the `booking` specialist from a free user's allowed set, and the supervisor's tier gate ends a free booking turn with a localized upgrade message before the HITL plan node is reachable (see [Agent state, runtime context and reply language](../agent/state-context-and-language.md) and [Guardrails](../agent/guardrails-pii-and-hitl.md)). Free users also carry a daily agent turn quota (see [Rate limiting and quotas](rate-limiting-and-quotas.md)).

Operationally, `python -m scripts.set_tier <supabase-user-id> premium|free` upserts a tier, and `python -m scripts.seed_supabase_user <email> <password> [--tier premium]` creates a Supabase auth user through the service-role API and the matching local `users` row without storing the password. The CI end-to-end account is always free tier, so browser tests must accept either booking outcome.

## The dashboard's separate gate

The server-rendered `/dashboard/*` operator pages do not use Supabase. `require_dashboard_access` enforces HTTP Basic with constant-time comparison when `DASHBOARD_BASIC_USER` and `DASHBOARD_BASIC_PASSWORD` are set (a malformed non-ASCII credential reads as wrong, never as a 500), leaves the pages open in development when they are unset, and returns 404 in production when they are unset, so the dashboard is never reachable in production without credentials. The 401 is raised as a Starlette `HTTPException` so the `WWW-Authenticate` challenge survives the JSON error envelope and the browser prompts. See [Admin API and server-rendered dashboard](../operations/admin-and-dashboard.md).

## The browser side

`apps/web/src/lib/supabase/` holds the browser, server and middleware Supabase clients built from `NEXT_PUBLIC_SUPABASE_URL` and the publishable key. `authHeader()` fetches a fresh access token on every call (never cached, because the SDK may silently refresh it) and returns `{}` when logged out or on the server, so the typed API client can attach it to every request and public endpoints are unaffected. The Next.js middleware refreshes the session cookies on each request, and redirects a signed-out visitor to `/auth/login?next=<path>` for the protected prefixes `/trips`, `/bookings`, `/expenses` and `/places`, since those pages can only ever produce 401s for anonymous callers. Auth pages, callbacks and the sign-in flow are covered in [Web app shell, routing and auth](../frontend/app-shell-and-routing.md).

## Tests

The shared test client in `apps/api/tests/conftest.py` overrides exactly two dependencies: `get_session` (to a temporary database) and `get_current_user` (to a fixed traveller, `test-user-1`, seeded as premium so book-route tests are not gated to 403). Tests that need a free caller or an anonymous caller override or clear that dependency locally; tests that need real verification use the offline JWKS fixture described above. See [Backend test strategy](../testing/backend-test-strategy.md).
