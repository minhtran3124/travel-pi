# places-nl-search — Escalations

## Public-contract boundary (new endpoint)

- **Date:** 2026-06-17
- **Boundary:** `POST /places/search/nl` is a new public API contract. `hooks/risk-corroboration.sh`
  treats new public contracts as a gate that would block a `normal`-lane commit.
- **Decision:** Authorized as an **additive, non-breaking** new endpoint (does not change
  existing `/places/search`). Lane stays `normal`. The user requested this feature via
  AGENT_IMPROVEMENTS.md #10 and invoked intake on it — intent is unambiguous (confidence: high).
- **Commit procedure:** demote just this category at commit —
  `RISK_WARN_CATEGORIES="public-contract" git commit …` — the hook's sanctioned warn-mode
  loosener (no file edit). See the `public-contract-hard-gate` project memory.
- **Status:** authorized; no further human gate. Not an intent ambiguity.
