"""Dashboard hotel/place pages render catalog text in the chosen language.

``?lang=`` wins, is remembered in a cookie, and the pages only read stored
translations (never a translator call). The seeded ``content_translations``
come from the checked-in ``app/data/content_translations.vi.json``.
"""

from app.services import content_translation_service as mod
from app.streaming.panels.places import CATEGORY_VI
from fastapi.testclient import TestClient


def _boom(texts, language):
    raise AssertionError("dashboard must never call the translator")


def test_places_vi_uses_seeded_translations_and_sets_cookie(
    client: TestClient, monkeypatch
):
    monkeypatch.setattr(mod, "llm_translator", _boom)
    en = client.get("/dashboard/places", params={"city": "Da Nang"})
    vi = client.get("/dashboard/places", params={"city": "Da Nang", "lang": "vi"})
    assert en.status_code == vi.status_code == 200
    assert vi.cookies.get("dashboard_lang") == "vi"
    assert 'name="lang" value="vi"' in vi.text
    assert CATEGORY_VI["restaurant"] in vi.text  # bounded category label swapped
    # Descriptions differ between the two renders (seeded vi rows applied).
    assert en.text != vi.text
    assert 'aria-current="true">VI' in vi.text


def test_cookie_keeps_language_without_query_param(client: TestClient):
    client.get("/dashboard/hotels", params={"lang": "vi"})
    page = client.get("/dashboard/hotels")
    assert page.status_code == 200
    assert 'name="lang" value="vi"' in page.text
    assert 'aria-current="true">VI' in page.text


def test_unknown_language_falls_back_to_default(client: TestClient):
    page = client.get("/dashboard/hotels", params={"lang": "fr"})
    assert page.status_code == 200
    assert 'name="lang" value="en"' in page.text
    assert page.cookies.get("dashboard_lang") == "en"


def test_hotels_vi_description_from_store(client: TestClient, monkeypatch):
    monkeypatch.setattr(mod, "llm_translator", _boom)
    en = client.get("/dashboard/hotels", params={"city": "Da Nang"})
    vi = client.get("/dashboard/hotels", params={"city": "Da Nang", "lang": "vi"})
    assert vi.status_code == 200
    assert en.text != vi.text
