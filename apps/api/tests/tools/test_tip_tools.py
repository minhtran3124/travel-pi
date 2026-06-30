"""Local-tips tool tests (specs/local-tip-agent-tool)."""

import pytest
from langchain_core.tools import ToolException


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
