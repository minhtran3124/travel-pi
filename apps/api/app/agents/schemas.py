"""Structured task/result models for the supervisor, synthesis workers, and synthesizer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    """One unit of work handed to a synthesis worker; ``index`` preserves ask order."""

    agent: str = Field(description="Which specialist should execute this task.")
    query: str = Field(
        description="The user-facing request specific to this specialist."
    )
    index: int = Field(
        description="Position in the supervisor's ordered task list.", ge=0
    )


class TaskResult(BaseModel):
    """Machine-readable result from one synthesis worker; the synthesizer writes prose."""

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
