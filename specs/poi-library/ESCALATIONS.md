# poi-library — Escalations

## Architectural fork (low confidence) + migration hard gate — resolve via brainstorming

- **Date:** 2026-06-18
- **Why escalated:**
  1. **Design fork (low confidence):** two materially different models for "reusable POI library":
     - **A — Static catalog + `saved_places` overlay:** `data/places.py` stays the read-only seed
       catalog; a new `saved_places` table holds user/agent POIs; `trip_place_link` M2M references
       either source. Keeps deterministic seed IDs and the mock ethos; adds a "source" distinction.
     - **B — Unify into one DB `places` table:** load the seed into SQLite on startup; single table
       + ID space. Simpler model, but changes the existing `/places` read path and abandons the
       "everything generated deterministically, never stored" rule (CLAUDE.md).
     These produce different schemas, endpoints, and serializers — must be chosen before planning.
  2. **Migration hard gate:** new tables + columns → `risk-corroboration.sh` will flag
     `data-loss/migration`. High-risk lane already covers this; commit-time waiver as in A0 if the
     diff is additive-only.
- **Decision needed (human):** pick Option A or B (or a variant) in `/brainstorming`. This also
  scopes how much of A1's richer fields (`favorite`, `visited`, `links`, `duration`) ship now.
- **Status:** routed to `/brainstorming` to resolve the design direction; PLAN/code blocked until
  the fork is decided and captured in `design.md`.
