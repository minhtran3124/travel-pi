#!/usr/bin/env python3
"""Validate provenance JSON under ``specs/gh-237-city-coverage-expansion/sources/``.

Checks every ``*.json`` file against one of the three shapes documented in
``specs/gh-237-city-coverage-expansion/sources/SCHEMA.md``: a city file (a list of
city objects with hotels/places/city_tips), ``countries.json`` (a list of
per-country summaries + tips) or ``foundations.json`` (countries/visa/airports/
airlines/fx). ``SCHEMA.md`` itself is skipped -- only ``*.json`` files are checked.

Run as a module from ``apps/api/``::

    python -m scripts.check_seed_sources specs/gh-237-city-coverage-expansion/sources
    python -m scripts.check_seed_sources specs/gh-237-city-coverage-expansion/sources/japan.json

Prints one line per violation, ``<file>: <city/record>: <message>``, and exits 1
if any violation was found, else prints ``OK <n> files`` and exits 0. Duplicate
checks (airport/airline codes, country name/code, city names, hotel/place
``(city, name)`` pairs) are run-level: they accumulate across every file in a
single invocation, not just within one entry.

By default, a directory with zero city-shape files only prints a warning (the
provenance directory can legitimately hold only ``foundations.json`` before the
city-data waves land); pass ``--require-cities`` to make that a violation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Make the `app` package importable when run by path, not only as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import certifi
import httpx
from app.core.geo import haversine_km
from app.data.fx import LAST_UPDATED as _APP_FX_LAST_UPDATED

USER_AGENT = "travel-pi-seed-check/1.0 (https://github.com/minhtran3124/travel-pi)"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_WIKIDATA_QID_RE = re.compile(r"^Q\d+$")
_ONLINE_COORD_RADIUS_KM = 1.0
_ONLINE_HTTP_TIMEOUT = 30.0
_ONLINE_MAX_TRIES = 3
_ONLINE_REQUEST_SLEEP_S = 0.5

_PLACE_RADIUS_KM = 60.0
_AIRPORT_RADIUS_KM = 80.0
# Fallback when the airport's city has no city-shape file yet: check against the
# country centroid instead, with a generous radius that still fits a large
# country (China, the US, Australia). See SCHEMA.md.
_AIRPORT_COUNTRY_RADIUS_KM = 2500.0

_PROPERTY_TYPES = {
    "Hotel",
    "Resort",
    "Boutique Hotel",
    "Villa Resort",
    "Homestay",
    "Hostel",
    "Apartment",
}
_PLACE_CATEGORIES = {
    "attraction",
    "restaurant",
    "cafe",
    "shopping",
    "activity",
    "nightlife",
}
_TIP_CATEGORIES = {
    "money",
    "transport",
    "best_time",
    "safety",
    "connectivity",
    "etiquette",
    "food",
    "health",
    "language",
    "culture",
}

_CITY_KEYS = {"name", "country", "airport_codes", "latitude", "longitude", "source_url"}
_HOTEL_KEYS = {
    "name",
    "address",
    "star_rating",
    "price_per_night",
    "currency",
    "amenities",
    "image_url",
    "rating",
    "review_count",
    "description",
    "property_type",
    "chain",
    "check_in_time",
    "check_out_time",
    "breakfast_included",
    "free_cancellation",
    "languages_spoken",
    "latitude",
    "longitude",
    "wikidata",
    "source_url",
}
_PLACE_KEYS = {
    "name",
    "category",
    "description",
    "address",
    "rating",
    "review_count",
    "price_level",
    "opening_hours",
    "image_url",
    "tags",
    "is_recommended",
    "latitude",
    "longitude",
    "wikidata",
    "source_url",
}
_TIP_KEYS = {"category", "title", "content", "is_essential", "source_url"}

_COUNTRY_ENTRY_KEYS = {"country", "summary", "summary_source_url", "tips"}

_FOUNDATIONS_COUNTRY_KEYS = {
    "name",
    "code",
    "region",
    "latitude",
    "longitude",
    "source_url",
}
_FOUNDATIONS_VISA_KEYS = {
    "country",
    "visa_free_days",
    "visa_on_arrival",
    "e_visa",
    "passport_validity_months",
    "summary",
    "source_url",
}
_FOUNDATIONS_AIRPORT_KEYS = {
    "code",
    "name",
    "city",
    "country",
    "latitude",
    "longitude",
    "source_url",
}
_FOUNDATIONS_AIRLINE_KEYS = {"code", "name", "source_url"}


class _RunState:
    """Accumulators shared across every file processed by one ``check_path`` call,
    so duplicate checks are run-level rather than per-entry or per-file."""

    def __init__(self) -> None:
        self.city_names: dict[str, str] = {}
        self.hotel_pairs: dict[tuple[str, str], str] = {}
        self.place_pairs: dict[tuple[str, str], str] = {}
        self.airport_codes: dict[str, str] = {}
        self.airline_codes: dict[str, str] = {}
        self.country_names: dict[str, str] = {}
        self.country_codes: dict[str, str] = {}
        self.city_files_seen = 0


def _missing_keys(record: dict, required: set[str]) -> list[str]:
    return sorted(k for k in required if k not in record)


def _check_source_url(record: dict) -> str | None:
    url = record.get("source_url")
    if not isinstance(url, str) or not url:
        return "missing source_url"
    if not (url.startswith("http://") or url.startswith("https://")):
        return f"source_url is not http(s): {url!r}"
    return None


def _check_image_url(record: dict, field: str = "image_url") -> str | None:
    url = record.get(field)
    if not isinstance(url, str) or not url.startswith("https://upload.wikimedia.org/"):
        return f"{field} does not start with https://upload.wikimedia.org/: {url!r}"
    return None


def _check_wikidata_field(record: dict) -> str | None:
    qid = record.get("wikidata")
    if not isinstance(qid, str) or not _WIKIDATA_QID_RE.match(qid):
        return f"wikidata is not a QID like 'Q123': {qid!r}"
    return None


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


_NETWORK_ERROR_PREFIX = "NETWORK ERROR: "


class _OnlineCache:
    """Batched Wikidata entity lookups for one ``--online`` run: up to 50 QIDs per
    ``wbgetentities`` call, sleeping between batches and honouring ``Retry-After``, so
    checking hundreds of hotels/places does not mean hundreds of individual requests."""

    def __init__(self, qids: list[str]) -> None:
        self.coords: dict[str, tuple[float, float] | None] = {}
        self.unresolved: set[str] = set()
        # A definitive non-429/5xx 4xx (e.g. a malformed id list) is a data/request
        # error, not network exhaustion: record it separately so the caller reports
        # it as a data violation (exit 1), not a NETWORK ERROR (exit 2).
        self.request_errors: dict[str, str] = {}
        unique = sorted(set(qids))
        for batch in _chunks(unique, 50):
            self._resolve_batch(batch)

    def _resolve_batch(self, batch: list[str]) -> None:
        headers = {"User-Agent": USER_AGENT}
        for attempt in range(_ONLINE_MAX_TRIES):
            time.sleep(_ONLINE_REQUEST_SLEEP_S)
            try:
                resp = httpx.get(
                    WIKIDATA_API,
                    params={
                        "action": "wbgetentities",
                        "ids": "|".join(batch),
                        "props": "claims",
                        "format": "json",
                    },
                    headers=headers,
                    timeout=_ONLINE_HTTP_TIMEOUT,
                    verify=certifi.where(),
                )
            except httpx.HTTPError:
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                wait_s = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                time.sleep(wait_s)
                continue
            if resp.status_code != 200:
                for qid in batch:
                    self.request_errors[qid] = (
                        f"wbgetentities request failed with HTTP {resp.status_code}"
                    )
                return
            entities = resp.json().get("entities", {})
            for qid in batch:
                self.coords[qid] = self._entity_coord(entities.get(qid))
            return
        self.unresolved.update(batch)

    @staticmethod
    def _entity_coord(entity: dict | None) -> tuple[float, float] | None:
        if not entity or "missing" in entity:
            return None
        claims = entity.get("claims", {}).get("P625")
        if not claims:
            return None
        try:
            value = claims[0]["mainsnak"]["datavalue"]["value"]
            return float(value["latitude"]), float(value["longitude"])
        except (KeyError, TypeError, ValueError):
            return None


def _check_image_reachable(url: str) -> str:
    """``"ok"`` on a 200/206 ranged GET, ``"unreachable"`` on a definitive non-2xx
    response, or ``"network_error"`` once retries on 429/5xx/connection errors are
    exhausted -- the caller must not conflate the last with a real data violation."""
    headers = {"User-Agent": USER_AGENT, "Range": "bytes=0-0"}
    for attempt in range(_ONLINE_MAX_TRIES):
        time.sleep(_ONLINE_REQUEST_SLEEP_S)
        try:
            resp = httpx.get(
                url,
                headers=headers,
                timeout=_ONLINE_HTTP_TIMEOUT,
                verify=certifi.where(),
            )
        except httpx.HTTPError:
            time.sleep(2.0 * (attempt + 1))
            continue
        if resp.status_code in (200, 206):
            return "ok"
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait_s = float(retry_after) if retry_after else 2.0 * (attempt + 1)
            time.sleep(wait_s)
            continue
        return "unreachable"
    return "network_error"


def _check_online_wikidata(record: dict, label: str, cache: _OnlineCache) -> list[str]:
    """Verify the record's ``wikidata`` QID exists, its P625 is within 1 km of the
    record's own coordinates, and its ``image_url`` loads. Assumes offline checks passed.
    A record without its own coordinates is a violation here, not a silently skipped
    check -- the whole point of ``--online`` is that the 1 km check actually runs."""
    problems: list[str] = []
    qid = record.get("wikidata")
    if not isinstance(qid, str):
        return problems

    if qid in cache.request_errors:
        problems.append(f"{label}: {cache.request_errors[qid]} (wikidata {qid})")
    elif qid in cache.unresolved:
        problems.append(
            f"{_NETWORK_ERROR_PREFIX}{label}: could not verify wikidata {qid} "
            "(network exhausted after retries)"
        )
    else:
        coords = cache.coords.get(qid)
        if coords is None:
            problems.append(f"{label}: wikidata {qid} does not exist or has no P625")
        else:
            lat = record.get("latitude")
            lon = record.get("longitude")
            if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
                problems.append(
                    f"{label}: missing latitude/longitude, cannot run the online "
                    "coordinate check"
                )
            else:
                distance = haversine_km(lat, lon, coords[0], coords[1])
                if distance > _ONLINE_COORD_RADIUS_KM:
                    problems.append(
                        f"{label}: coordinates are {distance:.2f} km from {qid}'s P625, "
                        f"exceeds {_ONLINE_COORD_RADIUS_KM} km"
                    )

    image_url = record.get("image_url")
    if isinstance(image_url, str) and image_url:
        status = _check_image_reachable(image_url)
        if status == "unreachable":
            problems.append(f"{label}: image_url did not return 200/206: {image_url}")
        elif status == "network_error":
            problems.append(
                f"{_NETWORK_ERROR_PREFIX}{label}: could not verify image_url "
                f"(network exhausted after retries): {image_url}"
            )

    return problems


def _check_lat_lon(record: dict) -> list[str]:
    problems: list[str] = []
    lat = record.get("latitude")
    lon = record.get("longitude")
    if not isinstance(lat, (int, float)) or not -90 <= lat <= 90:
        problems.append(f"latitude out of range: {lat!r}")
    if not isinstance(lon, (int, float)) or not -180 <= lon <= 180:
        problems.append(f"longitude out of range: {lon!r}")
    return problems


def _is_city_file(data: object) -> bool:
    return (
        isinstance(data, list)
        and len(data) > 0
        and isinstance(data[0], dict)
        and "city" in data[0]
    )


def _is_countries_file(data: object) -> bool:
    return (
        isinstance(data, list)
        and len(data) > 0
        and isinstance(data[0], dict)
        and "country" in data[0]
        and "tips" in data[0]
    )


def _is_foundations_file(data: object) -> bool:
    return isinstance(data, dict) and (
        "countries" in data
        or "visa" in data
        or "airports" in data
        or "airlines" in data
    )


def _collect_city_centres(dir_path: Path) -> dict[str, tuple[float, float]]:
    """Map city name -> (lat, lon) from every city-shape ``*.json`` file in ``dir_path``."""
    centres: dict[str, tuple[float, float]] = {}
    for path in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_city_file(data):
            continue
        for entry in data:
            city = entry.get("city")
            if not isinstance(city, dict):
                continue
            name = city.get("name")
            lat = city.get("latitude")
            lon = city.get("longitude")
            if (
                isinstance(name, str)
                and isinstance(lat, (int, float))
                and isinstance(lon, (int, float))
            ):
                centres[name] = (lat, lon)
    return centres


def _collect_country_centres(dir_path: Path) -> dict[str, tuple[float, float]]:
    """Map country name -> (lat, lon) from foundations.json's own ``countries`` list."""
    centres: dict[str, tuple[float, float]] = {}
    for path in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_foundations_file(data):
            continue
        for country in data.get("countries", []):
            if not isinstance(country, dict):
                continue
            name = country.get("name")
            lat = country.get("latitude")
            lon = country.get("longitude")
            if (
                isinstance(name, str)
                and isinstance(lat, (int, float))
                and isinstance(lon, (int, float))
            ):
                centres[name] = (lat, lon)
    return centres


