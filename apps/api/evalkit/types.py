"""Portable eval data model: Golden, Trace, CheckResult, CaseResult, Report.

Pydantic v2 only. These models never inherit the host app's `AppBaseModel`
(`app/schemas/base.py`) — evalkit must stay importable with zero `app.*`
dependency (`specs/agent-eval-pipeline/design-portability.md`).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ToolCall(BaseModel):
    """One tool invocation captured from an agent run."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: Any | None = None


class Golden(BaseModel):
    """One eval case: a capability/scenario-tagged input plus expectations.

    Exactly one of ``input`` (single-turn) or ``turns`` (multi-turn, replayed
    on one thread) must be set. ``capability`` and ``scenario`` are plain
    strings validated against a project-supplied taxonomy (`registry.py`),
    never core enums — see design-portability.md.
    """

    id: str
    capability: str
    scenario: str
    language: str
    suite: str
    input: str | None = None
    turns: list[str] | None = None
    expected_flow: str | None = None
    expected_tools: list[str] | None = None
    # Agent names the supervisor fans out to; order-free because tasks run in parallel.
    expected_tasks: list[str] | None = None
    # Opt-in resume of the plan-approval interrupt; the adapter owns the mechanics.
    hitl: Literal["approve", "reject"] | None = None
    expected_trajectory: list[str] | None = None
    oracle_checks: list[dict[str, Any]] | None = None
    metrics: list[str] | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_input_xor_turns(self) -> Golden:
        has_input = self.input is not None
        has_turns = self.turns is not None
        if has_input == has_turns:
            raise ValueError(
                f"Golden {self.id!r}: exactly one of 'input' or 'turns' must be set"
            )
        return self


class Trace(BaseModel):
    """What the agent actually did for one golden run."""

    reply: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    flow: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class CheckResult(BaseModel):
    """The outcome of one metric evaluated against one golden/trace pair."""

    name: str
    passed: bool
    score: float | None = None
    detail: str | None = None


class CaseResult(BaseModel):
    """All check results for one golden, plus the overall pass/fail."""

    golden_id: str
    capability: str
    scenario: str
    suite: str
    checks: list[CheckResult] = Field(default_factory=list)
    passed: bool


class Report(BaseModel):
    """The stable, versioned output contract: CI, baseline diff, and MCP all
    consume this schema. Change it additively (see design-portability.md).
    """

    schema_version: str
    run_meta: dict[str, Any] = Field(default_factory=dict)
    per_case: list[CaseResult] = Field(default_factory=list)
    per_capability: dict[str, dict[str, Any]] = Field(default_factory=dict)
