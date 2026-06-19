"""Tests for GET /destinations/climate.

All tests are hermetic — ``weather_service._fetch_json`` is monkeypatched
with a URL-keyed async fake so no network calls are made. The fixture spans
calendar years 2022–2024, making aggregated assertions deterministic.

Monkeypatch target: ``app.services.weather_service._fetch_json``
Cache clearing: ``climate_service.clear_climate_cache()`` before each test.
"""

import calendar

import pytest
from app.exceptions import WeatherUnavailableError
from app.services import weather_service
from app.services.climate_service import clear_climate_cache

# ---------------------------------------------------------------------------
# Canned geocode responses
# ---------------------------------------------------------------------------

_GEOCODE_HIT = {
    "results": [
        {
            "name": "Da Nang",
            "country": "Vietnam",
            "latitude": 16.07,
            "longitude": 108.22,
        }
    ]
}

_GEOCODE_MISS = {"generationtime_ms": 0.1}  # no "results" key → city not found


# ---------------------------------------------------------------------------
# Deterministic archive fixture: 2022-01-01 … 2024-12-31
#
# Design:
#   Jan / Feb  → avg high 25 °C (mild), 0.5 mm/day   (< 1 mm → 0 rainy days)
#   July       → avg high 35 °C (hot),  8.0 mm/day   (31 rainy days)
#   September  → avg high 30 °C (warm), 6.0 mm/day   (30 rainy days)
#   All others → avg high 28 °C (mild), 2.0 mm/day   (≥1 mm → all days rainy)
#
# Expected aggregates:
#   Jan: avg_tmax=25.0, avg_tmin=18.0, avg_precip_mm=15.5, rainy_days=0, comfort="mild, dry"
#   Feb: avg_tmax=25.0, avg_tmin=18.0, avg_precip_mm=14.2, rainy_days=0, comfort="mild, dry"
#   Jul: avg_tmax=35.0, avg_tmin=27.0, avg_precip_mm=248.0, rainy_days=31, comfort="hot, wet"
#   based_on_years=[2022, 2023, 2024], best_months=[1, 2, 4]
# ---------------------------------------------------------------------------


def _build_archive_daily() -> dict:
    """Return a ``daily`` dict matching Open-Meteo Archive API shape."""
    import datetime

    times: list[str] = []
    tmax: list[float] = []
    tmin: list[float] = []
    precip: list[float] = []

    for year in [2022, 2023, 2024]:
        for month in range(1, 13):
            days_in_month = calendar.monthrange(year, month)[1]
            for day in range(1, days_in_month + 1):
                d = datetime.date(year, month, day)
                times.append(d.isoformat())

                if month in (1, 2):
                    tmax.append(25.0)
                    tmin.append(18.0)
                    precip.append(0.5)  # below 1 mm → not a rainy day
                elif month == 7:
                    tmax.append(35.0)
                    tmin.append(27.0)
                    precip.append(8.0)  # hot & very wet
                elif month == 9:
                    tmax.append(30.0)
                    tmin.append(24.0)
                    precip.append(6.0)  # warm & wet
                else:
                    tmax.append(28.0)
                    tmin.append(22.0)
                    precip.append(2.0)  # moderate rain every day

    return {
        "timezone": "Asia/Ho_Chi_Minh",
        "daily": {
            "time": times,
            "temperature_2m_max": tmax,
            "temperature_2m_min": tmin,
            "precipitation_sum": precip,
        },
    }


_ARCHIVE = _build_archive_daily()


def _fake_fetch(geocode_response, archive_response=None):
    """Return an async ``_fetch_json`` replacement keyed on URL params.

    Geocode URL params include ``"name"``; archive URL params don't.
    """
    _archive = archive_response if archive_response is not None else _ARCHIVE

    async def _inner(url: str, params: dict) -> dict:
        if "name" in params:  # geocoding request
            return geocode_response
        return _archive  # archive request

    return _inner


# ---------------------------------------------------------------------------
# Autouse fixture: clear cache before every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cache():
    clear_climate_cache()


# ---------------------------------------------------------------------------
# Case 1: Happy path — full 12-month response
# ---------------------------------------------------------------------------


