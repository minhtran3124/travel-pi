# Summary: first-class Anthropic (Claude) provider

Epic #249; Phase 1 #250, Phase 2 #251; sub-issues #252-#258. All seven sub-PRs (#260-#266) merged into `feat/anthropic-provider`.

## What shipped

| Issue | PR | Result |
|---|---|---|
| #252 | #260 | Provider-aware `temperature` / `max_tokens` (anthropic drops temperature, default 16000); Claude 5.5 catalog and prices; per-provider default models, `llm_model` / `fast_llm_model` now `str \| None`; Anthropic block in `.env.example`. |
| #253 | #261 | `with_structured(llm, schema)` in `app/clients/llm.py` (json_schema on Anthropic, function_calling elsewhere); architecture guard against direct `.with_structured_output(`. |
| #254 | #262 | Assistant text read via `.text`; `_chunk_text` in the SSE mapper so thinking / block lists never reach `token` events. |
| #255 | #263 | Anthropic usage maps to a priced `agent_run`; `--provider {openai,anthropic}` for the eval CLI and `eval.research_smoke`; keyed runs (below). |
| #256 | #264 | `effort` column + migration, validated in the service, applied to Claude and OpenAI reasoning models; provider-aware dashboard form; temperature rejected where unsupported. |
| #257 | #266 | `strip_foreign_reasoning` drops foreign thinking / reasoning blocks before a model call; state is not mutated. |
| #258 | #265 | Embeddings fallback warning, `claude` profile base URL fixed, `eval/baselines/main-anthropic.json` and provider-based baseline selection. |

## Keyed smoke results (recorded from #263 and #266; not re-run for this PR)

Models: `claude-sonnet-5-5` (main), `claude-haiku-5-5` (fast).

- `python -m eval --suite smoke --provider anthropic`: 19/20 pass, no 400s. Only failure `errors-happy-en-01` (reply_language expected `en`, detected `vi`), an answer-quality issue, not an API error. Run with `OPENAI_API_KEY` empty.
- 6-turn stream on one thread (`SUMMARIZE_THRESHOLD=8`): all `completed`, no error events, no block garbage in `token` events, summarizer ran without tool_use/tool_result or thinking errors, every `agent_run` row costed ($0.07 to $0.28 per turn).
- `python -m eval.research_smoke --provider anthropic`: PASS, 10 dossier files, valid proposal, $0.74 (limit $1.00).
- Cross-provider (#257): Claude turn with a tool call, then OpenAI-shaped history replayed to Claude, no 400.

Four further Phase 1 bugs found by the keyed runs were fixed in #263 (schema too complex for 14 optional properties, assistant prefill in the reflection judge, non-consecutive system messages, summarizer reading `.content`).

## Verification (this branch)

See the PR description for the `make test` and `make lint` output.

## Known gaps

- The OpenAI half of the mixed-provider 3-turn run (#257) could not run: the OpenAI account had no credit (429). The filter is defensive; no 400 was ever reproduced.
- Claude prices were taken from the issue and not re-fetched from the pricing page (#252).
- No per-provider baseline delta: `main-anthropic.json` needs the paid judged `make eval-check`, which was out of scope.
- Chat turns show `cached_tokens` = 0 on large inputs, so prompt caching is not yet effective; the summarizer's merged summary hits its 1800-char cap on every merge.
- `ruff format --check` flags two files untouched here (`repositories/hotel_ref.py`, `place_ref.py`).
- Per-request provider selection from the web UI, Bedrock/Vertex and `cache_creation` pricing remain non-goals.
