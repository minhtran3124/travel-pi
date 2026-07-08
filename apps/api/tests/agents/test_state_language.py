from app.agents.state import TravelAgentState


def test_state_carries_language():
    state: TravelAgentState = {"messages": [], "language": "vi"}
    assert state.get("language") == "vi"


def test_state_language_absent_defaults_via_get():
    state: TravelAgentState = {"messages": []}
    assert state.get("language", "en") == "en"
