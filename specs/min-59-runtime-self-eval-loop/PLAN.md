---
slug: min-59-runtime-self-eval-loop
status: active
owner: Minh Tran
created: 2026-07-10
---

# MIN-59 — Runtime Rubric-Based Self-Evaluation Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** A dedicated `grader` node that rubric-grades booking/concierge answers at runtime (LLM-as-judge, cheap model), loops the sub-agent with per-criterion feedback when criteria fail, and produces a measured latency/cost/quality trade-off report on the MIN-58 eval set.

**Architecture:** New `grader` node inserted between the graded sub-agents (`booking`, `concierge`) and today's `reflection` node. When enabled it **replaces** reflection for those flows (still exactly one judge call per turn when satisfied); when disabled (per-request `AgentContext.allow_grader`, driven by the DB `agent_config."grader".enabled` toggle — same pattern as reflection's) it delegates straight to `reflection`, reproducing today's baseline bit-for-bit → clean with/without A/B. Verdict semantics converge with Deep Agents' `RubricMiddleware` (`satisfied` / `needs_revision` / `max_iterations_reached` / `grader_error`, per-criterion `{name, passed, gap}`) so the node can later fold into the middleware when the path-B migration reaches these sub-agents — but we self-define the Pydantic schema (no `deepagents` beta dependency). Feedback is injected as `SystemMessage` (never `HumanMessage` — the known language-flip bug).

**Tech Stack:** LangGraph `Command(goto)` node (same shape as `make_reflection_node`), Pydantic v2 structured output via `llm.with_structured_output`, prompt registry (`prompts/grader_booking/`, `prompts/grader_concierge/`), DB-backed model config (`AgentConfigCache` — `grader` gets the cheap tier via `FAST_AGENTS`), FakeLLM `structured_responses` for offline tests.

**Design source:** `specs/min-59-runtime-self-eval-loop/COMPARISON.md` (§5 verdict — option 2; §4 shared risks; Phụ lục A — why not RubricMiddleware now). Decision confirmed by human 2026-07-10.

**Key existing code (read before implementing):**
- `apps/api/app/agents/nodes.py:120-174` — `make_reflection_node`, the shape this node mirrors
- `apps/api/app/agents/graph.py:116-150` — node/edge assembly, `pick()` model resolution
- `apps/api/app/agents/context.py` — `AgentContext` + `resolve_agent_context`
- `apps/api/app/routers/agent.py:145-169` — `_resolve_context`, where DB toggles become context flags
- `apps/api/tests/agents/test_depth_toggles.py` — the test idiom to copy (FakeLLM, `_runtime`, `_base_state`)
- `apps/api/app/clients/llm.py:155-217` — `FakeLLM` (`structured_responses` cycles through `with_structured_output`)

**Non-goals:** streaming a "grading…" indicator to the FE (grader node name ∉ `SUBAGENTS` → automatically silent); grading planner/journal/budget; persisting verdicts in state or DB; touching `make_reflection_node`, the supervisor, or the HITL `plan` node; any `deepagents` dependency.

---

## Chunk 1: Foundations — context flag, constants, config surface, rubric prompts

### Task 1: `allow_grader` context flag + grader constants

**Files:**
- Modify: `apps/api/app/agents/constants.py`
- Modify: `apps/api/app/agents/context.py`
- Test: `apps/api/tests/agents/test_agent_context.py` (append)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/agents/constants.py, apps/api/app/agents/context.py, apps/api/tests/agents/test_agent_context.py</files>
  <action>Add GRADED_FLOWS + DEFAULT_MAX_GRADER_ITERATIONS constants, "grader" to FAST_AGENTS, and an allow_grader flag on AgentContext resolved via resolve_agent_context (same pattern as allow_reflection).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -x -q</verify>
  <done>New constants importable; AgentContext(allow_grader=...) round-trips through resolve_agent_context; existing context tests still green</done>
</task>
```

- [ ] **Step 1: Write the failing tests** — append to `apps/api/tests/agents/test_agent_context.py`:

```python
def test_context_allow_grader_defaults_true():
    """allow_grader defaults ON (parity with allow_reflection)."""
    ctx = resolve_agent_context(tier="premium")
    assert ctx.allow_grader is True


