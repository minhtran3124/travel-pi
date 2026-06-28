"""Supervisor routing node (specs/travel-agent Task 5.3).

Classifies the user's intent with structured output and hands off to one
specialist sub-agent via ``Command(goto=...)`` — the inter-agent routing seam.
Unknown intent ends gracefully with a fallback message.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.agents.context import ALL_SUBAGENTS, AgentContext
from app.agents.state import TravelAgentState, system_with_summary
from app.prompts.registry import registry

# Re-exported for callers that do `from app.agents.supervisor import SUBAGENTS`.
# Single source of truth lives in context.py (avoids circular imports).
SUBAGENTS = ALL_SUBAGENTS
_Target = Literal["planner", "concierge", "journal", "booking", "budget"]

_UPGRADE_MSG = "Booking is a premium feature. Please upgrade your plan to book trips."


class SupervisorIntent(BaseModel):
    """Structured routing decision."""

    target_agent: _Target = Field(description="Which specialist should handle this.")
    language: str = Field(default="en", description="Detected user language code.")


def make_supervisor(llm: BaseChatModel):
    """Return the supervisor node bound to a routing LLM."""
    # method="function_calling" avoids OpenAI's native json_schema parse path,
    # whose ParsedChatCompletion.parsed field trips a benign Pydantic serializer
    # warning when langchain-openai model_dump()s the response.
    router = llm.with_structured_output(SupervisorIntent, method="function_calling")
    system = SystemMessage(content=registry.get("supervisor"))

    def supervisor(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        intent = router.invoke([system_with_summary(state, system), *state["messages"]])
        target = getattr(intent, "target_agent", None)
        if target not in SUBAGENTS:
            return Command(
                update={
                    "messages": [
                        AIMessage(content="I'm not sure how to help with that yet.")
                    ]
                },
                goto=END,
            )
        # Tier gate (D.1): if the resolved context restricts sub-agents and the
        # chosen target is not in the allow-list, degrade gracefully instead of
        # routing there.  This also blocks the plan->booking HITL path for free
        # users because "plan" is only reachable via this branch.
        ctx = (
            runtime.context
            if runtime is not None and runtime.context is not None
            else AgentContext()
        )
        if ctx.allowed_subagents is not None and target not in ctx.allowed_subagents:
            return Command(
                update={"messages": [AIMessage(content=_UPGRADE_MSG)]},
                goto=END,
            )
        # Route booking through the HITL plan-approval node first.
        next_node = "plan" if target == "booking" else target
        return Command(update={"current_flow": target}, goto=next_node)

    return supervisor
