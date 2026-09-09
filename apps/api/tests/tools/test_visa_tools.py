"""Visa tool tests (specs/close-product-loop-s2-guide-and-map Task 1.1)."""

import pytest
from langchain_core.tools import ToolException


def test_get_visa_has_args_schema():
    from app.tools.visa_tools import GetVisaArgs, get_visa

    assert get_visa.args_schema is GetVisaArgs


def test_get_visa_returns_entry_for_known_country(agent_db):
    from app.tools.visa_tools import get_visa

    out = get_visa.invoke({"country": "Vietnam"})
    assert isinstance(out, dict)
    assert out["country"] == "Vietnam"
    assert out["found"] is True
    assert out["entry"] is not None
    assert out["disclaimer"]


def test_unknown_destination_returns_not_found(agent_db):
    from app.tools.visa_tools import get_visa

    out = get_visa.invoke({"country": "Xanadu"})
    assert out["found"] is False
    assert out["entry"] is None
    assert out["disclaimer"]


def test_get_visa_requires_city_or_country(agent_db):
    from app.tools.visa_tools import get_visa

    with pytest.raises(ToolException):
        get_visa.invoke({})


def test_get_visa_registered_readonly_on_concierge():
    from app.tools.registry import TOOL_METADATA, get_tools_for

    assert "get_visa" in {t.name for t in get_tools_for("concierge")}
    assert TOOL_METADATA["get_visa"] == {"readOnly": True, "destructive": False}


def test_get_visa_not_registered_elsewhere():
    from app.tools.registry import TOOLS_BY_DOMAIN

    for domain, tools in TOOLS_BY_DOMAIN.items():
        if domain == "concierge":
            continue
        assert "get_visa" not in {t.name for t in tools}
