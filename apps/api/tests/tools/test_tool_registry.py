"""Tool registry + weather/memory tools (specs/travel-agent Task 3.4)."""

import pytest


def test_get_tools_for_groups():
    from app.tools.registry import get_tools_for

    planner = {t.name for t in get_tools_for("planner")}
    assert "get_trip_summary" in planner
    assert "search_flights" in planner

    concierge = {t.name for t in get_tools_for("concierge")}
    assert "get_weather" in concierge
    assert "search_places" in concierge

    journal = {t.name for t in get_tools_for("journal")}
    assert "save_user_preference" in journal

    budget = {t.name for t in get_tools_for("budget")}
    assert "add_expense" in budget
    assert "get_trip_budget" in budget

    assert get_tools_for("nope") == []


# --- P2: episodic recall tool (Task 2.4) ---


def test_recall_past_trips_bound_to_planner():
    """recall_past_trips is in the planner's tool group (P2)."""
    from app.tools.registry import get_tools_for

    planner = {t.name for t in get_tools_for("planner")}
    assert "recall_past_trips" in planner


def test_recall_past_trips_not_in_other_domains():
    """recall_past_trips is bound to the planner only."""
    from app.tools.registry import get_tools_for

    for domain in ("concierge", "journal", "booking", "budget"):
        assert "recall_past_trips" not in {t.name for t in get_tools_for(domain)}


def test_recall_past_trips_hides_injected_store_and_user_id():
    """InjectedStore + InjectedState must NOT appear in the LLM-visible schema (C3)."""
    from app.tools.memory_tools import recall_past_trips

    assert "store" not in recall_past_trips.args
    assert "user_id" not in recall_past_trips.args
    assert "query" in recall_past_trips.args


def test_recall_past_trips_metadata_readonly():
    """recall_past_trips is auto-annotated readOnly=True, destructive=False."""
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["recall_past_trips"] == {
        "readOnly": True,
        "destructive": False,
    }


def test_tool_metadata_annotations():
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["get_trip_summary"] == {"readOnly": True, "destructive": False}
    assert TOOL_METADATA["add_expense"]["readOnly"] is False
    assert TOOL_METADATA["book_hotel"]["destructive"] is True


def test_all_tools_deduped():
    from app.tools.registry import ALL_TOOLS

    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names))  # no duplicates


def _all_tools():
    from app.tools.registry import ALL_TOOLS

    return list(ALL_TOOLS)


def _has_injected_args(tool):
    """True if the tool carries LangGraph-injected args (InjectedState/InjectedStore).

    Detected structurally: injected args appear in the full input schema but are
    stripped from the model-facing ``tool_call_schema``.
    """
    full = set(tool.get_input_schema().model_fields)
    facing = set(tool.tool_call_schema.model_fields)
    return full != facing


@pytest.mark.parametrize("tool", _all_tools(), ids=lambda t: t.name)
def test_every_tool_has_explicit_described_schema(tool):
    """Every registered tool must expose an EXPLICIT, described model-facing schema (MIN-46).

    LangChain auto-derives a non-None ``args_schema`` from the signature when none
    is supplied, so ``is not None`` is not enough. Two valid shapes:

    * Normal tools: a hand-authored ``<Tool>Args`` schema living in ``app.tools.*``.
    * Injection-bearing tools (InjectedState/InjectedStore): an explicit
      ``args_schema`` that omits the injected args would break ToolNode injection,
      so they keep the auto-derived schema but attach model-facing descriptions
      inline via ``Annotated[..., Field(description=...)]``. We require every
      model-facing field to carry a description instead. A tool whose only
      arg(s) are injected (e.g. ``get_trip_summary`` after the InjectedState
      refactor, specs/agent-trip-context) has an empty model-facing schema —
      that trivially satisfies "every field is described" and must pass, not fail.

    This guard blocks a future tool (e.g. from MIN-42) shipping with an
    undocumented, auto-derived schema.
    """
    assert tool.args_schema is not None
    if _has_injected_args(tool):
        facing = tool.tool_call_schema.model_fields
        if not facing:
            return  # no model-facing args left to describe — nothing to check
        for name, field in facing.items():
            assert field.description, (
                f"{tool.name}.{name} has no description — add "
                f"Annotated[..., Field(description=...)] on the signature."
            )
    else:
        assert tool.args_schema.__module__.startswith("app.tools"), (
            f"{tool.name} uses an auto-derived args_schema "
            f"({tool.args_schema.__module__}) — declare an explicit <Tool>Args(AppBaseModel)."
        )


