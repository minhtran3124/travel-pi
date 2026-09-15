from app.agents.state import TravelAgentState, with_reply_language
from langchain_core.messages import SystemMessage


def test_state_carries_language():
    state: TravelAgentState = {"messages": [], "language": "vi"}
    assert state.get("language") == "vi"


def test_state_language_absent_defaults_via_get():
    state: TravelAgentState = {"messages": []}
    assert state.get("language", "en") == "en"


# ---------------------------------------------------------------------------
# with_reply_language: every sub-agent reply is pinned to the supervisor-detected
# conversation language read from shared state (MIN-68 follow-up)
# ---------------------------------------------------------------------------

_BASE = SystemMessage(content="style rules")


def test_reply_language_injected_when_detected():
    out = with_reply_language(_BASE, {"messages": [], "language": "en"})
    assert out is not _BASE
    assert "style rules" in out.content
    assert "en" in out.content
    assert "traveller's own language" in out.content


def test_reply_language_carries_detected_code():
    out = with_reply_language(_BASE, {"messages": [], "language": "vi"})
    assert "vi" in out.content


def test_reply_language_noop_without_detected_language():
    out = with_reply_language(_BASE, {"messages": []})
    assert out is _BASE


def test_reply_language_noop_when_language_empty():
    out = with_reply_language(_BASE, {"messages": [], "language": ""})
    assert out is _BASE


def test_reply_language_prefix_is_byte_stable():
    out = with_reply_language(_BASE, {"messages": [], "language": "en"})
    assert "Reply in the traveller's own language: en" in out.content


def test_reply_language_allows_explicitly_requested_language():
    """gh-148: an explicit "switch to English" request sets the reply language."""
    out = with_reply_language(_BASE, {"messages": [], "language": "en"})
    normalized = " ".join(out.content.split())
    assert "explicitly asked" in normalized
