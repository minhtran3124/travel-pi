"""Historical climate normals via the Open-Meteo Archive API.

Backs ``GET /destinations/{city}/climate``. Like ``weather_service`` this
module makes real outbound calls — Open-Meteo's ERA5-based archive endpoint
is free and keyless (CC BY 4.0). City names are resolved via the same
``weather_service.geocode_city`` helper used by the live weather feature, so
both features share one geocoding provider.

Results are cached per (lat, lon) pair (rounded to 2 dp) so repeated calls
for the same location skip the ~3-year archive download. The ``month`` filter
is applied *after* the cache lookup and never stored in the cache — we always
cache the full 12-month response, then slice it before returning.

Tests monkeypatch ``weather_service._fetch_json`` to avoid the network and
call ``clear_climate_cache()`` between cases to keep them isolated.
"""

import calendar
import logging
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.exceptions import CityNotFoundError, WeatherUnavailableError
from app.schemas.climate import ClimateMonth, ClimateResponse
from app.schemas.weather import WeatherLocation
from app.services import weather_service

logger = logging.getLogger(__name__)

# Process-wide cache: (round(lat,2), round(lon,2)) → full ClimateResponse.
# The month filter is applied at return time, never at cache-write time.
_climate_cache: dict[tuple, ClimateResponse] = {}

# Heuristic thresholds — tunable; see specs/destinations-climate/design.md §4.
_LAG_DAYS = 7  # Open-Meteo ERA5 lags ~5 days; 7 is a safe buffer for end_date.
_RAINY_DAY_MM = 1.0  # a "rain day": daily precipitation_sum ≥ this many mm.
_WET_MONTH_DAYS = 10  # a month with ≥ this many rainy days is labelled "wet".
_COMFORT_TEMP_MIN = 22.0  # comfortable avg-high band lower bound (°C).
_COMFORT_TEMP_MAX = 32.0  # comfortable avg-high band upper bound (°C).
_COMFORT_TEMP_IDEAL = 27.0  # avg-high midpoint used to rank comfortable months.
_WARM_ABOVE = 28.0  # avg-high > this (and ≤ MAX) → "warm"; ≤ MIN → "cool".


def clear_climate_cache() -> None:
    """Empty the climate cache. Used by tests to keep cases isolated."""
    _climate_cache.clear()


# ---------------------------------------------------------------------------
# Private helpers (all sync — no I/O)
# ---------------------------------------------------------------------------


def _mean(xs: list[float]) -> float:
    """Arithmetic mean of a non-empty list. ZeroDivisionError if xs is empty."""
    return sum(xs) / len(xs)


def _median(xs: list[float | int]) -> float:
    """Median of a non-empty list."""
    sorted_xs = sorted(xs)
    n = len(sorted_xs)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_xs[mid])
    return (sorted_xs[mid - 1] + sorted_xs[mid]) / 2.0


def _temp_band(avg_temp_max_c: float) -> str:
    if avg_temp_max_c > _COMFORT_TEMP_MAX:
        return "hot"
    if avg_temp_max_c > _WARM_ABOVE:
        return "warm"
    if avg_temp_max_c > _COMFORT_TEMP_MIN:
        return "mild"
    return "cool"


def _comfort_label(avg_temp_max_c: float, rainy_days: int) -> str:
    wetness = "wet" if rainy_days >= _WET_MONTH_DAYS else "dry"
    return f"{_temp_band(avg_temp_max_c)}, {wetness}"


def _build_summary(
    name: str, best_months: list[int], all_months: list[ClimateMonth]
) -> str:
    """One sentence about when to visit and which month is wettest."""
    if not all_months:
        return (
            f"{name} climate data is available — check individual months for details."
        )

    wettest = max(all_months, key=lambda m: m.avg_precip_mm)

    if not best_months:
        return (
            f"{name} has variable conditions year-round; "
            f"{calendar.month_name[wettest.month]} tends to be the wettest month."
        )

    month_names = [calendar.month_name[m] for m in best_months]
    if len(month_names) == 1:
        best_str = month_names[0]
    else:
        best_str = f"{', '.join(month_names[:-1])} and {month_names[-1]}"

    return (
        f"{name} is driest and most comfortable around {best_str}; "
        f"{calendar.month_name[wettest.month]} is wettest."
    )


