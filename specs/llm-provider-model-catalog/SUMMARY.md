<!--
  Canonical SUMMARY.md shape. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
-->

# llm-provider-model-catalog — Summary

Lane: tiny
Confidence: high
Reason: Zero flags beyond a mild public-contract touch (the dashboard router
(`app/routers/dashboard.py`) surfaces `LLM_PROVIDERS` model lists for the config UI's
dropdowns) — but this only changes *values already returned* by an existing endpoint, adds
no new route/contract shape, and the catalog is explicitly documented as "a reference list
for UIs/dropdowns, not an allowlist" (existing `agent_config` DB rows referencing old model
strings keep working unchanged). No hard gate. Confidence high: every model ID change is
directly confirmed against OpenAI's and Google's own current docs (not inferred), and no
existing test asserts specific model strings (only structural invariants).
Flags: none (public-contract touch judged too mild to count — data values only, no schema/route change)
Affects: `apps/api/app/core/llm_providers.py` (`openai`/`clinepass` profile `models` lists)
Input-type: maintenance

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane.

### Intent

> "review LLM_PROVIDERS in apps/api/app/core/llm_providers.py, research online to check and
> make sure model exists and correct with provider"

## What changed

Web-research-verified every model ID in `LLM_PROVIDERS` against OpenAI's and Google's own
current model docs (Anthropic's IDs were verified against this session's own system-prompt
model list — an authoritative source needing no external lookup).

- **`openai` profile — all 5 listed models were deprecated.** `gpt-5`, `gpt-5.1`, `gpt-5-pro`,
  `gpt-5-mini`, `gpt-5-nano` are retired; OpenAI's current active generation is GPT-5.4/5.5.
  Replaced with `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.4`, `gpt-5.4-pro`, `gpt-5.4-mini`,
  `gpt-5.4-nano` (confirmed live via `developers.openai.com/api/docs/models/all`).
- **`clinepass` profile's `openai/*` entries — same deprecated generation.** Replaced
  `openai/gpt-5`, `openai/gpt-5-mini`, `openai/gpt-5-nano` with `openai/gpt-5.5`,
  `openai/gpt-5.4-mini`, `openai/gpt-5.4-nano` (kept the OpenRouter-style `provider/model`
  prefix this gateway requires, per the profile's own base_url/gateway contract). Its
  `anthropic/claude-sonnet-5` entry was already correct — untouched.
- **`anthropic` / `claude` profiles — no change needed.** `claude-opus-4-8`, `claude-sonnet-5`,
  `claude-haiku-4-5-20251001` match the current, authoritative Claude model IDs exactly.
- **`google_genai` profile — no change needed.** `gemini-2.5-pro` / `gemini-2.5-flash`
  confirmed still current and not deprecated via `ai.google.dev/gemini-api/docs/models`
  (though Gemini 3.x is now also GA — noted as an optional future addition, not added here
  since it wasn't broken and wasn't asked for).

### Rationale

Fix the stale reference data directly rather than leaving it for the next person to discover
via a 400/403 at runtime — this is exactly the class of bug found live in this same session
(the `agent_config` DB rows and `Settings` defaults elsewhere in the codebase pointed at
similarly-deprecated model names). Did not touch `app/core/config.py`'s `llm_model`/
`fast_llm_model` defaults (`"gpt-5"`/`"gpt-5-mini"`, also stale) or `scripts/seed_agent_config.py`'s
`DEFAULT_MODEL` — those are a related but distinct fix outside what was asked (`llm_providers.py`
specifically); flagging separately rather than silently expanding scope.

### Alternatives considered

- Also add the newer Gemini 3.x models to `google_genai` — deferred: not broken, not asked for,
  would be scope creep on a "verify what's here" request.
- Bump `app/core/config.py`'s global `llm_model`/`fast_llm_model` defaults too (same stale
  `"gpt-5"`/`"gpt-5-mini"` problem) — deferred as a separate, explicitly-flagged follow-up
  rather than silently widening this task's file scope.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Catalog invariant tests | `pytest tests/core/test_llm_providers.py -q` | 0 | 21 passed — no test hardcodes specific model strings, only structural shape |
| Agent-config + dashboard tests | `pytest tests/api/agent_config/ -q` | 0 | Included in the 37-passed run below |
| Broader consumer suite | `pytest tests/core/test_llm_providers.py tests/api/agent_config/ -q` | 0 | 37 passed |
| Lint | `ruff check app/core/llm_providers.py` | 0 | All checks passed |

### Rollback

- `git revert <sha>` — pure reference-data change, no schema/data migration, fully reversible.

### Harness-Delta

- none
