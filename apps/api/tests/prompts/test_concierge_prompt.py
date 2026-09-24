"""Concierge prompt pins: follow-up dedup (MIN-50), hotel-tool routing (gh-147, v12),
the visa tool (close-product-loop S2, v13), and the last-resort web rung (agent-web-search, v14)."""

from pathlib import Path

import yaml


def test_concierge_prompt_mentions_exclude_names_on_followup():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "exclude_names" in text


def test_concierge_prompt_names_the_visa_tool():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "get_visa" in text


def test_concierge_prompt_no_longer_denies_having_a_visa_source():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "no other source" not in text


def test_concierge_prompt_picks_the_right_hotel_tool():
    from app.prompts.registry import registry

    text = " ".join(registry.get("concierge").split())
    assert "never ask for dates, rooms or guests in order to browse" in text
    assert "already given you check-in and check-out" in text
    assert "You still do not book" in text


def test_concierge_prompt_never_shortlists_a_sold_out_hotel():
    from app.prompts.registry import registry

    text = " ".join(registry.get("concierge").split())
    assert "never shortlist a hotel the tool marked as having no free room" in text


def test_concierge_prompt_names_the_web_tools():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "search_web" in text
    assert "find_places_live" in text
    assert "web_result" in text
    # find_events was removed (2026-09-24, E005): SerpAPI deprecated google_events.
    assert "find_events" not in text


def test_active_yaml_points_concierge_at_14():
    active = Path(__file__).resolve().parents[2] / "app" / "prompts" / "active.yaml"
    versions = yaml.safe_load(active.read_text())
    assert versions["concierge"] == 14
