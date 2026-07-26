import pytest
from app.core.agent_config_cache import AgentConfigCache
from app.data.agent_config import AGENT_CONFIG_NODES
from app.exceptions import DomainValidationError, NotFoundError
from app.services.agent_config_service import AgentConfigService


def test_list_configs_returns_every_node(seeded_session):
    svc = AgentConfigService(seeded_session)
    configs = svc.list_configs()
    assert {c.agent_name for c in configs} == set(AGENT_CONFIG_NODES)
    assert len(configs) == len(AGENT_CONFIG_NODES)


def test_list_grouped_covers_every_node_once(seeded_session):
    from app.data.agent_config import AGENT_CONFIG_GROUPS

    groups = AgentConfigService(seeded_session).list_grouped()
    assert [g.title for g in groups] == [t for t, _, _ in AGENT_CONFIG_GROUPS]
    flat = [c.agent_name for g in groups for c in g.configs]
    assert flat == AGENT_CONFIG_NODES  # every node, once, in order
    assert len(set(flat)) == len(AGENT_CONFIG_NODES)


def test_get_config_unknown_agent_raises_not_found(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(NotFoundError):
        svc.get_config("does-not-exist")


def test_update_persists_and_forces_base_url_none(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config(
        "planner",
        provider="openai",
        model="gpt-4o",
        temperature="0.5",
        max_tokens="1024",
    )
    v = svc.get_config("planner")
    assert (v.provider, v.model, v.temperature, v.max_tokens) == (
        "openai",
        "gpt-4o",
        0.5,
        1024,
    )
    assert svc._repo.get("planner").base_url is None


def test_update_blank_fields_become_none(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config("planner", provider="", model="", temperature="", max_tokens="")
    v = svc.get_config("planner")
    assert (v.provider, v.model, v.temperature, v.max_tokens) == (
        None,
        None,
        None,
        None,
    )


def test_update_invalid_provider_raises(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError):
        svc.update_config(
            "planner", provider="bogus", model="x", temperature="", max_tokens=""
        )


def test_update_invalid_temperature_raises(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError):
        svc.update_config(
            "planner", provider="", model="", temperature="hot", max_tokens=""
        )


def test_update_is_per_agent_isolated(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config(
        "booking",
        provider="anthropic",
        model="claude-sonnet-5",
        temperature="",
        max_tokens="",
    )
    svc.update_config(
        "planner", provider="openai", model="gpt-4o-mini", temperature="", max_tokens=""
    )
    b = svc.get_config("booking")
    assert (b.provider, b.model) == ("anthropic", "claude-sonnet-5")


def test_update_invalidates_cache(seeded_session):
    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache({})
    assert AgentConfigCache._dirty is False
    AgentConfigService(seeded_session).update_config(
        "planner", provider="openai", model="gpt-4o", temperature="", max_tokens=""
    )
    assert AgentConfigCache._dirty is True


def test_update_rejects_negative_temperature(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError):
        svc.update_config(
            "planner", provider="", model="", temperature="-0.5", max_tokens=""
        )


def test_update_rejects_temperature_above_2(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError):
        svc.update_config(
            "planner", provider="", model="", temperature="3", max_tokens=""
        )


def test_update_rejects_non_finite_temperature(seeded_session):
    svc = AgentConfigService(seeded_session)
    for bad in ("nan", "inf", "1e999"):
        with pytest.raises(DomainValidationError):
            svc.update_config(
                "planner", provider="", model="", temperature=bad, max_tokens=""
            )


def test_update_rejects_zero_or_negative_max_tokens(seeded_session):
    svc = AgentConfigService(seeded_session)
    for bad in ("0", "-5"):
        with pytest.raises(DomainValidationError):
            svc.update_config(
                "planner", provider="", model="", temperature="", max_tokens=bad
            )


def test_update_accepts_valid_bounds(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config(
        "planner", provider="", model="", temperature="2.0", max_tokens="1"
    )
    v = svc.get_config("planner")
    assert (v.temperature, v.max_tokens) == (2.0, 1)


def test_update_config_persists_enabled_and_view_reflects_it(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config(
        "summarize",
        provider="",
        model="",
        temperature="",
        max_tokens="",
        enabled=False,
    )
    assert svc.get_config("summarize").enabled is False
