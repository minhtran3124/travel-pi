#!/usr/bin/env python3
"""Fetch real hotel/place candidates for a city from Wikidata, Commons, Wikipedia and Wikivoyage.

Writes ``candidates/<city>.json`` (default ``specs/gh-237-city-coverage-expansion/
candidates/``) with the raw material a curation pass selects from: it never invents a
record, name, coordinate or image -- everything traces back to a Wikidata QID.

Run as a module from ``apps/api/``::

    python -m scripts.fetch_city_candidates Osaka Q35765
    python -m scripts.fetch_city_candidates Osaka Q35765 --out ../../specs/.../candidates
    python -m scripts.fetch_city_candidates "Los Angeles" Q65 --max-km 25
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import certifi
import httpx

# Make the `app` package importable when run by path, not only as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.geo import haversine_km

USER_AGENT = "travel-pi-seed-check/1.0 (https://github.com/minhtran3124/travel-pi)"
WDQS_URL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"

# Exact instance-of only (P31, no P279* subclass expansion): Wikidata's accommodation
# class graph has known bad edges (e.g. "amusement park" is mis-modelled as a direct
# P279 subclass of the old "capsule hotel" QID this fetcher used to point at), so
# subclass expansion pulled in theme parks and office towers as "hotels". Every QID
# below was confirmed live against the Wikidata API before use.
_ACCOMMODATION_CLASSES = (
    "Q27686",  # hotel
    "Q654772",  # hostel
    "Q837834",  # capsule hotel
    "Q562930",  # ryokan
    "Q1761296",  # minshuku
    "Q2880255",  # resort hotel
    "Q259618",  # boutique hotel
    "Q2460422",  # guest house
)
# "Business hotel" has no dedicated Wikidata class distinct from plain "hotel" (Q27686)
# as of this fetch -- confirmed by a live wbsearchentities lookup, not guessed. Hotels
# that are actually business hotels are still reachable via Q27686.
_EXCLUDED_ACCOMMODATION_CLASSES = ("Q1033548",)  # love hotel

_RESTAURANT_CLASSES = ("Q11707", "Q30022")  # restaurant, cafe

# Exact instance-of exclusions for places. Every QID confirmed live. A live SPARQL
# ASK/VALUES probe against WDQS showed that P279* subclass expansion (e.g. resolving
# "occurrence" or "railway station" transitively) reliably times out on this endpoint
# even when bounded to a handful of candidate classes, so -- as with the accommodation
# classes -- exclusions here are exact P31 matches, extended with the specific
# subtypes actually seen on live Osaka data rather than a subclass walk.
_EXCLUDED_PLACE_CLASSES = (
    "Q5",  # human
    "Q4830453",  # business
    "Q783794",  # company
    "Q56061",  # administrative territorial entity
    "Q137773",  # ward of Japan (an administrative-area subtype, seen live: Chuo-ku)
    "Q55488",  # railway station
    "Q928830",  # metro station
    "Q124642584",  # group of railway stations
    "Q11670533",  # elevated station
    "Q1147171",  # interchange station
    "Q7886778",  # union station
    "Q132555858",  # railway station in a highway median
    "Q124416148",  # underground metro station
    "Q5503",  # rapid transit (a transit system/network, not a single place)
    "Q15265344",  # broadcaster
    "Q1616075",  # television station
    "Q3918",  # university
    "Q3914",  # school
    "Q2385804",  # educational institution
    "Q3947",  # house (private residence)
    "Q1307276",  # single-family detached home
    # Occurrences/events: verified live as the actual P31 values seen on Osaka's own
    # bad candidates (a building fire, a mass shooting, a World Expo) rather than
    # walking "occurrence" (Q1190554) via P279*, which timed out on WDQS.
    "Q1190554",  # occurrence
    "Q1656682",  # planned event
    "Q3839081",  # disaster
    "Q7625093",  # structure fire
    "Q168983",  # conflagration
    "Q750215",  # mass murder
    "Q5853505",  # World Expo
    "Q198",  # war
    "Q273120",  # protest
)
# A former/destroyed thing: P5816 (state of use) is one of these. P576 (dissolved /
# demolished date) was tried first per the brief but rejected after live data showed
# it is too blunt: Osaka Castle's own item (Q321242) carries a P576 for the original
# 1615/1868 destructions even though the standing 1931/1997 reconstruction is very
# much an operating landmark with no P5816 marking it destroyed. P5816 is the
# purpose-built "current state of use" property and does not have this false-positive.
_DESTROYED_STATE_OF_USE_CLASSES = (
    "Q56556915",  # demolished or destroyed
    "Q19860854",  # destroyed building or structure
)

_WIKIVOYAGE_SECTIONS = ("Get around", "Stay safe", "Eat", "Sleep")
_WIKIVOYAGE_SECTION_CHAR_CAP = 6000

_DEFAULT_MAX_KM = 15.0

_SPARQL_TIMEOUT = 60.0
_HTTP_TIMEOUT = 30.0
_REQUEST_SLEEP_S = 1.0
_MAX_TRIES = 3

_last_request_at: float = 0.0


def _client_verify() -> str:
    return certifi.where()


def _throttle() -> None:
    """Sleep so consecutive outbound API calls stay >= _REQUEST_SLEEP_S apart.

    Applied to every SPARQL, Commons, Wikipedia and Wikivoyage call, not only SPARQL:
    all four are third-party APIs this fetcher must be polite to."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _REQUEST_SLEEP_S:
        time.sleep(_REQUEST_SLEEP_S - elapsed)
    _last_request_at = time.monotonic()