def test_context_allow_grader_passthrough():
    """resolve_agent_context threads allow_grader into the frozen context."""
    ctx = resolve_agent_context(tier="premium", allow_grader=False)
    assert ctx.allow_grader is False
```

Match the file's existing import style (it already imports `resolve_agent_context`).

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -x -q`
Expected: FAIL — `TypeError: resolve_agent_context() got an unexpected keyword argument 'allow_grader'`

- [ ] **Step 3: Add the constants** — in `apps/api/app/agents/constants.py`:

Change `FAST_AGENTS` (line 35-37) to include `"grader"`:

```python
FAST_AGENTS: frozenset[str] = frozenset(
    {"summarize", "journal", "budget", "reflection", "extract_memory", "grader"}
)
```

Append a new section after the `# --- reflection ---` block (line 44-46):

```python
# --- runtime rubric grader (MIN-59) ------------------------------------------
# Sub-agent flows whose answers pass through the rubric grader node instead of
# the generic reflection judge. Each flow needs a ``prompts/grader_<flow>/``
# rubric; the grader delegates any other flow straight to ``reflection``.
GRADED_FLOWS: frozenset[str] = frozenset({"booking", "concierge"})

# Revise-loop cap for the grader (shares the ``revisions`` state counter with
# reflection, so the combined loop count can never exceed this). MIN-59
# proposes 2 rounds for the prototype.
DEFAULT_MAX_GRADER_ITERATIONS = 2
```

- [ ] **Step 4: Add the context flag** — in `apps/api/app/agents/context.py`:

Add the field to `AgentContext` right after `allow_reflection` (line 35):

```python
    allow_grader: bool = True
```

Add the parameter to `resolve_agent_context` (line 45-47) and thread it through:

```python
def resolve_agent_context(
    *,
    tier: Tier | str | None,
    allow_reflection: bool = True,
    allow_grader: bool = True,
) -> AgentContext:
```

…and in the returned `AgentContext(...)` (line 81-89) add `allow_grader=allow_grader,` after `allow_reflection=allow_reflection,`. Update the docstring's param list with one line: `:param allow_grader: DB-config-driven rubric-grader gate (from agent_config."grader".enabled); defaults True.`

- [ ] **Step 5: Run the tests**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -x -q`
Expected: PASS (all, including pre-existing).

### Task 2: Rubric prompts for booking + concierge

**Files:**
- Create: `apps/api/app/prompts/grader_booking/v1.md`
- Create: `apps/api/app/prompts/grader_concierge/v1.md`
- Modify: `apps/api/app/prompts/active.yaml`
- Modify: `apps/api/app/prompts/CHANGELOG.md`

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/prompts/grader_booking/v1.md, apps/api/app/prompts/grader_concierge/v1.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md</files>
  <action>Add per-flow rubric prompts (criteria from the MIN-58 eval rubrics: language, completeness, grounding, no-redundant-questions) and register them in active.yaml. Registry auto-discovers the dirs; active.yaml pins v1.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'You are' in registry.get('grader_booking'); assert 'You are' in registry.get('grader_concierge'); print('ok')"</verify>
  <done>registry.get("grader_booking") / ("grader_concierge") return the rubric text; active.yaml pins both at 1</done>
</task>
```

- [ ] **Step 1: Create `apps/api/app/prompts/grader_booking/v1.md`:**

```markdown
# Role: Booking Rubric Grader

You are a strict, impartial reviewer of a travel-booking assistant. You are
given the conversation so far; the assistant's LAST message is the answer
under review. Judge that answer against each rubric criterion below —
independently, on evidence from the conversation only.

## Rubric

- **required_info**: If the answer confirms or executes a booking, every
  required detail (traveller, dates, destination/flight or hotel identity,
  price) was already provided by the traveller or a tool result. It never
  confirms with missing or assumed details.
- **no_redundant_questions**: The answer does not re-ask for information the
  traveller already gave earlier in the conversation.
- **grounding**: Every flight, hotel, price, and time in the answer comes from
  a tool result in the conversation. Nothing is invented.
- **language**: The answer is written in the traveller's own language (the
  language of their latest message).

## Output

For each criterion return: its exact name, whether it passed, and — when it
failed — a one-sentence, actionable gap the assistant can fix. Be strict on
grounding and required_info; be lenient on style. Do not invent criteria.
```

