---
slug: user-feedback-learning
doc: research
lang: en
status: complete
created: 2026-07-21
source_of_truth: true
---

> **Language note:** This English document is the source of truth. For the Vietnamese translation,
> see [RESEARCH.vi.md](./RESEARCH.vi.md).

# Deep research — Learning from user feedback in the LLM graph

## Executive answer

**Do not create a specialist `learning_agent` for the supervisor to route through after every
request.** The travel-pi supervisor should continue to do one job: understand travel intent and
handoff to planner/concierge/journal/booking/budget. Learning is a **cross-cutting** capability. It
runs in the hot path for explicit commands such as “remember this/do not remember this,” and in the
background for corrections or implicit signals.

**The LLM should not have unilateral authority to decide what is stored.** The appropriate division
of responsibility is:

1. Product policy defines which data categories may be remembered, their scope, retention, consent,
   and prohibited data.
2. Code/a policy engine applies deterministic rules for explicit versus implicit signals,
   confidence, conflicts, and create/update/delete permissions.
3. The LLM only reads the trajectory and produces a structured `MemoryCandidate`.
4. The user or a human reviewer decides ambiguous and sensitive cases, as well as every change to
   shared behavior.

This is also the direction described by LangGraph/LangMem: memory may be written in the hot path or
by a background task; it does not have to be an agent orchestrated by the supervisor
([LangGraph memory overview](https://docs.langchain.com/oss/python/concepts/memory),
[LangMem concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)).

## 1. First, distinguish the three meanings of “learn”

| Meaning | Example | Where it is updated | Automatic in the request graph? |
|---|---|---|---|
| **Per-user adaptation** | Minh prefers a window seat, eats vegetarian, and does not stay in hostels | Long-term Store keyed by `user_id` | May run in the hot path/background |
| **Product/system improvement** | The planner often forgets to ask for the number of travellers; the prompt/tool/routing needs correction | Trace → dataset → eval → new prompt/code version | No; runs offline with gates |
| **Model-weight learning** | Fine-tune a model using a large feedback dataset | A separate training pipeline owned by the model provider/ML team | Never online per turn |

If a user says “do not suggest hostels to **me**,” that is user memory. If 300 users complain that
the planner does not explain trade-offs, that is evidence for changing the product/prompt after
evaluation. These flows must not write to the same namespace, and a single feedback item must not
change the production system prompt.

## 2. How travel-pi actually runs today

### 2.1 The answer graph has no memory agent/node at the end

The current topology is:

```text
START → load_context → summarize → supervisor
                                  ↓
                    planner | concierge | journal | booking | budget
                                  ↓
                           dispatch_next → reflection → END
```

`build_graph()` does not register `extract_memory`; after compilation, it only attaches the model
handle `compiled.extract_memory_llm` for the router to use outside the graph
([graph.py](../../apps/api/app/agents/graph.py#L122-L175)). `nodes.py` also states explicitly that
extraction moved to a post-turn background runner
([nodes.py](../../apps/api/app/agents/nodes.py#L1-L15)). The direct answer to the original question
is therefore: **the supervisor does not pass through an “agent that learns feedback.”**

### 2.2 The current write path is background extraction

- `/agent/chat` completes the graph, persists the assistant reply, and then schedules
  `run_memory_extraction` through `BackgroundTasks`
  ([agent.py](../../apps/api/app/routers/agent.py#L357-L373)).
- `/agent/stream` drains SSE, obtains the final state in `sink`, and then runs a `BackgroundTask`
  after the response ([agent.py](../../apps/api/app/routers/agent.py#L456-L481)).
- The runner calls a fast LLM, receives `preferences`, `instructions`, and `episodes`, then upserts
  them directly into the Store
  ([extraction_runner.py](../../apps/api/app/memory/extraction_runner.py#L23-L107)).
- The extractor only sees the final exchange and parses JSON manually
  ([extractor.py](../../apps/api/app/memory/extractor.py#L32-L128)).
- Prompt v5 requires extraction of durable signals only and uses canonical keys
  ([memory_extraction/v5.md](../../apps/api/app/prompts/memory_extraction/v5.md)).

### 2.3 The current read path

The long-term Store separates namespaces by user:

- `("users", user_id, "prefs")` — semantic facts/preferences.
- `("users", user_id, "procedural")` — that user's standing instructions.
- `("users", user_id, "episodes")` — outcomes of previous trips.

The Store is key-addressed: the same key is overwritten; the `text` field has a semantic index
([store.py](../../apps/api/app/memory/store.py#L104-L216)). `load_context_node` reads profile,
instructions, and preferences into state/the prompt before the supervisor
([nodes.py](../../apps/api/app/agents/nodes.py#L86-L130)). This is personalization through external
memory, not the model retraining its weights.

### 2.4 What the current code does not yet have

1. There is no canonical `FeedbackEvent`: thumbs up/down, reason, correction, accept/reject, edit,
   click/save/book/cancel are not persisted as immutable evidence.
2. The LLM extractor currently both creates the candidate and decides the write; there is no
   independent policy/verifier.
3. Memory has no provenance, confidence, source message/run, sensitivity, TTL, or
   `proposed/disputed/superseded` state.
4. The system only upserts; it has no first-class correction/delete/forget flow or conflict
   resolution.
5. Prompted JSON plus a defensive parser is not a structured output schema; parsing failure becomes
   a silent no-op.
6. A FastAPI in-process background task is not durable: if the process dies after replying,
   extraction may be lost; a subsequent turn that arrives too quickly may not see the new memory.
7. `allow_memory_write` is currently always `True` in the resolved context
   ([context.py](../../apps/api/app/agents/context.py#L89-L97)); there is no user-facing opt-out.
8. `WORKFLOW.md` still describes the old topology with terminal `extract_memory`, while the current
   code has moved it to the background. The documentation should be corrected alongside feature
   implementation.

## 3. Architecture comparison

| Option | Execution | Advantages | Problems | Decision |
|---|---|---|---|---|
| A. Supervisor routes to `learning_agent` | Learning is a travel intent/sub-agent | Easy to draw in the graph | Routing can miss it; increases latency; mixes domain routing with data governance | **Reject** |
| B. Terminal node in the graph | Every path passes through an extractor before `END` | Deterministic and checkpoint-visible | The user waits for another LLM call; interrupt/error paths become more complex | Do not restore |
| C. Specialist calls a memory tool | Planner/journal decides whether to write | Memory is immediate and visible to the user | Tool use is discretionary; policy diverges across agents; distracts from the primary task | Use only for explicit commands |
| D. Post-response background pipeline | Emit trajectory → extract → verify → write | Does not increase reply latency; centralized policy; easy to batch/consolidate | Eventual consistency; requires retry/idempotency | **Default** |
| E. Hybrid C + D | Explicit hot path, implicit/background | Balances immediacy and quality | Both write paths need the same policy/idempotency | **Recommended** |

LangMem calls these mechanisms conscious/hot-path and subconscious/background. The hot path gives
immediate updates but adds latency and forces the agent to multitask; the background path separates
the logic and does not block the response
([LangMem concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/),
[background quickstart](https://langchain-ai.github.io/langmem/background_quickstart/)). LangMem's
memory tool also supports create/update/delete and allows the application to restrict actions —
further evidence that write authority should be enforced through policy, not only through a prompt
([Memory Tools API](https://langchain-ai.github.io/langmem/reference/tools/)).

## 4. Target architecture for travel-pi

```text
ONLINE ANSWER PATH
User turn
  → load_context (active user memories)
  → supervisor → specialist → tools → reflection → reply
  ├─ explicit "remember/correct/forget" → deterministic policy → immediate user-memory write
  └─ emit immutable trajectory + FeedbackEvent
                                      │
                                      ▼
BACKGROUND USER-MEMORY PATH
Candidate extractor (LLM, structured output)
  → deterministic policy/verifier
  → conflict + scope + sensitivity gate
  → versioned MemoryRecord in the existing LangGraph Store
  → audit metric / optional "I remembered …" notification

OFFLINE PRODUCT-LEARNING PATH
Traces + feedback events
  → sampling / human annotation / root-cause attribution
  → regression dataset
  → candidate prompt/tool/routing change
  → offline eval + A/B + approval
  → versioned deploy (never direct self-edit in production)
```

The memory pipeline is a cross-cutting service/worker. It can be implemented with plain functions
or a small, separate `StateGraph` if retries/branching are needed, but **do not put it in the list of
specialists to which the travel supervisor routes**.

## 5. Who decides what is learned?

### Decision stack

| Layer | Decides | Must not decide |
|---|---|---|
| Product policy | Category, scope, consent, retention, sensitive denylist, promotion threshold | Specific candidate content |
| Deterministic code | Signal strength, conflict precedence, allowed operation, idempotency | Infer meaning from free text on its own |
| LLM extractor | Candidate type/key/value/scope + evidence span + proposed operation | Bypass policy or modify the global prompt |
| User | Confirm/correct/forget, view/edit/delete, turn personalization off | Accidentally change behavior for every user |
| Human/eval gate | Ship shared procedural/prompt/tool/routing changes | Write personal preferences on a user's behalf |

The supervisor may add routing metadata (`current_flow`, specialist, tool trace) to the event to
support root-cause attribution, but it is not the memory gate.

## 6. Proposed event and candidate models

`FeedbackEvent` should be immutable:

```json
{
  "event_id": "fb_...",
  "user_id": "u_...",
  "trip_id": "trip_...",
  "conversation_id": "conv_...",
  "run_id": "run_...",
  "target_message_id": "msg_...",
  "node": "planner",
  "tool_call_ids": ["call_..."],
  "signal": "correction",
  "explicitness": "explicit",
  "value": "I prefer aisle, not window",
  "created_at": "...",
  "prompt_versions": {"supervisor": 6, "planner": 7},
  "model_config_version": "..."
}
```

`MemoryCandidate`/`MemoryRecord` should contain at least:

```json
{
  "kind": "preference",
  "key": "seat",
  "text": "Traveller prefers an aisle seat",
  "scope": {"level": "user", "destination": null, "travel_group": null},
  "operation": "update",
  "confidence": 0.98,
  "status": "active",
  "learned_from": "explicit_correction",
  "evidence_event_ids": ["fb_..."],
  "source_message_ids": ["msg_..."],
  "sensitivity": "normal",
  "supersedes": "memory_old_id",
  "last_confirmed_at": "...",
  "expires_at": null
}
```

Not every field needs to be added to the semantic index; only `text` needs embedding. Metadata is
used for auditing, filtering, conflict handling, and UI. A small/canonical profile should use direct
key lookup; episodes are where semantic search is useful. LangGraph Store organizes memory through
namespace + key and supports cross-session search
([LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence/)).

## 7. Concrete write policy

| Signal | Example | Action |
|---|---|---|
| Explicit remember | “Remember that I am vegetarian” | Upsert `prefs/diet` immediately; acknowledge |
| Explicit standing rule | “Always display prices in EUR” | Upsert user `procedural/price_currency` immediately |
| Explicit correction | “No, I prefer aisle rather than window” | New explicit value wins; old record becomes `superseded`; preserve evidence |
| Explicit forget | “Forget that I like ANA” | Delete/tombstone the exact memory; acknowledge |
| Contextual preference | “When travelling with young children, only choose hotels with an elevator” | Scope to `travel_group=family`; do not turn it into a global rule |
| Thumb-down without reason | 👎 | Store a feedback event; **do not infer** a preference |
| One click/booking | Select a boutique hotel once | Episode/outcome evidence; do not yet promote to a durable preference |
| Repeated consistent behavior | Select boutique hotels across three different trips | Create a `proposed` candidate; confirm or use threshold-gated promotion |
| Silence/no click | Do not click a suggestion | Do not treat it as dislike; `not_observed != negative evidence` |
| Sensitive data | Passport/card/health detail | Do not put it in semantic memory; use an appropriate domain store or reject |

Proposed conflict precedence:

```text
new explicit correction
  > explicit statement
  > repeated cross-session behavior
  > one-off implicit behavior
  > model inference
```

If two facts may both be true in different contexts, separate them by scope instead of overwriting.
If the scope is unclear, keep the candidate `disputed/proposed` and ask the user. Do not treat an
LLM's floating-point confidence as ground truth; confidence is only one input to the deterministic
gate.

## 8. Product-level learning from feedback

User memory and system behavior need a firewall. For example, when a user says “this answer is too
long,” it may indicate:

- a personal preference: the user repeatedly requests concise responses → per-user `procedural`;
- a product defect: many negative traces fail the same rubric → update the communication prompt;
- a data/tool error: a price is wrong → fix the service/tool, not the prompt;
- a routing error: the supervisor chooses concierge instead of budget → add a routing eval/case.

The offline pipeline must therefore attribute feedback to `supervisor | specialist | tool |
retrieval | memory | UX` before creating a candidate change. LangMem has a prompt optimizer that
accepts multiple trajectories with feedback, but its output should only be a candidate that is
evaluated and version-controlled, never something that directly flips the active prompt
([Prompt optimization guide](https://langchain-ai.github.io/langmem/guides/optimize_memory_prompt/),
[multi-prompt optimization](https://langchain-ai.github.io/langmem/guides/optimize_compound_system/)).
LangSmith describes a loop of production trace → online monitoring → failing cases added to a
dataset → offline experiment → redeploy; thumbs-down can enter an annotation queue rather than be
used directly as training truth
([evaluation lifecycle](https://docs.langchain.com/langsmith/evaluation),
[annotation queues](https://docs.langchain.com/langsmith/annotation-queues)). Travel-pi can apply
this pattern using its existing DeepEval + Langfuse stack without adopting LangSmith.

## 9. User control and privacy

The minimum product contract should include:

- “What I remember” — show active memory with explainable evidence/source.
- Edit, forget one, clear all, disable future writes, and temporary/no-memory chat.
- Notify the user when an explicit command creates/updates/deletes memory.
- A sensitive-data denylist; do not infer protected/sensitive traits.
- Retention/expiry for old episodes; an audit log for write/delete; cross-user isolation tests.

OpenAI's current memory controls are a useful product precedent: users can view, edit/delete memory,
turn memory off, and sensitive information should not be proactively remembered unless the user
requests it
([OpenAI Memory FAQ](https://help.openai.com/en/articles/8590148-personalization-and-data-controls-faq)).
This is a design pattern, not a claim that travel-pi complies with any regulatory regime.

## 10. Evaluation gates

### User-memory quality

- Candidate precision/recall by kind and explicitness.
- False-write rate, especially for one-off signals and sensitive data.
- Correct update/delete/conflict/scope rate.
- Cross-user leakage = 0 in adversarial tests.
- Retrieval relevance and “memory used correctly,” not only “memory found.”
- User correction/forget rate after memory is used.

### Runtime/operations

- Reply p50/p95 does not increase on the background path.
- Extraction completion, retry, dead-letter, and idempotency rate.
- Eventual-consistency lag until memory can be recalled.
- Cost/tokens per extracted candidate and per accepted memory.

### Product improvement

- Offline regression by flow/specialist before a prompt/tool change is shipped.
- Pairwise quality and task success, not only aggregate thumbs-up.
- A/B memory on/off or policy-version A/B with safety/privacy guardrails.

The launch gate should prioritize **precision over recall**: missing a preference usually only makes
the response less personalized; storing a wrong preference damages user trust. Every important
negative production trace should become a reproducible regression case.

## 11. Phased roadmap

### Phase 0 — Explicit feedback foundation

- Capture immutable feedback events + trace/run/message/node/tool provenance.
- Support `remember`, `correct`, and `forget` with canonical keys and acknowledgement.
- Do not enable implicit writes.

### Phase 1 — Safe background candidates (shadow mode)

- Change the extractor to a structured schema.
- The LLM creates candidates; policy/verifier decides `reject/propose/activate`.
- Store confidence, evidence, scope, sensitivity, and conflict action; do not yet inject proposed
  memory into the prompt.

### Phase 2 — Controlled personalization

- Enable high-confidence, low-risk background writes.
- Only repeated implicit signals may be promoted; ambiguous cases ask for confirmation.
- Add memory-management UI/API, opt-out, retention, and a durable worker/retry mechanism.

### Phase 3 — Offline system-learning loop

- Curate negative/positive trajectories into DeepEval datasets.
- Perform root-cause attribution by graph node/tool/prompt version.
- Generate candidate prompt changes, regression-evaluate them, require human approval, and use a
  versioned rollout.

### Phase 4 — Only when enough data exists

- Consider offline fine-tuning/ranker training if memory/prompt/tool fixes are insufficient and
  consent/data governance permits it. Never update model weights from a live user turn.

## 12. Mapping to the repository for implementation

| Concern | Existing seam | Likely work |
|---|---|---|
| Candidate extraction | `memory/extractor.py` | Structured candidate schema + evidence spans |
| Central policy/write | `memory/extraction_runner.py` | Separate extractor from verifier/policy; idempotency/conflict |
| Long-term records | `memory/store.py` | Metadata, update/delete/tombstone, scoped keys |
| Scheduling | `routers/agent.py` background calls | Emit event, durable job handoff later; keep off critical path |
| Explicit hot path | memory tool/domain command | Reuse the same policy service, never a second policy |
| Feedback capture | schemas/router/service/repository + FE | New contract/schema is a separate high-risk implementation plan |
| Recall | `load_context_node`, `recall_past_trips` | Read only active, in-scope, non-expired memories |
| Offline learning | `apps/api/eval/`, Langfuse traces | Feedback datasets, node attribution, regression reports |
| User controls | `apps/web` + API | View/edit/delete/disable/temporary chat |

**Repository-specific recommendation:** keep the current hand-built `StateGraph` and existing
`BaseStore`; do not add LangMem merely to name this pattern. First harden the one existing write
seam. A new dependency is justified only if conflict/consolidation/versioning needs exceed what this
small structured policy can safely handle.

## 13. Recommended implementation sequence

Implementation should use a new `specs/user-feedback-v1/` package; this research remains the
architecture decision record. Do not add `learning_agent` to the supervisor's specialist list.

### PR 1 — Feedback event foundation

Collect evidence only; do not change memory behavior yet.

- Add an immutable SQL `FeedbackEvent` model.
- Support `thumbs_up`, `thumbs_down`, `comment`, `correction`, `remember`, and `forget` signals.
- Add `POST /agent/feedback`.
- Attach feedback to `assistant_message_id`, `conversation_id`, `user_id`, specialist/tool trace,
  and prompt version.
- Return `assistant_message_id` from `/chat` and the SSE `done` event.
- Add frontend thumbs up/down controls with an optional reason.
- Enforce ownership so users can only submit feedback for their own messages.
- Add idempotency so retries or double-clicks do not create duplicate events.

A thumb-down without a reason must create only a feedback event; it must **not** write memory.

### PR 2 — Memory candidate pipeline in shadow mode

Separate LLM extraction from write authority:

```text
Feedback/trajectory
  → LLM extracts MemoryCandidate
  → deterministic policy
  → reject | proposed | active
```

- Move extraction to structured output.
- Include `kind`, `key`, `value`, `operation=create|update|delete`, `scope`, `confidence`,
  `evidence_event_ids`, and `sensitivity` in each candidate.
- Apply the precedence rule: explicit correction > explicit statement > repeated implicit signal >
  one-off implicit signal.
- Detect conflicts with current memory.
- Run in shadow mode: record decisions, but do not inject `proposed` memory into prompts.
- Do not infer passport, payment, or other sensitive data.

### PR 3 — Explicit remember/correct/forget

Enable learning only for unambiguous cases:

- “Remember that I am vegetarian” → activate `prefs/diet`.
- “I prefer aisle, not window” → supersede the old preference.
- “Forget that I like ANA” → delete/tombstone the memory.
- Confirm to the user exactly what was remembered, corrected, or forgotten.
- Make both the hot path and background path use the same policy service.

### PR 4 — Memory controls

Before enabling implicit learning:

- Add APIs to view, edit, and delete memory.
- Add a “What I remember” UI.
- Support clear all, disable memory, and temporary chat.
- Show provenance: which feedback/evidence caused each memory.
- Apply TTL to episodes; explicit preferences do not expire automatically.
- Audit delete/update operations and test cross-user isolation.

### PR 5 — Controlled implicit learning

Promote implicit signals only when evidence is sufficient:

- A single click/booking becomes episode evidence, not a durable preference.
- Repeated signals across multiple trips may create a `proposed` candidate.
- Scope contextual preferences by solo/family/destination context.
- Ask the user when conflicts are ambiguous instead of overwriting.
- Track false-write and correction rates.

### PR 6 — Offline product learning

Keep shared product improvement in a separate offline flow:

```text
Feedback events + Langfuse traces
  → root-cause attribution
  → DeepEval dataset
  → prompt/tool/routing candidate
  → regression eval
  → human-approved deployment
```

Never let a live turn directly edit the active prompt or train model weights online.

### Cross-cutting acceptance gates

- Thumbs-only feedback never creates memory.
- Cross-user feedback/read/write is rejected and covered by tests.
- Feedback events and memory operations are idempotent.
- Background processing does not increase reply latency.
- Every active memory is traceable to its evidence.
- Sensitive data is never written to semantic memory.
- Implicit learning stays disabled until user controls and the shadow-evaluation gate exist.

**Immediate recommendation:** start with **PR 1 — Feedback event foundation**. It establishes
auditable evidence and stable identifiers before the system is allowed to learn. Classify this work
as **high-risk** because it introduces a database schema/migration and changes public HTTP/SSE
contracts. It therefore needs a dedicated implementation plan, migration/rollback reasoning,
ownership and idempotency tests, contract tests, and rerunnable verification evidence.

## Final decision

```text
Supervisor decides: “Which travel specialist does this request need?”
Memory extractor proposes: “Does this exchange contain a durable signal?”
Policy engine decides: “May this candidate be created/updated/deleted?”
User/human decides: “Should this ambiguous/sensitive/global change be accepted?”
Offline eval decides: “Is this system change good enough to deploy?”
```

The shortest answer is: **this should not be an agent that the supervisor must pass through; it
should be a separate background pipeline plus a hot path for explicit feedback. The LLM proposes
what to learn, while policy + user controls have the authority to decide what is stored.**