def _check_city_file(
    filename: str,
    data: list,
    *,
    online: bool = False,
    state: _RunState,
    cache: _OnlineCache | None = None,
) -> list[str]:
    violations: list[str] = []
    state.city_files_seen += 1

    for entry in data:
        if not isinstance(entry, dict) or "city" not in entry:
            violations.append(f"{filename}: <root>: entry missing 'city' key")
            continue

        city = entry["city"]
        city_name = city.get("name") if isinstance(city, dict) else None
        label = city_name or "<unknown city>"

        if not isinstance(city, dict):
            violations.append(f"{filename}: {label}: 'city' is not an object")
            continue

        for key in _missing_keys(city, _CITY_KEYS):
            violations.append(f"{filename}: {label}: city missing key '{key}'")
        err = _check_source_url(city)
        if err:
            violations.append(f"{filename}: {label}: city {err}")
        for err in _check_lat_lon(city):
            violations.append(f"{filename}: {label}: city {err}")

        if isinstance(city_name, str):
            existing = state.city_names.get(city_name)
            if existing is not None:
                violations.append(
                    f"{filename}: {label}: duplicate city '{city_name}' "
                    f"(first seen in {existing})"
                )
            else:
                state.city_names[city_name] = filename

        city_lat, city_lon = city.get("latitude"), city.get("longitude")
        city_centre_valid = isinstance(city_lat, (int, float)) and isinstance(
            city_lon, (int, float)
        )

        hotels = entry.get("hotels")
        if not isinstance(hotels, list):
            violations.append(f"{filename}: {label}: 'hotels' is not a list")
            hotels = []
        places = entry.get("places")
        if not isinstance(places, list):
            violations.append(f"{filename}: {label}: 'places' is not a list")
            places = []
        city_tips = entry.get("city_tips")
        if not isinstance(city_tips, list):
            violations.append(f"{filename}: {label}: 'city_tips' is not a list")
            city_tips = []

        cheap_hotels = 0
        good_hotels = 0
        for hotel in hotels:
            if not isinstance(hotel, dict):
                violations.append(f"{filename}: {label}: hotel entry is not an object")
                continue
            name = hotel.get("name") or "<unnamed hotel>"
            for key in _missing_keys(hotel, _HOTEL_KEYS):
                violations.append(
                    f"{filename}: {label} hotel '{name}': missing key '{key}'"
                )
            err = _check_source_url(hotel)
            if err:
                violations.append(f"{filename}: {label} hotel '{name}': {err}")
            err = _check_image_url(hotel)
            if err:
                violations.append(f"{filename}: {label} hotel '{name}': {err}")
            err = _check_wikidata_field(hotel)
            if err:
                violations.append(f"{filename}: {label} hotel '{name}': {err}")
            elif online:
                for problem in _check_online_wikidata(
                    hotel, f"{filename}: {label} hotel '{name}'", cache
                ):
                    violations.append(problem)
            for err in _check_lat_lon(hotel):
                violations.append(f"{filename}: {label} hotel '{name}': {err}")

            hotel_lat, hotel_lon = hotel.get("latitude"), hotel.get("longitude")
            if (
                city_centre_valid
                and isinstance(hotel_lat, (int, float))
                and isinstance(hotel_lon, (int, float))
            ):
                distance = haversine_km(city_lat, city_lon, hotel_lat, hotel_lon)
                if distance > _PLACE_RADIUS_KM:
                    violations.append(
                        f"{filename}: {label} hotel '{name}': "
                        f"{distance:.1f} km from city centre, exceeds {_PLACE_RADIUS_KM} km"
                    )

            stars = hotel.get("star_rating")
            if not isinstance(stars, (int, float)) or not 1 <= stars <= 5:
                violations.append(
                    f"{filename}: {label} hotel '{name}': star_rating out of range: {stars!r}"
                )
            elif stars >= 4:
                good_hotels += 1

            rating = hotel.get("rating")
            if not isinstance(rating, (int, float)) or not 1 <= rating <= 5:
                violations.append(
                    f"{filename}: {label} hotel '{name}': rating out of range: {rating!r}"
                )

            price = hotel.get("price_per_night")
            if not isinstance(price, (int, float)) or price <= 0:
                violations.append(
                    f"{filename}: {label} hotel '{name}': price_per_night must be > 0: {price!r}"
                )
            elif price <= 130:
                cheap_hotels += 1

            property_type = hotel.get("property_type")
            if property_type not in _PROPERTY_TYPES:
                violations.append(
                    f"{filename}: {label} hotel '{name}': invalid property_type: {property_type!r}"
                )

            pair = (label, name)
            existing = state.hotel_pairs.get(pair)
            if existing is not None:
                violations.append(
                    f"{filename}: {label}: duplicate hotel (city, name) {pair!r} "
                    f"(first seen in {existing})"
                )
            else:
                state.hotel_pairs[pair] = filename

        if not 6 <= len(hotels) <= 8:
            violations.append(
                f"{filename}: {label}: expected 6-8 hotels, got {len(hotels)}"
            )
        if cheap_hotels < 2:
            violations.append(
                f"{filename}: {label}: expected >= 2 hotels priced <= 130, got {cheap_hotels}"
            )
        if good_hotels < 2:
            violations.append(
                f"{filename}: {label}: expected >= 2 hotels of 4 stars or above, got {good_hotels}"
            )

        attraction_count = 0
        food_count = 0
        for place in places:
            if not isinstance(place, dict):
                violations.append(f"{filename}: {label}: place entry is not an object")
                continue
            name = place.get("name") or "<unnamed place>"
            for key in _missing_keys(place, _PLACE_KEYS):
                violations.append(
                    f"{filename}: {label} place '{name}': missing key '{key}'"
                )
            err = _check_source_url(place)
            if err:
                violations.append(f"{filename}: {label} place '{name}': {err}")
            err = _check_image_url(place)
            if err:
                violations.append(f"{filename}: {label} place '{name}': {err}")
            err = _check_wikidata_field(place)
            if err:
                violations.append(f"{filename}: {label} place '{name}': {err}")
            elif online:
                for problem in _check_online_wikidata(
                    place, f"{filename}: {label} place '{name}'", cache
                ):
                    violations.append(problem)

            category = place.get("category")
            if category not in _PLACE_CATEGORIES:
                violations.append(
                    f"{filename}: {label} place '{name}': invalid category: {category!r}"
                )
            elif category == "attraction":
                attraction_count += 1
            elif category in ("restaurant", "cafe"):
                food_count += 1

            rating = place.get("rating")
            if not isinstance(rating, (int, float)) or not 1 <= rating <= 5:
                violations.append(
                    f"{filename}: {label} place '{name}': rating out of range: {rating!r}"
                )
            price_level = place.get("price_level")
            if not isinstance(price_level, (int, float)) or not 1 <= price_level <= 4:
                violations.append(
                    f"{filename}: {label} place '{name}': price_level out of range: {price_level!r}"
                )

            for err in _check_lat_lon(place):
                violations.append(f"{filename}: {label} place '{name}': {err}")

            place_lat, place_lon = place.get("latitude"), place.get("longitude")
            if (
                city_centre_valid
                and isinstance(place_lat, (int, float))
                and isinstance(place_lon, (int, float))
            ):
                distance = haversine_km(city_lat, city_lon, place_lat, place_lon)
                if distance > _PLACE_RADIUS_KM:
                    violations.append(
                        f"{filename}: {label} place '{name}': "
                        f"{distance:.1f} km from city centre, exceeds {_PLACE_RADIUS_KM} km"
                    )

            pair = (label, name)
            existing = state.place_pairs.get(pair)
            if existing is not None:
                violations.append(
                    f"{filename}: {label}: duplicate place (city, name) {pair!r} "
                    f"(first seen in {existing})"
                )
            else:
                state.place_pairs[pair] = filename

        if len(places) < 8:
            violations.append(
                f"{filename}: {label}: expected >= 8 places, got {len(places)}"
            )
        if attraction_count < 5:
            violations.append(
                f"{filename}: {label}: expected >= 5 attraction places, got {attraction_count}"
            )
        if food_count < 2:
            violations.append(
                f"{filename}: {label}: expected >= 2 restaurant/cafe places, got {food_count}"
            )

        for i, tip in enumerate(city_tips):
            if not isinstance(tip, dict):
                violations.append(
                    f"{filename}: {label}: city_tip #{i} is not an object"
                )
                continue
            for key in _missing_keys(tip, _TIP_KEYS):
                violations.append(
                    f"{filename}: {label} city_tip #{i}: missing key '{key}'"
                )
            err = _check_source_url(tip)
            if err:
                violations.append(f"{filename}: {label} city_tip #{i}: {err}")
            if tip.get("category") not in _TIP_CATEGORIES:
                violations.append(
                    f"{filename}: {label} city_tip #{i}: invalid category: {tip.get('category')!r}"
                )

        if len(city_tips) < 3:
            violations.append(
                f"{filename}: {label}: expected >= 3 city_tips, got {len(city_tips)}"
            )

    return violations


