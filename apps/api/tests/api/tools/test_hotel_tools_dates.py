import pytest
from app.tools.hotel_tools import search_hotels
from langchain_core.tools import ToolException


def _invoke(args: dict):
    # search_hotels uses response_format="content_and_artifact"; invoking with a
    # plain args dict only returns the content string, so wrap as a ToolCall to
    # get the (content, artifact) ToolMessage — matches tests/tools/test_hotel_tools.py.
    return search_hotels.invoke(
        {"type": "tool_call", "id": "t1", "name": "search_hotels", "args": args}
    )


def test_word_dates_are_rejected_toward_resolve_date():
    with pytest.raises(ToolException, match="resolve_date"):
        _invoke(
            {
                "city": "Da Nang",
                "check_in": "ngày mai",
                "check_out": "ngày kia",
                "rooms": 1,
                "adults": 2,
                "children": 0,
            }
        )


def test_unparseable_check_in_raises():
    with pytest.raises(ToolException):
        _invoke(
            {
                "city": "Da Nang",
                "check_in": "someday",
                "check_out": "ngày kia",
                "rooms": 1,
                "adults": 2,
                "children": 0,
            }
        )
