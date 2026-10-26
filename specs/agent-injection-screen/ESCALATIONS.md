# agent-injection-screen — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-09-24
- trigger: low-confidence
- question: Which decision model runs the injection screen — hosted Jev (TypeSafe API) or self-hosted Laya?
- context: Blocks brainstorming/design; decides the dependency, the secret, the Docker image footprint and whether fetched web text leaves the box.
- options:
  - A) Jev via `langchain-typesafe` + `TYPESAFE_API_KEY` — ~100–500 ms per call, $0.042/M input, no local compute; new paid vendor, English-first (web pages mostly English so acceptable), fetched content is sent to TypeSafe, ZDR only on enterprise.
  - B) Laya (`pip install laya`, Apache-2.0, multilingual mmBERT-base 322M) — self-hosted in the api container (python:3.12-slim, CPU inference, adds torch + weights to the image, tens of ms on GPU / likely 100s of ms on CPU), no vendor, no data egress; less mature, own ops burden.
  - C) Both behind one interface (`InjectionScreen` protocol) with a config switch — most flexible, but doubles the external surface and the eval matrix.
- default_if_no_response: BLOCK
- decision: A (Jev hosted; transport is plain httpx per design.md §2 — `langchain-typesafe` 0.0.1a3 is alpha and not used)
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-24

## E002

- raised_by: orchestrator
- date: 2026-09-24
- trigger: ambiguous-direction
- question: What happens to a flagged page/chunk — drop it, or keep it wrapped with a warning attribute?
- context: Decides tool-output shape and how the concierge prompt must treat flagged items.
- options:
  - A) Drop above threshold, log a metric; below threshold pass through unchanged. Simplest, may lose a useful page on a false positive.
  - B) Keep every item, add `flagged="true" p="0.87"` on the `<web_result>` block and a prompt rule to ignore instructions inside flagged items. Never loses content; relies on the model honouring the attribute.
  - C) Two thresholds: wrap between t1 and t2, drop above t2. Most control, most tuning.
- default_if_no_response: BLOCK
- decision: B (keep every item, wrap with flagged attribute + prompt rule)
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-24