def _check_countries_file(filename: str, data: list) -> list[str]:
    violations: list[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            violations.append(f"{filename}: <root>: entry is not an object")
            continue
        country = entry.get("country") or "<unknown country>"
        for key in _missing_keys(entry, _COUNTRY_ENTRY_KEYS):
            violations.append(f"{filename}: {country}: missing key '{key}'")

        summary = entry.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            violations.append(f"{filename}: {country}: missing summary")

        summary_url = entry.get("summary_source_url")
        if not isinstance(summary_url, str) or not (
            summary_url.startswith("http://") or summary_url.startswith("https://")
        ):
            violations.append(
                f"{filename}: {country}: summary_source_url is not http(s): {summary_url!r}"
            )

        tips = entry.get("tips")
        if not isinstance(tips, list):
            violations.append(f"{filename}: {country}: 'tips' is not a list")
            tips = []

        for i, tip in enumerate(tips):
            if not isinstance(tip, dict):
                violations.append(f"{filename}: {country}: tip #{i} is not an object")
                continue
            for key in _missing_keys(tip, _TIP_KEYS):
                violations.append(
                    f"{filename}: {country} tip #{i}: missing key '{key}'"
                )
            err = _check_source_url(tip)
            if err:
                violations.append(f"{filename}: {country} tip #{i}: {err}")
            if tip.get("category") not in _TIP_CATEGORIES:
                violations.append(
                    f"{filename}: {country} tip #{i}: invalid category: {tip.get('category')!r}"
                )

        if len(tips) < 3:
            violations.append(
                f"{filename}: {country}: expected >= 3 tips, got {len(tips)}"
            )

    return violations


def _check_fx_block(filename: str, fx: object) -> list[str]:
    violations: list[str] = []
    if not isinstance(fx, dict):
        violations.append(f"{filename}: fx: missing or not an object")
        return violations

    date = fx.get("date")
    if date != _APP_FX_LAST_UPDATED:
        violations.append(
            f"{filename}: fx: date {date!r} does not match app.data.fx.LAST_UPDATED "
            f"{_APP_FX_LAST_UPDATED!r}"
        )

    ecb = fx.get("ecb")
    if not isinstance(ecb, dict):
        violations.append(f"{filename}: fx.ecb: missing or not an object")
    else:
        err = _check_source_url(ecb)
        if err:
            violations.append(f"{filename}: fx.ecb: {err}")

    for group in ("pegs", "other"):
        entries = fx.get(group)
        if entries is None:
            continue
        if not isinstance(entries, list):
            violations.append(f"{filename}: fx.{group}: not a list")
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                violations.append(
                    f"{filename}: fx.{group}[{i}]: entry is not an object"
                )
                continue
            err = _check_source_url(entry)
            if err:
                violations.append(f"{filename}: fx.{group}[{i}]: {err}")

    return violations


def _check_foundations_file(
    filename: str,
    data: dict,
    city_centres: dict[str, tuple[float, float]],
    country_centres: dict[str, tuple[float, float]],
    *,
    state: _RunState,
) -> list[str]:
    violations: list[str] = []

    for country in data.get("countries", []):
        name = country.get("name") if isinstance(country, dict) else None
        label = name or "<unknown country>"
        if not isinstance(country, dict):
            violations.append(f"{filename}: {label}: country entry is not an object")
            continue
        for key in _missing_keys(country, _FOUNDATIONS_COUNTRY_KEYS):
            violations.append(f"{filename}: country {label}: missing key '{key}'")
        err = _check_source_url(country)
        if err:
            violations.append(f"{filename}: country {label}: {err}")
        for err in _check_lat_lon(country):
            violations.append(f"{filename}: country {label}: {err}")

        if isinstance(name, str):
            existing = state.country_names.get(name)
            if existing is not None:
                violations.append(
                    f"{filename}: country {label}: duplicate country name '{name}' "
                    f"(first seen in {existing})"
                )
            else:
                state.country_names[name] = filename

        code = country.get("code") if isinstance(country, dict) else None
        if isinstance(code, str):
            existing = state.country_codes.get(code)
            if existing is not None:
                violations.append(
                    f"{filename}: country {label}: duplicate country code '{code}' "
                    f"(first seen in {existing})"
                )
            else:
                state.country_codes[code] = filename

    for visa in data.get("visa", []):
        label = visa.get("country") if isinstance(visa, dict) else None
        label = label or "<unknown country>"
        if not isinstance(visa, dict):
            violations.append(f"{filename}: {label}: visa entry is not an object")
            continue
        for key in _missing_keys(visa, _FOUNDATIONS_VISA_KEYS):
            violations.append(f"{filename}: visa {label}: missing key '{key}'")
        err = _check_source_url(visa)
        if err:
            violations.append(f"{filename}: visa {label}: {err}")

    for airport in data.get("airports", []):
        code = airport.get("code") if isinstance(airport, dict) else None
        label = code or "<unknown airport>"
        if not isinstance(airport, dict):
            violations.append(f"{filename}: airport {label}: entry is not an object")
            continue
        for key in _missing_keys(airport, _FOUNDATIONS_AIRPORT_KEYS):
            violations.append(f"{filename}: airport {label}: missing key '{key}'")
        err = _check_source_url(airport)
        if err:
            violations.append(f"{filename}: airport {label}: {err}")
        for err in _check_lat_lon(airport):
            violations.append(f"{filename}: airport {label}: {err}")

        if isinstance(code, str):
            existing = state.airport_codes.get(code)
            if existing is not None:
                violations.append(
                    f"{filename}: airport {label}: duplicate airport code '{code}' "
                    f"(first seen in {existing})"
                )
            else:
                state.airport_codes[code] = filename

        lat, lon = airport.get("latitude"), airport.get("longitude")
        city_name = airport.get("city")
        country_name = airport.get("country")
        lat_lon_valid = isinstance(lat, (int, float)) and isinstance(lon, (int, float))

        if lat_lon_valid and isinstance(city_name, str) and city_name in city_centres:
            city_lat, city_lon = city_centres[city_name]
            distance = haversine_km(lat, lon, city_lat, city_lon)
            if distance > _AIRPORT_RADIUS_KM:
                violations.append(
                    f"{filename}: airport {label}: "
                    f"{distance:.1f} km from {city_name}, exceeds {_AIRPORT_RADIUS_KM} km"
                )
        elif (
            lat_lon_valid
            and isinstance(country_name, str)
            and country_name in country_centres
        ):
            country_lat, country_lon = country_centres[country_name]
            distance = haversine_km(lat, lon, country_lat, country_lon)
            if distance > _AIRPORT_COUNTRY_RADIUS_KM:
                violations.append(
                    f"{filename}: airport {label}: {distance:.1f} km from "
                    f"{country_name}'s centroid, exceeds {_AIRPORT_COUNTRY_RADIUS_KM} km "
                    f"(city {city_name!r} has no city file; country-centroid fallback)"
                )
            else:
                print(
                    f"NOTE: {filename}: airport {label}: city {city_name!r} has no "
                    f"city file yet; checked against {country_name}'s country centroid "
                    f"({_AIRPORT_COUNTRY_RADIUS_KM:.0f} km) only, city radius unchecked"
                )
        elif lat_lon_valid:
            print(
                f"NOTE: {filename}: airport {label}: neither city {city_name!r} nor "
                f"country {country_name!r} centroid is known yet; distance unchecked"
            )

    for airline in data.get("airlines", []):
        code = airline.get("code") if isinstance(airline, dict) else None
        label = code or "<unknown airline>"
        if not isinstance(airline, dict):
            violations.append(f"{filename}: airline {label}: entry is not an object")
            continue
        for key in _missing_keys(airline, _FOUNDATIONS_AIRLINE_KEYS):
            violations.append(f"{filename}: airline {label}: missing key '{key}'")
        err = _check_source_url(airline)
        if err:
            violations.append(f"{filename}: airline {label}: {err}")

        if isinstance(code, str):
            existing = state.airline_codes.get(code)
            if existing is not None:
                violations.append(
                    f"{filename}: airline {label}: duplicate airline code '{code}' "
                    f"(first seen in {existing})"
                )
            else:
                state.airline_codes[code] = filename

    if "fx" in data:
        violations.extend(_check_fx_block(filename, data.get("fx")))

    return violations


def check_path(
    path: str | Path, *, online: bool = False, require_cities: bool = False
) -> list[str]:
    """Validate ``path`` (a single provenance ``*.json`` file, or a directory of
    them) and return one violation string per problem found, empty if clean.

    With ``online=True``, every hotel and place also has its ``wikidata`` QID
    checked against the live Wikidata API (existence, coordinates within 1 km)
    and its ``image_url`` checked with a ranged GET.

    With ``require_cities=True``, zero city-shape files under ``path`` is itself
    a violation; otherwise it only prints a warning (see module docstring)."""
    p = Path(path)

    if p.is_dir():
        json_files = sorted(f for f in p.glob("*.json"))
        scan_dir = p
    else:
        json_files = [p]
        scan_dir = p.parent

    city_centres = _collect_city_centres(scan_dir)
    country_centres = _collect_country_centres(scan_dir)
    state = _RunState()

    parsed_files: list[tuple[str, object]] = []
    violations: list[str] = []
    for file_path in json_files:
        filename = file_path.name
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            violations.append(f"{filename}: <root>: invalid JSON: {exc}")
            continue
        except OSError as exc:
            violations.append(f"{filename}: <root>: could not read file: {exc}")
            continue
        parsed_files.append((filename, data))

    cache: _OnlineCache | None = None
    if online:
        qids: list[str] = []
        for _, data in parsed_files:
            if not _is_city_file(data):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                for record in list(entry.get("hotels") or []) + list(
                    entry.get("places") or []
                ):
                    if isinstance(record, dict) and isinstance(
                        record.get("wikidata"), str
                    ):
                        qids.append(record["wikidata"])
        cache = _OnlineCache(qids)

    for filename, data in parsed_files:
        if _is_foundations_file(data):
            violations.extend(
                _check_foundations_file(
                    filename, data, city_centres, country_centres, state=state
                )
            )
        elif _is_countries_file(data):
            violations.extend(_check_countries_file(filename, data))
        elif _is_city_file(data):
            violations.extend(
                _check_city_file(
                    filename, data, online=online, state=state, cache=cache
                )
            )
        else:
            violations.append(
                f"{filename}: <root>: unrecognised shape "
                "(expected a city list, countries.json, or foundations.json)"
            )

    if state.city_files_seen == 0:
        if require_cities:
            violations.append(
                f"{p}: no city-shape *.json file found (--require-cities)"
            )
        else:
            print(f"WARNING: 0 city files checked under {p}")

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="A provenance *.json file, or a directory of them")
    parser.add_argument(
        "--online",
        action="store_true",
        help="Also verify each wikidata QID and image_url against the live APIs",
    )
    parser.add_argument(
        "--require-cities",
        action="store_true",
        help="Fail if zero city-shape *.json files are found under path",
    )
    args = parser.parse_args(argv)

    p = Path(args.path)
    if not p.exists():
        print(f"{args.path}: <root>: path does not exist")
        return 1

    violations = check_path(p, online=args.online, require_cities=args.require_cities)
    for line in violations:
        print(line)

    network_errors = [v for v in violations if _NETWORK_ERROR_PREFIX in v]
    data_violations = [v for v in violations if _NETWORK_ERROR_PREFIX not in v]
    if network_errors:
        print(
            f"ERROR: {len(network_errors)} check(s) could not be verified "
            "(network exhausted after retries), distinct from a data violation"
        )
        return 2
    if data_violations:
        return 1

    n_files = len(list(p.glob("*.json"))) if p.is_dir() else 1
    print(f"OK {n_files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