def _get_with_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = _HTTP_TIMEOUT,
) -> httpx.Response | None:
    """GET with the same politeness + backoff as the SPARQL client: retries 429/5xx,
    honours ``Retry-After``, sleeps between tries. Returns ``None`` (never raises) once
    retries are exhausted, since a single candidate's network failure should not abort
    the whole fetch."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_TRIES):
        _throttle()
        try:
            resp = httpx.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
                verify=_client_verify(),
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait_s = float(retry_after) if retry_after else 2.0 * (attempt + 1)
            time.sleep(wait_s)
            last_exc = RuntimeError(f"{url} returned {resp.status_code}")
            continue
        return resp
    print(f"WARNING: request to {url} failed after {_MAX_TRIES} tries: {last_exc}")
    return None


def _sparql(query: str) -> list[dict[str, Any]]:
    """Run one SPARQL query against WDQS, retrying 429/5xx with backoff."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    resp = _get_with_retry(
        WDQS_URL,
        params={"query": query, "format": "json"},
        headers=headers,
        timeout=_SPARQL_TIMEOUT,
    )
    if resp is None:
        raise RuntimeError(f"SPARQL query failed after {_MAX_TRIES} tries")
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def _val(binding: dict[str, Any], key: str) -> str | None:
    entry = binding.get(key)
    return entry.get("value") if entry else None


def _qid_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def _parse_point(wkt: str | None) -> tuple[float, float] | None:
    if not wkt:
        return None
    match = re.match(r"Point\(([-\d.]+)\s+([-\d.]+)\)", wkt)
    if not match:
        return None
    lon, lat = float(match.group(1)), float(match.group(2))
    return lat, lon


def _filename_from_p18(image_uri: str | None) -> str | None:
    if not image_uri:
        return None
    marker = "Special:FilePath/"
    idx = image_uri.find(marker)
    if idx == -1:
        return None
    return urllib.parse.unquote(image_uri[idx + len(marker) :])


def _class_values(classes: tuple[str, ...]) -> str:
    return " ".join(f"wd:{c}" for c in classes)


def _city_coord(qid: str) -> tuple[float, float] | None:
    """The city item's own P625, used as the centre for the --max-km place filter."""
    rows = _sparql(f"SELECT ?coord WHERE {{ wd:{qid} wdt:P625 ?coord }} LIMIT 1")
    if not rows:
        return None
    return _parse_point(_val(rows[0], "coord"))


