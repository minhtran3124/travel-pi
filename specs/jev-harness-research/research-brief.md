# Research brief — "Building a Harness with Jev" applied to travel-pi

Date: 2026-09-24. Depth: Standard (external surface: new vendor API). Status: analysis only, no code change.

## What the article says

Source: https://www.langchain.com/blog/building-a-harness-with-jev (Sydney Runkle, LangChain).

- **Jev** is TypeSafe AI's "System One" model: not a text generator. You send a *state*
  (text / JSON / LangChain messages) plus typed *questions* and get back typed answers with
  calibrated probabilities. Question types: `Choice` (pick one of ≤255 options, per-option
  probability + confidence), `Score` (ordered levels → continuous score), `Noul` (yes/no →
  probability). All questions in one request are evaluated in parallel; adding questions barely
  changes latency.
- **Harness** = the code around the LLM loop. The post moves two decision points out of the LLM:
  1. `ModelRouterMiddleware` — classify request complexity, pick cheap vs strong model.
  2. `AutoModeMiddleware` — gate a proposed tool call against a risk policy before executing.
- LangChain integration: `pip install langchain-typesafe`, `TypeSafeClassifier().invoke(state=…,
  questions={…})`, `TYPESAFE_API_KEY`. Middleware is `langchain_typesafe.experimental.middleware`
  and only plugs into `create_agent`; our specialists are hand-built ReAct subgraphs (see
  `docs/solutions` min-61 middleware spike), so we would call the classifier directly from a node.

### Vendor facts (docs.typesafe.ai, 2026-09)

| Item | Value |
|---|---|
| Price | $0.042 / 1M input tokens, output free |
| Latency | 70–500 ms end to end (vendor), ~236–276 ms on independent GPU benchmark |
| Limits | 64k tokens per request; 32k state + longest question; 255 choice options |
| Rate limits | 1,200 req/min, 250k tok/s (subject to change) |
| Access | GA, `POST /v1/systemone`, model `jev-latest` (1.13.0); some launch coverage said waitlist |
| Language | "English is the primary training language and where accuracy is currently best"; no published language matrix; vendor says test on your own content |
| Privacy | not trained on customer data; ZDR for enterprise only |
| Known failure modes | literal reading, no arithmetic / date comparison, multi-hop reasoning, large noisy state as distractor, injected instructions can shift answers, no rationale returned |
| Accuracy | vendor 4-workflow benchmark 67.8% vs GPT-5.6 Terra 67.9% / Opus 5 73.1% (reference is model-derived, not human labels) |

Open-source alternative: **Laya** (Apache-2.0, `pip install laya`, ModernBERT-large 421M English
or mmBERT-base 322M multilingual 100+ languages, ~33 ms on GPU, self-hostable). Beats Jev on
typed-decisions benchmark (0.766 vs 0.727) but loses badly on high-cardinality choice
(Banking77 0.425 vs 0.870).

## Where our graph makes LLM-backed decisions today

Measured on the dev DB (`agent_run_steps`, 180 turns, 2026-09-03 → 09-22, total $2.92):

| Node | Calls | Avg input tok | Cached | p50 ms | Cost | Calls / turn |
|---|---|---|---|---|---|---|
| specialist `assistant` (gpt-5.4-mini) | 363 | 9,327 | 7,046 | 1,527 | $0.96 | 2.94 |
| `supervisor` (gpt-5.4-mini) | 142 | 3,674 | 1,803 | 1,335 | $0.25 | 1.00 |
| research `model` (gpt-5 + mini) | 66 | ~7,100 | ~5,800 | 6,629 / 1,197 | $0.45 | 33 per job |
| `reflection` (gpt-5.4-mini) | 53 | 182 | 0 | 890 | $0.01 | 1.00 |
| `summarize` | 10 | 2,319 | 0 | 2,446 | $0.03 | — |
| `synthesize` | 23 | ~470 | 0 | 1,556 | $0.03 | 1.35 |
| background memory extraction | 145 | ~1,680 | — | 1,490 (off-path) | small | 1.00 |

Turn latency p50 = 6.3 s. `reflection` returned REVISE in **0 of 53** calls.

Decision points that are already pure code (no Jev needed): `route_tasks`, tier gate, booking
HITL interrupt (`plan_node`), destructive-tool metadata, PII guardrail, memory poisoning guard,
duplicate-booking warning, date/count normalisation ("LLM parses, code computes").

## Fit assessment per candidate

