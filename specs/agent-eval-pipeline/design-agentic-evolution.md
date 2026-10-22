# Design — Agentic, self-evolving evaluation (direction note)

Status: direction discussion 2026-07-13 (user vision), layered on top of PLAN.md phase 1.
Not yet tasked; extends — does not replace — the phase-1 substrate.

## The vision (user, 2026-07-13)

> agent có thể đọc được data ở DB local → data insight; quan sát data-in-transit
> (request/response, tool calls) để hiểu data đi thế nào, đúng không, shape ra sao →
> từ đó build một hệ thống evaluation agentic, thông minh, tự tiến hoá.

## Why this repo is unusually suited

Everything except weather/routing/LLM is **deterministic and DB-seeded** (same query = same
flights/hotels; trips/bookings/FX live in the DB). So an eval agent is not limited to
LLM-judge opinions — it can **compute the ground truth** by querying the same DB/services
the chatbot's tools use, and check the chatbot's answer factually. A real oracle: cheap,
deterministic, zero judge variance.

## Architecture — four agentic layers on the phase-1 substrate

```
L-A  DB-as-Oracle metrics      (deterministic fact-checking against local DB)
L-B  Transit capture + shape   (request/response + tool I/O tracing, schema checks)
L-C  Golden-generation agent   (mines DB + schemas → synthesizes goldens, human-gated PR)
L-D  Failure-mining agent      (clusters eval/prod failures → proposes goldens/rubric
                                updates as PRs — the self-evolving loop)
```

### L-A — DB-as-Oracle (highest value, uniquely possible here)

An oracle module that, per golden, recomputes expected facts through repositories/services
(NOT through the agent): flight prices/times for a seeded query, hotel availability, trip
budget math (`total_spent`, gaps), FX conversion, climate ranges. A new metric class
`OracleFactCheck` extracts claimed facts from the chatbot reply (small LLM extraction is OK
— extraction, not judgment; code computes, LLM parses, per `llm-parses-code-computes`) and
compares against oracle values. Turns "no_hallucination" from a rubric opinion into a
computation.

### L-B — Data-in-transit capture

- Offline: harness already captures `tools_called`; task 2.3 adds tool outputs + ordered
  messages. Add per-tool-call arg/return **schema validation** (pydantic) → "shape" checks.
- Online (phase 2/Langfuse or a thin homegrown middleware): capture `/agent/*`
  request/response + tool spans into a trace store; sampled judging + failure mining read
  from it.

### L-C — Golden-generation agent

Reads seed data (`app/data/`), tool schemas, and the capability×scenario matrix; finds
under-populated cells; synthesizes candidate goldens **grounded in actual DB rows** (so
L-A can verify them) in the task-1.1 schema. Output = a PR, never a direct dataset write.

### L-D — Failure-mining agent (the flywheel)

Consumes nightly reports (task 3.1 JSON) + traces; clusters failures; proposes new goldens,
threshold adjustments, or rubric fixes — as PRs with evidence attached.

## Guardrails (what keeps "self-evolving" from becoming self-deceiving)

1. **Human-gated evolution**: agents propose via PR; datasets/rubrics never mutate silently.
   Eval is the measuring stick — a stick that bends itself is Goodhart bait.
2. **Oracle > judge**: wherever a fact is computable from the DB, the deterministic oracle
   wins; G-Eval only for genuinely subjective qualities (tone, formatting, helpfulness).
3. **Separation of powers**: the generator agent and the judge must not share a prompt/model
   config lineage (self-preference bias).
4. **Determinism is a dependency**: the seed algorithm is load-bearing for the oracle
   (CLAUDE.md already forbids changing it).

## Sequencing

| Step | What | Builds on |
|---|---|---|
| Phase 1 (PLAN.md, unchanged) | schema'd goldens, L0 checks, trajectory, runner, baseline, CI | — |
| Phase 1.5 | L-A oracle metrics + L-B offline shape checks | tasks 1.1, 2.3, 3.1 |
| Phase 2 | tracing (Langfuse decision) + L-D failure mining | phase 1.5 |
| Phase 2.5 | L-C golden generation | matrix gaps visible via 2.1 |

Phase 1 is unchanged and remains the prerequisite: agents need the schema, runner, and
report formats as their action space.