def test_memory_tool_hides_injected_store_and_user_id():
    from app.tools.memory_tools import save_user_preference

    # InjectedStore + InjectedState must NOT appear in the LLM-visible args schema
    # (the model supplies only the semantic args; user_id comes from graph state — C3).
    assert "store" not in save_user_preference.args
    assert "user_id" not in save_user_preference.args
    assert "key" in save_user_preference.args
    assert "text" in save_user_preference.args


def test_weather_tool_maps_upstream_error(monkeypatch):
    import asyncio

    from app.exceptions import UpstreamError, WeatherUnavailableError
    from app.services import weather_service
    from app.tools.weather_tools import get_weather

    async def boom(city, days=None):
        raise WeatherUnavailableError("open-meteo down")

    monkeypatch.setattr(weather_service, "get_weather", boom)
    with pytest.raises(UpstreamError):
        asyncio.run(get_weather.ainvoke({"city": "Tokyo"}))


def test_weather_tool_returns_panel(monkeypatch):
    """get_weather is panel-capable: a ToolCall yields a ToolMessage whose
    ``.content`` is the model-facing summary and ``.artifact`` is the
    ``{"kind":"weather","data":...}`` side-panel payload (specs/agent-side-panel).
    """
    import asyncio

    from app.schemas.weather import (
        CurrentWeather,
        DailyForecast,
        WeatherLocation,
        WeatherResponse,
    )
    from app.services import weather_service
    from app.tools.weather_tools import get_weather
    from langchain_core.messages import ToolMessage

    async def ok(city, days=None):
        return WeatherResponse(
            location=WeatherLocation(
                name="Tokyo",
                country="Japan",
                latitude=35.6,
                longitude=139.7,
                timezone="Asia/Tokyo",
            ),
            current=CurrentWeather(
                time="2026-06-30T00:00",
                temperature_c=24.6,
                apparent_temperature_c=25.1,
                relative_humidity=70,
                wind_speed_kmh=8.0,
                weather_code=2,
                description="Partly cloudy",
            ),
            daily=[
                DailyForecast(
                    date="2026-06-30",
                    temp_min_c=20.0,
                    temp_max_c=27.0,
                    precipitation_probability_max=30,
                    weather_code=2,
                    description="Partly cloudy",
                )
            ],
        )

    monkeypatch.setattr(weather_service, "get_weather", ok)
    msg = asyncio.run(
        get_weather.ainvoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "get_weather",
                "args": {"city": "Tokyo"},
            }
        )
    )
    assert isinstance(msg, ToolMessage)
    # Model-facing summary: a short non-empty string carrying the forecast.
    assert isinstance(msg.content, str) and "Tokyo" in msg.content
    # Side-panel artifact carries the rich weather data.
    assert msg.artifact["kind"] == "weather"
    data = msg.artifact["data"]
    assert data["location_name"] == "Tokyo"
    assert data["current"]["emoji"] and data["current"]["condition"] == "partly"
    assert data["daily"][0]["precipitation_probability_max"] == 30


def test_air_quality_tool_returns_panel(monkeypatch):
    """get_air_quality is panel-capable: a ToolCall yields a ToolMessage whose
    ``.artifact`` is the ``{"kind":"air_quality","data":...}`` side-panel payload.
    """
    import asyncio

    from app.schemas.air_quality import AirQualityDay, AirQualityResponse
    from app.schemas.weather import WeatherLocation
    from app.services import air_quality_service
    from app.tools.weather_tools import get_air_quality
    from langchain_core.messages import ToolMessage

    async def ok(city):
        return AirQualityResponse(
            location=WeatherLocation(
                name="Hanoi",
                country="Vietnam",
                latitude=21.0,
                longitude=105.8,
                timezone="Asia/Bangkok",
            ),
            time="2026-06-30T14:00",
            us_aqi=35,
            category="Good",
            pm2_5=8.3,
            attribution="Air quality data by Open-Meteo.com (CC BY 4.0)",
            forecast=[AirQualityDay(date="2026-06-30", max_us_aqi=35, category="Good")],
        )

    monkeypatch.setattr(air_quality_service, "get_air_quality", ok)
    msg = asyncio.run(
        get_air_quality.ainvoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "get_air_quality",
                "args": {"city": "Hanoi"},
            }
        )
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and "Hanoi" in msg.content
    assert msg.artifact["kind"] == "air_quality"
    data = msg.artifact["data"]
    assert data["us_aqi"] == 35 and data["band"] == "good" and data["emoji"] == "😊"
    assert len(data["pollutants"]) == 6
    assert data["forecast"][0]["category"] == "Good"


