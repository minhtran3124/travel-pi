"""Web-search settings + SDK pins (specs/agent-web-search Task 1.1)."""

from importlib import metadata

import pytest
from app.core.config import Settings
from packaging.requirements import Requirement
from packaging.version import Version
from pydantic import ValidationError


def test_web_search_settings_have_off_defaults(monkeypatch):
    # The Verify command blanks these to "" in the environment; drop them so the
    # genuine None default is observable rather than the env override.
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.web_search_enabled is False
    assert s.tavily_api_key is None
    assert s.serpapi_api_key is None
    assert s.web_search_timeout_seconds == 10.0
    assert s.web_search_cache_ttl_seconds == 3600
    assert s.web_search_news_cache_ttl_seconds == 900
    assert s.web_search_cache_max_entries == 512
    assert s.web_search_user_hourly_limit == 30
    assert s.tavily_search_available is False
    assert s.serpapi_search_available is False


def test_tavily_search_available_needs_flag_and_key():
    assert (
        Settings(web_search_enabled=False, tavily_api_key="k").tavily_search_available
        is False
    )
    assert (
        Settings(web_search_enabled=True, tavily_api_key=None).tavily_search_available
        is False
    )
    assert (
        Settings(web_search_enabled=True, tavily_api_key="   ").tavily_search_available
        is False
    )
    assert (
        Settings(web_search_enabled=True, tavily_api_key="k").tavily_search_available
        is True
    )


def test_serpapi_search_available_needs_flag_and_key():
    assert (
        Settings(web_search_enabled=False, serpapi_api_key="k").serpapi_search_available
        is False
    )
    assert (
        Settings(web_search_enabled=True, serpapi_api_key=None).serpapi_search_available
        is False
    )
    assert (
        Settings(
            web_search_enabled=True, serpapi_api_key="   "
        ).serpapi_search_available
        is False
    )
    assert (
        Settings(web_search_enabled=True, serpapi_api_key="k").serpapi_search_available
        is True
    )


def test_sdks_import_at_pinned_versions():
    import serpapi  # noqa: F401
    import tavily  # noqa: F401

    for name, spec in (("tavily-python", ">=0.8.4,<0.9"), ("serpapi", ">=1.1.2,<2")):
        installed = Version(metadata.version(name))
        req = Requirement(f"{name}{spec}")
        assert installed in req.specifier, f"{name} {installed} does not satisfy {spec}"


@pytest.mark.parametrize("limit", [0, -1])
def test_web_search_hourly_limit_must_be_positive(limit):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, web_search_user_hourly_limit=limit)
