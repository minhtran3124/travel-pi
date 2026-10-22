# memory-poisoning-hardening — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-15
- trigger: hard-gate
- question: Scope of the "wrap untrusted content" bullet — memory only, or memory + RAG + tool output?
- context: blocks brainstorming/design; wrapping tool output touches every specialist's ToolMessage path (much wider blast radius than memory).
- options:
  - A) Memory only (instructions + preferences + episodes blocks in system prompt) — narrow, closes the persistent vector; RAG/tool wrapping → follow-up spec.
  - B) Memory + RAG docs + tool output — full review bullet; larger diff, more eval risk.
- default_if_no_response: BLOCK
- decision: A) Memory only — RAG/tool-output wrapping deferred to a follow-up spec
- decided_by: Minh Tran
- decided_at: 2026-09-15

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-15
- trigger: ambiguous-direction
- question: Policy for rejecting meta-instruction text in stored instructions.
- context: a regex blocklist is bypassable and may drop legitimate standing instructions ("always reply in Vietnamese"); an LLM-classifier adds cost/latency per extraction.
- options:
  - A) Key allowlist + length cap + deterministic pattern blocklist (reject + log), extractor prompt tightened to only store travel preferences.
  - B) A) plus LLM judge on candidate instructions before upsert.
  - C) Key allowlist + length cap only; rely on delimiter wrapping, no content filter.
- default_if_no_response: BLOCK
- decision: A) Key allowlist + length cap + deterministic pattern blocklist (reject + log) + tightened extractor prompt; no LLM judge
- decided_by: Minh Tran
- decided_at: 2026-09-15
