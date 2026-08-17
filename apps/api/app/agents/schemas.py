"""Structured state objects shared by the supervisor, synthesis workers, and synthesizer.

These Pydantic models are kept separate from the SQLAlchemy/API schemas so the agent
graph has a single, versioned contract for tasks and results.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    """One unit of work handed to a synthesis worker.

    The supervisor decomposes a multi-intent turn into an ordered list of tasks.
    ``index`` preserves that order so the synthesizer can combine results in the
    same sequence the traveller asked for them.
    """

    agent: str = Field(description="Which specialist should execute this task.")
    query: str = Field(
        description="The user-facing request specific to this specialist."
    )
    index: int = Field(
        description="Position in the supervisor's ordered task list.", ge=0
    )


class TaskResult(BaseModel):
    """Structured output returned by one synthesis worker.

    Workers do not write user-facing prose. They gather facts with tools and return
    a concise, machine-readable result that the synthesizer turns into the final
    answer.
    """

    agent: str = Field(description="Specialist that produced this result.")
    index: int = Field(
        description="Position of the source task in the ordered task list.", ge=0
    )
    findings: str = Field(
        description="Concise summary of facts gathered by the specialist."
    )
    panels: list[dict] = Field(
        default_factory=list,
        description="Side-panel artifacts produced by tool calls, if any.",
    )
