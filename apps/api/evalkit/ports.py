"""Ports: the seams a host project implements to plug evalkit into itself.

Each `Protocol` here is the entire contract for one concern (running the
agent, computing ground truth, scoring a trace, loading/saving data).
Adopting evalkit in another project means implementing these against that
project's own agent/services — evalkit never depends on the implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from evalkit.types import CheckResult, Golden, Report, Trace


@runtime_checkable
class AgentRunner(Protocol):
    """Drives the host agent for one golden and captures what happened."""

    def run(self, golden: Golden) -> Trace: ...


@runtime_checkable
class Oracle(Protocol):
    """Project-computed ground truth, looked up by kind (DB-as-Oracle)."""

    def lookup(self, kind: str, params: dict[str, Any]) -> Any: ...

    def supports(self, kind: str) -> bool: ...


@runtime_checkable
class Metric(Protocol):
    """A single scoring rule over one (golden, trace) pair."""

    name: str

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None
    ) -> CheckResult: ...


@runtime_checkable
class DatasetStore(Protocol):
    """Loads/saves the golden dataset (e.g. one JSON file per capability)."""

    def load(self, **filters: Any) -> list[Golden]: ...

    def save(self, goldens: list[Golden]) -> None: ...


@runtime_checkable
class BaselineStore(Protocol):
    """Persists and retrieves a committed baseline Report for regression gating."""

    def save(self, report: Report, path: str) -> None: ...

    def load(self, path: str) -> Report: ...
