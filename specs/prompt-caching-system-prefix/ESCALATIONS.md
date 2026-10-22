# prompt-caching-system-prefix — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-08
- trigger: hard-gate
- question: Which provider is prompt caching being optimised for — the OpenAI path that serves traffic today, or the Anthropic path the review recommends benchmarking?
- context: Blocks the design. `external-provider` is a block-mode hard gate, so scope must be narrowed by a human before any code. Default agent models are `gpt-5`/`gpt-5-mini` (OpenAI, automatic caching); `cache_control` is Anthropic-only and would measure ~0 on current traffic.
- options:
  - A) **Provider-agnostic prefix stabilisation only** — move the `ground_current_date` note from prefix to suffix so the stable ~3.3k prompt sits at token 0; measure OpenAI `cached_tokens` before/after from the existing `agent_run` metrics. Small, reversible, benefits today's traffic. No Anthropic work.
  - B) **A + Anthropic `cache_control`** — also emit `cache_control` breakpoints on the system block when the resolved profile's SDK is `anthropic`. Larger blast radius (provider-specific shaping inside a deliberately provider-agnostic layer, `app/clients/llm.py`), plus `pricing.py` must start pricing `cache_creation` at 1.25x input. Only pays off once an Anthropic model is actually routed.
  - C) **A now, B gated on the model benchmark** — ship A, and defer B until the review's "benchmark reasoning tier on Sonnet 5" item decides whether Anthropic gets real traffic.
- default_if_no_response: BLOCK
- decision: **A** — provider-agnostic prefix stabilisation only. Move the `ground_current_date` note from prefix to suffix; measure OpenAI `cached_tokens` before/after from `agent_run`. No Anthropic `cache_control`, no change to `app/clients/llm.py` or `pricing.py`. B stays out of scope (may be re-raised as its own spec once an Anthropic model carries real traffic).
- decided_by: Minh Tran (user, via AskUserQuestion in session 2026-09-10)
- decided_at: 2026-09-10

## E002

- raised_by: orchestrator (feature-intake, re-run 2026-09-10 after measuring live cache hit rate)
- date: 2026-09-10
- trigger: hard-gate
- question: Dev-DB measurement shows caching is ALREADY at 71.9% (specialists 75.8%, supervisor 49.4%) and that 28/30 supervisor misses follow an idle gap (>60 min → 0/17 hits; <5 min → 94/98), i.e. in-memory eviction, not the date prefix. Option A alone fixes ~2/30 misses. May scope grow to a one-call probe of OpenAI `prompt_cache_retention="24h"` on the default model and, if accepted, a kwarg in the existing `if profile.sdk == "openai"` branch of `_build_chat_model` (`app/clients/llm.py`)?
- context: Blocks the design. `external-provider` is a block-mode hard gate and `app/clients/llm.py` is the deliberately provider-agnostic layer E001 kept out of scope.
- options:
  - A) Keep E001/A only — prefix move + hit-rate report script; expected gain small, mainly standards-compliance and tooling.
  - B) A + retention probe — one paid call with `prompt_cache_retention="24h"` on `gpt-5.4-mini`; if the API accepts it, wire the kwarg (openai SDK branch only, `model_kwargs`), guarded by a settings flag; if rejected, record and stop at A.
  - C) Close the spec with the finding only (no code).
- default_if_no_response: BLOCK
- decision: **B** — A + retention probe; wiring is conditional on the probe result and stays inside the existing openai-only branch.
- decided_by: Minh Tran (user, via AskUserQuestion in session 2026-09-10)
- decided_at: 2026-09-10

## E003

- raised_by: orchestrator (plan review, after the 21-min A/B tied)
- date: 2026-09-10
- trigger: hard-gate
- question: E002/B authorised wiring `prompt_cache_retention` into `app/clients/llm.py` on the strength of a probe that has since come back inconclusive (both arms HIT at 21 min idle). Should the wiring stay in wave 1, or become a conditional task gated on the >60-min A/B verdict?
- context: Blocks plan structure. Wiring first would put a provider-SDK parameter in the shared client with zero measured benefit; the flag would ship dark anyway on a TIE.
- options:
  - A) Keep the wiring in wave 1 behind the settings flag, decide the default later.
  - B) **Make it a conditional wave** — waves 1–3 ship the provider-agnostic reorder, the hit-rate report and the A/B probe; the wiring fires only on verdict `RETENTION-WINS`, and is recorded as `skipped — not triggered` otherwise.
- default_if_no_response: BLOCK
- decision: **B** — conditional wave. Pre-authorised in both directions, so no further human gate is needed when the probe reports: `RETENTION-WINS` → Task 4.1 runs; any other verdict (`TIE`, `BOTH-MISS`, or `CONTROL-ONLY` — the fourth cell of the two-arm table, found during Task 2.2) → Task 4.1 is skipped with the verdict recorded, and D1/D3/D4 ship alone.
- decided_by: Minh Tran (user, 2026-09-10 — "ok, dong y vs ban" accepting the closing recommendation)
- decided_at: 2026-09-10

### E003 outcome (recorded 2026-09-10 06:25Z)

The pre-registered rule fired. Early discriminating trial, true idle gap about 87 minutes: `24h`
MISS, `in_memory` MISS → verdict `BOTH-MISS`, which is not `RETENTION-WINS`, so Task 4.1 is skipped.
No new decision was needed or taken. Task 3.1 re-runs the trial with the production probe script to
close SC-7 formally.

Production trial (SC-7), 2026-09-10 08:43:01Z: `scripts/probe_cache_retention.py`, true idle gap
86.8 min, `24h` MISS and `in_memory` MISS → `BOTH-MISS`, exit 0. Second independent trial, same
verdict. Task 4.1 recorded `skipped — not triggered`.
