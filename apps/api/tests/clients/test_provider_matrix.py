"""Offline provider-switching matrix: every agent resolves the right provider/model/kwargs (issue #268)."""

import pytest
from app.agents.constants import FAST_MODEL_AGENTS
from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride
from app.core.config import get_settings
from app.data.agent_config import AGENT_CONFIG_NODES

AGENTS = [*AGENT_CONFIG_NODES, "trip_research", "trip_research_grader"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "FAST_LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    AgentConfigCache.clear()
    yield
    AgentConfigCache.clear()
    get_settings.cache_clear()


@pytest.fixture
def built(monkeypatch):
    calls: list[dict] = []

    def fake_init(model, *, model_provider, **kwargs):
        calls.append({"model": model, "sdk": model_provider, "kwargs": kwargs})
        return object()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)

    def resolve(agent: str) -> dict:
        from app.clients.llm import get_agent_llm

        get_agent_llm(agent)
        return calls[-1]

    return resolve


def _global(monkeypatch, provider, **env):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def _assert_clean(call):
    """No cross-vendor leakage in the model name or kwargs."""
    if call["sdk"] == "anthropic":
        assert call["model"].startswith("claude-")
        assert "reasoning_effort" not in call["kwargs"]
        assert "temperature" not in call["kwargs"]
        assert "stream_usage" not in call["kwargs"]
        assert call["kwargs"]["max_tokens"] == 16000
    else:
        assert not call["model"].startswith("claude-")
        assert "output_config" not in call["kwargs"]


@pytest.mark.parametrize("agent", AGENTS)
def test_all_anthropic_uses_sonnet_and_haiku_tiers(monkeypatch, built, agent):
    _global(monkeypatch, "anthropic")
    call = built(agent)
    assert call["sdk"] == "anthropic"
    assert call["model"] == (
        "claude-haiku-5-5" if agent in FAST_MODEL_AGENTS else "claude-sonnet-5-5"
    )
    _assert_clean(call)


def test_supervisor_classification_runs_on_the_fast_tier(monkeypatch, built):
    """A cold/NULL-model agent_config row must not promote the supervisor to the main model (#270)."""
    assert "supervisor" in FAST_MODEL_AGENTS
    _global(monkeypatch, "anthropic")
    assert built("supervisor")["model"] == "claude-haiku-5-5"


@pytest.mark.parametrize("agent", AGENTS)
def test_all_openai_uses_openai_defaults(monkeypatch, built, agent):
    _global(monkeypatch, "openai")
    call = built(agent)
    assert call["sdk"] == "openai"
    assert call["model"] == ("gpt-5-mini" if agent in FAST_MODEL_AGENTS else "gpt-5")
    assert call["kwargs"]["stream_usage"] is True
    _assert_clean(call)


def test_env_models_override_provider_defaults(monkeypatch, built):
    _global(
        monkeypatch,
        "anthropic",
        LLM_MODEL="claude-opus-5-5",
        FAST_LLM_MODEL="claude-haiku-5-5",
    )
    assert built("planner")["model"] == "claude-opus-5-5"
    assert built("summarize")["model"] == "claude-haiku-5-5"


def test_mixed_supervisor_openai_planner_and_research_anthropic(monkeypatch, built):
    _global(
        monkeypatch,
        "openai",
        LLM_MODEL="gpt-5.5",
        LLM_BASE_URL="https://oai.example/v1",
    )
    AgentConfigCache.sync_from_cache(
        {
            "planner": AgentModelOverride(provider="anthropic", effort="high"),
            "trip_research": AgentModelOverride(
                provider="anthropic", model="claude-opus-5-5", temperature=0.3
            ),
            "trip_research_grader": AgentModelOverride(provider="anthropic"),
        }
    )
    sup = built("supervisor")
    assert (sup["sdk"], sup["model"]) == ("openai", "gpt-5-mini")  # fast tier
    assert sup["kwargs"]["base_url"] == "https://oai.example/v1"
    _assert_clean(sup)

    planner = built("planner")
    # The global OpenAI model and gateway must not leak into the Anthropic agent.
    assert (planner["sdk"], planner["model"]) == ("anthropic", "claude-sonnet-5-5")
    assert planner["kwargs"]["output_config"] == {"effort": "high"}
    assert "base_url" not in planner["kwargs"]
    _assert_clean(planner)

    research = built("trip_research")
    assert (research["sdk"], research["model"]) == ("anthropic", "claude-opus-5-5")
    _assert_clean(research)  # temperature dropped for Anthropic

    grader = built("trip_research_grader")
    assert (grader["sdk"], grader["model"]) == ("anthropic", "claude-haiku-5-5")

    # Untouched agents stay on the global provider.
    assert built("concierge")["sdk"] == "openai"
    assert built("summarize")["model"] == "gpt-5-mini"


def test_mixed_inverse_global_anthropic_one_agent_openai(monkeypatch, built):
    _global(monkeypatch, "anthropic", LLM_MODEL="claude-sonnet-5-5")
    AgentConfigCache.sync_from_cache(
        {"supervisor": AgentModelOverride(provider="openai", effort="max")}
    )
    sup = built("supervisor")
    assert (sup["sdk"], sup["model"]) == ("openai", "gpt-5-mini")  # fast, not claude
    assert sup["kwargs"]["reasoning_effort"] == "xhigh"
    _assert_clean(sup)
    assert built("planner")["sdk"] == "anthropic"


def test_stale_cross_vendor_model_in_row_falls_back_to_provider_default(
    monkeypatch, built, caplog
):
    _global(monkeypatch, "anthropic")
    AgentConfigCache.sync_from_cache(
        {"planner": AgentModelOverride(provider="anthropic", model="gpt-5.4-nano")}
    )
    call = built("planner")
    assert call["model"] == "claude-sonnet-5-5"
    assert "does not fit provider" in caplog.text


def test_row_model_without_provider_on_anthropic_global_is_guarded(monkeypatch, built):
    _global(monkeypatch, "anthropic")
    AgentConfigCache.sync_from_cache(
        {"summarize": AgentModelOverride(model="gpt-5-mini")}
    )
    assert built("summarize")["model"] == "claude-haiku-5-5"


def test_embeddings_follow_openai_key_not_chat_provider(monkeypatch):
    from app.core.embeddings import get_embeddings
    from langchain_core.embeddings import DeterministicFakeEmbedding

    _global(monkeypatch, "anthropic")
    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    assert isinstance(get_embeddings(), DeterministicFakeEmbedding)
