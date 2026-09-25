import re

from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.engine import get_session_factory
from app.services.agent_config_service import AgentConfigService


def test_list_page_shows_all_agents(client):
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    for name in AGENT_CONFIG_NODES:
        assert name in r.text


def test_list_page_is_card_grid_with_edit_modal(client):
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    assert 'class="agent-grid"' in r.text
    assert r.text.count('class="agent-card"') == len(AGENT_CONFIG_NODES)
    assert 'id="agent-modal"' in r.text
    assert 'id="agent-form"' in r.text
    assert '<select name="provider"' in r.text
    for field in ("model", "temperature", "max_tokens"):
        assert f'name="{field}"' in r.text
    for name in AGENT_CONFIG_NODES:
        assert f'data-agent="{name}"' in r.text


def test_list_page_renders_role_sections(client):
    from app.data.agent_config import AGENT_CONFIG_GROUPS

    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    assert r.text.count('class="ac-section"') == len(AGENT_CONFIG_GROUPS)
    for title, _blurb, _names in AGENT_CONFIG_GROUPS:
        assert title in r.text


def test_list_page_shows_saved_banner(client):
    r = client.get("/dashboard/agent-config?saved=1")
    assert r.status_code == 200
    assert "saved" in r.text.lower()


def test_post_redirects_to_list_page(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "openai",
            "model": "gpt-5",
            "temperature": "",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/dashboard/agent-config?saved=1"


def test_edit_page_renders_for_known_agent(client):
    r = client.get("/dashboard/agent-config/planner")
    assert r.status_code == 200
    assert "planner" in r.text


def test_edit_page_unknown_agent_404(client):
    r = client.get("/dashboard/agent-config/nope")
    assert r.status_code == 404


def test_post_persists_and_redirects(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": "0.3",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "saved=1" in r.headers["location"]
    assert "gpt-4o" in client.get("/dashboard/agent-config/planner").text


def test_post_invalid_provider_returns_400_and_preserves_input(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "bogus",
            "model": "keep-me",
            "temperature": "",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "keep-me" in r.text
    assert "bogus" in r.text or "provider" in r.text.lower()


def test_post_unknown_agent_404(client):
    r = client.post(
        "/dashboard/agent-config/nope",
        data={"provider": "", "model": "", "temperature": "", "max_tokens": ""},
        follow_redirects=False,
    )
    assert r.status_code == 404


def test_reflection_edit_page_shows_enabled_checkbox(client):
    resp = client.get("/dashboard/agent-config/reflection")
    assert resp.status_code == 200
    assert 'name="enabled"' in resp.text
    assert 'name="enabled_marker"' in resp.text


def test_non_reflection_edit_page_has_no_checkbox(client):
    resp = client.get("/dashboard/agent-config/supervisor")
    assert resp.status_code == 200
    assert 'name="enabled_marker"' not in resp.text


def test_saving_reflection_unchecked_disables_it(client, tmp_db):
    # Unchecked checkbox submits no `enabled`; the hidden marker signals intent.
    resp = client.post(
        "/dashboard/agent-config/reflection",
        data={
            "provider": "",
            "model": "",
            "temperature": "",
            "max_tokens": "",
            "enabled_marker": "1",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    with get_session_factory(tmp_db)() as session:
        view = AgentConfigService(session).get_config("reflection")
    assert view.enabled is False


def test_modal_edit_preserves_disabled_reflection(client, tmp_db):
    # A modal model-only edit (no enabled_marker) must not re-enable reflection.
    disable = client.post(
        "/dashboard/agent-config/reflection",
        data={
            "provider": "",
            "model": "",
            "temperature": "",
            "max_tokens": "",
            "enabled_marker": "1",
        },
        follow_redirects=False,
    )
    assert disable.status_code == 303
    # Modal edits only the model — it never submits an enabled_marker.
    modal = client.post(
        "/dashboard/agent-config/reflection",
        data={
            "provider": "",
            "model": "gpt-4o",
            "temperature": "",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert modal.status_code == 303
    with get_session_factory(tmp_db)() as session:
        view = AgentConfigService(session).get_config("reflection")
    assert view.enabled is False


def test_modal_exposes_reflection_toggle(client):
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    assert "data-enabled" in r.text
    assert 'id="am-enabled"' in r.text
    assert 'id="am-enabled-marker"' in r.text


def test_reflection_checkbox_has_hidden_override_rule(client):
    # An ID-scoped rule must beat `.am-field { display: flex }` so the checkbox
    # stays hidden on non-reflection agents (specificity, not !important).
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    rule = re.search(
        r"#am-enabled-field\[hidden\]\s*\{\s*display:\s*none;?\s*\}", r.text
    )
    assert rule is not None


def test_modal_save_preserves_null_for_non_reflection(client, tmp_db):
    # A non-reflection modal save (no marker) must leave enabled None, not True.
    resp = client.post(
        "/dashboard/agent-config/supervisor",
        data={
            "provider": "",
            "model": "gpt-4o",
            "temperature": "",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    with get_session_factory(tmp_db)() as session:
        view = AgentConfigService(session).get_config("supervisor")
    assert view.enabled is None


def test_post_unpriced_model_saves_and_warns_on_list_page(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "openai",
            "model": "gpt-4o",  # not in MODEL_PRICES_USD_PER_1M
            "temperature": "",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    location = r.headers["location"]
    assert "saved=1" in location
    assert "unpriced_model=gpt-4o" in location
    assert "gpt-4o" in client.get("/dashboard/agent-config/planner").text  # save stood

    page = client.get(location)
    assert 'class="ac-warn"' in page.text
    assert "planner" in page.text
    assert "NULL cost" in page.text


def test_list_page_escapes_unpriced_banner_params(client):
    r = client.get(
        "/dashboard/agent-config?saved=1&unpriced_agent=x&unpriced_model=%3Cscript%3E"
    )
    assert "<script>" not in r.text.split('class="ac-warn"', 1)[1].split("</p>", 1)[0]
    assert "&lt;script&gt;" in r.text


def test_post_priced_model_has_no_warning(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "openai",
            "model": "gpt-5",
            "temperature": "",
            "max_tokens": "",
        },
        follow_redirects=False,
    )
    assert "unpriced" not in r.headers["location"]
    assert 'class="ac-warn"' not in client.get(r.headers["location"]).text
