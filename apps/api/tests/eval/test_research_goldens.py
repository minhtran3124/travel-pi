"""Research routing goldens (trip-research-deep-agent, Task 5.1 / SC-21).

The two ``research-routing-*`` goldens live under the existing ``routing``
capability (a new capability would perturb the committed eval baseline —
design.md §12), carry ``expected_flow == "research"``, and validate against the
real project TAXONOMY (`eval/adapters/config.py`).
"""

from __future__ import annotations

from eval.adapters.config import DATASET_DIR, TAXONOMY
from evalkit.dataset import JsonDatasetStore

RESEARCH_GOLDEN_IDS = ("research-routing-en-01", "research-routing-vi-01")


def _routing_by_id() -> dict:
    store = JsonDatasetStore(DATASET_DIR, TAXONOMY)
    return {case.id: case for case in store.load(capability="routing")}


def test_research_goldens_exist_under_routing_capability():
    by_id = _routing_by_id()
    for golden_id in RESEARCH_GOLDEN_IDS:
        case = by_id.get(golden_id)
        assert case is not None, f"golden {golden_id!r} is missing from routing.json"
        assert case.capability == "routing"


def test_research_goldens_expect_research_flow():
    by_id = _routing_by_id()
    for golden_id in RESEARCH_GOLDEN_IDS:
        case = by_id[golden_id]
        assert case.expected_flow == "research"
        assert "flow_match" in (case.metrics or [])


def test_research_goldens_cover_en_and_vi():
    by_id = _routing_by_id()
    assert by_id["research-routing-en-01"].language == "en"
    assert by_id["research-routing-vi-01"].language == "vi"


def test_research_flow_is_a_known_supervisor_target():
    """The goldens' expected flow must be a real routing target."""
    from app.agents.constants import ALL_SUBAGENTS

    assert "research" in ALL_SUBAGENTS
