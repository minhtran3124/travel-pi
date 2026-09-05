"""Content-level pins for the budget agent's trip-aware flow (specs/agent-budget-trip-context, SC-6).

Asserts on wording only — never on a version number (see
``tests/prompts/test_active_versions_load.py`` for why literal pins were removed).
"""

import pytest


@pytest.mark.parametrize(
    "needle",
    [
        "get_trip_summary",
        "estimate_trip_budget",
        "set_trip_budget",
        "trip_dates_unknown",
    ],
)
def test_active_budget_prompt_names_trip_tools(needle):
    from app.prompts.registry import registry

    assert needle in registry.get("budget")


def test_active_supervisor_prompt_routes_budget_caps():
    from app.prompts.registry import registry

    assert "budget caps" in registry.get("supervisor")
