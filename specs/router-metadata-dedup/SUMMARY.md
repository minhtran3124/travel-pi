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

(To be filled at completion.) Planned: add `app/routers/tags.py` (`Tags` enum, values =
current tag strings) and replace `tags=[...]` in 16 group routers (P2, byte-identical
OpenAPI); then lift each router's all-routes-common error codes into the `APIRouter(...)`
constructor, leaving only route-specific extras on decorators (P1, superset-or-equal).

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

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full suite (P2) | `make test` | 0 | 682 passed (suite grew past plan's 663) |
| OpenAPI identical (P2) | `app.openapi()` tags+responses diff vs baseline | 0 | tag set + all 55 ops byte-identical; 0 changed ops |
| Lint clean (P2) | `ruff check app/routers/` | 0 | imports hoisted by isort; no F821 |
| Full suite (P1) | `make test` | _pending_ | — |
| Error-code superset (P1) | per-op `responses` diff vs baseline | _pending_ | each op ≥ prior set |
| Docker py3.12 parity | `make test-docker` | _pending_ | `Tags(str, Enum)` for 3.10+ compat |

### Rollback

- `git revert <sha>` (reversible; no schema change → no `travel.db` rebuild).

### Harness-Delta

- backlog — feature-intake Step-3 hard-gate list omits "public contract" while
  `rules/orchestration.md` ESCALATE list and memory `public-contract-hard-gate`
  include it. Worth reconciling so the classifier and the hook agree.
