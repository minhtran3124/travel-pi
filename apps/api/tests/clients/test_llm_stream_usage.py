"""stream_usage is OpenAI-scoped, and FakeLLM emits usage (agent-turn-metrics SC-1).

Pins: an OpenAI-profile chat model is built with ``stream_usage=True`` (so
streaming calls return ``usage_metadata``); a non-OpenAI profile receives no
``stream_usage`` kwarg (policy test — ``ChatAnthropic`` declares its own default
``True``, the guard just keeps the kwarg OpenAI-scoped); and every FakeLLM reply
carries deterministic ``usage_metadata`` + ``response_metadata.model_name``.
"""

from langchain_core.messages import HumanMessage


def test_openai_profile_model_requests_stream_usage(monkeypatch):
    # Real init_chat_model: the built OpenAI model must expose stream_usage=True.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.clients.llm import _build_chat_model

    model = _build_chat_model("openai", "gpt-4.1")
    assert model.stream_usage is True
    get_settings.cache_clear()


def test_anthropic_profile_receives_no_stream_usage_kwarg(monkeypatch):
    # Capture init_chat_model kwargs; the anthropic profile must not carry the
    # OpenAI-scoped stream_usage key.
    captured: dict = {}

    def fake_init(model, *, model_provider, **kwargs):
        captured["model_provider"] = model_provider
        captured["kwargs"] = kwargs
        from app.clients.llm import FakeLLM

        return FakeLLM()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_base_url": None,
                "llm_timeout_seconds": 120.0,
                "anthropic_api_key": None,
            },
        )(),
    )
    from app.clients.llm import _build_chat_model

    _build_chat_model("anthropic", "claude-sonnet-4-6")
    assert captured["model_provider"] == "anthropic"
    assert "stream_usage" not in captured["kwargs"]


def test_openai_profile_passes_stream_usage_kwarg(monkeypatch):
    # The same capture proves the OpenAI branch does forward the kwarg.
    captured: dict = {}

    def fake_init(model, *, model_provider, **kwargs):
        captured["model_provider"] = model_provider
        captured["kwargs"] = kwargs
        from app.clients.llm import FakeLLM

        return FakeLLM()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_base_url": None,
                "llm_timeout_seconds": 120.0,
                "openai_api_key": None,
            },
        )(),
    )
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "gpt-4.1")
    assert captured["model_provider"] == "openai"
    assert captured["kwargs"].get("stream_usage") is True


def test_fakellm_invoke_carries_usage_and_model_name():
    from app.clients.llm import FakeLLM

    reply = FakeLLM(responses=["hi there"]).invoke([HumanMessage(content="hello")])
    assert reply.usage_metadata == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert reply.response_metadata["model_name"] == "fake-llm"
