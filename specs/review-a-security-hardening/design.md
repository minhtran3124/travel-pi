# review-a-security-hardening — Design

Status: approved at intake (decisions E001–E004 in ESCALATIONS.md). Source: docs/reviews/2026-09-02-deep-review.md §3.A.

## Problem

Identity is optional or absent on three write surfaces:

1. `/agent/chat|stream|conversations*` accept a client-supplied `user_id` when no JWT is present
   (`app/routers/agent.py:88-98`). Conversations, checkpoint threads, the long-term memory store
   (namespace `("users", user_id, kind)`) and the daily quota all key on that id, so any caller can
   read or claim another anonymous user's history and memories, and rotate ids past the quota.
2. `bookings` and `saved_places` have no `user_id` column; their routers have no auth dependency.
   Anyone can list, read or cancel any booking by id (`app/routers/bookings.py`), and the agent
   tools that create/cancel bookings cannot stamp an owner even if they wanted to.
3. `/dashboard/*` (19 Jinja pages) can change every sub-agent's model and toggle reflection with no
   authentication (`app/routers/dashboard.py`, `dashboard_prompts.py`).

## Decisions (WHAT)

| # | Decision | Consequence |
|---|---|---|
| E001 | `/agent/*` requires a Supabase JWT. `body.user_id` / `?user_id=` are ignored. | Anonymous chat is removed. Web `ChatWidget` shows a sign-in state when logged out. `POST /agent/conversations/claim` stays so a legacy localStorage id can be claimed once. Rate-limit wiring is **not** in scope (quota already keys on the now-trusted subject). |
| E002 | `bookings.user_id` and `saved_places.user_id` are `NOT NULL` + indexed, added in one destructive Alembic revision that first deletes all rows (pattern `a4d8e2c6b013`). | Dev/prod DBs lose booking + saved-place rows on upgrade. Documented in the revision docstring; backup before upgrade. |
| E002' | Ownership semantics mirror #118: repository methods take `user_id`; a foreign id resolves to *not found* (404), never 403. | No oracle for "id exists but is not yours". |
| E003 | Dashboard guard: 404 when `is_production` and no basic credentials; HTTP Basic when `DASHBOARD_BASIC_USER`/`PASSWORD` are set (any env); open in dev without credentials. | One `Depends` on both dashboard routers; `secrets.compare_digest`. |
| E004 | `book_flight`, `book_hotel`, `cancel_flight`, `cancel_hotel` take `user_id: Annotated[str, InjectedState("user_id")]`; they drop off MCP. | FEATURES.md §8 and prompts CHANGELOG note the removal. |

## Out of scope (non-goals)

- Rate-limit wiring by IP (deferred; revisit with user-feedback-v1 wave 4).
- Server-signed anonymous session tokens.
- Linking bookings to trips (`trip_id`) — product roadmap, not security.
- Admin-JWT dashboard login.
- The reflection routing bug — separate tiny spec `fix-reflection-synthesize-goto`.

## Shape of the change (HOW, briefly)

- **Schema:** `Booking.user_id`, `SavedPlace.user_id` (`String`, `nullable=False`, `index=True`);
  revision deletes `bookings` and `saved_places` rows, adds columns + indexes.
- **Data access:** `BookingRepository.get/list_all/update_status/get_by_confirmation_code` and
  `SavedPlaceRepository.get/list/soft_delete/set_flag/find_duplicate` gain a `user_id` filter;
  `add` stamps it. Services thread `user_id`; `get_booking_service` / `get_saved_place_service`
  stay request-scoped.
- **Routers:** `bookings.py`, `places.py` (saved-place routes only), `flights.py` `POST /flights/book`,
  `hotels.py` `POST /hotels/book` add `CurrentUserDep`. Public catalog routes on `places.py`
  remain open.
- **Agent:** `routers/agent.py` swaps `OptionalUserDep` → `CurrentUserDep` on chat/stream/list/get;
  deletes `_effective_user_id`'s fallback branch. Tools inject `user_id` from state and pass it to
  `BookingService`.
- **Dashboard:** new `app/core/dashboard_auth.py` dependency + two settings; `dependencies=[...]` on
  both routers.
- **Web:** `lib/identity/provider.tsx` stops minting anonymous ids; `lib/api/client.ts` drops
  `X-User-Id`; `useAgentStream` gates on the Supabase session and keeps the one-shot legacy claim;
  `ChatWidget` renders a "Sign in to chat with Tin" state with an `auth/login` link (en + vi keys).

## Risks

- Test fan-out: 92 agent API tests, 40 booking, 12 saved-place tests assume anonymous or unscoped
  access; expect wide but mechanical churn.
- Postgres parity: partial unique indexes on `bookings` already exist; the revision must use
  `batch_alter_table` for SQLite. Run `make test-docker` before PR.
- Web e2e is already broken on protected routes (deep review §3.C.10); do not rely on it as proof.
