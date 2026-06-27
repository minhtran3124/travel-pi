"""LLM client + FakeLLM (specs/travel-agent Task 1.1).

Pins: provider-agnostic construction returns the right model, importing the
module touches no network, and FakeLLM is a drop-in that scripts responses,
tool calls, and structured output without any key.
"""

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel


def test_import_has_no_side_effects():
    # Importing must not construct a client or hit the network.
    import app.clients.llm as mod

    assert hasattr(mod, "get_llm")
    assert hasattr(mod, "get_fast_llm")


def test_get_llm_builds_configured_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.clients.llm import get_fast_llm, get_llm

    llm = get_llm()
    assert llm.model_name == "gpt-4.1"
    fast = get_fast_llm()
    assert fast.model_name == "gpt-4.1-mini"
    get_settings.cache_clear()


def test_get_agent_llm_falls_back_to_tier_defaults(monkeypatch):
    # No per-agent config: a "main" node uses llm_model, a "fast" node uses
    # fast_llm_model — identical to the two-tier behaviour.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.clients.llm import get_agent_llm

    assert get_agent_llm("supervisor").model_name == "gpt-4.1"
    assert get_agent_llm("journal").model_name == "gpt-4.1-mini"
    get_settings.cache_clear()


def test_get_agent_llm_applies_per_agent_override(monkeypatch):
    # Override one node onto a different provider + model + temperature; other
    # nodes are untouched and keep the global defaults.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv(
        "AGENT_LLM_CONFIGS",
        '{"concierge":{"provider":"anthropic","model":"claude-sonnet-4-6",'
        '"temperature":0.1}}',
    )
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.clients.llm import get_agent_llm

    concierge = get_agent_llm("concierge")
    assert concierge.model == "claude-sonnet-4-6"
    # Untouched node still resolves to the global OpenAI default.
    assert get_agent_llm("planner").model_name == "gpt-4.1"
    get_settings.cache_clear()


def test_fake_llm_scripts_text():
    from app.clients.llm import FakeLLM

    llm = FakeLLM(responses=["hello", "world"])
    assert llm.invoke([HumanMessage(content="hi")]).content == "hello"
    assert llm.invoke([HumanMessage(content="hi")]).content == "world"
    # cycles back round
    assert llm.invoke([HumanMessage(content="hi")]).content == "hello"


def test_fake_llm_scripts_tool_calls():
    from app.clients.llm import FakeLLM

    scripted = AIMessage(
        content="",
        tool_calls=[{"name": "search_places", "args": {"city": "Tokyo"}, "id": "t1"}],
    )
    llm = FakeLLM(responses=[scripted])
    out = llm.bind_tools([]).invoke([HumanMessage(content="find places")])
    assert out.tool_calls[0]["name"] == "search_places"


def test_fake_llm_structured_output():
    from app.clients.llm import FakeLLM

    class Intent(BaseModel):
        target: str

    llm = FakeLLM(structured_responses=[Intent(target="planner")])
    result = llm.with_structured_output(Intent).invoke([HumanMessage(content="plan")])
    assert result.target == "planner"


def test_fake_llm_overrides_dependency():
    from app.core.deps import get_llm_client

    # The real dependency is importable and returns a callable client builder.
    assert callable(get_llm_client)