def test_climate_happy_path_status_and_top_level(client, monkeypatch):
    """GET /destinations/climate?city=Da Nang → 200 with all required top-level keys."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    resp = client.get("/destinations/climate", params={"city": "Da Nang"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["location"]["name"] == "Da Nang"
    assert body["based_on_years"] == [2022, 2023, 2024]
    assert len(body["months"]) == 12
    assert isinstance(body["best_months"], list)
    assert len(body["best_months"]) > 0
    assert isinstance(body["summary"], str) and body["summary"]
    assert "Open-Meteo" in body["attribution"]


def test_climate_month_structure(client, monkeypatch):
    """Each ClimateMonth in the response has all required fields with correct types."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    body = client.get("/destinations/climate", params={"city": "Da Nang"}).json()
    jan = next(m for m in body["months"] if m["month"] == 1)

    assert jan["name"] == "January"
    assert isinstance(jan["avg_temp_max_c"], float)
    assert isinstance(jan["avg_temp_min_c"], float)
    assert isinstance(jan["avg_precip_mm"], float)
    assert isinstance(jan["rainy_days"], int)
    assert isinstance(jan["comfort"], str)


# ---------------------------------------------------------------------------
# Case 2: best_months is deterministic from fixture
# ---------------------------------------------------------------------------


def test_climate_best_months_deterministic(client, monkeypatch):
    """best_months should be [1, 2, 4]: Jan and Feb are driest+comfortable,
    April ties driest-among-comfortable-30-rainy-day months closest to 27 °C.
    """
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    body = client.get("/destinations/climate", params={"city": "Da Nang"}).json()
    assert body["best_months"] == [1, 2, 4]


# ---------------------------------------------------------------------------
# Case 2b: Aggregated values match hand-computed expectations from the fixture
# ---------------------------------------------------------------------------


def test_climate_aggregated_values_january(client, monkeypatch):
    """January values match hand-computed aggregation of the fixture (25 °C high,
    18 °C low, 15.5 mm precip, 0 rainy days, mild/dry comfort label)."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    body = client.get("/destinations/climate", params={"city": "Da Nang"}).json()
    jan = next(m for m in body["months"] if m["month"] == 1)

    assert jan["avg_temp_max_c"] == 25.0
    assert jan["avg_temp_min_c"] == 18.0
    assert jan["avg_precip_mm"] == 15.5
    assert jan["rainy_days"] == 0
    assert jan["comfort"] == "mild, dry"


def test_climate_aggregated_values_july(client, monkeypatch):
    """July values match hand-computed aggregation (35 °C high, 27 °C low,
    248 mm precip, 31 rainy days, hot/wet comfort label)."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    body = client.get("/destinations/climate", params={"city": "Da Nang"}).json()
    jul = next(m for m in body["months"] if m["month"] == 7)

    assert jul["avg_temp_max_c"] == 35.0
    assert jul["avg_temp_min_c"] == 27.0
    assert jul["avg_precip_mm"] == 248.0
    assert jul["rainy_days"] == 31
    assert jul["comfort"] == "hot, wet"


# ---------------------------------------------------------------------------
# Case 3: ?month=12 → single month, best_months=[]
# ---------------------------------------------------------------------------


