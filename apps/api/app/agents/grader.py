"""Runtime rubric grader node (specs/min-59-runtime-self-eval-loop, MIN-59).

A dedicated LLM-as-judge that grades the answers of high-risk flows
(``GRADED_FLOWS``: booking, concierge) against a per-flow rubric, replacing the
generic ``reflection`` judge for those flows. Verdict semantics converge with
LangChain Deep Agents' ``RubricMiddleware`` (per-criterion name/passed/gap;
satisfied / needs_revision / max_iterations_reached / grader_error) so this
node can fold into the middleware once the path-B ``create_agent`` migration
reaches these sub-agents — see COMPARISON.md Phụ lục A.

Contract (every outcome writes ``state["grader_verdict"]`` — see ``GraderVerdict``):
- disabled (``AgentContext.allow_grader=False``) or ungraded flow → delegate to
  the ``reflection`` node (bit-for-bit baseline; the with/without A/B lever);
- ``satisfied`` → END (answer ships as-is);
- ``needs_revision`` → per-criterion gaps injected as a ``SystemMessage`` (NEVER a
  ``HumanMessage`` — the reflection-humanmessage-language-flip bug) and loop back
  to ``current_flow``, bounded by the turn-scoped ``grader_iterations`` counter;
- ``max_iterations_reached`` → END: the budget is exhausted. The cap is checked
  AFTER the judge call, so the answer that reaches the traveller has always been
  graded — checking it first would ship the final revision unevaluated;
- ``grader_error`` → END, fail-open: a broken judge must never block the reply.
  Transient provider errors are re-raised instead, so the node's ``LLM_RETRY``
  policy can do its job.
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
from app.agents.retry import _is_retryable_llm
from app.agents.state import TravelAgentState
from app.enums import GraderVerdict
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

    # min_length=1: an empty verdict would otherwise read as "nothing failed" and
    # silently approve the answer. A judge that says nothing is a grader_error.
    evaluations: list[CriterionResult] = Field(min_length=1)


def make_grader_node(
    llm: BaseChatModel, max_iterations: int = DEFAULT_MAX_GRADER_ITERATIONS
):
    """Return the rubric grader node for the graded flows.

    :param llm: The judge chat model (cheap tier — ``grader`` ∈ ``FAST_AGENTS``).
    :param max_iterations: Revise-loop cap, counted on the turn-scoped
        ``grader_iterations`` state field (never reflection's ``revisions``).
    :return: A node function ``grader(state, runtime) -> Command``.
    """
    prompts = {
        flow: SystemMessage(content=registry.get(f"grader_{flow}"))
        for flow in sorted(GRADED_FLOWS)
    }

    def _end(verdict: GraderVerdict) -> Command:
        return Command(update={"grader_verdict": verdict.value}, goto=END)

    def grader(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        ctx = runtime.context if runtime.context is not None else None
        allow_grader = ctx.allow_grader if ctx is not None else True
        flow = state.get("current_flow")

        if not allow_grader or flow not in prompts:
            # Baseline path: today's generic judge, untouched (A/B lever).
            logger.info("[agent] node=grader → reflection (delegated, flow=%s)", flow)
            return Command(goto="reflection")

        try:
            result = llm.with_structured_output(GraderResponse).invoke(
                [prompts[flow], *state["messages"]]
            )
            failed = [e for e in result.evaluations if not e.passed]
        except Exception as exc:
            # Transient provider failures must reach the node's LLM_RETRY policy —
            # swallowing them here would make that policy dead code and skip the
            # rubric on a single network blip.
            if _is_retryable_llm(exc):
                raise
            # Fail-open: a broken judge must never block the reply.
            logger.exception("[agent] grader → END (grader_error — keeping answer)")
            return _end(GraderVerdict.GRADER_ERROR)

        if not failed:
            logger.info("[agent] grader → END (satisfied, flow=%s)", flow)
            return _end(GraderVerdict.SATISFIED)

        names = ", ".join(e.name for e in failed)

        # The cap is checked AFTER grading, so the answer that actually reaches the
        # traveller is always the one the grader looked at. Checking it first would
        # ship the final revision ungraded and log it as "max_iterations_reached",
        # which reads like a quality verdict but only means "never evaluated".
        iterations = state.get("grader_iterations", 0)
        if iterations >= max_iterations:
            logger.info("[agent] grader → END (max_iterations_reached: %s)", names)
            return _end(GraderVerdict.MAX_ITERATIONS_REACHED)

        gaps = "\n".join(f"- {e.name}: {e.gap}" for e in failed)
        logger.info("[agent] grader → %s (needs_revision: %s)", flow, names)
        return Command(
            update={
                "grader_iterations": iterations + 1,
                "grader_verdict": GraderVerdict.NEEDS_REVISION.value,
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
