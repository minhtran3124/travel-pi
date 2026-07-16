---
slug: min-65-chatbot-intelligence
created: 2026-07-12
owner: Minh Tran
---

# MIN-65 — Intake & Record

Lane: normal
Confidence: high
Reason: Multi-layer agent change (state + supervisor + graph + nodes + tools + prompts + eval + FE i18n) → needs a full plan. No hard gate: no auth, no DB migration, no new external provider, no public-contract change (`ChatResponse.suggestions` keeps its list-of-keys shape). The foundation (store, extraction, suggestions, eval) is already shipped and was mapped thoroughly → high confidence.
Flags: existing-behavior (supervisor structured output, suggestions call sites), weak-proof (eval needs a real key to run the baseline)
Affects: app/agents/{state,supervisor,graph,nodes,suggestions}.py, app/memory/store.py, app/tools/{_ranking,hotel_tools,flight_tools}.py, app/prompts/* (5 new versions), eval/*, apps/web/messages/*.json
Input-type: feature request (Linear MIN-65)
Route: research (3 agents) → HLD.md → DESIGN.md → PLAN.md (8 waves, 10 tasks) → await user review before executing
Escalate: no

## Status

**Plan-only** (at the time this record was written). Artifacts: `HLD.md` (research +
option comparison), `DESIGN.md` (D1–D9 + test matrix), `PLAN.md` (XML tasks). No code
changed yet.

## Rationale

Running the memory decision-tree (working/semantic/episodic/procedural) per information
type: the only real memory gap is **working-memory slots** (`trip_facts` in state) +
preference injection coverage; the long-term side is already shipped (P1/P2). Reasoning
is solved with a bounded secondary-intent + dispatch node (zero extra LLM calls);
suggestions are solved with a deterministic rule engine that keeps the i18n contract;
ranking uses a stable-sort re-rank inside the tool. Eval-first, exactly as the ticket
requested.

## Alternatives considered

- Adopting Mem0 / LangMem / Letta — rejected (HLD §3.1): a second memory system running
  alongside the checkpointer/store, overkill for a mock backend; BaseStore + pgvector
  already provides enough of the mechanism.
- A dedicated slot-extraction node, or an LLM-discretionary tool — rejected (HLD §3.2):
  either +1 LLM call/turn or repeats the exact gap P1 already fixed; folding it into the
  supervisor's structured output is zero-cost.
- LLM-generated suggestions — rejected for v1 (HLD §3.4): breaks the i18n-key contract
  with the FE.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| (pending) per-task | see PLAN.md `<verify>` rows | — | filled in during execution |

### Rollback

- Plan-only: delete `specs/min-65-chatbot-intelligence/` if this direction is abandoned.
- During execution: one commit per task → `git revert <sha>`; prompt rollback = flip
  `active.yaml` back to the old version (old files are never edited); no DB migration.
