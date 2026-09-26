---
slug: llm-call-timeout
status: shipped
owner: Minh Tran
created: 2026-09-26
---

# LLM call timeout: bound a stalled provider call at a configurable 120s

## 1. Motivation

Every chat model is built in `_build_chat_model` (`apps/api/app/clients/llm.py:28-60`). No
`timeout` is passed there, so each call falls back to the SDK default of
`httpx.Timeout(600, connect=5)` (openai `_constants.py:7`, anthropic `_constants.py:7`). A stalled
provider connection can therefore hold a chat turn for up to 10 minutes before `LLM_RETRY`
(`app/agents/retry.py:45-55`, which already treats timeouts as transient) gets a chance to retry
it.

On the dev DB (777 LLM steps), the slowest calls observed are: gpt-5 with p99 27.6s and max
31.3s, and gpt-5.4-mini with max 6.8s. A 120s bound is about 4x the slowest real call, and it
turns a hang into a retry. This implements item 3 of the LLM-gateway evaluation backlog
(PR #233, `specs/llm-gateway-eval/research-brief.md`).

## 2. Non-goals

- Per-agent timeouts in `agent_config`. That needs a schema change and is deferred until one
  global value proves wrong.
- Changing retry policy, SDK `max_retries`, or the research-run 600s budget.
- Timeouts for non-LLM HTTP clients (weather, routing and web search already have their own).

## Global Constraints

- One setting, `llm_timeout_seconds: float = Field(default=120.0, gt=0)` in
  `app/core/config.py`, placed next to the other LLM settings and read via `get_settings()`.
- Pass it as `timeout=` through `init_chat_model`, which is the kwarg all three SDKs in use
  accept: langchain-openai 1.6.2, langchain-anthropic 1.7.2 and langchain-google-genai 4.4.0.
  Use `kwargs.setdefault("timeout", …)` so an explicit caller value still wins, mirroring the
  existing `max_retries` line.
- Keep comments minimal, with a one-line rationale at most, and match the surrounding style.
- Tests follow `tests/clients/test_llm_max_retries.py`: monkeypatch `init_chat_model` and
  assert on the captured kwargs. Never pass `OPENAI_API_KEY=` as empty.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Every model built by `_build_chat_model` gets `timeout=120.0` by default, and the value follows `llm_timeout_seconds` when that is overridden. | `cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_timeout.py -q` | exit 0 |
| SC-2 | A non-positive `llm_timeout_seconds` is rejected at settings load. | `cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_timeout.py -q -k invalid` | exit 0 |
| SC-3 | The existing LLM client tests still pass (max_retries, stream_usage, DB config). | `cd apps/api && ../../.venv/bin/python -m pytest tests/clients -q` | exit 0 |
| SC-4 | Lint is clean. | `cd apps/api && ruff check app scripts` | exit 0 |

## 4. Tasks

### Task 1.1 — Configurable LLM request timeout (wave 1)

- **Files:** apps/api/app/core/config.py, apps/api/app/clients/llm.py, apps/api/tests/clients/test_llm_timeout.py, apps/api/.env.example
- **Action:** Add `llm_timeout_seconds` to `Settings`, next to `llm_model` and
  `fast_llm_model`, with a one-line comment: bounds a stalled provider call, and the SDK
  default is 600s. In `_build_chat_model`, add `kwargs.setdefault("timeout", s.llm_timeout_seconds)`
  next to the `max_retries` default. Document `LLM_TIMEOUT_SECONDS=120` in `apps/api/.env.example`,
  in the LLM block, but only if that file lists the LLM settings. Create
  `tests/clients/test_llm_timeout.py` with these tests:
  (a) the default is 120.0 for the openai profile;
  (b) an override via monkeypatched settings is honoured;
  (c) an explicit `timeout=` kwarg from the caller wins;
  (d) the anthropic and google_genai profiles also receive `timeout`;
  (e) `Settings(llm_timeout_seconds=0)` raises a ValidationError. Name this test with the word
  `invalid` so the SC-2 filter selects it.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/clients -q`
- **Done:** The new tests and every existing `tests/clients` test pass, and ruff is clean.
- **Criteria:** SC-1, SC-2, SC-3, SC-4
- **Interfaces:** Consumes: the existing Settings and _build_chat_model. Produces: `app/core/config.py::llm_timeout_seconds`, `tests/clients/test_llm_timeout.py`.

## 5. Risks

- **Too-short timeout on a long reasoning call.** Streaming read timeouts apply to the gap
  between chunks, and gpt-5 can think for a while before its first chunk. The mitigation is
  that 120s is about 4x the observed max and is env-tunable. A timeout is retried by
  `LLM_RETRY`, not surfaced as a hard failure.
- **Retry amplification.** A call that genuinely needs more than 120s would be retried, not
  completed. The mitigation is the same data: none of the observed calls come close.

## 6. Status Log

- 2026-09-26: plan written. Intake is normal / medium. Worktree is
  `../travel-pi-llm-call-timeout`, branch `feat/llm-call-timeout` from `fb824f69`. The baseline
  suite at that same commit was 3129 passed, 9 skipped (run on 2026-09-25 for llm-pricing-coverage).
- 2026-09-26: Task 1.1 is in 1e40dd84. The task review passed with fixes, and the full suite gives 3135 passed. The correctness review (6 angles, 8 locations scored) led to the fixes in 85c34bbc: a research-path run-budget timeout, accurate comments, and a pinned SC-2 test.
- 2026-09-26: re-review of 85c34bbc found no new bug. Intent review raised E001, and the owner chose A. The full suite gives 3137 passed, 9 skipped. The receipt pins 85c34bbc. Ready for PR.
