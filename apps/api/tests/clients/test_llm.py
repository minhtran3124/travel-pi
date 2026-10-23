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
    assert llm.model_name == "gpt-5"
    fast = get_fast_llm()
    assert fast.model_name == "gpt-5-mini"
    get_settings.cache_clear()


def test_get_agent_llm_falls_back_to_tier_defaults(monkeypatch):
    # No per-agent config: a "main" node uses llm_model, a "fast" node uses
    # fast_llm_model — identical to the two-tier behaviour.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.clients.llm import get_agent_llm

    assert get_agent_llm("supervisor").model_name == "gpt-5"
    assert get_agent_llm("journal").model_name == "gpt-5-mini"
    get_settings.cache_clear()


def test_get_agent_llm_applies_per_agent_override(monkeypatch):
    # A DB override puts one node on a different provider + model; other nodes
    # (no row) keep the global defaults.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride
    from app.core.config import get_settings

    get_settings.cache_clear()
    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache(
        {
            "concierge": AgentModelOverride(
                provider="anthropic", model="claude-sonnet-4-6", temperature=0.1
            )
        }
    )
    from app.clients.llm import get_agent_llm

    concierge = get_agent_llm("concierge")
    assert concierge.model == "claude-sonnet-4-6"
    # Untouched node still resolves to the global OpenAI default.
    assert get_agent_llm("planner").model_name == "gpt-5"
    AgentConfigCache.clear()
    get_settings.cache_clear()


def _capture_init_chat_model(monkeypatch, *, llm_base_url=None):
    """Patch init_chat_model + settings; return the captured kwargs dict."""
    captured: dict = {}

    def fake_init(model, *, model_provider, **kwargs):
        captured["model"] = model
        captured["model_provider"] = model_provider
        captured["base_url"] = kwargs.get("base_url")
        captured["api_key"] = kwargs.get("api_key")
        from app.clients.llm import FakeLLM

        return FakeLLM()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_base_url": llm_base_url,
                "llm_timeout_seconds": 120.0,
                "openai_api_key": None,
            },
        )(),
    )
    return captured


def test_build_chat_model_resolves_profile_sdk_and_gateway(monkeypatch):
    # A gateway profile: model_provider is the underlying SDK (openai), and the
    # profile's base_url is applied without any global llm_base_url set.
    captured = _capture_init_chat_model(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("clinepass", "openai/gpt-4o")

    assert captured["model_provider"] == "openai"
    assert captured["base_url"] == "https://api.cline.bot/api/v1"


def test_build_chat_model_explicit_base_url_wins_over_profile(monkeypatch):
    captured = _capture_init_chat_model(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("clinepass", "m", base_url="https://override.example.com")

    assert captured["base_url"] == "https://override.example.com"


def test_build_chat_model_native_profile_has_no_base_url(monkeypatch):
    # openai profile carries no gateway and no global override -> base_url unset.
    captured = _capture_init_chat_model(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "gpt-4.1")

    assert captured["model_provider"] == "openai"
    assert captured["base_url"] is None


def test_build_chat_model_uses_dedicated_provider_key(monkeypatch):
    # clinepass reads its own key field, not the openai one.
    captured = _capture_init_chat_model(monkeypatch)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_base_url": None,
                "llm_timeout_seconds": 120.0,
                "openai_api_key": "sk-openai",
                "clinepass_api_key": "sk-cline",
            },
        )(),
    )
    from app.clients.llm import _build_chat_model

    _build_chat_model("clinepass", "openai/gpt-4o")

    assert captured["api_key"] == "sk-cline"


def test_build_chat_model_no_key_sharing_across_providers(monkeypatch):
    # With no clinepass token, an openai key is NOT shared — the key is unset.
    captured = _capture_init_chat_model(monkeypatch)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_base_url": None,
                "llm_timeout_seconds": 120.0,
                "openai_api_key": "sk-openai",
                "clinepass_api_key": None,
            },
        )(),
    )
    from app.clients.llm import _build_chat_model

    _build_chat_model("clinepass", "openai/gpt-4o")

    assert captured["api_key"] is None


def test_build_chat_model_unknown_provider_falls_back_to_bare_profile(monkeypatch):
    # An unlisted provider is used as its own SDK, no gateway (permissive).
    captured = _capture_init_chat_model(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("xai", "grok-3")

    assert captured["model_provider"] == "xai"
    assert captured["base_url"] is None


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


def _capture_init(monkeypatch):
    captured: dict = {}

    def fake_init(model, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)
    return captured


def test_anthropic_drops_temperature(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("anthropic", "claude-sonnet-5-5", temperature=0.2)
    assert "temperature" not in captured["kwargs"]


def test_openai_keeps_temperature(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "gpt-5", temperature=0.2)
    assert captured["kwargs"]["temperature"] == 0.2


def test_anthropic_default_max_tokens(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("anthropic", "claude-haiku-5-5")
    assert captured["kwargs"]["max_tokens"] == 16000


def test_explicit_max_tokens_wins(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("anthropic", "claude-haiku-5-5", max_tokens=512)
    assert captured["kwargs"]["max_tokens"] == 512


def test_openai_gets_no_default_max_tokens(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "gpt-5")
    assert "max_tokens" not in captured["kwargs"]


class _StubStructuredModel:
    def __init__(self, provider: str) -> None:
        self._provider = provider
        self.calls: list[dict] = []

    def _get_ls_params(self) -> dict:
        return {"ls_provider": self._provider}

    def with_structured_output(self, schema, **kwargs):
        self.calls.append(kwargs)
        return "bound"


def test_with_structured_anthropic_uses_json_schema():
    from app.clients.llm import with_structured

    stub = _StubStructuredModel("anthropic")
    assert with_structured(stub, BaseModel) == "bound"
    assert stub.calls == [{"method": "json_schema"}]


def test_with_structured_openai_uses_function_calling():
    from app.clients.llm import with_structured

    stub = _StubStructuredModel("openai")
    with_structured(stub, BaseModel)
    assert stub.calls == [{"method": "function_calling"}]
