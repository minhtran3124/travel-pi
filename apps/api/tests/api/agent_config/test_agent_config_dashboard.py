from app.data.agent_config import AGENT_CONFIG_NODES


def test_list_page_shows_all_agents(client):
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    for name in AGENT_CONFIG_NODES:
        assert name in r.text


def test_list_page_is_card_grid_with_edit_modal(client):
    # Card grid + in-page edit modal (no separate detail page navigation).
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    assert 'class="agent-grid"' in r.text
    assert r.text.count('class="agent-card"') == len(AGENT_CONFIG_NODES)
    assert 'id="agent-modal"' in r.text
    assert 'id="agent-form"' in r.text
    # the modal carries the full edit form (provider select + all four fields)
    assert '<select name="provider"' in r.text
    for field in ("model", "temperature", "max_tokens"):
        assert f'name="{field}"' in r.text
    # each card carries its agent key for the modal to target the POST
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
    # POST redirects here with ?saved=1; the confirmation banner must render.
    r = client.get("/dashboard/agent-config?saved=1")
    assert r.status_code == 200
    assert "saved" in r.text.lower()


def test_post_redirects_to_list_page(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={
            "provider": "openai",
            "model": "gpt-4o",
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