def _hotel_query(qid: str, limit: int) -> str:
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31 wd:{c} . }}"
        for c in _EXCLUDED_ACCOMMODATION_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?districtLabel ?sitelinks ?enTitle
    WHERE {{
      VALUES ?class {{ {_class_values(_ACCOMMODATION_CLASSES)} }}
      ?item wdt:P31 ?class .
      ?item wdt:P131* wd:{qid} .
      ?item wdt:P625 ?coord .
{exclusions}
      OPTIONAL {{ ?item wdt:P18 ?image . }}
      OPTIONAL {{ ?item wdt:P6375 ?address . }}
      OPTIONAL {{ ?item wdt:P131 ?district . }}
      ?item wikibase:sitelinks ?sitelinks .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {limit}
    """


def _restaurant_query(qid: str, limit: int) -> str:
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?address ?sitelinks ?enTitle
    WHERE {{
      VALUES ?class {{ {_class_values(_RESTAURANT_CLASSES)} }}
      ?item wdt:P31 ?class .
      ?item wdt:P131* wd:{qid} .
      ?item wdt:P625 ?coord .
      OPTIONAL {{ ?item wdt:P18 ?image . }}
      OPTIONAL {{ ?item wdt:P6375 ?address . }}
      ?item wikibase:sitelinks ?sitelinks .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {limit}
    """


def _place_query(qid: str, limit: int) -> str:
    exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P31 wd:{c} . }}"
        for c in _EXCLUDED_PLACE_CLASSES
    )
    destroyed_exclusions = "\n".join(
        f"      FILTER NOT EXISTS {{ ?item wdt:P5816 wd:{c} . }}"
        for c in _DESTROYED_STATE_OF_USE_CLASSES
    )
    return f"""
    SELECT ?item ?itemLabel ?coord ?image ?class ?classLabel ?sitelinks ?enTitle
    WHERE {{
      ?item wdt:P131* wd:{qid} .
      FILTER (?item != wd:{qid})
      ?item wdt:P625 ?coord .
      ?item wdt:P18 ?image .
      ?item wdt:P31 ?class .
{exclusions}
{destroyed_exclusions}
      ?item wikibase:sitelinks ?sitelinks .
      OPTIONAL {{
        ?enArticle schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> ;
                   schema:name ?enTitle .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?sitelinks)
    LIMIT {limit}
    """


def _merge_place_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The place query yields one row per (item, instance-of class); merge by QID."""
    by_qid: dict[str, dict[str, Any]] = {}
    for row in rows:
        uri = _val(row, "item")
        qid = _qid_from_uri(uri)
        if not qid:
            continue
        entry = by_qid.setdefault(
            qid,
            {
                "qid": qid,
                "label": _val(row, "itemLabel"),
                "coord": _val(row, "coord"),
                "image": _val(row, "image"),
                "sitelinks": _val(row, "sitelinks"),
                "en_title": _val(row, "enTitle"),
                "instance_of": [],
            },
        )
        class_label = _val(row, "classLabel")
        if class_label and class_label not in entry["instance_of"]:
            entry["instance_of"].append(class_label)
    ordered = sorted(
        by_qid.values(), key=lambda e: float(e["sitelinks"] or 0), reverse=True
    )
    return ordered


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _rewrite_to_upload_host(thumburl: str) -> str:
    """A Commons ``thumburl`` resolves through the ``thumb.wikimedia.org`` CDN host;
    rewrite it onto ``upload.wikimedia.org`` (same path shape) and drop the query
    string, per the schema's ``image_url`` contract."""
    parsed = urllib.parse.urlsplit(thumburl)
    return urllib.parse.urlunsplit(
        ("https", "upload.wikimedia.org", parsed.path, "", "")
    )