- [ ] **Step 2: Create `apps/api/app/prompts/grader_concierge/v1.md`:**

```markdown
# Role: Concierge Rubric Grader

You are a strict, impartial reviewer of a travel-concierge assistant. You are
given the conversation so far; the assistant's LAST message is the answer
under review. Judge that answer against each rubric criterion below —
independently, on evidence from the conversation only.

## Rubric

- **grounding**: Every hotel, place, price, and fact in the answer comes from
  a tool result in the conversation. No invented names, prices, or details.
- **completeness**: When presenting hotels or places, the answer includes the
  key deciding facts available from the tools (for hotels: price and
  location/area). It does not silently drop what the tools returned.
- **search_vs_booking**: If the traveller is only searching/browsing, the
  answer does NOT demand booking details (exact dates, guest counts) as a
  precondition for showing results.
- **language**: The answer is written in the traveller's own language (the
  language of their latest message).

## Output

For each criterion return: its exact name, whether it passed, and — when it
failed — a one-sentence, actionable gap the assistant can fix. Be strict on
grounding; be lenient on style. Do not invent criteria.
```

- [ ] **Step 3: Register in `apps/api/app/prompts/active.yaml`** — add two lines (keep the file's existing alphabetical/name grouping style; read it first):

```yaml
grader_booking: 1
grader_concierge: 1
```

- [ ] **Step 4: Note the addition in `apps/api/app/prompts/CHANGELOG.md`** following its existing entry format (read the top entries and mimic; one line each for the two new prompts, dated 2026-07-10, tagged MIN-59).

- [ ] **Step 5: Verify the registry loads them**

Run: `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'You are' in registry.get('grader_booking'); assert 'You are' in registry.get('grader_concierge'); print('ok')"`
Expected: `ok`

> ⚠️ Per `docs/solutions/` (supervisor-active-yaml-is-a-pointer): a prompt dir without an `active.yaml` entry silently serves the newest version — the explicit pin in Step 3 is REQUIRED, not cosmetic.

### Task 3: Config surface — `grader` row in `agent_config`

**Files:**
- Modify: `apps/api/app/data/agent_config.py`
- Test: `apps/api/tests/scripts/test_seed_agent_config.py` (hard-coded node count → derive from `AGENT_CONFIG_NODES`)

```xml
<task id="1.3" wave="1">
  <files>apps/api/app/data/agent_config.py, apps/api/tests/scripts/test_seed_agent_config.py</files>
  <action>Add "grader" to the Support agents group and AGENT_DESCRIPTIONS so seeding creates its DB row (model override + enabled toggle surface on the existing dashboard modal for free — dashboard is driven by AGENT_CONFIG_GROUPS).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py tests/db/test_seed_agent_config.py tests/scripts/test_seed_agent_config.py -x -q</verify>
  <done>AGENT_CONFIG_NODES includes "grader"; dashboard tests green; seed will create the row idempotently on next startup</done>
</task>
```

- [ ] **Step 1: Edit `apps/api/app/data/agent_config.py`** — in `AGENT_CONFIG_GROUPS`, change the Support agents entry:

```python
    (
        "Support agents",
        "Background nodes for memory, summarization and reflection.",
        ["summarize", "reflection", "grader", "extract_memory"],
    ),
```

…and add to `AGENT_DESCRIPTIONS`:

```python
    "grader": "Grades booking/concierge answers against a rubric and asks for a fix.",
```

- [ ] **Step 2: Run the dashboard + seed tests** (some assert node lists/counts — if one asserts an exact list, update it to include `grader`; that is the test tracking the source of truth, not a behavior change):

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py tests/db/test_seed_agent_config.py tests/scripts/test_seed_agent_config.py -x -q`
Expected: PASS.

> Note: `enabled` (nullable, NULL=on) already exists on the `agent_config` ORM model — **no migration**. The dashboard modal shows the checkbox because it renders per-node from these groups (MIN-48 pattern; upsert is preserve-on-absent).

---

## Chunk 2: The grader node

### Task 4: `GraderResponse` schema + `make_grader_node` (TDD)

**Files:**
- Create: `apps/api/app/agents/grader.py`
- Test: `apps/api/tests/agents/test_grader.py`

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/grader.py, apps/api/tests/agents/test_grader.py</files>
  <action>Implement the rubric grader node: structured verdict (per-criterion name/passed/gap, convergent with RubricMiddleware's GraderResponse), delegate-to-reflection when disabled or flow ungraded, satisfied→END, needs_revision→SystemMessage feedback + goto current_flow, max_iterations/grader_error→END fail-open. Mirror make_reflection_node's shape (nodes.py:120-174).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_grader.py -x -q</verify>
  <done>All grader unit tests pass; ruff clean; no import of deepagents anywhere</done>
</task>
```

- [ ] **Step 1: Write the failing tests** — create `apps/api/tests/agents/test_grader.py`:

```python
"""Rubric grader node tests (specs/min-59-runtime-self-eval-loop).

Verifies the grader node's routing contract:
- delegates to "reflection" when disabled or the flow has no rubric (baseline A/B);
- ends the turn on a satisfied verdict (answer accepted as-is);
- loops back to the sub-agent with SystemMessage feedback on needs_revision;
- fail-open (END, answer kept) on max_iterations and on grader errors.

All tests are offline: FakeLLM.structured_responses feeds the verdicts.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext
from app.agents.grader import CriterionResult, GraderResponse, make_grader_node
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END


def _runtime(ctx: AgentContext | None = None):
    """Minimal runtime stand-in: exposes only .context, which is all nodes read."""
    return SimpleNamespace(context=ctx)


def _state(**overrides):
    state = {
        "messages": [HumanMessage(content="tìm khách sạn ở Đà Nẵng"),
                     AIMessage(content="Here are 3 hotels...")],
        "revisions": 0,
        "current_flow": "concierge",
        "user_id": None,
        "trip_id": None,
        "summary": None,
        "trip_context": None,
    }
    state.update(overrides)
    return state


def _satisfied():
    return GraderResponse(
        evaluations=[CriterionResult(name="grounding", passed=True)]
    )


def _needs_revision():
    return GraderResponse(
        evaluations=[
            CriterionResult(name="grounding", passed=True),
            CriterionResult(
                name="language",
                passed=False,
                gap="Reply in Vietnamese — the traveller wrote in Vietnamese.",
            ),
        ]
    )


def test_grader_delegates_to_reflection_when_disabled():
    """allow_grader=False routes to the reflection node — the exact baseline path."""
    llm = FakeLLM(structured_responses=[_satisfied()])  # must NOT be consumed
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext(allow_grader=False)))

    assert result.goto == "reflection"
    assert llm._structured_cursor == 0


def test_grader_delegates_for_ungraded_flow():
    """A flow without a rubric (planner) falls through to reflection untouched."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm)

    result = grade(_state(current_flow="planner"), _runtime(AgentContext()))

    assert result.goto == "reflection"
    assert llm._structured_cursor == 0


def test_grader_satisfied_ends_turn():
    """All criteria passed -> the answer ships as-is."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext()))

    assert result.goto == END


def test_grader_needs_revision_loops_with_system_feedback():
    """A failed criterion loops back to the sub-agent with SystemMessage feedback."""
    llm = FakeLLM(structured_responses=[_needs_revision()])
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext()))

    assert result.goto == "concierge"
    assert result.update["revisions"] == 1
    (feedback,) = result.update["messages"]
    assert isinstance(feedback, SystemMessage)  # NEVER HumanMessage (language-flip bug)
    assert "language" in feedback.content
    assert "Reply in Vietnamese" in feedback.content
    assert "internal review note" in feedback.content


def test_grader_stops_at_max_iterations():
    """revisions >= cap -> END without invoking the judge (fail-open, answer kept)."""
    llm = FakeLLM(structured_responses=[_needs_revision()])
    grade = make_grader_node(llm, max_iterations=2)

    result = grade(_state(revisions=2), _runtime(AgentContext()))

    assert result.goto == END
    assert llm._structured_cursor == 0


def test_grader_error_fails_open():
    """A grader exception keeps the original answer (END), never blocks the reply."""
    llm = FakeLLM(structured_responses=[])  # with_structured_output raises ValueError
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext()))

    assert result.goto == END


def test_grader_default_context_none_is_enabled():
    """No runtime context behaves like defaults (grader on) — parity with reflection."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(None))

    assert result.goto == END
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_grader.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.grader'`

- [ ] **Step 3: Implement** — create `apps/api/app/agents/grader.py`:

```python
"""Runtime rubric grader node (specs/min-59-runtime-self-eval-loop, MIN-59).

A dedicated LLM-as-judge that grades the answers of high-risk flows
(``GRADED_FLOWS``: booking, concierge) against a per-flow rubric, replacing the
generic ``reflection`` judge for those flows. Verdict semantics converge with
LangChain Deep Agents' ``RubricMiddleware`` (per-criterion name/passed/gap;
satisfied / needs_revision / max_iterations_reached / grader_error) so this
node can fold into the middleware once the path-B ``create_agent`` migration
reaches these sub-agents — see COMPARISON.md Phụ lục A.

Contract:
- disabled (``AgentContext.allow_grader=False``) or ungraded flow → delegate to
  the ``reflection`` node (bit-for-bit baseline; the with/without A/B lever);
- satisfied → END (answer ships as-is);
- needs_revision → per-criterion gaps injected as a ``SystemMessage`` (NEVER a
  ``HumanMessage`` — the reflection-humanmessage-language-flip bug) and loop
  back to ``current_flow``, bounded by the shared ``revisions`` counter;
- max iterations reached / grader error → END, fail-open: a broken judge must
  never block the traveller's reply.
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.agents.constants import DEFAULT_MAX_GRADER_ITERATIONS, GRADED_FLOWS
from app.agents.context import AgentContext
from app.agents.state import TravelAgentState
from app.prompts.registry import registry

logger = logging.getLogger(__name__)


class CriterionResult(BaseModel):
    """One rubric criterion's verdict (mirrors RubricMiddleware's shape)."""

    name: str = Field(description="The rubric criterion's exact name.")
    passed: bool = Field(description="Whether the answer satisfies the criterion.")
    gap: str = Field(
        default="",
        description="When failed: one actionable sentence on what to fix.",
    )


class GraderResponse(BaseModel):
    """Structured grader verdict: one entry per rubric criterion."""

    evaluations: list[CriterionResult]


def make_grader_node(
    llm: BaseChatModel, max_iterations: int = DEFAULT_MAX_GRADER_ITERATIONS
):
    """Return the rubric grader node for the graded flows.

    :param llm: The judge chat model (cheap tier — ``grader`` ∈ ``FAST_AGENTS``).
    :param max_iterations: Revise-loop cap; shares the ``revisions`` state
        counter with reflection so combined loops stay bounded.
    :return: A node function ``grader(state, runtime) -> Command``.
    """
    prompts = {
        flow: SystemMessage(content=registry.get(f"grader_{flow}"))
        for flow in sorted(GRADED_FLOWS)
    }

    def grader(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        ctx = runtime.context if runtime.context is not None else None
        allow_grader = ctx.allow_grader if ctx is not None else True
        flow = state.get("current_flow")

        if not allow_grader or flow not in prompts:
            # Baseline path: today's generic judge, untouched (A/B lever).
            logger.info("[agent] node=grader → reflection (delegated, flow=%s)", flow)
            return Command(goto="reflection")

        revisions = state.get("revisions", 0)
        if revisions >= max_iterations:
            logger.info("[agent] grader → END (max_iterations_reached)")
            return Command(goto=END)

        try:
            result = llm.with_structured_output(GraderResponse).invoke(
                [prompts[flow], *state["messages"]]
            )
            failed = [e for e in result.evaluations if not e.passed]
        except Exception:
            # Fail-open: a broken judge must never block the reply.
            logger.exception("[agent] grader → END (grader_error — keeping answer)")
            return Command(goto=END)

        if not failed:
            logger.info("[agent] grader → END (satisfied, flow=%s)", flow)
            return Command(goto=END)

        gaps = "\n".join(f"- {e.name}: {e.gap}" for e in failed)
        logger.info(
            "[agent] grader → %s (needs_revision: %s)",
            flow,
            ", ".join(e.name for e in failed),
        )
        return Command(
            update={
                "revisions": revisions + 1,
                "messages": [
                    SystemMessage(
                        content=(
                            "Your previous answer failed these review criteria — "
                            f"fix them and answer again:\n{gaps}\n"
                            "This is an internal review note, not a message from "
                            "the traveller — keep replying in the traveller's own "
                            "language."
                        )
                    )
                ],
            },
            goto=flow,
        )

    return grader
```

> ⚠️ ruff-on-edit hook strips imports that precede their usage — write the file in one `Write` call (import + usage together), then run `ruff check --select F821 app/agents/grader.py`.

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_grader.py -x -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Lint**

Run: `cd apps/api && ruff check app/agents/grader.py tests/agents/test_grader.py`
Expected: clean.

---

## Chunk 3: Wiring — graph edges + request-context toggle

### Task 5: Graph wiring

**Files:**
- Modify: `apps/api/app/agents/graph.py`
- Test: `apps/api/tests/agents/test_grader.py` (append wiring tests)

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/agents/graph.py, apps/api/tests/agents/test_grader.py, apps/api/tests/api/agent/test_agent_chat.py, apps/api/tests/api/agent/test_stream_persistence.py</files>
  <action>Add the grader node (pick("grader"), LLM_RETRY, destinations=(*GRADED_FLOWS, "reflection", END)) and rewire the static sub-agent edges: booking/concierge → grader, the rest → reflection. Reflection node itself is untouched.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ -x -q</verify>
  <done>Compiled graph routes booking/concierge through grader and the other three through reflection; the full agents suite is green</done>
</task>
```

- [ ] **Step 1: Write the failing wiring tests** — append to `apps/api/tests/agents/test_grader.py`:

```python
# ---------------------------------------------------------------------------
# Graph wiring — booking/concierge route through grader; others unchanged
# ---------------------------------------------------------------------------


def _compiled_edges():
    from app.agents.graph import build_graph

    fake = FakeLLM(responses=["OK"])
    compiled = build_graph(llm=fake, fast_llm=fake)
    return {(e.source, e.target) for e in compiled.get_graph().edges}


def test_graded_flows_route_through_grader():
    edges = _compiled_edges()
    assert ("booking", "grader") in edges
    assert ("concierge", "grader") in edges
    assert ("booking", "reflection") not in edges
    assert ("concierge", "reflection") not in edges


def test_ungraded_flows_keep_reflection_edge():
    edges = _compiled_edges()
    for name in ("planner", "journal", "budget"):
        assert (name, "reflection") in edges
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_grader.py -x -q`
Expected: the two new tests FAIL (`("booking", "grader") not in edges`).

- [ ] **Step 3: Wire the node** — in `apps/api/app/agents/graph.py`:

Add to the imports: `from app.agents.grader import make_grader_node` (alongside the `app.agents.nodes` import block) and `GRADED_FLOWS` via `from app.agents.constants import GRADED_FLOWS`.

After the `reflection` node registration (line 134-139), add:

```python
    builder.add_node(
        "grader",
        make_grader_node(pick("grader")),
        destinations=(*sorted(GRADED_FLOWS), "reflection", END),
        retry_policy=LLM_RETRY,
    )
```

Replace the static-edge loop (lines 145-146):

```python
    for name in SUBAGENTS:
        builder.add_edge(name, "grader" if name in GRADED_FLOWS else "reflection")
```

Update the module docstring's ASCII flow (lines 5-10) to show `booking/concierge → grader → (sub-agent | reflection | END)`.

- [ ] **Step 4: Run the full agents suite**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ -x -q`
Expected: PASS. If an existing graph-shape test asserts the old `name → reflection` edge for booking/concierge, update it — that is this feature's intended change (note it in SUMMARY `### Deviations` if anything else moves).

### Task 6: Request-context toggle from the DB row

**Files:**
- Modify: `apps/api/app/routers/agent.py:145-169`
- Test: `apps/api/tests/agents/test_agent_context.py` (the existing `_resolve_context` reflection-toggle test lives here — `test_resolve_context_disables_reflection_from_db_config`, line ~93)

```xml
<task id="3.2" wave="3">
  <files>apps/api/app/routers/agent.py, apps/api/tests/agents/test_agent_context.py, apps/api/tests/api/agent/test_identity_hybrid.py</files>
  <action>Read agent_config."grader".enabled in _resolve_context (NULL/no-row = on, exactly like reflection's toggle) and pass allow_grader to resolve_agent_context. Mirror lines 167-169.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py tests/api/agent/ -x -q</verify>
  <done>allow_grader flows DB row → AgentContext per request; context + agent API tests green</done>
</task>
```

- [ ] **Step 1: Add the grader twin** of `test_resolve_context_disables_reflection_from_db_config` in `apps/api/tests/agents/test_agent_context.py`: monkeypatch `AgentConfigCache.get` to return `enabled=False` for `"grader"` (copy the reflection test's stubbing style exactly) and assert the context resolved by `_resolve_context` has `allow_grader is False`.

- [ ] **Step 2: Implement** — in `_resolve_context` (`apps/api/app/routers/agent.py:167-169`), extend:

```python
    refl = AgentConfigCache.get("reflection")
    allow_reflection = True if (refl is None or refl.enabled is None) else refl.enabled
    grader = AgentConfigCache.get("grader")
    allow_grader = True if (grader is None or grader.enabled is None) else grader.enabled
    return resolve_agent_context(
        tier=tier, allow_reflection=allow_reflection, allow_grader=allow_grader
    )
```

- [ ] **Step 3: Run the context + agent API tests**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py tests/api/agent/ -x -q`
Expected: PASS.

> ⚠️ risk-corroboration hook: keep the token `session` off changed lines where possible (known false-positive on the auth gate); the edit above doesn't touch the `session` parameter lines — leave them alone.

---

## Chunk 4: Verification + measurement (the primary deliverable)

### Task 7: Full-suite gate + live smoke

```xml
<task id="4.1" wave="4">
  <files>(no source changes — verification only)</files>
  <action>Run the full BE suite on SQLite, then a live /agent/chat smoke on the dev stack (docker compose up -d from apps/api; force graph rebuild — prompt/graph changes are NOT hot-reloaded) exercising a concierge hotel-search turn in Vietnamese with the grader on, then off (dashboard toggle), confirming: exactly one final answer streams, no grader text leaks into SSE, and log lines show grader verdicts.</action>
  <verify>cd apps/api && make test</verify>
  <done>Full suite green; manual smoke log shows "node=grader" verdict lines; SSE shows one answer per turn in both toggle states</done>
</task>
```

- [ ] **Step 1:** `cd apps/api && make test` → all green.
- [ ] **Step 2:** Start the stack (`docker compose up -d` from `apps/api` — NOT raw `docker restart`, which loses DB DNS), then `docker exec api-api-1 touch app/main.py` to force the graph rebuild (prompt/graph wiring is baked at lifespan — uvicorn reload watches only `.py`, and the registry is a singleton).
- [ ] **Step 3:** Send a Vietnamese hotel-search turn via the web app or `curl` to `/agent/chat`; check `docker logs api-api-1` for `node=grader` lines; toggle `grader.enabled` off in the dashboard config modal and repeat — logs must show `→ reflection (delegated…)`.
- [ ] **Step 4:** Use a **fresh thread_id per attempt** (poisoned-thread gotcha — old turns replay stale behavior).

### Task 8: Latency/cost/quality measurement → REPORT.md

```xml
<task id="4.2" wave="4">
  <files>specs/min-59-runtime-self-eval-loop/REPORT.md, specs/min-59-runtime-self-eval-loop/ab-results.json, apps/api/eval/run_grader_ab.py</files>
  <action>Run the MIN-58 offline eval set (apps/api/eval/ — read its README/runner first) twice: grader off (baseline) and on, on the hotel-search + booking cases. Toggle lever = `AgentContext(allow_grader=...)` passed to `graph.invoke`. NOT the DB row: `eval/harness.py` constructs `AgentContext()` directly and never calls `_resolve_context`, so `agent_config."grader".enabled` has no effect in this harness (the plan's original claim was wrong). The flag is the same one the router would produce, one layer down. Also: the eval process must call `AgentConfigCache.configure` + `reload_from_db` itself, or every node — grader included — silently falls back to the env default model instead of its DB row. Note in methodology: disabled mode still traverses one extra grader→reflection node hop (behavior-identical, trace-visible) so latency deltas aren't misattributed. Capture per-case wall-clock latency, LLM call counts (grader invocations + revision loops from logs), and G-Eval scores. Write REPORT.md: methodology, results table (quality delta vs latency/cost delta), % of requests that triggered needs_revision, grader false-positive spot-check on ≥5 revised cases (manual read of verdict vs answer), and a go/no-go recommendation on expanding to other flows. Needs a judge API key — coordinate with the human before running (cost); note .env gotchas (OPENAI_API_KEY=test breaks LLM tests; DATABASE_URL override).</action>
  <verify>test -s specs/min-59-runtime-self-eval-loop/REPORT.md && grep -q "needs_revision" specs/min-59-runtime-self-eval-loop/REPORT.md</verify>
  <done>REPORT.md contains both runs' numbers, the revision-trigger rate, the false-positive spot-check, and an explicit expand/hold recommendation — MIN-59's checklist items 5-7</done>
</task>
```

---

## 5. Risks

- **R1 — grader misjudge (false positive) loops good answers** → cap 2 iterations; fail-open on error; REPORT.md includes a manual spot-check of revised cases (issue's checklist item).
- **R2 — SSE double-answer during revise loop** → same mechanics as reflection's revise today (new `msg_id` → `events.reset()` drops the superseded draft, `streaming/mapper.py:157-164`); grader node name ∉ `SUBAGENTS` so its own output never streams. Verified live in Task 7.
- **R3 — language flip via injected feedback** → `SystemMessage` only + explicit "traveller's own language" note (test-asserted in Task 4).
- **R4 — structured output on a cheap model fails/parses badly** → counts as `grader_error` → fail-open END; visible in logs; measured in REPORT.md.
- **R5 — booking flow: revise loop re-enters the sub-agent, NOT the HITL `plan` node** → the loop goes `grader → booking` directly (same as reflection's `goto current_flow` today), so no double-interrupt; guarded booking tools remain behind the plan gate upstream. Watch in Task 7 smoke.
- **R6 — existing tests assert the old edge shape** → expected, update alongside Task 5 (they encode the topology this feature intentionally changes).

## 6. Status Log

- 2026-07-10 — Plan written (option 2 per COMPARISON.md §5; human-confirmed). Status: proposed.
- 2026-07-10 — Tasks 1–7 implemented and green (1435 passed on a fresh DB). Live smoke on the dev
  stack confirmed the grader catching a real hallucination, the A/B toggle, and the SSE contract.
- 2026-07-10 — `/correctness-review` + `/intent-review` raised four Rule-4 findings (E1–E4 in
  `ESCALATIONS.md`); all four decided by the human and implemented. A second correctness pass then
  caught a CI-breaking test regression that a stale local `travel.db` had masked. Status: active.
- 2026-07-10 — Task 8 complete: 19-case A/B on the MIN-58 set (`eval/run_grader_ab.py`), real judge.
  Verdict: **HOLD** — grounding gains on `concierge` are largely abstention artifacts; the grader
  works on hotel search only. Ship-blockers listed in `REPORT.md`. Status: active (not shipped).
