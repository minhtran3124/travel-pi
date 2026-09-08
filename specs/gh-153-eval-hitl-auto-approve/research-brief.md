# gh-153-eval-hitl-auto-approve — Research Brief

Depth: **Standard** (intake lane normal). No waiver. External surface: **none new** — the only version-specific API (LangGraph `interrupt` / `Command(resume=…)` / `__interrupt__`) is already used by `app/routers/agent.py` and `tests/agents/test_hitl_plan.py` at the pinned version; upstream evidence is the installed package source, not web docs.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **reuse existing** — copy the router's resume call (`agent.py:385`) and the `__interrupt__` read (`agent.py:440`) into `LangGraphRunner.run`; add one optional `Golden.hitl` field. |
| **Why this is the lightest credible path** | Every mechanism already exists and is tested (`tests/agents/test_hitl_plan.py` drives interrupt → approve/reject with a FakeLLM); the runner only lacks the second invoke. |
| **Confidence** | 90% |
| **Next step** | writing-plans; the paid re-baseline is the last task and needs the user's OK at execution time. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo; this spec touches `apps/api/eval/**`, `apps/api/evalkit/types.py`, `apps/api/tests/eval/**` only |
| Primary language + runtime | Python 3.14 local / 3.12 CI |
| Frameworks / platforms | LangGraph **1.2.6** (installed), pydantic v2, DeepEval 4.0.7 |
| Relevant packages | `evalkit/` (portable engine, no `app.*` imports — `tests/eval/test_boundary.py`), `eval/adapters/` (may import `app.*`) |
| Important constraints | branch `feat/agent-eval-pipeline` (PR #157) is the only place the runner exists; no `apps/api/app/**` edits; a judged full run costs ~84 agent turns + ~105 judge calls (review-b7 SUMMARY) and needs the copied `apps/api/.env` + Docker Postgres; `.venv` symlink gotcha for worktrees (review-b7 PLAN Global Constraints) |

## Feature Understanding and Assumptions

- **Requested feature:** grade the booking path in the eval harness by resuming the HITL interrupt, opt-in per golden (`hitl: approve|reject`), always recording the interrupt payload in `Trace.meta`; regenerate the baseline afterwards.
- **What success appears to mean:** FakeLLM runner tests for no-hitl / approve / reject pass keyless; the annotated goldens run through `booking` tools in a real run; `eval/baselines/main.json` regenerated and `make eval-compare` exits 0 against it.
- **Assumptions from the request:** one `plan_approval` interrupt per turn at most; a second interrupt in the same turn is recorded, not resumed.
- **Assumptions still needing confirmation:** how many of the 12 `hitl` goldens actually pass after approval (the booking sub-agent's behaviour on `HTL-999999` etc. is unmeasured) — this is what the paid run decides; it changes the triage, not the design.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `eval/adapters/langgraph_runner.py:178-210` — `run()` loops `turns`, each `graph.invoke({"messages":[HumanMessage]}, cfg, context=…)`; builds `Trace(reply, tool_calls, flow, messages, meta{thread_id, model, elapsed_s, n_turns, tasks, suggestions})`. No `Command`, no `__interrupt__` read. |
| `Local` | `app/agents/nodes.py:263-292` — `plan_node`: `interrupt({"type":"plan_approval","draft": last message})`; resume value `{"approved": bool}`; `False` → `AIMessage("Booking cancelled as requested.")` + `goto=END`; `True` → `AIMessage("Plan approved. Proceeding with booking.")`, `plan_approved=True`, `goto="booking"`. |
| `Local` | `app/routers/agent.py:385, 440-445` — production resumes with `graph.ainvoke(Command(resume=body.resume), cfg, context=ctx)` and reads `result.get("__interrupt__", [])`, `interrupts[0].value`; reply is `""` while an interrupt is pending. The runner should mirror both. |
| `Upstream` | installed `langgraph 1.2.6`, `langgraph/types.py:278, 381, 535, 759-771` — invoke output carries `__interrupt__` as a tuple of `Interrupt` objects with `.value` (and `.id`); `Command(resume=value)` resumes the parked node (value or a mapping of interrupt ids → values). |
| `Local` | `tests/agents/test_hitl_plan.py:20-95` — FakeLLM recipe that reaches the interrupt (`SupervisorIntent(target_agent="booking")` ×6, `responses=[answer]*6`, `MemorySaver`, `InMemoryStore`), then `graph.invoke(Command(resume={"approved": True|False}), cfg)`; asserts `"Hotel booked"` on approve and `"cancelled"` on reject. Directly reusable for the runner tests (`tests/eval/test_langgraph_runner.py::_build_runner` already takes `target=`). |
| `Local` | `evalkit/types.py:23-46` — `Golden` has no `model_config`/`extra` override; fields are plain optionals; `hitl: Literal["approve","reject"] \| None = None` is additive and a typo fails pydantic validation at load (`JsonDatasetStore` validates every case). |
| `Local` | 17 goldens with `expected_flow: booking`: booking.json ×8 (`happy-vi-01`, `happy-en-01/02`, `ambiguous-vi-01/en-01`, `multi_turn-vi-01/en-01`, `tool_failure-vi-01`), dates.json ×2 (`multi_turn-vi-01/en-01`), errors.json ×2 (`ambiguous-en-01`, `tool_failure-vi-01`), routing.json ×3 (`ambiguous-en-01`, `multi_turn-vi-01/en-01`), suggestions.json ×2 (`happy-vi-04/en-04`). Design assigns `hitl: approve` to 12: booking-happy ×3, booking-multi_turn ×2, booking-tool_failure-vi-01, errors-tool_failure-vi-01, dates-multi_turn ×2, routing-ambiguous-en-01, suggestions-happy ×2 — the 3 `ambiguous` goldens (`booking-ambiguous-*`, `errors-ambiguous-en-01`) and `routing-multi_turn-*` (flow_match only; en-01 is the #155 crash) stay without `hitl`. |
| `Local` | `evalkit/runner.py:129-142` — a per-golden exception from `agent_runner.run` becomes a failed `agent_run` check, not an aborted run; a resume that raises is therefore graded, not fatal. |
| `Local` | `eval/README.md:51-79, 216-230` — golden fields are documented in one list (`expected_tools`, `oracle_checks`, `expected_tasks` with its own section); `hitl` gets the same treatment. |
| `Local` | `apps/api/Makefile:55-71` — `eval-full` (k=3 judged), `eval-baseline` (copy latest → `$(BASELINE)`), `eval-compare`, `eval-check`; review-b7 SUMMARY records one full run ≈ 84 agent turns + ~105 judge calls and that make exits 2 while capabilities sit below threshold (report still written). |
| `Inference` | Sending a plain `HumanMessage` to a thread parked on an interrupt starts a new step from the graph entry rather than clearing the interrupt (LangGraph semantics; the spec reviewer flagged this) — so multi-turn goldens whose turn 1 interrupts must carry `hitl`, or the runner must resume before turn 2. The design resumes right after the interrupting turn, before the next `HumanMessage`, which sidesteps the question. |

## Local Findings

- **Relevant files:** `eval/adapters/langgraph_runner.py`, `evalkit/types.py`, `eval/datasets/{booking,dates,errors,routing,suggestions}.json`, `eval/README.md`, `tests/eval/test_langgraph_runner.py`, `tests/agents/test_hitl_plan.py` (recipe), `app/agents/nodes.py::plan_node` (read-only contract), `app/routers/agent.py:385,440` (read-only contract).
- **Extension points:** `Golden` additive fields; `Trace.meta` open dict; `_build_runner(target=…)` test helper.
- **Conventions:** `evalkit/` framework-free (boundary test) — the `hitl` field is a string literal there, resume mechanics stay in `eval/adapters/`; goldens carry `notes` explaining expectations; baseline refresh only via `make eval-baseline` with the reason in the commit message.
- **Reusable as-is:** `test_hitl_plan.py` FakeLLM recipe; router's `Command(resume=…)` + `__interrupt__` reads.
- **Missing locally:** any resume in the eval runner; `hitl` field; `meta["interrupts"]`.

## Upstream Findings

- **Repositories inspected:** installed `langgraph==1.2.6` source in `.venv` (`langgraph/types.py`), i.e. the exact pinned version.
- **Pattern present upstream:** `invoke()` returns `__interrupt__: tuple[Interrupt,…]`; `Interrupt.value` holds the payload; `Command(resume=…)` resumes.
- **Match to this repo:** exact — `agent.py` and `test_hitl_plan.py` use precisely this shape.
- **Gaps:** none.

## Docs Findings

- none (local-only; no new external surface).

## Recommendation

- **Primary:** reuse existing — after each `invoke`, read `out.get("__interrupt__", [])`; if the first value is a `plan_approval` and `golden.hitl` is set, `out = graph.invoke(Command(resume={"approved": golden.hitl == "approve"}), cfg, context=self._context)`; always append `{"type","draft","turn"}` to `meta["interrupts"]`.
- **Why lightest:** two lines of orchestration, one additive field, tests copied from an existing recipe.
- **Why the next-best alternative lost:** `get_state(cfg).tasks[*].interrupts` needs an extra checkpointer round-trip and diverges from the router's pattern.
- **What would flip this:** if `plan_node` ever emits more than one interrupt per turn (it does not today), the one-resume-per-turn rule would need a loop.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** the paid run flips up to 12 goldens — some may still fail for agent reasons (e.g. `book_hotel` on `HTL-999999` must surface NotFound gracefully; unmeasured); the baseline is regenerated regardless and failures re-triaged into issues. `booking-ambiguous-*` and `errors-ambiguous-en-01` will keep failing `non_empty_reply` until the plan node clarifies instead of interrupting (agent work, out of scope).
- **Evidence gaps:** whether the FakeLLM booking sub-agent emits a tool call in the runner test (the recipe's `answer="Hotel booked!"` is plain text) — test (b) asserts the post-approval AIMessage, and tool calls only if the recipe is extended with a scripted tool call.
- **Version uncertainties:** none.
- **Follow-up questions for the user:** authorise the paid full run when wave 3 starts (≈ same cost as review-b7's runs).

## Source Pack

- **Local files read:** `eval/adapters/langgraph_runner.py`, `evalkit/types.py`, `evalkit/runner.py`, `evalkit/dataset.py`, `eval/README.md`, `eval/datasets/*.json`, `apps/api/Makefile`, `app/agents/nodes.py`, `app/routers/agent.py`, `tests/agents/test_hitl_plan.py`, `tests/eval/test_langgraph_runner.py`, `specs/review-b7-eval-baseline-ci/SUMMARY.md`, `specs/gh-153-eval-hitl-auto-approve/{SUMMARY,design}.md`.
- **Upstream repositories or pages checked:** installed `langgraph==1.2.6` (`.venv/lib/python3.14/site-packages/langgraph/types.py`).
- **Official docs domains or pages checked:** - none (local-only; no external surface)

## Evidence Boundary

> Confirmed from artifacts: runner loop shape, `plan_node` approve/reject outputs, router resume + `__interrupt__` read, langgraph 1.2.6 `Interrupt`/`Command` contract, the 17 booking goldens and their metrics, `Golden` additivity, per-golden exception handling, make targets and cost.
> Inferred from patterns: plain-HumanMessage-on-parked-thread semantics (not executed); which of the 11 `hitl` goldens will pass after approval.
> Not checked: whether the FakeLLM booking path emits tool calls without extra scripting.
