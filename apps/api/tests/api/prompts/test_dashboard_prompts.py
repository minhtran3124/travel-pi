"""Read-only /dashboard/prompts routes; coverage is driven off the live registry so a new prompt dir is exercised without editing this file."""

from app.prompts.registry import registry


def test_browse_page_lists_every_prompt_in_sidebar(client):
    r = client.get("/dashboard/prompts")
    assert r.status_code == 200
    for name in registry.names():
        assert name in r.text


def test_sidebar_shows_active_version_badges(client):
    r = client.get("/dashboard/prompts")
    assert r.status_code == 200
    assert f"v{registry.active_version('supervisor')}" in r.text
    assert f"v{registry.active_version('budget')}" in r.text


def test_sidebar_is_dynamic_off_the_registry(client):
    # Match the class attribute (not the CSS selector, which also mentions the class).
    r = client.get("/dashboard/prompts")
    assert r.text.count('class="prompt-nav-item') == len(registry.names())


def test_browse_defaults_to_first_prompt(client):
    # The bare browse page auto-selects the first (sorted) prompt.
    r = client.get("/dashboard/prompts")
    assert r.status_code == 200
    first = sorted(registry.names())[0]
    assert f'action="/dashboard/prompts/{first}/diff"' in r.text
    assert 'aria-current="page"' in r.text


def test_detail_defaults_to_latest_and_compare_prev_to_latest(client):
    # supervisor: right pane defaults to latest, compare bar to previous→latest.
    versions = registry.versions("supervisor")
    latest, prev = versions[-1], versions[-2]
    r = client.get("/dashboard/prompts/supervisor")
    assert r.status_code == 200
    assert f'<option value="v{latest}" selected' in r.text  # compare "to" = latest
    assert f'<option value="v{prev}" selected' in r.text  # compare "from" = previous


def test_detail_page_lists_versions_and_flags_active(client):
    r = client.get("/dashboard/prompts/budget")
    assert r.status_code == 200
    for v in registry.versions("budget"):
        assert f"v{v}" in r.text
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
