"""travel-pi eval taxonomy: capabilities, scenarios, thresholds, dataset paths.

`evalkit` treats capability/scenario as project-supplied strings, never core
enums (`specs/agent-eval-pipeline/design-portability.md`) — this module is
the travel-pi vocabulary, built once as a `Taxonomy` (`evalkit/registry.py`)
for the dataset store to validate goldens against and the runner to
threshold per-capability pass rates on.
"""

from __future__ import annotations

import os
from pathlib import Path

from evalkit.registry import Taxonomy

# PLAN.md §4 — the capability x scenario golden matrix. One dataset file per
# capability (`eval/datasets/<capability>.json`), so these names are also the
# filenames; `routing` covers supervisor hand-off, which the legacy routing
# smoke suite used to own.
CAPABILITIES: list[str] = [
    "flight_search",
    "hotels",
    "booking",
    "budget",
    "journal",
    "memory",
    "language",
    "dates",
    "errors",
    "routing",
]

SCENARIOS: list[str] = [
    "happy",
    "ambiguous",
    "multi_turn",
    "tool_failure",
    "adversarial",
]

DEFAULT_THRESHOLD = 0.7

TAXONOMY = Taxonomy(
    capabilities=CAPABILITIES,
    scenarios=SCENARIOS,
    thresholds=dict.fromkeys(CAPABILITIES, DEFAULT_THRESHOLD),
)

# apps/api/eval/
EVAL_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = EVAL_DIR / "datasets"
BASELINE_DIR = EVAL_DIR / "baselines"

# Model for the oracle extractor (`eval/adapters/extractor.py`), which parses
# the agent's reply into claimed values. It is EVAL infrastructure, not a graph
# node, so its model is configured here rather than seeded into the product's
# `agent_config` table (where it would surface on the config dashboard as an
# agent nobody serves).
#
# Unset falls back to the env `FAST_LLM_MODEL`. That default is only usable if
# the provider key can actually call it — this repo's key cannot call the
# `gpt-5-mini` default, which is exactly the misconfiguration `ExtractionError`
# now reports instead of charging it to the agent. Set `EVAL_EXTRACTOR_MODEL`
# to a model the key can call (here: `gpt-5.4-mini`, what the DB serves).
EXTRACTOR_MODEL: str | None = os.environ.get("EVAL_EXTRACTOR_MODEL") or None
