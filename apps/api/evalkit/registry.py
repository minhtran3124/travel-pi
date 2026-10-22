"""Metric registry + project taxonomy.

Metrics register themselves by name via `@register_metric` so a runner can
look them up by string (from a golden's `metrics` field or a capability
default) without evalkit importing any concrete metric module.

`Taxonomy` is the project-supplied vocabulary for `capability`/`scenario` —
core never hardcodes a travel-specific (or any other domain's) enum; see
`specs/agent-eval-pipeline/design-portability.md`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from evalkit.ports import Metric
from evalkit.types import Golden

_METRICS: dict[str, Metric] = {}


def register_metric(metric: Metric) -> Metric:
    """Class/instance decorator: register *metric* under its `.name`."""
    _METRICS[metric.name] = metric
    return metric


def get_metric(name: str) -> Metric:
    """Look up a registered metric by name; raises KeyError if unregistered."""
    try:
        return _METRICS[name]
    except KeyError:
        raise KeyError(
            f"no metric registered under {name!r}; known: {sorted(_METRICS)}"
        ) from None


def list_metrics() -> list[str]:
    """All currently registered metric names."""
    return sorted(_METRICS)


class Taxonomy(BaseModel):
    """Project-supplied vocabulary: valid capabilities/scenarios + gates."""

    capabilities: list[str]
    scenarios: list[str]
    thresholds: dict[str, float] = Field(default_factory=dict)

    def validate_golden(self, golden: Golden) -> None:
        """Raise ValueError if *golden* uses an unknown capability/scenario."""
        if golden.capability not in self.capabilities:
            raise ValueError(
                f"Golden {golden.id!r}: unknown capability {golden.capability!r}; "
                f"known: {self.capabilities}"
            )
        if golden.scenario not in self.scenarios:
            raise ValueError(
                f"Golden {golden.id!r}: unknown scenario {golden.scenario!r}; "
                f"known: {self.scenarios}"
            )

    def threshold_for(self, capability: str) -> float:
        """Per-capability pass-rate gate, default 1.0 if unspecified."""
        return self.thresholds.get(capability, 1.0)