def test_climate_single_month_filter(client, monkeypatch):
    """?month=12 returns exactly one ClimateMonth for December with best_months=[]."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    resp = client.get("/destinations/climate", params={"city": "Da Nang", "month": 12})
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["months"]) == 1
    assert body["months"][0]["month"] == 12
    assert body["best_months"] == []


# ---------------------------------------------------------------------------
# Case 4: Invalid ?month values and missing city → 422
# ---------------------------------------------------------------------------


def test_climate_month_zero_returns_422(client):
    """`?month=0` is below the allowed 1–12 range → 422."""
    resp = client.get("/destinations/climate", params={"city": "Da Nang", "month": 0})
    assert resp.status_code == 422


def test_climate_month_thirteen_returns_422(client):
    """`?month=13` is above the allowed 1–12 range → 422."""
    resp = client.get("/destinations/climate", params={"city": "Da Nang", "month": 13})
    assert resp.status_code == 422


def test_climate_missing_city_returns_422(client):
    """Omitting the required `city` query param → 422."""
    resp = client.get("/destinations/climate")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Case 5: Null cells in fixture arrays → still 200 (no 500)
# ---------------------------------------------------------------------------


def _archive_with_nulls() -> dict:
    """Same shape as _ARCHIVE but with some None values scattered through
    temperature and precipitation arrays."""
    daily = _ARCHIVE["daily"]
    times = daily["time"][:]
    tmax = list(daily["temperature_2m_max"])
    tmin = list(daily["temperature_2m_min"])
    precip = list(daily["precipitation_sum"])

    # Scatter Nones into first few entries for January 2022
    tmax[0] = None  # 2022-01-01 tmax → None
    tmin[5] = None  # 2022-01-06 tmin → None
    precip[3] = None  # 2022-01-04 precip → None

    return {
        "timezone": "Asia/Ho_Chi_Minh",
        "daily": {
            "time": times,
            "temperature_2m_max": tmax,
            "temperature_2m_min": tmin,
            "precipitation_sum": precip,
        },
    }


def test_climate_null_cells_returns_200(client, monkeypatch):
    """Some None values in temp/precip arrays are skipped gracefully → 200."""
    monkeypatch.setattr(
        weather_service,
        "_fetch_json",
        _fake_fetch(_GEOCODE_HIT, archive_response=_archive_with_nulls()),
    )

    resp = client.get("/destinations/climate", params={"city": "Da Nang"})
    assert resp.status_code == 200
    body = resp.json()
    jan = next(m for m in body["months"] if m["month"] == 1)
    # Prove the None cells were SKIPPED (not crashed, not coerced to a value):
    #   precip: Jan-2022 day-4 is None → 30×0.5 = 15.0; 2023/2024 = 15.5 each
    #   → mean = (15.0 + 15.5 + 15.5)/3 = 15.3 (it would be 15.5 with no None handling)
    assert jan["avg_precip_mm"] == 15.3
    #   tmax: Jan-2022 day-1 None dropped; every remaining value is 25.0
    assert jan["avg_temp_max_c"] == 25.0
    assert jan["rainy_days"] == 0
    assert jan["comfort"] == "mild, dry"


# ---------------------------------------------------------------------------
# Case 6: Empty daily arrays → 502
# ---------------------------------------------------------------------------

_EMPTY_ARCHIVE = {
    "timezone": "UTC",
    "daily": {
        "time": [],
        "temperature_2m_max": [],
        "temperature_2m_min": [],
        "precipitation_sum": [],
    },
}


def test_climate_empty_data_returns_502(client, monkeypatch):
    """An archive response with empty daily arrays → 502 (WeatherUnavailableError)."""
    monkeypatch.setattr(
        weather_service,
        "_fetch_json",
        _fake_fetch(_GEOCODE_HIT, archive_response=_EMPTY_ARCHIVE),
    )

    resp = client.get("/destinations/climate", params={"city": "Da Nang"})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Case 7: Unknown city → 404 with error envelope
# ---------------------------------------------------------------------------


def test_climate_unknown_city_returns_404(client, monkeypatch):
    """Geocode returns no results for unknown city → 404 error envelope."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_MISS))

    resp = client.get("/destinations/climate", params={"city": "Nowhereville"})
    assert resp.status_code == 404

    body = resp.json()
    assert "error" in body
    assert "message" in body
    assert body["status_code"] == 404
    assert "path" in body


# ---------------------------------------------------------------------------
# Case 8: Upstream error → 502
# ---------------------------------------------------------------------------


def test_climate_upstream_error_returns_502(client, monkeypatch):
    """``WeatherUnavailableError`` raised by ``_fetch_json`` → 502."""

    async def _boom(url: str, params: dict) -> dict:
        raise WeatherUnavailableError("connection timed out")

    monkeypatch.setattr(weather_service, "_fetch_json", _boom)

    resp = client.get("/destinations/climate", params={"city": "Da Nang"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["status_code"] == 502
    assert "error" in body


# ---------------------------------------------------------------------------
# Regression: leap-day date window must not crash (uncaught 500)
# ---------------------------------------------------------------------------


def test_climate_leap_day_window_no_crash(client, monkeypatch):
    """When today-7d lands on Feb 29, the start-of-window date must not raise.

    Reconstructing date(year - N, 2, 29) would ValueError (year-N is never a
    leap year) and escape as a 500. The service subtracts whole days instead.
    """
    import datetime as _dt

    from app.services import climate_service

    class _FixedDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            # 2024-03-07 minus the 7-day lag lands on 2024-02-29 (a leap day).
            return _dt.datetime(2024, 3, 7, tzinfo=tz)

    monkeypatch.setattr(climate_service, "datetime", _FixedDatetime)
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))

    resp = client.get("/destinations/climate", params={"city": "Da Nang"})
    assert resp.status_code == 200
