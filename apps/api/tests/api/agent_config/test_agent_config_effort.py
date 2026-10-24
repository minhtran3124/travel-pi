"""Effort knob + provider-aware temperature rules (service and dashboard)."""

import re

import pytest
from app.exceptions import DomainValidationError
from app.services.agent_config_service import AgentConfigService


def test_update_persists_effort(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config(
        "planner",
        provider="anthropic",
        model="claude-opus-5-5",
        temperature="",
        max_tokens="",
        effort="low",
    )
    assert svc.get_config("planner").effort == "low"


def test_update_invalid_effort_raises(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError, match="effort"):
        svc.update_config(
            "planner",
            provider="anthropic",
            model="",
            temperature="",
            max_tokens="",
            effort="turbo",
        )


@pytest.mark.parametrize("provider", ["anthropic", "claude"])
def test_update_rejects_temperature_for_anthropic(seeded_session, provider):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError, match="temperature"):
        svc.update_config(
            "planner", provider=provider, model="", temperature="0.5", max_tokens=""
        )


def test_post_anthropic_with_temperature_returns_400(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "temperature": "0.5",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "temperature" in r.text.lower()


def test_post_persists_effort(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "anthropic",
            "model": "claude-opus-5-5",
            "temperature": "",
            "max_tokens": "",
            "effort": "high",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get("/dashboard/agent-config/planner").text
    assert re.search(r'<option value="high"\s+selected', page)


def test_post_invalid_effort_returns_400(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "",
            "model": "",
            "temperature": "",
            "max_tokens": "",
            "effort": "turbo",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "url", ["/dashboard/agent-config", "/dashboard/agent-config/planner"]
)
def test_forms_expose_effort_and_provider_data(client, url):
    text = client.get(url).text
    assert 'name="effort"' in text
    assert "claude-opus-5-5" in text  # per-provider model map
    assert "NO_TEMPERATURE" in text