def _pick_best_months(months: list[ClimateMonth]) -> list[int]:
    """Up to 3 month numbers considered the best time to visit.

    Candidates: months with avg_temp_max_c in [22, 32].
    From those, keep the ones with rainy_days ≤ median rainy_days across all
    produced months. Sort by (rainy_days, abs(avg_temp_max_c - 27)); take up
    to 3.

    Fallback: if no temperature-comfortable candidates, take the 3 months
    with the lowest rainy_days overall.
    """
    if not months:
        return []

    all_rainy = [m.rainy_days for m in months]
    med = _median(all_rainy)

    candidates = [
        m for m in months if _COMFORT_TEMP_MIN <= m.avg_temp_max_c <= _COMFORT_TEMP_MAX
    ]
    comfortable_dry = [m for m in candidates if m.rainy_days <= med]

    if comfortable_dry:
        ranked = sorted(
            comfortable_dry,
            key=lambda m: (m.rainy_days, abs(m.avg_temp_max_c - _COMFORT_TEMP_IDEAL)),
        )
        return [m.month for m in ranked[:3]]

    # Fallback: driest months overall
    ranked_all = sorted(months, key=lambda m: m.rainy_days)
    return [m.month for m in ranked_all[:3]]


def _aggregate(
    data: dict, lat: float, lon: float, location_name: str, country: str | None
) -> ClimateResponse:
    """Walk the archive response and build a full ClimateResponse.

    Structural access (``data["daily"]["time"]`` etc.) is intentionally
    unguarded: the caller wraps this in a try/except that converts any
    KeyError/IndexError/TypeError/ZeroDivisionError into
    WeatherUnavailableError. The one explicit guard here is the empty
    time-series case, which raises WeatherUnavailableError directly.
    """
    daily = data["daily"]
    times: list[str] = daily["time"]
    tmax_raw: list = daily["temperature_2m_max"]
    tmin_raw: list = daily["temperature_2m_min"]
    precip_raw: list = daily["precipitation_sum"]

    if not times:
        # Empty time series → let ZeroDivisionError propagate from _mean, or
        # raise explicitly for a cleaner message.
        raise WeatherUnavailableError(
            "Open-Meteo returned an empty climate time series"
        )

    # Per-month accumulators.
    # tmax_vals[m] / tmin_vals[m]: daily non-None values for averaging.
    # precip_by_year[m][(y,m)]: running precip sum per calendar-year month.
    # rainy_by_year[m][(y,m)]: rainy-day count (precip ≥ 1.0 mm) per year-month.
    tmax_vals: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    tmin_vals: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    precip_by_year: dict[int, dict[tuple[int, int], float]] = {
        m: {} for m in range(1, 13)
    }
    rainy_by_year: dict[int, dict[tuple[int, int], int]] = {m: {} for m in range(1, 13)}

    for i, ts in enumerate(times):
        y = int(ts[:4])
        m = int(ts[5:7])
        ym = (y, m)

        tx = tmax_raw[i]
        tn = tmin_raw[i]
        pr = precip_raw[i]

        if tx is not None:
            tmax_vals[m].append(float(tx))
        if tn is not None:
            tmin_vals[m].append(float(tn))

        # Precip accumulation — skip None days
        if pr is not None:
            pr_f = float(pr)
            precip_by_year[m][ym] = precip_by_year[m].get(ym, 0.0) + pr_f
            if pr_f >= _RAINY_DAY_MM:
                rainy_by_year[m][ym] = rainy_by_year[m].get(ym, 0) + 1
        else:
            # Ensure the year-month key exists so it contributes a zero
            # rainy-day count to the mean (don't silently skip the year).
            if ym not in rainy_by_year[m]:
                rainy_by_year[m][ym] = 0
            if ym not in precip_by_year[m]:
                precip_by_year[m][ym] = 0.0

    climate_months: list[ClimateMonth] = []
    for m in range(1, 13):
        if not tmax_vals[m] or not tmin_vals[m]:
            continue  # need both temperature series to describe the month

        avg_max = round(_mean(tmax_vals[m]), 1)
        avg_min = round(_mean(tmin_vals[m]), 1)

        year_precips = list(precip_by_year[m].values())
        avg_precip = round(_mean(year_precips), 1) if year_precips else 0.0

        year_rainy = list(rainy_by_year[m].values())
        rainy_avg = round(_mean(year_rainy)) if year_rainy else 0

        climate_months.append(
            ClimateMonth(
                month=m,
                name=calendar.month_name[m],
                avg_temp_max_c=avg_max,
                avg_temp_min_c=avg_min,
                avg_precip_mm=avg_precip,
                rainy_days=rainy_avg,
                comfort=_comfort_label(avg_max, rainy_avg),
            )
        )

    based_on_years = sorted({int(t[:4]) for t in times})
    best_months = _pick_best_months(climate_months)
    summary = _build_summary(location_name, best_months, climate_months)

    return ClimateResponse(
        location=WeatherLocation(
            name=location_name,
            country=country,
            latitude=lat,
            longitude=lon,
            timezone=data.get("timezone", "UTC"),
        ),
        based_on_years=based_on_years,
        months=climate_months,
        best_months=best_months,
        summary=summary,
        attribution="Weather data by Open-Meteo.com (CC BY 4.0)",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_climate(city: str, month: int | None = None) -> ClimateResponse:
    """Return monthly climate normals for ``city``, optionally filtered to ``month``.

    Raises :class:`CityNotFoundError` if the city cannot be geocoded, and
    :class:`WeatherUnavailableError` if the Open-Meteo Archive API is
    unreachable or returns an unexpected response shape.

    The full 12-month ClimateResponse is cached per (lat, lon) key; the
    ``month`` filter is applied at return time and never persisted to cache.
    """
    settings = get_settings()

    # 1. Geocode ---------------------------------------------------------------
    location = await weather_service.geocode_city(city)
    if location is None:
        raise CityNotFoundError(
            f"Could not find a location named '{city}'",
            hint="Check the spelling, or use GET /cities?q=<partial-name>.",
        )

    lat: float = location["latitude"]
    lon: float = location["longitude"]
    loc_name: str = location["name"]
    country: str | None = location.get("country")

    cache_key = (round(lat, 2), round(lon, 2))

    # 2. Cache hit -------------------------------------------------------------
    full_response = _climate_cache.get(cache_key)

    if full_response is None:
        # 3. Build date window (never hardcoded dates) -------------------------
        end: date = datetime.now(timezone.utc).date() - timedelta(days=_LAG_DAYS)
        start: date = date(end.year - settings.climate_years, end.month, end.day)
        start_date = start.isoformat()
        end_date = end.isoformat()

        # 4. Fetch archive data ------------------------------------------------
        data = await weather_service._fetch_json(
            settings.weather_archive_url,
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto",
            },
        )

        # 5. Aggregate — defensive; malformed/empty → WeatherUnavailableError -
        try:
            full_response = _aggregate(data, lat, lon, loc_name, country)
        except WeatherUnavailableError:
            raise  # already the right type; don't double-wrap
        except (KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
            logger.warning(
                "Open-Meteo Archive returned an unexpected response for %s: %s",
                city,
                exc,
            )
            raise WeatherUnavailableError(
                "Open-Meteo returned an unexpected or empty climate response"
            ) from exc

        _climate_cache[cache_key] = full_response

    # 6. Month filter (never mutate the cached object) -------------------------
    if month is not None:
        filtered_months = [m for m in full_response.months if m.month == month]
        month_name = calendar.month_name[month]
        if filtered_months:
            cm = filtered_months[0]
            single_summary = (
                f"{full_response.location.name} in {month_name}: "
                f"{cm.comfort}, with an average high of {cm.avg_temp_max_c}°C "
                f"and about {cm.rainy_days} rainy day(s)."
            )
        else:
            single_summary = (
                f"No climate data is available for {full_response.location.name} "
                f"in {month_name}."
            )
        return full_response.model_copy(
            update={
                "months": filtered_months,
                "best_months": [],
                "summary": single_summary,
            }
        )

    return full_response
