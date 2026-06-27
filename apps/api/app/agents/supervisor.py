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
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.agents.state import TravelAgentState, system_with_summary
from app.prompts.registry import registry

SUBAGENTS = ("planner", "concierge", "journal", "booking", "budget")
_Target = Literal["planner", "concierge", "journal", "booking", "budget"]


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

    def supervisor(state: TravelAgentState) -> Command:
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
        # Route booking through the HITL plan-approval node first.
        next_node = "plan" if target == "booking" else target
        return Command(update={"current_flow": target}, goto=next_node)

    return supervisor
