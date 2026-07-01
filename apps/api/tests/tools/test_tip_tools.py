"""Local-tips tool tests (specs/local-tip-agent-tool, specs/standardize-tool-args-schema Task 2.4)."""

import json

import pytest
from langchain_core.tools import ToolException
from pydantic import ValidationError

TIP_CATEGORY_VALUES = [
    "transport",
    "money",
    "safety",
    "culture",
    "food",
    "connectivity",
    "health",
    "etiquette",
    "best_time",
    "language",
]


def test_get_local_tips_has_args_schema():
    from app.tools.tip_tools import GetLocalTipsArgs, get_local_tips

    assert get_local_tips.args_schema is GetLocalTipsArgs


def test_get_local_tips_schema_lists_all_category_values():
    from app.tools.tip_tools import get_local_tips

    schema_json = json.dumps(get_local_tips.get_input_schema().model_json_schema())
    for value in TIP_CATEGORY_VALUES:
        assert value in schema_json


def test_get_local_tips_invalid_category_raises_on_invoke():
    from app.tools.tip_tools import get_local_tips

    with pytest.raises(ValidationError):
        get_local_tips.invoke({"country": "Vietnam", "category": "not-a-category"})


def test_get_local_tips_returns_response_for_seeded_country(agent_db):
    from app.tools.tip_tools import get_local_tips

    out = get_local_tips.invoke({"country": "Vietnam"})
    assert isinstance(out, dict)
    assert out["country"] == "Vietnam"
    assert out["count"] >= 1
    assert isinstance(out["tips"], list) and out["tips"]


def test_get_local_tips_requires_city_or_country(agent_db):
    from app.tools.tip_tools import get_local_tips

    with pytest.raises(ToolException):
        get_local_tips.invoke({})


def test_get_local_tips_category_filter(agent_db):
    from app.tools.tip_tools import get_local_tips

    out = get_local_tips.invoke({"country": "Vietnam", "category": "money"})
    assert all(t["category"] == "money" for t in out["tips"])


def test_get_local_tips_unknown_location_returns_zero(agent_db):
    from app.tools.tip_tools import get_local_tips

    out = get_local_tips.invoke({"country": "Atlantis"})
    assert out["count"] == 0


def test_get_local_tips_registered_readonly_on_concierge():
    from app.tools.registry import TOOL_METADATA, get_tools_for

    assert "get_local_tips" in {t.name for t in get_tools_for("concierge")}
    assert TOOL_METADATA["get_local_tips"] == {"readOnly": True, "destructive": False}
