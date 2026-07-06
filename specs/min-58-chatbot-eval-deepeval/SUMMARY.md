# min-58-chatbot-eval-deepeval — Summary

Lane: normal
Confidence: high
Reason: 1 risk flag (external systems — adds the `deepeval` dependency + an LLM-as-judge grader that calls a provider); no hard gate — eval-only tooling, additive, reversible, does not touch auth / schema / API contract / production request path.
Flags: external-systems
Affects: apps/api/eval/ (offline eval harness — new tooling, not a public/shared contract); requirements.txt (new `deepeval` dep)
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- User's request verbatim at intake — MIN-58 ticket + the three scoping decisions
     confirmed in-conversation. The intent oracle for /intent-review reads this. -->

Ticket **MIN-58** — "Design & Implementation: Hệ thống Evaluation cho chatbot với DeepEval + G-Eval (tham khảo Rubric pattern của LangChain Deep Agents)". Verbatim scope-deciding content:

> **Mục tiêu:** Thiết kế và triển khai hệ thống evaluation cho Travel Assistant chatbot, sử dụng **DeepEval** (framework) và **G-Eval** (LLM-as-judge metric), có tham khảo pattern Rubric-based self-evaluation mà LangChain vừa giới thiệu cho Deep Agents.
>
> **Hai lớp evaluation cần xây dựng:**
> 1. **Offline evaluation (ưu tiên trước — dùng DeepEval + G-Eval):** Test suite dạng dataset các cặp (input, expected behavior/criteria), chạy qua DeepEval framework. Dùng `GEval` metric để định nghĩa custom rubric bằng ngôn ngữ tự nhiên cho từng khía cạnh: đúng ngôn ngữ trả lời, đúng intent (search vs booking), không hallucinate thông tin khách sạn/chuyến bay, format đúng. Kết hợp metric có sẵn nếu phù hợp: `AnswerRelevancyMetric`, `ToolCorrectnessMetric`, `HallucinationMetric`.
> 2. **Runtime self-evaluation (giai đoạn sau, lấy cảm hứng từ RubricMiddleware):** grader sub-agent nhẹ trong LangGraph flow — **phần mở rộng, tách sang MIN-59** (blocked by MIN-58).
>
> **Kiến trúc đề xuất:** thư mục eval chứa `datasets/` (test case theo từng sub-agent), `metrics/` (G-Eval criteria + threshold), `runners/` (script chạy DeepEval, CI-friendly). Tích hợp CI. Grader model rẻ (Haiku-class).
>
> **Các bước:** (1) Setup DeepEval + cấu hình model provider cho LLM-as-judge. (2) Dataset ~15-20 case cho bug/feature đã biết: intent booking vs search (MIN-51), ngôn ngữ side panel (MIN-57), tool args_schema (MIN-46). (3) G-Eval criteria natural-language cho từng nhóm. (4) Baseline run làm mốc. (5) CI (GitHub Actions). (6) Doc hướng dẫn thêm case/criteria. (7) [sau — MIN-59] runtime self-eval loop.

**Scoping decisions confirmed at intake (in-conversation, 2026-07-06):**

1. **Scope = Foundation-first.** This ticket delivers: setup DeepEval + config grader provider, `apps/api/eval/` structure, G-Eval custom criteria, initial datasets (~15-20 cases). **Deferred to a small follow-up:** CI wiring (step 5) + internal how-to doc (step 6) — done after the harness quality is verified, so we don't lock a not-yet-trusted harness into CI. (NOTE: an earlier draft listed the **baseline run** as in-scope here; that is **superseded by decision 5 below** — the baseline run is deferred, this ticket ships a *runnable* harness only.)
2. **Legacy routing harness kept + layered.** The existing `apps/api/eval/run_eval.py` (no-network FakeLLM routing-accuracy smoke) stays as the cheap CI smoke; DeepEval / G-Eval is a **separate LLM-judge quality layer** (runs with a provider key, gated). The two are complementary, not a migration.
3. **Placement = `apps/api/eval/`.** Extend the existing scaffold (per CLAUDE.md: BE work lives in `apps/api/`), not a root-level `eval/` as the ticket text proposed.

**Refinements confirmed after xia2 research (2026-07-06):**

4. **Grader = OpenAI** (e.g. `gpt-4o-mini`), passed as a `model=` **string** to DeepEval metrics — DeepEval supports OpenAI natively, so **no custom `DeepEvalBaseLLM` adapter is built now** (deferred; only needed to switch to a provider DeepEval lacks). Runner must skip gracefully when no *real* OpenAI key is present (`apps/api/.env` ships `OPENAI_API_KEY=test`, a fake) so the no-network CI path stays green.
5. **Baseline run deferred.** This ticket delivers a **runnable harness + datasets + metrics only**; the actual baseline execution against a real provider is a follow-up (avoids API spend now). Net remaining scope: deepeval dep (post-resolution-spike) + G-Eval/ToolCorrectness metrics + graph→LLMTestCase harness + ~15-20 datasets + keyed runner; routing smoke kept.

## What changed

<!-- Filled at DONE. -->

Pending implementation. Product delta (planned): a DeepEval + G-Eval offline evaluation layer added under `apps/api/eval/` — natural-language G-Eval rubrics per quality dimension (response language, search-vs-booking intent, hotel/flight non-hallucination, format), an initial dataset of ~15-20 known-bug/feature cases, a CI-friendly runner, and a recorded baseline. Existing no-network routing smoke preserved. CI wiring + docs follow separately.

### Rationale

Foundation-first + keep-and-layer + `apps/api/eval/` were chosen to (a) verify the DeepEval harness produces trustworthy scores before gating CI on it, (b) preserve the free no-network smoke that already guards routing regressions, and (c) stay on the monorepo convention (BE in `apps/api/`). These were confirmed with the user at intake rather than guessed.

### Alternatives considered

- **Full Phase 1 in one go (incl. CI + docs)** — rejected: wiring an unproven LLM-judge harness into CI risks flaky/costly gates before its scores are trusted.
- **Migrate routing eval fully into DeepEval** — rejected: loses the existing free no-network smoke that runs on every CI pass without a provider key.
- **Root-level `eval/`** (ticket text) — rejected: violates the `apps/api/` monorepo convention and complicates `app.agents.*` imports.

### Deviations

- none

### Verify

<!-- Filled at DONE — one row per check actually run. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| _pending_ | _pending_ | | |

### Rollback

- `git revert <sha>` (additive tooling under `apps/api/eval/` + `deepeval` in requirements.txt; no schema/migration)

### Harness-Delta

- none