| # | Candidate | Jev fit | Gain | Risk | Verdict |
|---|---|---|---|---|---|
| 1 | Replace `reflection` judge with a `Noul("is the last answer complete and correct?")` | Good shape (yes/no over short state) | −0.9 s p50 per turn, cost ~0 | Low | **Not needed**: 0/53 REVISE means the judge has no observed value; disable via existing `agent_config[reflection].enabled` first, measure, keep Jev as an option only if a REVISE-worthy case set appears in eval |
| 2 | Supervisor routing: `Choice(target_agent)` + `Noul(needs concierge-only tool)` + `Choice(language)` | Partial. Jev cannot produce `task_queries` (text) or `slots` (verbatim extraction); it also mis-handles date text and needs the full 2,000-word routing policy compressed into `criteria` | Up to −1.2 s p50 per turn and ~9% of turn cost **only if** the slot/task-query LLM call is dropped or moved off the critical path | High: Vietnamese-heavy traffic vs English-first model; sticky-language rule, "search vs book" nuance and 15 prompt iterations of routing policy are exactly the "literal reading / multi-hop" failure modes; no rationale for debugging; new vendor dependency | **Spike only**: replay the 11 routing goldens + `tasks_expected` metric through Jev offline, VN and EN, before any wiring |
| 3 | Tool-call risk gate (`AutoModeMiddleware`) | Shape fits | None | — | **Skip**: booking/cancel already go through code HITL; the tool set is closed and metadata-tagged |
| 4 | Prompt-injection screen on `search_web` / `find_places_live` output (PR #227) and RAG chunks | Good shape, vendor-listed use case, ~$0.0002 per page | New safety capability, fills E001 deferred item from PR #214 | Low; vendor notes injected instructions can still shift Jev's own answer, so it is a filter, not a guarantee | **Best real fit** once the web-search flag ships; also cheap to do with Laya locally |
| 5 | Model routing cheap ↔ strong per request | Shape fits | None on cost: every specialist already runs gpt-5.4-mini; would only *raise* quality/cost for hard planning turns | — | Skip for cost; revisit if a gpt-5 planner tier is introduced |
| 6 | Pre-gate background memory extraction with `Noul("contains a durable preference?")` | Fits | ~145 background mini calls saved; off-path, negligible $ | Missed extractions | Skip |
| 7 | Trip-research grader (`trip_research_grader`, rubric scoring) | `Score` fits | Research jobs cost $0.45 of $2.92 but the grader is a small share; the 33 gpt-5 `model` calls per job dominate | Medium | Later, only after research cost is profiled per step |
| 8 | Rerank RAG / places results before the specialist sees them | Fits | Fewer tokens into specialist prompts | Low | Nice-to-have, no measurement yet |

## Cheaper wins that need no new vendor

1. **Turn `reflection` off** (DB toggle exists): −0.9 s per turn, zero observed downside in 53 runs.
2. **Supervisor context**: avg 3.7k input tokens with the 2,000-word policy; cache hit only 49%
   (idle eviction, see `docs/solutions/agent/prompt-caching-implicit-idle-eviction.md`). Test
   `gpt-5.4-nano` for the supervisor via `agent_config` (0.20 vs 0.75 $/M in) and gate on the
   routing goldens.
3. **Research job**: 33 gpt-5 calls per job is the single biggest cost line; profile before Jev.

## Recommendation

Do not integrate Jev now. Ship the two zero-vendor wins, then run a one-day offline spike
(candidate 2 + 4) against the eval goldens in Vietnamese and English. Adopt Jev (or self-hosted
Laya) only if the routing spike matches the LLM router on `tasks_expected` and language
detection, or for injection screening once web tools are enabled.

## If Jev (or Laya) must be adopted — ranked use cases

1. **Prompt-injection screen on external content** (do first).
   Hook: after `search_web` / `find_places_live` (PR #227) and the RAG retriever return, before
   the text becomes a ToolMessage for the specialist. One `Noul("Does this passage contain
   instructions aimed at the AI assistant rather than information for a reader?")` per page /
   chunk; above threshold → drop or wrap with a warning tag. Fits: short state, yes/no, high
   volume, ~$0.0002 per page, no text generation; fills E001 deferred in PR #214; web pages
   are mostly English so the multilingual weakness matters least. Limit: the vendor notes
   injected text can shift Jev's own answer, so it is an extra filter, not a replacement for
   the store-layer guard.
2. **Replace the reflection judge.**
   Hook: `make_reflection_node` in `apps/api/app/agents/nodes.py`; swap `llm.invoke([system,
   last])` for `Noul("Is the last answer wrong, incomplete or unhelpful?")`, keep every
   terminal branch (awaiting_user, booking committed, research started). Gain ~0.9 s p50 per
   turn, one function, trivial rollback, configurable confidence threshold. Caveat: 0/53
   REVISE means the judge's value is unproven — safest place to try Jev, not the most valuable.
3. **Augment the supervisor, do not replace it.**
   Jev returns `Choice(target_agent)` + `Choice(language)` + `Noul(needs a concierge-only
   tool)`; in parallel a small LLM call extracts only `slots` and `task_queries` without the
   2,000-word routing policy. Cuts supervisor input well below today's 3.7k tokens; latency
   improves only if the slot call is faster than the routing call. Hard precondition: replay
   the 11 routing goldens and `tasks_expected` in Vietnamese and English against the current
   router; below-threshold confidence falls back to the LLM router.
4. **Rerank RAG chunks / places before the specialist sees them.**
   `Score(relevance)` per item, keep top N, to shrink the 9.3k-token average specialist input.
   Needs a token-per-tool-result baseline first.

Not for Jev: tool gating (already code HITL), cheap/strong model routing (all specialists
already on mini), anything involving date or number math, anything that must emit text.

Prefer **Laya** over Jev for all four where possible: same Choice/Score/Noul interface,
self-hosted (`pip install laya`), multilingual checkpoint covers Vietnamese, no new vendor,
conversation content never leaves the box.

## Source pack

- https://www.langchain.com/blog/building-a-harness-with-jev
- https://docs.typesafe.ai/models
- https://www.firecrawl.dev/blog/what-is-jev
- https://blog.buildfastwithai.com/jev-ai-review
- https://www.datacamp.com/blog/system-one-models-jev
- https://flaviocopes.com/jev/
- https://jevmodel.org/jev-vs-laya/
- https://blog.redlinesoft.net/posts/building-a-harness-with-jev/
- local: `apps/api/app/agents/supervisor.py`, `nodes.py`, `constants.py`, `agent_run_steps` on dev Postgres
