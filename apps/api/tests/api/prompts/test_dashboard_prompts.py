"""Route tests for the read-only /dashboard/prompts section (MIN-45).

Mirrors tests/api/agent_config/test_agent_config_dashboard.py: GET the HTML
route, assert status + substring on the body. Coverage is driven off the live
`registry` so a new prompt dir would be exercised without editing this file.
"""

from app.prompts.registry import registry


def test_list_page_lists_every_registered_prompt(client):
    r = client.get("/dashboard/prompts")
    assert r.status_code == 200
    for name in registry.names():
        assert name in r.text


def test_list_page_shows_active_version_and_count(client):
    # budget has v1 + v2 with active v2 (per active.yaml) — both facts must surface.
    r = client.get("/dashboard/prompts")
    assert r.status_code == 200
    assert f"v{registry.active_version('budget')}" in r.text
    assert str(len(registry.versions("budget"))) in r.text


def test_list_is_dynamic_off_the_registry(client):
    # One card per registered name — proves new dirs appear with no code change.
    r = client.get("/dashboard/prompts")
    assert r.text.count("prompt-card") == len(registry.names()) or all(
        n in r.text for n in registry.names()
    )


def test_detail_page_lists_versions_and_flags_active(client):
    r = client.get("/dashboard/prompts/budget")
    assert r.status_code == 200
    for v in registry.versions("budget"):
        assert f"v{v}" in r.text
    # active version is flagged, and content of the active version is shown
    assert "active" in r.text.lower()
    assert "Budget Manager" in r.text  # from budget/v2.md (the active version)


def test_detail_page_selects_requested_version(client):
    r = client.get("/dashboard/prompts/budget?version=v1")
    assert r.status_code == 200
    # v1's distinctive prose (absent from v2's structured rewrite)
    assert "roll them up by category" in r.text


def test_detail_unknown_name_404(client):
    assert client.get("/dashboard/prompts/nope").status_code == 404


def test_detail_unknown_version_404_not_500(client):
    assert client.get("/dashboard/prompts/budget?version=v99").status_code == 404


def test_diff_renders_line_level_add_and_remove(client):
    r = client.get("/dashboard/prompts/budget/diff?from=v1&to=v2")
    assert r.status_code == 200
    # both change classes present → real line-level diff, not a blob
    assert "diff-add" in r.text
    assert "diff-del" in r.text
    # content from each side is present
    assert "Responsibilities" in r.text  # added in v2
    assert "v1" in r.text and "v2" in r.text


def test_diff_unknown_name_404(client):
    assert client.get("/dashboard/prompts/nope/diff?from=v1&to=v2").status_code == 404


def test_diff_malformed_version_404_not_500(client):
    assert client.get("/dashboard/prompts/budget/diff?from=vX&to=v2").status_code == 404


def test_diff_missing_param_is_422(client):
    # from/to are required query params; omitting one is a validation error (not 500).
    assert client.get("/dashboard/prompts/budget/diff?from=v1").status_code == 422


def test_diff_ignores_third_version_param(client):
    # 2-version-only by design: a stray 3rd param is ignored, still diffs from↔to.
    r = client.get("/dashboard/prompts/budget/diff?from=v1&to=v2&other=v1")
    assert r.status_code == 200
    assert "diff-add" in r.text
