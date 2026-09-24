"""The traveller reads the dossier without tool names or ids (research-dossier-reader SC-1).

The stored files keep ``(search_flights)`` citations and ids — the grader checks the
citations and the proposal is assembled from the ids — so the reader view strips them
only on the way to the traveller. Inputs are lines from the live Đà Nẵng run ``0f71586a``.
"""

from __future__ import annotations

import pytest
from app.research.reader import reader_view

UUID = "38382e5c-a32e-5d1e-9d08-8d2d69c51dca"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "- Five outbound offers and five return offers were returned (search_flights).",
            "- Five outbound offers and five return offers were returned.",
        ),
        (
            "- **Cheapest:** VN456 SGN→DAD on 2026-10-25 16:15, USD 139, offer_id "
            f"`{UUID}`; paired with TG449 (search_flights).",
            "- **Cheapest:** VN456 SGN→DAD on 2026-10-25 16:15, USD 139; paired with TG449.",
        ),
        (
            f"- **Cham Hotel Danang** — hotel_id `{UUID}`; USD 35/night (search_hotels).",
            "- **Cham Hotel Danang**; USD 35/night.",
        ),
        (
            f"- 08:00 Breakfast at Lighthouse Coffee Roaster, place_id `{UUID}` (search_places).",
            "- 08:00 Breakfast at Lighthouse Coffee Roaster.",
        ),
        (
            "Current air quality is Good, US AQI 50 (get_air_quality).",
            "Current air quality is Good, US AQI 50.",
        ),
        (
            "- **Days:** Lịch đi rất chậm (search_places; get_climate).",
            "- **Days:** Lịch đi rất chậm.",
        ),
        (
            "- Budget under the cap (estimate_trip_budget, get_trip_budget).",
            "- Budget under the cap.",
        ),
        (
            "- Party: 1 traveler (user prompt)",
            "- Party: 1 traveler",
        ),
    ],
)
def test_tool_tags_and_ids_are_removed(raw: str, expected: str) -> None:
    assert reader_view(raw) == expected


def test_a_parenthetical_that_is_not_a_citation_survives() -> None:
    text = "- Sao Beach (best at sunset) and the cable car (about 15 min)."
    assert reader_view(text) == text


def test_the_ids_section_is_hidden() -> None:
    raw = (
        "# Chỗ ở\n\n- **Cham Hotel Danang**: USD 35/đêm (search_hotels).\n\n"
        f"## Ids\n\n- Cham Hotel Danang: {UUID}\n- Danang Boutique Hotel: {UUID}\n"
    )
    assert reader_view(raw) == "# Chỗ ở\n\n- **Cham Hotel Danang**: USD 35/đêm.\n"


def test_a_later_section_after_ids_is_kept() -> None:
    raw = f"# Flights\n\n## Ids\n\n- VN456: {UUID}\n\n## Notes\n\nBook early.\n"
    assert reader_view(raw) == "# Flights\n\n## Notes\n\nBook early.\n"


def test_a_line_that_only_lists_bare_ids_is_dropped() -> None:
    raw = (
        "## Recommendation\n"
        f"- Best budget-first shortlist for the proposal: `{UUID}`, `{UUID}` (search_hotels).\n"
        "- Cham Hotel Danang is the cheapest (search_hotels).\n"
    )
    assert reader_view(raw) == (
        "## Recommendation\n- Cham Hotel Danang is the cheapest.\n"
    )


def test_a_body_citation_is_stripped_around_the_sources_section() -> None:
    raw = "Lantern night on 23 Oct (search_web)."
    assert reader_view(raw) == "Lantern night on 23 Oct."


def test_the_sources_section_survives_byte_for_byte() -> None:
    raw = (
        "# Guide\n\n"
        "## Sources\n\n"
        "- [Hoi An events](https://example.com/e)\n"
        "- [Cafe](https://www.google.com/maps/place/?q=place_id:ChIJabc)\n"
        f"- [Doc](https://example.com/{UUID})\n"
    )
    assert reader_view(raw) == raw


def test_a_place_id_in_the_body_outside_sources_is_still_stripped() -> None:
    raw = f"- 08:00 Breakfast at Lighthouse, place_id `{UUID}` (search_places)."
    assert reader_view(raw) == "- 08:00 Breakfast at Lighthouse."


def test_sources_renders_and_a_following_ids_section_is_dropped() -> None:
    raw = (
        "# Guide\n\n"
        "## Sources\n\n"
        "- [Hoi An events](https://example.com/e)\n\n"
        f"## Ids\n\n- Hoi An events: {UUID}\n"
    )
    assert reader_view(raw) == (
        "# Guide\n\n## Sources\n\n- [Hoi An events](https://example.com/e)\n"
    )


def test_a_sources_section_at_the_end_runs_to_the_end_of_the_file() -> None:
    raw = (
        "# Guide\n\n- Lantern night (search_web).\n\n"
        "## Sources\n\n"
        "- [Hoi An events](https://example.com/e)\n"
        "- [Cafe](https://www.google.com/maps/place/?q=place_id:ChIJabc)\n"
    )
    assert reader_view(raw) == (
        "# Guide\n\n- Lantern night.\n\n"
        "## Sources\n\n"
        "- [Hoi An events](https://example.com/e)\n"
        "- [Cafe](https://www.google.com/maps/place/?q=place_id:ChIJabc)\n"
    )


def test_blank_line_runs_inside_sources_are_not_collapsed() -> None:
    raw = (
        "# Guide\n\n## Sources\n\n"
        "- [A](https://example.com/a)\n\n\n- [B](https://example.com/b)\n"
    )
    assert reader_view(raw) == raw