def _strip_query(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _resolve_commons_images(filenames: list[str]) -> dict[str, str]:
    """Resolve Commons file names to a real, query-string-free upload.wikimedia.org URL:
    a 1280px-wide thumb, or the original (query stripped) when it is already narrower
    than 1280px. SVGs get their thumbed ``.png`` suffix from Commons itself."""
    resolved: dict[str, str] = {}
    unique = sorted({f for f in filenames if f})
    headers = {"User-Agent": USER_AGENT}
    for batch in _chunks(unique, 50):
        titles = "|".join(f"File:{name}" for name in batch)
        resp = _get_with_retry(
            COMMONS_API,
            params={
                "action": "query",
                "titles": titles,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "iiurlwidth": 1280,
                "format": "json",
            },
            headers=headers,
        )
        if resp is None:
            continue
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            infos = page.get("imageinfo") or []
            if not infos or not title.startswith("File:"):
                continue
            info = infos[0]
            thumburl = info.get("thumburl")
            full_url = info.get("url")
            thumb_width = info.get("thumbwidth")
            width = info.get("width")
            if thumburl and thumb_width and width and width > thumb_width:
                url = _rewrite_to_upload_host(thumburl)
            elif full_url:
                url = _strip_query(full_url)
            elif thumburl:
                url = _rewrite_to_upload_host(thumburl)
            else:
                continue
            resolved[title[len("File:") :]] = url
    return resolved


def _fetch_wikipedia_summary(title: str, qid: str) -> dict[str, str] | None:
    """Fetch the summary for the item's own enwiki sitelink title, and drop it unless
    the response's own ``wikibase_item`` matches ``qid``: a sitelink title can still
    redirect Wikipedia-side to a different article about a different Wikidata item
    (this is exactly how a restaurant with no enwiki article at all previously picked
    up an unrelated "Drug withdrawal" extract via its label, and how a building's own
    sitelink title redirected to its neighbouring landmark's article)."""
    headers = {"User-Agent": USER_AGENT}
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    resp = _get_with_retry(
        WIKIPEDIA_SUMMARY_URL.format(title=encoded),
        headers=headers,
    )
    if resp is None or resp.status_code != 200:
        return None
    data = resp.json()
    extract = data.get("extract")
    if not extract:
        return None
    if data.get("wikibase_item") != qid:
        return None
    return {"title": data.get("title", title), "extract": extract}


def _wikitext_to_plain(text: str) -> str:
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # one more pass for shallow nesting
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\*+\s*", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:_WIKIVOYAGE_SECTION_CHAR_CAP]


def _extract_sections(wikitext: str, names: tuple[str, ...]) -> dict[str, str | None]:
    """Slice each wanted heading to the next heading of the *same or higher* level
    (fewer or equal ``=`` characters), so its subsections (e.g. "Eat" -> "Budget" /
    "Mid-range" / "Splurge", "Get around" -> "By train") are kept rather than cut at
    the first subsection boundary. A heading that exists but whose body is only
    templates/links (nothing left after ``_wikitext_to_plain``) is recorded as an
    empty string; a heading that does not exist at all is recorded as ``None`` --
    the two are not the same and callers should not conflate them."""
    heading_re = re.compile(r"^(=+)\s*([^=]+?)\s*=+\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(wikitext))
    sections: dict[str, str | None] = dict.fromkeys(names, None)
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        if heading not in names:
            continue
        start = m.end()
        end = len(wikitext)
        for later in matches[i + 1 :]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        sections[heading] = _wikitext_to_plain(wikitext[start:end])
    return sections


def _fetch_wikivoyage_sections(city: str) -> dict[str, str | None]:
    headers = {"User-Agent": USER_AGENT}
    resp = _get_with_retry(
        WIKIVOYAGE_API,
        params={
            "action": "parse",
            "page": city,
            "prop": "wikitext",
            "format": "json",
        },
        headers=headers,
    )
    if resp is None or resp.status_code != 200:
        return dict.fromkeys(_WIKIVOYAGE_SECTIONS, None)
    data = resp.json()
    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    if not wikitext:
        return dict.fromkeys(_WIKIVOYAGE_SECTIONS, None)
    return _extract_sections(wikitext, _WIKIVOYAGE_SECTIONS)


def _build_hotel_like_entries(
    rows: list[dict[str, Any]],
    image_map: dict[str, str],
) -> list[dict[str, Any]]:
    """One entry per distinct QID. A row repeats per matched class (e.g. an item
    reachable from both ``hotel`` and ``hostel``), so dedupe here."""
    by_qid: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = _qid_from_uri(_val(row, "item"))
        if not qid or qid in by_qid:
            continue
        point = _parse_point(_val(row, "coord"))
        filename = _filename_from_p18(_val(row, "image"))
        image_url = image_map.get(filename) if filename else None
        by_qid[qid] = {
            "qid": qid,
            "label": _val(row, "itemLabel"),
            "latitude": point[0] if point else None,
            "longitude": point[1] if point else None,
            "image_url": image_url,
            "address": _val(row, "address") or _val(row, "districtLabel"),
            "sitelinks": int(float(_val(row, "sitelinks") or 0)),
            "en_title": _val(row, "enTitle"),
        }
    return sorted(by_qid.values(), key=lambda e: e["sitelinks"], reverse=True)


def _build_place_entries(
    rows: list[dict[str, Any]],
    image_map: dict[str, str],
    city_coord: tuple[float, float] | None,
    max_km: float,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    dropped_far = 0
    for row in _merge_place_rows(rows):
        point = _parse_point(row["coord"])
        if city_coord and point:
            distance = haversine_km(city_coord[0], city_coord[1], point[0], point[1])
            if distance > max_km:
                dropped_far += 1
                print(
                    f"NOTE: dropping {row['label']!r} ({row['qid']}): "
                    f"{distance:.1f} km from city centre, exceeds --max-km {max_km}"
                )
                continue
        filename = _filename_from_p18(row["image"])
        image_url = image_map.get(filename) if filename else None
        entries.append(
            {
                "qid": row["qid"],
                "label": row["label"],
                "latitude": point[0] if point else None,
                "longitude": point[1] if point else None,
                "image_url": image_url,
                "instance_of": row["instance_of"],
                "sitelinks": int(float(row["sitelinks"] or 0)),
                "en_title": row["en_title"],
            }
        )
    if dropped_far:
        print(f"NOTE: dropped {dropped_far} place(s) beyond --max-km {max_km}")
    return entries


def fetch_city_candidates(
    city: str,
    qid: str,
    hotel_limit: int = 40,
    place_limit: int = 60,
    restaurant_limit: int = 30,
    max_km: float = _DEFAULT_MAX_KM,
) -> dict[str, Any]:
    """Fetch and assemble one city's candidate file. Returns the JSON-ready dict."""
    city_coord = _city_coord(qid)

    hotel_rows = _sparql(_hotel_query(qid, hotel_limit))
    place_rows = _sparql(_place_query(qid, place_limit))
    restaurant_rows = _sparql(_restaurant_query(qid, restaurant_limit))

    all_p18_uris = [_val(r, "image") for r in hotel_rows + place_rows + restaurant_rows]
    filenames = [f for f in (_filename_from_p18(u) for u in all_p18_uris) if f]
    image_map = _resolve_commons_images(filenames)

    hotels = _build_hotel_like_entries(hotel_rows, image_map)
    places = _build_place_entries(place_rows, image_map, city_coord, max_km)
    restaurants = _build_hotel_like_entries(restaurant_rows, image_map)

    wikipedia: dict[str, dict[str, str]] = {}
    for entry in hotels + places + restaurants:
        # Only ever the item's own enwiki sitelink title -- never the Wikidata label,
        # which for an item with no enwiki article at all can coincidentally match an
        # unrelated Wikipedia page title (see _fetch_wikipedia_summary docstring).
        title = entry.get("en_title")
        if not title or entry["qid"] in wikipedia:
            continue
        summary = _fetch_wikipedia_summary(title, entry["qid"])
        if summary:
            wikipedia[entry["qid"]] = summary

    wikivoyage = _fetch_wikivoyage_sections(city)

    landmark_image: str | None = None
    if city_coord:
        city_image_rows = _sparql(
            f"SELECT ?image WHERE {{ wd:{qid} wdt:P18 ?image }} LIMIT 1"
        )
        if city_image_rows:
            city_filename = _filename_from_p18(_val(city_image_rows[0], "image"))
            if city_filename:
                city_image_map = _resolve_commons_images([city_filename])
                landmark_image = city_image_map.get(city_filename)

    return {
        "city": city,
        "wikidata_qid": qid,
        "max_km": max_km,
        "hotels": hotels,
        "places": places,
        "restaurants": restaurants,
        "landmark_image": landmark_image,
        "wikipedia": wikipedia,
        "wikivoyage": wikivoyage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", help="City name, e.g. Osaka")
    parser.add_argument("qid", help="The city's Wikidata QID, e.g. Q35765")
    parser.add_argument(
        "--out",
        default="../../specs/gh-237-city-coverage-expansion/candidates",
        help="Output directory for <city>.json (default: the plan's candidates dir)",
    )
    parser.add_argument(
        "--max-km",
        type=float,
        default=_DEFAULT_MAX_KM,
        help=(
            "Drop any place candidate farther than this from the city's own P625 "
            f"(default {_DEFAULT_MAX_KM}; a sprawling metro like LA or Sydney may need 25)"
        ),
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.city}.json"

    data = fetch_city_candidates(args.city, args.qid, max_km=args.max_km)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    n_hotels = len(data["hotels"])
    n_places = len(data["places"])
    n_restaurants = len(data["restaurants"])
    print(
        f"{args.city}: {n_hotels} hotels, {n_places} places, "
        f"{n_restaurants} restaurants -> {out_path}"
    )

    shortfalls = []
    if n_hotels < 6:
        shortfalls.append(f"hotels ({n_hotels} < 6)")
    if n_places < 8:
        shortfalls.append(f"places ({n_places} < 8)")
    if n_restaurants < 2:
        shortfalls.append(f"restaurants ({n_restaurants} < 2)")
    if shortfalls:
        print(f"WARNING: below minimum coverage: {', '.join(shortfalls)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