def test_hotel_tool_split():
    """concierge gets the dateless browse_hotels; booking keeps availability
    search_hotels + book_hotel (MIN-51)."""
    from app.tools.registry import ALL_TOOLS, TOOL_METADATA, get_tools_for

    concierge = {t.name for t in get_tools_for("concierge")}
    assert "browse_hotels" in concierge
    assert "search_hotels" not in concierge
    assert "book_hotel" not in concierge

    booking = {t.name for t in get_tools_for("booking")}
    assert "search_hotels" in booking
    assert "book_hotel" in booking

    all_names = {t.name for t in ALL_TOOLS}
    assert "browse_hotels" in all_names
    assert "search_hotels" in all_names

    assert TOOL_METADATA["browse_hotels"]["destructive"] is False
    assert TOOL_METADATA["browse_hotels"]["readOnly"] is True
    assert TOOL_METADATA["search_hotels"]["destructive"] is False


def test_planner_never_binds_destructive_tools():
    """The planner must never hold money/irreversible tools: only the booking
    route passes through the HITL plan_node gate, so a destructive tool bound
    to planner would execute without human approval. Booking owns them all.
    Guards against a shared tool list leaking a new destructive tool into the
    planner again (it happened twice: book_hotel at registry birth, book_flight
    in MIN-42)."""
    from app.tools.registry import TOOL_METADATA, get_tools_for

    planner = {t.name for t in get_tools_for("planner")}
    destructive_in_planner = {n for n in planner if TOOL_METADATA[n]["destructive"]}
    assert not destructive_in_planner, (
        f"planner binds destructive tools {destructive_in_planner} — move them "
        "to the booking domain (HITL-gated) instead"
    )

    # Planner keeps its search tools; booking keeps the full lifecycle.
    assert {"search_flights", "search_hotels"} <= planner
    booking = {t.name for t in get_tools_for("booking")}
    assert {"book_flight", "book_hotel", "cancel_flight", "cancel_hotel"} <= booking


def test_create_trip_bound_to_planner_only():
    """create_trip (specs/agent-trip-context) is scoped to the planner domain
    only — it is not part of the shared TRIP_TOOLS list, so it must be added
    explicitly and must not leak into the other sub-agents."""
    from app.tools.registry import get_tools_for

    planner = {t.name for t in get_tools_for("planner")}
    assert "create_trip" in planner

    for domain in ("concierge", "journal", "booking", "budget"):
        assert "create_trip" not in {t.name for t in get_tools_for(domain)}


def test_create_trip_metadata_is_write_not_destructive():
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["create_trip"] == {"readOnly": False, "destructive": False}


def test_mcp_surface_unchanged_by_planner_scoping():
    """ALL_TOOLS dedupes across domains, so scoping planner to search-only must
    not remove the booking tools from the MCP/manifest surface."""
    from app.tools.registry import ALL_TOOLS

    all_names = {t.name for t in ALL_TOOLS}
    assert {"book_flight", "book_hotel", "cancel_flight", "cancel_hotel"} <= all_names


# --- gh-125 ratchet: injected trip-scoped params must tolerate absent state ---


def test_injected_trip_id_params_have_defaults():
    """Registry-wide gh-125 ratchet: every ``InjectedState("trip_id")`` param on
    every registered tool must declare a default. A required injected param opts
    out of ToolNode's ``_optional_state_args`` tolerance, so a conversation with
    no active trip crashes with ``KeyError: 'trip_id'`` during injection — the
    exact gh-125 bug. The per-tool tests in
    ``test_trip_tools_no_active_trip.py`` cover only a hard-coded tool list;
    this loop catches the sixth trip-scoped tool automatically.
    """
    import inspect
    import typing

    from app.tools.registry import ALL_TOOLS
    from langgraph.prebuilt import InjectedState

    checked = 0
    for reg_tool in ALL_TOOLS:
        fn = reg_tool.coroutine or reg_tool.func
        hints = typing.get_type_hints(fn, include_extras=True)
        for pname, param in inspect.signature(fn).parameters.items():
            metadata = getattr(hints.get(pname), "__metadata__", ())
            if any(
                isinstance(m, InjectedState) and m.field == "trip_id"
                for m in metadata
            ):
                assert param.default is not inspect.Parameter.empty, (
                    f"{reg_tool.name}.{pname}: InjectedState('trip_id') without a "
                    "default reintroduces the gh-125 injection KeyError"
                )
                checked += 1
    assert checked >= 5  # the five trip tools, at minimum — not vacuous
