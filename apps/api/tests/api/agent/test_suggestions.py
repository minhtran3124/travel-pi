import pytest
from app.agents.constants import ALL_SUBAGENTS
from app.agents.suggestions import MAX_SUGGESTIONS, suggestions_for_flow


@pytest.mark.parametrize("flow", ALL_SUBAGENTS)
def test_known_flow_returns_bounded_prefixed_keys(flow):
    keys = suggestions_for_flow(flow)
    assert 1 <= len(keys) <= MAX_SUGGESTIONS
    assert all(k.startswith(f"{flow}.") for k in keys)


@pytest.mark.parametrize("flow", [None, "", "unknown", "supervisor"])
def test_unknown_or_none_flow_returns_empty(flow):
    assert suggestions_for_flow(flow) == []
