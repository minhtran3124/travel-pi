<!--
  Canonical SUMMARY.md shape. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
-->

# router-metadata-dedup — Summary

Lane: normal
Confidence: high
Reason: 2 flags (public-contract: P1 alters generated OpenAPI error docs; existing-behavior: edits all 13 test-covered group routers). No forcing hard gate — not a new endpoint, no auth/data/migration/external-provider/validation change.
Flags: public-contracts, existing-behavior
Affects: OpenAPI schema (router `tags` + per-operation error `responses`) — public contract the FE TS client codegens against.
Input-type: change request

> `Lane` drives ceremony (proof). `Confidence` drives interruption (human gate).
> A hard gate forces high-risk. This work trips no forcing hard gate, but the
> public-contract flag means the commit may be flagged by `risk-corroboration.sh`
> — authorize then per memory `public-contract-hard-gate` if it fires.

### Intent

User invocation, verbatim:

> /feature-intake for specs/router-metadata-dedup/PLAN.md

Scope-deciding content (from the PLAN this classifies — outcome of a `/deep-research`
comparison against FastAPI `bigger-applications` docs):

> P1 — lift shared `responses=` to the `APIRouter` level. Today every route repeats
> `responses=error_responses(...)` (~50 call sites across 13 routers). Per-route
> `responses` merge with router-level ones, so error codes common to *all* routes in
> a group can be declared once.

> P2 — store tags in an `Enum`. 16 routers use plain-string tags that can drift.
> Enum values equal today's tag strings, so `GET /openapi.json` tag names are unchanged.

> Neither changes runtime behavior. P2 is engineered to leave generated OpenAPI
> byte-identical; P1 deliberately changes the OpenAPI error documentation
> (superset-or-equal per operation — never fewer error codes than before). P3
> (router-level `dependencies=`) and any by-domain restructure are non-goals.

## What changed

P2: added `app/routers/tags.py` (`Tags(str, Enum)`, values = current tag strings) and
replaced `tags=[...]` across all 16 group routers — OpenAPI byte-identical.

P1: lifted each multi-route router's all-routes-common error codes into the `APIRouter(...)`
constructor (bookings/cities/flights/hotels/trips → `422`; destinations → `404,422`;
weather → `404,422,502`), leaving only route-specific extras on each decorator. Per-op error
**code sets are unchanged** (no op lost or gained a code). One beneficial side effect: 3 trips
routes whose 422 was the stale auto-generated `HTTPValidationError` now document the real
`ErrorResponse` envelope (which is what the runtime already returns).

### Rationale

Both patterns are endorsed by primary FastAPI docs and remove ~50 repeated call sites /
drift-prone string tags. Normal lane (not high-risk) because there is no runtime,
schema, or auth change; the only contract movement is OpenAPI error *documentation*,
fenced by a superset-or-equal acceptance check and 663 passing tests.

### Alternatives considered

- P3 router-level `dependencies=` — skipped; no shared per-router concern in an
  auth-less mock.
- By-domain (`routers/services/...` → per-feature) restructure — research-refuted
  (0–3 votes); by-type layout is endorsed for small-to-mid apps.

### Deviations

- Scope (judgment, per behavior.md simplicity) — P1 lifted only **multi-route** routers where
  it removes real duplication. Single-route routers (airports, currency, tips, visa,
  air-quality, meta, health) were left unchanged: lifting there is pure indirection with no
  dedup. `places` was left unchanged because its routes share **no** common error code (empty
  intersection) — matches PLAN §4 ("unchanged if the intersection is empty").
- Side effect (beneficial, flagged) — lifting `422` to the `trips` router normalized 3 routes'
  422 OpenAPI model from the stale `HTTPValidationError` to `ErrorResponse`. Runtime behavior
  unchanged (the 422 handler in `main.py` already returns `ErrorResponse`); only the docs were
  stale. Code set per op unchanged; the 2 still-stale 422s live in the untouched `places` router.
- Rule 3 — local-only `.git/info/exclude` entry for `.claude/` to unblock `check-untracked-py.sh`,
  whose `.claude` exclusion misses root-level paths (leading-slash pattern bug). No tracked file
  or hook modified; matches the hook's clear intent. Reversible: remove the line from
  `.git/info/exclude`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full suite (P2) | `make test` | 0 | 682 passed (suite grew past plan's 663) |
| OpenAPI identical (P2) | `app.openapi()` tags+responses diff vs baseline | 0 | tag set + all 55 ops byte-identical; 0 changed ops |
| Lint clean (P2) | `ruff check app/routers/` | 0 | imports hoisted by isort; no F821 |
| Full suite (P1) | `make test` | 0 | 682 passed |
| Error-code superset (P1) | per-op error-code diff vs baseline | 0 | 0 ops lost a code; 0 ops gained a spurious code |
| 422 model normalized (P1) | per-op 422 `$ref` check | 0 | 3 trips routes: stale HTTPValidationError → ErrorResponse (matches runtime) |
| Docker py3.12 parity | `make test-docker` | 0 | 682 passed; `Tags(str, Enum)` OK on 3.12 |

### Rollback

- `git revert <sha>` (reversible; no schema change → no `travel.db` rebuild).

### Harness-Delta

- backlog — feature-intake Step-3 hard-gate list omits "public contract" while
  `rules/orchestration.md` ESCALATE list and memory `public-contract-hard-gate`
  include it. Worth reconciling so the classifier and the hook agree.
