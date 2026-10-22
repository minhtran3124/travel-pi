# prompt-caching-system-prefix — Research Brief

**Depth: Deep** (intake lane `high-risk` → Deep per `rules/research-depth.md`). Deep signal: a
provider-SDK request parameter in the shared LLM client (`app/clients/llm.py`), read by every graph
node.

**External surface: yes.** The change relies on a version-specific provider API
(`prompt_cache_retention`, OpenAI Chat Completions) through pinned SDKs.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | reorder the existing prompt assembly (no new abstraction) + one settings-gated kwarg in the existing OpenAI branch + two small operator scripts |
| **Why lightest** | every building block exists: `ground_current_date`, `system_with_summary`, the `profile.sdk == "openai"` branch, `agent_run_steps.cached_tokens`, `scripts/` + `tests/scripts/` conventions |
| **Confidence** | 85% on D1/D3/D4 (deterministic, unit-testable); 60% that D2 changes the measured number (depends on whether `24h` retains on a `-mini` model — the delayed probe settles it before wave 3) |
| **Next step** | `writing-plans` → 3 waves + record (see `PLAN.md`) |

## Repo Snapshot

| Field | Detected |
|---|---|
| Prompt assembly | `app/agents/state.py` — `system_with_summary` (:120), `with_reply_language` (:198), `ground_current_date` (:231, **prepends**, docstring says appends) |
| Call sites | `app/agents/supervisor.py:254`, `app/agents/subagents/_base.py:251` (wraps `ground_current_date` innermost) |
| LLM client | `app/clients/llm.py` `_build_chat_model` — `init_chat_model`, `if profile.sdk == "openai": kwargs["stream_usage"] = True` (the only SDK-specific branch) |
| Provider profiles | `app/core/llm_providers.py` — `openai` (no base_url), `clinepass` (sdk openai + gateway base_url) |
| Usage plumbing | `app/agents/metrics.py:223` reads `input_token_details.cache_read` → `agent_run_steps.cached_tokens`; `pricing.py:104-107` prices `cached_input` |
| Pinned SDKs | openai 2.44.0 (`prompt_cache_retention: Literal["in_memory","24h"]` in `completion_create_params.py:192`), langchain-openai 0.3.34 (`model_kwargs` passthrough, `base.py:449`), langchain-core 1.4.8 |
| Tests | `tests/agents/test_state.py` (date-grounding + capture pattern), `tests/clients/test_llm.py` (profile/base_url tests), `tests/scripts/test_set_tier.py` (script + temp SQLite pattern) |

## Findings

1. **Caching already at 71.9%** on dev traffic; supervisor 49.4%. Misses correlate with idle gap
   (>60 min → 0/17). Query set in `SUMMARY.md` §Verify. This overturns the review's "chưa bật".
2. **Date note is identical within a day/zone**, so the prepend costs only day-rollover + per-zone
   fragmentation (2/30 misses observed at 23:58–00:01Z).
3. **`prompt_cache_retention` is live on the pinned SDK and accepted by `gpt-5.4-mini`** (probe
   2026-09-10: bogus value → 400 naming the param; `24h`/`in_memory` → 200, cache_read 2,816/3,236).
4. **OpenAI docs** (fetched 2026-09-10): min cacheable prefix 1,024 tokens; `cached_tokens` rounded
   down to 128; `in_memory` "5 to 10 minutes of inactivity, up to one hour"; `24h` "around 30
   minutes … up to 24 hours"; extended-retention model list names `gpt-5`, `gpt-5.4`… but **no `-mini`
   model**; "place timestamps … at the end"; non-ZDR orgs default to `24h` on supported models.
5. **LangChain blog (Deep Agents fork/isolated)**: the value of forking is prompt-cache reuse; the
   project's specialists already receive the full history (fork-shaped), so a warm prefix is what makes
   that cheap. Context only — no framework adoption.

## Source Pack

- OpenAI — Prompt caching guide: https://developers.openai.com/api/docs/guides/prompt-caching (fetched 2026-09-10)
- openai-python 2.44.0 — `openai/types/chat/completion_create_params.py:192-205` (`prompt_cache_retention`)
- langchain-openai 0.3.34 — `chat_models/base.py:449` (`model_kwargs`), `:2777-2794` (`prompt_cache_key` docs)
- LangChain blog — Organizing Context in a Multi-Agent Harness: https://www.langchain.com/blog/organizing-context-in-a-multi-agent-harness
- Local measurement — dev Postgres `agent_runs` / `agent_run_steps` (queries recorded in `SUMMARY.md`)
- Local probe — scratchpad `retention_probe.py` (to be promoted to `scripts/probe_cache_retention.py`, D4)
